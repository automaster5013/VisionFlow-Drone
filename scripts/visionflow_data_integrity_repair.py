from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import visionflow_data_integrity_audit as audit


MYSQL_CONTAINER = "visionflow-mysql"
UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


class RepairError(RuntimeError):
    pass


MISSING_SESSION_SQL = """
SELECT
    r.session_id,
    SUM(r.event_rows),
    SUM(r.alert_rows),
    SUM(r.incident_rows),
    SUM(r.drone_rows),
    COUNT(DISTINCT r.drone_id),
    MIN(r.drone_id),
    MAX(r.drone_id),
    MIN(r.observed_at),
    MAX(r.observed_at),
    MAX(r.drone_status)
FROM (
    SELECT session_id, drone_id, captured_at AS observed_at,
           1 AS event_rows, 0 AS alert_rows, 0 AS incident_rows,
           0 AS drone_rows, NULL AS drone_status
    FROM ai_inference_event
    UNION ALL
    SELECT session_id, drone_id, captured_at,
           0, 1, 0, 0, NULL
    FROM ai_alert
    UNION ALL
    SELECT session_id, drone_id, occurred_at,
           0, 0, 1, 0, NULL
    FROM incident
    WHERE session_id IS NOT NULL
    UNION ALL
    SELECT flight_session_id, id, NULL,
           0, 0, 0, 1, status
    FROM drone
    WHERE flight_session_id IS NOT NULL
) r
LEFT JOIN flight_session fs ON fs.session_id = r.session_id
WHERE fs.session_id IS NULL
GROUP BY r.session_id
ORDER BY r.session_id
"""


EXISTING_SESSION_SQL = """
SELECT
    fs.session_id,
    fs.drone_id,
    fs.status,
    fs.started_at,
    fs.ended_at,
    COUNT(e.id)
FROM flight_session fs
LEFT JOIN ai_inference_event e ON e.session_id = fs.session_id
GROUP BY fs.session_id, fs.drone_id, fs.status, fs.started_at, fs.ended_at
ORDER BY fs.session_id
"""


TOTALS_SQL = """
SELECT
    (SELECT COUNT(*) FROM flight_session),
    (SELECT COUNT(*) FROM drone),
    (SELECT COUNT(*) FROM ai_inference_event),
    (SELECT COUNT(*) FROM ai_alert),
    (SELECT COUNT(*) FROM incident)
"""


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RepairError(f"JSON 최상위 값이 객체가 아닙니다: {path}")
    return value


