from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import visionflow_data_integrity_audit as integrity


MYSQL_CONTAINER = "visionflow-mysql"
BACKEND_CONTAINER = "visionflow-backend"
CONFIRMATION = "REPAIR_VISIONFLOW_FLYWAY_V21"
EXPECTED_CONSTRAINTS = {
    "fk_telemetry_history_drone": ("drone_telemetry_history", "CASCADE"),
    "fk_flight_quality_drone": ("flight_quality_assessment", "CASCADE"),
    "fk_flight_session_drone": ("flight_session", "CASCADE"),
    "fk_maintenance_work_order_drone": (
        "maintenance_work_order",
        "NO ACTION",
    ),
}


class RecoveryError(RuntimeError):
    pass


HISTORY_SQL = """
SELECT installed_rank, version, description, type, script, checksum,
       installed_by, DATE_FORMAT(installed_on, '%Y-%m-%d %H:%i:%s.%f'),
       execution_time, success
FROM flyway_schema_history
WHERE version = '21'
ORDER BY installed_rank
"""


CONSTRAINT_SQL = """
SELECT CONSTRAINT_NAME, TABLE_NAME, DELETE_RULE
FROM information_schema.REFERENTIAL_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = DATABASE()
  AND REFERENCED_TABLE_NAME = 'drone'
ORDER BY CONSTRAINT_NAME
"""


def parse_int(value: str) -> int:
    return int(value) if value not in {"", "NULL"} else 0


def collect_state(
    query: Callable[[str], list[list[str]]],
    backend_status: Callable[[], str],
) -> dict[str, Any]:
    history_rows = query(HISTORY_SQL)
    history = [
        {
            "installedRank": parse_int(row[0]),
            "version": row[1],
            "description": row[2],
            "type": row[3],
            "script": row[4],
            "checksum": parse_int(row[5]),
            "installedBy": row[6],
            "installedOn": row[7],
            "executionTime": parse_int(row[8]),
            "success": parse_int(row[9]),
        }
        for row in history_rows
    ]
    constraints = {
        row[0]: {"table": row[1], "deleteRule": row[2]}
        for row in query(CONSTRAINT_SQL)
    }
    _, finding_counts, _ = integrity.collect_database(query)
    return {
        "backendStatus": backend_status(),
        "history": history,
        "constraints": constraints,
        "databaseFindingCounts": finding_counts,
    }


def evaluate_state(state: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if state.get("backendStatus") != "exited":
        failures.append(
            "backend container must be stopped: "
            f"actual={state.get('backendStatus') or 'UNKNOWN'}"
        )
    history = state.get("history", [])
    if len(history) != 1:
        failures.append(f"expected one V21 history row, actual={len(history)}")
    else:
        row = history[0]
        expected = {
            "installedRank": 21,
            "version": "21",
            "description": "restrict drone history delete",
            "type": "SQL",
            "script": "V21__restrict_drone_history_delete.sql",
            "success": 0,
        }
        for key, wanted in expected.items():
            if row.get(key) != wanted:
                failures.append(
                    f"V21 {key} drift: expected={wanted}, actual={row.get(key)}"
                )
    constraints = state.get("constraints", {})
    actual_names = set(constraints)
    if actual_names != set(EXPECTED_CONSTRAINTS):
        failures.append(
            "Drone FK set drift: "
            f"expected={sorted(EXPECTED_CONSTRAINTS)}, "
            f"actual={sorted(actual_names)}"
        )
    for name, (table, delete_rule) in EXPECTED_CONSTRAINTS.items():
        actual = constraints.get(name, {})
        if actual.get("table") != table or actual.get("deleteRule") != delete_rule:
            failures.append(
                f"{name} drift: expected={table}/{delete_rule}, "
                f"actual={actual.get('table')}/{actual.get('deleteRule')}"
            )
    nonzero = {
        key: value
        for key, value in state.get("databaseFindingCounts", {}).items()
        if int(value) != 0
    }
    if nonzero:
        failures.append(f"database integrity findings are not zero: {nonzero}")
    return failures


def build_repair_sql() -> str:
    return "\n".join(
        [
            "SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE;",
            "START TRANSACTION;",
            "SELECT GET_LOCK('visionflow_flyway_v21_recovery', 10) INTO @vf_lock;",
            "SET @vf_guard = IF(@vf_lock = 1, 1, "
            "(SELECT 1 FROM information_schema.tables "
            "WHERE table_name = '__visionflow_guard_failure__'));",
            "SELECT COUNT(*) INTO @vf_failed FROM flyway_schema_history "
            "WHERE installed_rank = 21 AND version = '21' "
            "AND description = 'restrict drone history delete' "
            "AND type = 'SQL' "
            "AND script = 'V21__restrict_drone_history_delete.sql' "
            "AND success = 0;",
            "SET @vf_guard = IF(@vf_failed = 1, 1, "
            "(SELECT 1 FROM information_schema.tables "
            "WHERE table_name = '__visionflow_guard_failure__'));",
            "DELETE FROM flyway_schema_history "
            "WHERE installed_rank = 21 AND version = '21' "
            "AND description = 'restrict drone history delete' "
            "AND type = 'SQL' "
            "AND script = 'V21__restrict_drone_history_delete.sql' "
            "AND success = 0;",
            "SELECT ROW_COUNT() INTO @vf_deleted;",
            "SET @vf_guard = IF(@vf_deleted = 1, 1, "
            "(SELECT 1 FROM information_schema.tables "
            "WHERE table_name = '__visionflow_guard_failure__'));",
            "COMMIT;",
            "SELECT CONCAT('VISIONFLOW_RESULT:', @vf_deleted);",
            "SELECT RELEASE_LOCK('visionflow_flyway_v21_recovery');",
        ]
    )


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def create_backup(root: Path, state: dict[str, Any]) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = root / "artifacts" / "flyway-v21-recovery" / f"repair-{timestamp}"
    output.mkdir(parents=True, exist_ok=False)
    document = {
        "schemaVersion": 1,
        "project": "visionflow",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "pre-repair failed Flyway V21 metadata",
        "containsCredentials": False,
        "databaseRowsChangedByRepair": 0,
        "flywayMetadataRowsDeletedByRepair": 1,
        "state": state,
    }
    atomic_write(
        output / "before-state.json",
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
    )
    return output


def container_status(name: str) -> str:
    completed = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Status}}", name],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "UNKNOWN"