def hash_prefix(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def parse_nullable(value: str) -> str | None:
    return None if value in {"", "NULL"} else value


def parse_int(value: str) -> int:
    if value in {"", "NULL"}:
        return 0
    return int(value)


def collect_state(
    query: Callable[[str], list[list[str]]],
) -> dict[str, Any]:
    database, database_counts, _ = audit.collect_database(query)
    missing_rows = query(MISSING_SESSION_SQL)
    missing = []
    for row in missing_rows:
        if len(row) != 11:
            raise RepairError("누락 세션 집계 결과 형식이 올바르지 않습니다.")
        session_id = row[0]
        missing.append(
            {
                "sessionId": session_id,
                "hash": hash_prefix(session_id),
                "eventRows": parse_int(row[1]),
                "alertRows": parse_int(row[2]),
                "incidentRows": parse_int(row[3]),
                "currentDroneReferences": parse_int(row[4]),
                "distinctDrones": parse_int(row[5]),
                "minDroneId": parse_int(row[6]),
                "maxDroneId": parse_int(row[7]),
                "firstObservedAt": parse_nullable(row[8]),
                "lastObservedAt": parse_nullable(row[9]),
                "droneStatus": parse_nullable(row[10]),
            }
        )

    existing_rows = query(EXISTING_SESSION_SQL)
    existing = []
    for row in existing_rows:
        if len(row) != 6:
            raise RepairError("기존 세션 집계 결과 형식이 올바르지 않습니다.")
        existing.append(
            {
                "sessionId": row[0],
                "hash": hash_prefix(row[0]),
                "droneId": parse_int(row[1]),
                "status": row[2],
                "startedAt": parse_nullable(row[3]),
                "endedAt": parse_nullable(row[4]),
                "aiEvents": parse_int(row[5]),
            }
        )

    totals_rows = query(TOTALS_SQL)
    if len(totals_rows) != 1 or len(totals_rows[0]) != 5:
        raise RepairError("테이블 행 수 집계 결과 형식이 올바르지 않습니다.")
    totals = {
        "flightSessionRows": parse_int(totals_rows[0][0]),
        "droneRows": parse_int(totals_rows[0][1]),
        "aiEventRows": parse_int(totals_rows[0][2]),
        "aiAlertRows": parse_int(totals_rows[0][3]),
        "incidentRows": parse_int(totals_rows[0][4]),
    }
    return {
        "database": database,
        "databaseCounts": database_counts,
        "totals": totals,
        "missingSessions": missing,
        "existingSessions": existing,
    }


def expected_finding_counts(policy: dict[str, Any]) -> dict[str, int]:
    expected = policy["expected"]
    counts = {key: 0 for key in audit.DATABASE_RULES}
    counts.update(
        {
            "session-orphan-drone": 1,
            "session-orphan-ai-event": int(expected["orphanEventRows"]),
            "session-orphan-ai-alert": int(expected["orphanAlertRows"]),
            "session-orphan-incident": int(expected["orphanIncidentRows"]),
        }
    )
    return counts


def evaluate_profile(
    policy: dict[str, Any], state: dict[str, Any]
) -> list[str]:
    failures: list[str] = []
    expected = policy.get("expected", {})
    for key in (
        "flightSessionRows",
        "droneRows",
        "aiEventRows",
        "aiAlertRows",
        "incidentRows",
    ):
        actual = state["totals"].get(key)
        wanted = int(expected.get(key, -1))
        if actual != wanted:
            failures.append(f"{key} drift: expected={wanted}, actual={actual}")

    wanted_counts = expected_finding_counts(policy)
    for key, wanted in wanted_counts.items():
        actual = int(state["databaseCounts"].get(key, -1))
        if actual != wanted:
            failures.append(
                f"database finding drift: {key} expected={wanted}, actual={actual}"
            )

    recoverable = [
        row
        for row in state["missingSessions"]
        if row["eventRows"] or row["alertRows"] or row["incidentRows"]
    ]
    stale = [
        row
        for row in state["missingSessions"]
        if not (row["eventRows"] or row["alertRows"] or row["incidentRows"])
    ]
    actual_recoverable = {row["hash"]: row for row in recoverable}
    wanted_recoverable = {
        str(row["hash"]): row for row in expected.get("recoverableSessions", [])
    }
    if set(actual_recoverable) != set(wanted_recoverable):
        failures.append(
            "recoverable session hash drift: "
            f"expected={sorted(wanted_recoverable)}, "
            f"actual={sorted(actual_recoverable)}"
        )
    for item_hash in sorted(set(actual_recoverable) & set(wanted_recoverable)):
        actual = actual_recoverable[item_hash]
        wanted = wanted_recoverable[item_hash]
        wanted_rows = int(wanted["rows"])
        wanted_drone = int(wanted["droneId"])
        if not (
            actual["eventRows"] == wanted_rows
            and actual["alertRows"] == wanted_rows
            and actual["incidentRows"] == wanted_rows
            and actual["currentDroneReferences"] == 0
            and actual["distinctDrones"] == 1
            and actual["minDroneId"] == wanted_drone
            and actual["maxDroneId"] == wanted_drone
            and actual["firstObservedAt"] is not None
            and actual["lastObservedAt"] is not None
        ):
            failures.append(f"recoverable session content drift: hash={item_hash}")

    wanted_stale = expected.get("staleDronePointer", {})
    if len(stale) != 1:
        failures.append(f"stale pointer count drift: expected=1, actual={len(stale)}")
    elif not (
        stale[0]["hash"] == wanted_stale.get("hash")
        and stale[0]["currentDroneReferences"]
        == int(wanted_stale.get("currentReferences", -1))
        and stale[0]["distinctDrones"] == 1
        and stale[0]["minDroneId"] == int(wanted_stale.get("droneId", -1))
        and stale[0]["maxDroneId"] == int(wanted_stale.get("droneId", -1))
        and stale[0]["droneStatus"] == wanted_stale.get("droneStatus")
    ):
        failures.append("stale Drone pointer profile drift")

    actual_existing = {row["hash"]: row for row in state["existingSessions"]}
    wanted_existing = {
        str(row["hash"]): row for row in expected.get("existingSessions", [])
    }
    if set(actual_existing) != set(wanted_existing):
        failures.append(
            "existing session hash drift: "
            f"expected={sorted(wanted_existing)}, actual={sorted(actual_existing)}"
        )
    for item_hash in sorted(set(actual_existing) & set(wanted_existing)):
        actual = actual_existing[item_hash]
        wanted = wanted_existing[item_hash]
        if not (
            actual["droneId"] == int(wanted["droneId"])
            and actual["status"] == wanted["status"]
            and actual["aiEvents"] == int(wanted["aiEvents"])
        ):
            failures.append(f"existing session content drift: hash={item_hash}")
    return failures


def require_uuid(value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as error:
        raise RepairError("세션 식별자가 UUID 형식이 아닙니다.") from error
    canonical = str(parsed)
    if canonical.lower() != value.lower() or len(value) != 36:
        raise RepairError("세션 식별자가 canonical UUID 형식이 아닙니다.")
    return canonical


def sql_string(value: str) -> str:
    if "\x00" in value:
        raise RepairError("SQL 문자열에 NUL은 허용되지 않습니다.")
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def guard(condition: str) -> str:
    return (
        "SET @vf_guard_sql = IF((" + condition + "), "
        "'SELECT 1', 'SELECT * FROM visionflow_repair_guard_failed');\n"
        "PREPARE vf_guard FROM @vf_guard_sql;\n"
        "EXECUTE vf_guard;\n"
        "DEALLOCATE PREPARE vf_guard;"
    )


def build_apply_sql(policy: dict[str, Any], state: dict[str, Any]) -> str:
    expected = policy["expected"]
    repair = policy["repair"]
    recoverable = sorted(
        (
            row
            for row in state["missingSessions"]
            if row["eventRows"] or row["alertRows"] or row["incidentRows"]
        ),
        key=lambda row: row["sessionId"],
    )
    stale = [
        row
        for row in state["missingSessions"]
        if not (row["eventRows"] or row["alertRows"] or row["incidentRows"])
    ]
    if len(recoverable) != int(repair["expectedSessionInserts"]) or len(stale) != 1:
        raise RepairError("복구 SQL 생성 전 대상 수가 변경됐습니다.")
    session_ids = [require_uuid(str(row["sessionId"])) for row in recoverable]
    stale_id = require_uuid(str(stale[0]["sessionId"]))
    id_list = ", ".join(sql_string(value) for value in session_ids)
    stale_literal = sql_string(stale_id)
    recovered_status = sql_string(str(repair["recoveredStatus"]))
    name_prefix = sql_string(str(repair["recoveredNamePrefix"]))
    description = sql_string(str(repair["recoveredDescription"]))
    lock_name = sql_string("visionflow_data_integrity_repair")
    expected_inserts = int(repair["expectedSessionInserts"])
    expected_updates = int(repair["expectedDroneUpdates"])
    expected_events = int(expected["orphanEventRows"])
    expected_alerts = int(expected["orphanAlertRows"])
    expected_incidents = int(expected["orphanIncidentRows"])
    expected_sessions_before = int(expected["flightSessionRows"])
    expected_sessions_after = expected_sessions_before + expected_inserts
    stale_drone_id = int(expected["staleDronePointer"]["droneId"])
    stale_status = sql_string(str(expected["staleDronePointer"]["droneStatus"]))

    statements = [
        "SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE;",
        "START TRANSACTION;",
        f"SELECT GET_LOCK({lock_name}, 10) INTO @vf_lock;",
        guard("@vf_lock = 1"),
        "SELECT COUNT(*) INTO @vf_sessions_before FROM flight_session;",
        guard(f"@vf_sessions_before = {expected_sessions_before}"),
        (
            "SELECT COUNT(*), COUNT(DISTINCT session_id) "
            "INTO @vf_events, @vf_event_sessions FROM ai_inference_event "
            f"WHERE session_id IN ({id_list});"
        ),
        guard(
            f"@vf_events = {expected_events} AND "
            f"@vf_event_sessions = {expected_inserts}"
        ),
        (
            "SELECT COUNT(*), COUNT(DISTINCT session_id) "
            "INTO @vf_alerts, @vf_alert_sessions FROM ai_alert "
            f"WHERE session_id IN ({id_list});"
        ),
        guard(
            f"@vf_alerts = {expected_alerts} AND "
            f"@vf_alert_sessions = {expected_inserts}"
        ),
        (
            "SELECT COUNT(*), COUNT(DISTINCT session_id) "
            "INTO @vf_incidents, @vf_incident_sessions FROM incident "
            f"WHERE session_id IN ({id_list});"
        ),
        guard(
            f"@vf_incidents = {expected_incidents} AND "
            f"@vf_incident_sessions = {expected_inserts}"
        ),
        (
            "SELECT COUNT(*) INTO @vf_existing_targets FROM flight_session "
            f"WHERE session_id IN ({id_list});"
        ),
        guard("@vf_existing_targets = 0"),
        (
            "SELECT COUNT(*) INTO @vf_stale_pointer "
            "FROM drone d LEFT JOIN flight_session fs "
            "ON fs.session_id = d.flight_session_id "
            f"WHERE d.id = {stale_drone_id} "
            f"AND d.status = {stale_status} "
            f"AND d.flight_session_id = {stale_literal} "
            "AND fs.session_id IS NULL;"
        ),
        guard("@vf_stale_pointer = 1"),
        (
            "INSERT INTO flight_session ("
            "session_id, drone_id, name, description, status, source_device_id, "
            "started_at, ended_at, created_at, updated_at) "
            "SELECT e.session_id, MIN(e.drone_id), "
            f"CONCAT({name_prefix}, ' ', "
            "DATE_FORMAT(MIN(e.captured_at), '%Y-%m-%d %H:%i:%s')), "
            f"{description}, {recovered_status}, NULL, "
            "MIN(e.captured_at), MAX(e.captured_at), "
            "MIN(e.captured_at), MAX(e.captured_at) "
            "FROM ai_inference_event e "
            "JOIN drone d ON d.id = e.drone_id "
            "LEFT JOIN flight_session fs ON fs.session_id = e.session_id "
            f"WHERE e.session_id IN ({id_list}) AND fs.session_id IS NULL "
            "GROUP BY e.session_id HAVING COUNT(DISTINCT e.drone_id) = 1;"
        ),
        "SELECT ROW_COUNT() INTO @vf_inserted;",
        guard(f"@vf_inserted = {expected_inserts}"),
        (
            "UPDATE drone SET flight_session_id = NULL "
            f"WHERE id = {stale_drone_id} "
            f"AND status = {stale_status} "
            f"AND flight_session_id = {stale_literal};"
        ),
        "SELECT ROW_COUNT() INTO @vf_updated;",
        guard(f"@vf_updated = {expected_updates}"),
        (
            "SELECT COUNT(*) INTO @vf_post_event_orphans "
            "FROM ai_inference_event e LEFT JOIN flight_session fs "
            "ON fs.session_id = e.session_id WHERE fs.session_id IS NULL;"
        ),
        guard("@vf_post_event_orphans = 0"),
        (
            "SELECT COUNT(*) INTO @vf_post_alert_orphans "
            "FROM ai_alert a LEFT JOIN flight_session fs "
            "ON fs.session_id = a.session_id WHERE fs.session_id IS NULL;"
        ),
        guard("@vf_post_alert_orphans = 0"),
        (
            "SELECT COUNT(*) INTO @vf_post_incident_orphans "
            "FROM incident i LEFT JOIN flight_session fs "
            "ON fs.session_id = i.session_id "
            "WHERE i.session_id IS NOT NULL AND fs.session_id IS NULL;"
        ),
        guard("@vf_post_incident_orphans = 0"),
        (
            "SELECT COUNT(*) INTO @vf_post_drone_orphans "
            "FROM drone d LEFT JOIN flight_session fs "
            "ON fs.session_id = d.flight_session_id "
            "WHERE d.flight_session_id IS NOT NULL AND fs.session_id IS NULL;"
        ),
        guard("@vf_post_drone_orphans = 0"),
        "SELECT COUNT(*) INTO @vf_sessions_after FROM flight_session;",
        guard(f"@vf_sessions_after = {expected_sessions_after}"),
        "COMMIT;",
        "SELECT CONCAT('VISIONFLOW_RESULT:', @vf_inserted, ':', @vf_updated);",
        f"SELECT RELEASE_LOCK({lock_name});",
    ]
    sql = "\n".join(statements)
    if re.search(r"\bDELETE\b", sql, re.IGNORECASE):
        raise RepairError("적용 SQL에 DELETE가 포함됐습니다.")
    return sql


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


def create_backup(
    root: Path, policy: dict[str, Any], state: dict[str, Any]
) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = root / "artifacts" / "data-integrity-repair" / f"repair-{timestamp}"
    output.mkdir(parents=True, exist_ok=False)
    recoverable = [
        row
        for row in state["missingSessions"]
        if row["eventRows"] or row["alertRows"] or row["incidentRows"]
    ]
    stale = [
        row
        for row in state["missingSessions"]
        if not (row["eventRows"] or row["alertRows"] or row["incidentRows"])
    ][0]
    backup = {
        "schemaVersion": 1,
        "project": "visionflow",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "pre-repair session correlation state",
        "containsOperationalIdentifiers": True,
        "containsCredentials": False,
        "recoverableSessions": recoverable,
        "staleDronePointer": stale,
        "existingSessions": state["existingSessions"],
        "databaseCounts": state["databaseCounts"],
        "totals": state["totals"],
    }
    atomic_write(
        output / "before-state.json",
        json.dumps(backup, ensure_ascii=False, indent=2) + "\n",
    )
    session_ids = sorted(require_uuid(row["sessionId"]) for row in recoverable)
    id_list = ", ".join(sql_string(value) for value in session_ids)
    stale_id = require_uuid(stale["sessionId"])
    drone_id = int(policy["expected"]["staleDronePointer"]["droneId"])
    rollback = (
        "-- MANUAL ROLLBACK ONLY: this restores the pre-repair orphan state.\n"
        "START TRANSACTION;\n"
        "UPDATE drone SET flight_session_id = "
        f"{sql_string(stale_id)} WHERE id = {drone_id} "
        "AND flight_session_id IS NULL;\n"
        f"DELETE FROM flight_session WHERE session_id IN ({id_list});\n"
        "COMMIT;\n"
    )
    atomic_write(output / "rollback.sql", rollback)
    return output


def sanitize_error(value: str) -> str:
    redacted = UUID_PATTERN.sub("<redacted-session-id>", value)
    lines = [line.strip() for line in redacted.splitlines() if line.strip()]
    return lines[-1] if lines else "unknown MySQL error"


def execute_apply(container: str, sql: str) -> tuple[int, int]:
    completed = subprocess.run(
        [
            "docker",
            "exec",
            "--env",
            f"VISIONFLOW_REPAIR_SQL={sql}",
            container,
            "sh",
            "-c",
            'MYSQL_PWD="$MYSQL_PASSWORD" mysql --user="$MYSQL_USER" '
            '--batch --raw --skip-column-names --default-character-set=utf8mb4 '
            '"$MYSQL_DATABASE" --execute "$VISIONFLOW_REPAIR_SQL"',
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    if completed.returncode != 0:
        detail = sanitize_error(completed.stderr or completed.stdout)
        raise RepairError(f"MySQL 트랜잭션 실패: {detail}")
    marker = next(
        (
            line.strip()
            for line in completed.stdout.splitlines()
            if line.strip().startswith("VISIONFLOW_RESULT:")
        ),
        None,
    )
    if marker is None:
        raise RepairError("MySQL 적용 결과 marker를 찾지 못했습니다.")
    parts = marker.split(":")
    if len(parts) != 3:
        raise RepairError("MySQL 적용 결과 marker 형식이 올바르지 않습니다.")
    return int(parts[1]), int(parts[2])


def verify_post_state(policy: dict[str, Any], state: dict[str, Any]) -> list[str]:
    failures = []
    repair = policy["repair"]
    expected = policy["expected"]
    if state["missingSessions"]:
        failures.append(
            f"post-repair missing sessions remain: {len(state['missingSessions'])}"
        )
    nonzero = {
        key: value for key, value in state["databaseCounts"].items() if value != 0
    }
    if nonzero:
        failures.append(f"post-repair database findings remain: {nonzero}")
    expected_sessions = int(expected["flightSessionRows"]) + int(
        repair["expectedSessionInserts"]
    )
    if state["totals"]["flightSessionRows"] != expected_sessions:
        failures.append(
            "post-repair flightSessionRows mismatch: "
            f"expected={expected_sessions}, "
            f"actual={state['totals']['flightSessionRows']}"
        )
    for key in ("aiEventRows", "aiAlertRows", "incidentRows", "droneRows"):
        if state["totals"][key] != int(expected[key]):
            failures.append(
                f"post-repair {key} changed: expected={expected[key]}, "
                f"actual={state['totals'][key]}"
            )
    return failures


def print_header() -> None:
    print("VisionFlow session data integrity repair")
    print("Scope: recover missing flight_session=13; clear stale Drone pointer=1")
    print("Mutation: INSERT=13, UPDATE=1, DELETE=0")
    print("Safety: exact profile guard; SERIALIZABLE transaction; no service restart")
    print()


def print_plan(state: dict[str, Any]) -> None:
    recoverable = sorted(
        (
            row
            for row in state["missingSessions"]
            if row["eventRows"] or row["alertRows"] or row["incidentRows"]
        ),
        key=lambda row: row["hash"],
    )
    print("Hash              Drone  Events  Alerts  Incidents")
    print("----------------  -----  ------  ------  ---------")
    for row in recoverable:
        print(
            f"{row['hash']}  {row['minDroneId']:>5}  "
            f"{row['eventRows']:>6}  {row['alertRows']:>6}  "
            f"{row['incidentRows']:>9}"
        )
    stale = [
        row
        for row in state["missingSessions"]
        if not (row["eventRows"] or row["alertRows"] or row["incidentRows"])
    ]
    if stale:
        print(
            f"Stale pointer: hash={stale[0]['hash']}, "
            f"drone={stale[0]['minDroneId']}, status={stale[0]['droneStatus']}"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VisionFlow confirmation-gated session integrity repair"
    )
    parser.add_argument("--root", type=Path, default=SCRIPT_DIR.parent)
    parser.add_argument("--container", default=MYSQL_CONTAINER)
    parser.add_argument(
        "--policy",
        type=Path,
        default=SCRIPT_DIR / "visionflow_data_integrity_repair_policy.json",
    )
    parser.add_argument("action", choices=("plan", "repair"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    print_header()
    try:
        root = args.root.resolve()
        policy = read_object(args.policy.resolve())
        audit.require_running_container(args.container)
        state = collect_state(lambda sql: audit.mysql_query(args.container, sql))
        failures = evaluate_profile(policy, state)
        if failures:
            for failure in failures:
                print(f"[BLOCKED] {failure}")
            print("Status: BLOCKED")
            return 1
        print_plan(state)
        print("[PASS] 현재 DB가 승인된 복구 프로필과 정확히 일치합니다.")
        print("[PASS] 13개 세션은 각각 하나의 기존 Drone에 일관되게 연결됩니다.")
        print("[PASS] 기존 정상 세션 2건과 AI 연쇄 데이터는 변경 대상이 아닙니다.")

        confirmation = str(policy["confirmation"])
        if args.action == "plan" or not args.apply:
            print("Status: READY")
            print(f"Apply: repair --apply --confirm {confirmation}")
            return 0
        if args.confirm != confirmation:
            print("Status: BLOCKED")
            print(f"Confirmation required: --confirm {confirmation}")
            return 2

        backup = create_backup(root, policy, state)
        sql = build_apply_sql(policy, state)
        inserted, updated = execute_apply(args.container, sql)
        expected_inserted = int(policy["repair"]["expectedSessionInserts"])
        expected_updated = int(policy["repair"]["expectedDroneUpdates"])
        if inserted != expected_inserted or updated != expected_updated:
            raise RepairError(
                f"적용 결과 불일치: inserted={inserted}, updated={updated}"
            )
        post_state = collect_state(lambda query: audit.mysql_query(args.container, query))
        post_failures = verify_post_state(policy, post_state)
        if post_failures:
            for failure in post_failures:
                print(f"[FAIL] {failure}")
            print("Status: VERIFY_FAILED")
            print(f"Backup: {backup}")
            return 1

        print("Status: REPAIRED")
        print(f"Inserted flight sessions: {inserted}")
        print(f"Cleared stale Drone pointers: {updated}")
        print("Deleted rows: 0")
        print("AI event, alert, and Incident rows changed: 0")
        print(f"Backup: {backup}")
        print("Services were not rebuilt or restarted.")
        print("Next: run scripts\\run-visionflow-data-integrity-audit.bat")
        return 0
    except (OSError, KeyError, ValueError, RepairError, audit.AuditError) as error:
        print(f"Status: BLOCKED\n[FAIL] {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