def execute_repair(container: str, sql: str) -> int:
    completed = subprocess.run(
        [
            "docker",
            "exec",
            "--env",
            f"VISIONFLOW_RECOVERY_SQL={sql}",
            container,
            "sh",
            "-c",
            'MYSQL_PWD="$MYSQL_PASSWORD" mysql --user="$MYSQL_USER" '
            '--batch --raw --skip-column-names --default-character-set=utf8mb4 '
            '"$MYSQL_DATABASE" --execute "$VISIONFLOW_RECOVERY_SQL"',
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if completed.returncode != 0:
        raise RecoveryError("Flyway V21 metadata repair transaction failed")
    marker = next(
        (
            line.strip()
            for line in completed.stdout.splitlines()
            if line.strip().startswith("VISIONFLOW_RESULT:")
        ),
        None,
    )
    if marker != "VISIONFLOW_RESULT:1":
        raise RecoveryError("Flyway V21 metadata repair marker is invalid")
    return 1


def print_state(state: dict[str, Any]) -> None:
    print(f"Backend status: {state['backendStatus']}")
    print("Constraint                          Table                       DeleteRule")
    print("----------------------------------  --------------------------  ----------")
    for name in sorted(state["constraints"]):
        row = state["constraints"][name]
        print(f"{name:34}  {row['table']:26}  {row['deleteRule']}")
    history = state["history"]
    if history:
        row = history[0]
        print(
            "Failed V21: "
            f"rank={row['installedRank']}, success={row['success']}, "
            f"checksum={row['checksum']}"
        )
    findings = sum(int(value) for value in state["databaseFindingCounts"].values())
    print(f"Database integrity findings: {findings}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VisionFlow failed Flyway V21 metadata recovery"
    )
    parser.add_argument("--root", type=Path, default=SCRIPT_DIR.parent)
    parser.add_argument("--container", default=MYSQL_CONTAINER)
    parser.add_argument("action", choices=("plan", "repair"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    print("VisionFlow Flyway V21 recovery")
    print("Scope: remove exactly one failed V21 Flyway metadata row")
    print("Database data rows: 0 changed; schema DDL: 0 executed")
    print("Safety: exact failed-profile guard; Backend must be stopped")
    print()
    try:
        query = lambda sql: integrity.mysql_query(args.container, sql)
        state = collect_state(query, lambda: container_status(BACKEND_CONTAINER))
        print_state(state)
        failures = evaluate_state(state)
        if failures:
            for failure in failures:
                print(f"[BLOCKED] {failure}")
            print("Status: BLOCKED")
            return 1
        print("[PASS] DB가 승인된 V21 실패 프로필과 정확히 일치합니다.")
        print("[PASS] 세 FK는 CASCADE 상태이며 반쪽 DDL 적용이 없습니다.")
        print(
            "[PASS] "
            f"{len(integrity.DATABASE_RULES)}개 DB 정합성 규칙의 "
            "finding이 0입니다."
        )
        if args.action == "plan":
            print("Status: READY")
            print(
                "Repair: repair --apply --confirm "
                f"{CONFIRMATION}"
            )
            return 0
        if not args.apply or args.confirm != CONFIRMATION:
            print("Status: BLOCKED")
            print(
                "Confirmation required: repair --apply --confirm "
                f"{CONFIRMATION}"
            )
            return 2
        backup = create_backup(root, state)
        deleted = execute_repair(args.container, build_repair_sql())
        post_rows = query(HISTORY_SQL)
        if post_rows:
            raise RecoveryError("V21 failed metadata remains after repair")
        print("Status: REPAIRED")
        print(f"Deleted failed Flyway metadata rows: {deleted}")
        print("Operational database rows changed: 0")
        print("Schema DDL executed: 0")
        print(f"Backup: {backup}")
        print("Backend remains stopped. Rebuild it to apply corrected V21.")
        return 0
    except (OSError, subprocess.SubprocessError, RecoveryError, ValueError) as error:
        print(f"Status: BLOCKED\n[FAIL] {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
