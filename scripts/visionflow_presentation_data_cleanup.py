#!/usr/bin/env python3
"""Safely quarantine, delete, verify, and restore VisionFlow presentation data.

This tool is intentionally scoped to the 2026 second-project cleanup:

* flight sessions whose source_device_id is ``visionflow-demo-console``
* AI events whose source_id starts with ``presentation-``

The validated real-smartphone session is explicitly protected.  The tool uses
an operation manifest and exact ID fingerprints so that the target cannot drift
between plan, quarantine, and delete phases.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


MYSQL_CONTAINER = "visionflow-mysql"
DEMO_SOURCE_DEVICE_ID = "visionflow-demo-console"
PRESENTATION_SOURCE_LIKE = "presentation-%"
PROTECTED_SESSION_ID = "3c0b11cc-c115-45b4-9814-9ef18ada6188"
OPERATION_SCHEMA_VERSION = 1
TARGET_NAME = "SECOND_PROJECT_PRESENTATION_DATA"

SERVICE_CONTAINERS = (
    "visionflow-frontend",
    "visionflow-ai",
    "visionflow-backend",
)
SERVICE_START_ORDER = (
    "visionflow-backend",
    "visionflow-ai",
    "visionflow-frontend",
)

EXPECTED_TARGET_COUNTS = {
    "flightSessions": 40,
    "demoScenarios": 40,
    "telemetry": 200,
    "events": 59,
    "detections": 109,
    "alerts": 59,
    "incidents": 59,
    "actions": 158,
    "snapshots": 59,
}

PLAN_TOKEN = "PLAN_PRESENTATION_DATA"
QUARANTINE_TOKEN = "QUARANTINE_PRESENTATION_59_SNAPSHOTS"
DELETE_TOKEN = "DELETE_PRESENTATION_DATA"
RESTORE_TOKEN = "RESTORE_PRESENTATION_DATA"
RECONCILE_TOKEN = "RECONCILE_DELETED_PRESENTATION_DATA"

ID_FIELDS = {
    "flightSessions": ("flight_session", "session_id", False),
    "demoScenarios": ("demo_scenario", "scenario_id", False),
    "telemetry": ("drone_telemetry_history", "id", True),
    "events": ("ai_inference_event", "id", True),
    "detections": ("ai_detection", "id", True),
    "alerts": ("ai_alert", "id", True),
    "incidents": ("incident", "id", True),
    "actions": ("incident_action_history", "id", True),
}

RESTORE_ORDER = (
    "flightSessions",
    "events",
    "detections",
    "alerts",
    "incidents",
    "actions",
    "telemetry",
    "demoScenarios",
)

HANDLED_FOREIGN_KEYS = {
    ("demo_scenario", "flight_session_id", "flight_session", "session_id"): "demoScenarios",
    (
        "drone_telemetry_history",
        "flight_session_id",
        "flight_session",
        "session_id",
    ): "telemetry",
    ("ai_detection", "event_id", "ai_inference_event", "id"): "detections",
    ("ai_alert", "event_id", "ai_inference_event", "id"): "alerts",
    ("incident_action_history", "incident_id", "incident", "id"): "actions",
}


class CleanupError(RuntimeError):
    """Raised when a cleanup safety condition is not satisfied."""


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_root() -> Path:
    return Path(__file__).resolve().parent.parent


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def run(
    arguments: list[str],
    *,
    input_text: str | None = None,
    stdin_file: Path | None = None,
    binary_stdout=None,
) -> subprocess.CompletedProcess[str]:
    if sum(value is not None for value in (input_text, stdin_file, binary_stdout)) > 1:
        raise ValueError("표준 입출력 리디렉션 옵션은 하나만 지정할 수 있습니다.")

    if stdin_file is not None:
        with stdin_file.open("rb") as stream:
            completed = subprocess.run(
                arguments,
                stdin=stream,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        stdout = completed.stdout.decode("utf-8", errors="replace")
        stderr = completed.stderr.decode("utf-8", errors="replace")
    elif binary_stdout is not None:
        completed = subprocess.run(
            arguments,
            stdout=binary_stdout,
            stderr=subprocess.PIPE,
            check=False,
        )
        stdout = ""
        stderr = completed.stderr.decode("utf-8", errors="replace")
    else:
        completed = subprocess.run(
            arguments,
            input=input_text,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
        stdout = completed.stdout
        stderr = completed.stderr

    if completed.returncode != 0:
        raise CleanupError(
            f"명령 실패({completed.returncode}): {' '.join(arguments)}\n{stderr}"
        )
    return subprocess.CompletedProcess(
        args=arguments,
        returncode=0,
        stdout=stdout,
        stderr=stderr,
    )


def mysql_query(sql: str) -> str:
    command = (
        'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -D "$MYSQL_DATABASE" '
        '--batch --raw --skip-column-names '
        f"-e {shlex.quote(sql)}"
    )
    return run(
        ["docker", "exec", MYSQL_CONTAINER, "sh", "-lc", command]
    ).stdout


def mysql_import(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise CleanupError(f"복원 SQL 파일이 없거나 비어 있습니다: {path}")
    command = (
        'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" '
        '-D "$MYSQL_DATABASE" --show-warnings'
    )
    run(
        ["docker", "exec", "-i", MYSQL_CONTAINER, "sh", "-lc", command],
        stdin_file=path,
    )


def event_condition(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return (
        "("
        f"{prefix}source_id LIKE '{PRESENTATION_SOURCE_LIKE}' OR "
        f"{prefix}session_id IN ("
        "SELECT session_id FROM flight_session "
        f"WHERE source_device_id='{DEMO_SOURCE_DEVICE_ID}'"
        ")"
        ")"
    )


def query_values(sql: str) -> list[str]:
    return [line.strip() for line in mysql_query(sql).splitlines() if line.strip()]


def query_rows(sql: str, fields: int) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in mysql_query(sql).splitlines():
        if not line.strip():
            continue
        values = line.split("\t")
        if len(values) != fields:
            raise CleanupError(f"DB 조회 열 수가 올바르지 않습니다: {line!r}")
        rows.append(values)
    return rows


def query_ids() -> dict[str, list[str]]:
    condition = event_condition("e")
    return {
        "flightSessions": query_values(
            "SELECT session_id FROM flight_session "
            f"WHERE source_device_id='{DEMO_SOURCE_DEVICE_ID}' "
            "ORDER BY session_id;"
        ),
        "demoScenarios": query_values(
            "SELECT ds.scenario_id FROM demo_scenario ds "
            "JOIN flight_session fs ON fs.session_id=ds.flight_session_id "
            f"WHERE fs.source_device_id='{DEMO_SOURCE_DEVICE_ID}' "
            "ORDER BY ds.scenario_id;"
        ),
        "telemetry": query_values(
            "SELECT th.id FROM drone_telemetry_history th "
            "JOIN flight_session fs ON fs.session_id=th.flight_session_id "
            f"WHERE fs.source_device_id='{DEMO_SOURCE_DEVICE_ID}' "
            "ORDER BY th.id;"
        ),
        "events": query_values(
            "SELECT e.id FROM ai_inference_event e "
            f"WHERE {condition} ORDER BY e.id;"
        ),
        "detections": query_values(
            "SELECT d.id FROM ai_detection d "
            "JOIN ai_inference_event e ON e.id=d.event_id "
            f"WHERE {condition} ORDER BY d.id;"
        ),
        "alerts": query_values(
            "SELECT a.id FROM ai_alert a "
            "JOIN ai_inference_event e ON e.id=a.event_id "
            f"WHERE {condition} ORDER BY a.id;"
        ),
        "incidents": query_values(
            "SELECT i.id FROM incident i "
            "JOIN ai_alert a ON i.source_type='AI_ALERT' AND i.source_id=a.id "
            "JOIN ai_inference_event e ON e.id=a.event_id "
            f"WHERE {condition} ORDER BY i.id;"
        ),
        "actions": query_values(
            "SELECT h.id FROM incident_action_history h "
            "JOIN incident i ON i.id=h.incident_id "
            "JOIN ai_alert a ON i.source_type='AI_ALERT' AND i.source_id=a.id "
            "JOIN ai_inference_event e ON e.id=a.event_id "
            f"WHERE {condition} ORDER BY h.id;"
        ),
    }


def quote_identifier(value: str) -> str:
    return "`" + value.replace("`", "``") + "`"


def foreign_key_dependencies(ids: dict[str, list[str]]) -> list[dict[str, Any]]:
    parent_keys = {
        ("flight_session", "session_id"): (ids["flightSessions"], False),
        ("ai_inference_event", "id"): (ids["events"], True),
        ("incident", "id"): (ids["incidents"], True),
    }
    definitions = query_rows(
        "SELECT k.TABLE_NAME,k.COLUMN_NAME,k.REFERENCED_TABLE_NAME,"
        "k.REFERENCED_COLUMN_NAME,r.DELETE_RULE "
        "FROM information_schema.KEY_COLUMN_USAGE k "
        "JOIN information_schema.REFERENTIAL_CONSTRAINTS r "
        "ON r.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA "
        "AND r.CONSTRAINT_NAME=k.CONSTRAINT_NAME "
        "AND r.TABLE_NAME=k.TABLE_NAME "
        "WHERE k.CONSTRAINT_SCHEMA=DATABASE() "
        "AND k.REFERENCED_TABLE_NAME IN "
        "('flight_session','ai_inference_event','incident') "
        "ORDER BY k.TABLE_NAME,k.COLUMN_NAME;",
        5,
    )
    results: list[dict[str, Any]] = []
    for child_table, child_column, parent_table, parent_column, delete_rule in definitions:
        parent = parent_keys.get((parent_table, parent_column))
        if parent is None:
            continue
        parent_ids, numeric = parent
        if parent_ids:
            count = int(
                mysql_query(
                    "SELECT COUNT(*) FROM "
                    f"{quote_identifier(child_table)} WHERE "
                    f"{quote_identifier(child_column)} IN "
                    f"({sql_list(parent_ids, numeric)});"
                ).strip()
            )
        else:
            count = 0
        relation = (child_table, child_column, parent_table, parent_column)
        handled_key = HANDLED_FOREIGN_KEYS.get(relation)
        if handled_key is None and count:
            raise CleanupError(
                "자동 백업·복원 범위 밖의 연결 데이터가 발견됐습니다: "
                f"{child_table}.{child_column} -> "
                f"{parent_table}.{parent_column}, rows={count}"
            )
        if handled_key is not None and count != len(ids[handled_key]):
            raise CleanupError(
                "외래 키 연결 건수와 선택 대상이 다릅니다: "
                f"{child_table}.{child_column}, fkRows={count}, "
                f"selected={len(ids[handled_key])}"
            )
        results.append(
            {
                "childTable": child_table,
                "childColumn": child_column,
                "parentTable": parent_table,
                "parentColumn": parent_column,
                "deleteRule": delete_rule,
                "targetRows": count,
                "handledBy": handled_key,
            }
        )
    return results


def total_counts() -> dict[str, int]:
    output = mysql_query(
        "SELECT "
        "(SELECT COUNT(*) FROM flight_session),"
        "(SELECT COUNT(*) FROM demo_scenario),"
        "(SELECT COUNT(*) FROM drone_telemetry_history),"
        "(SELECT COUNT(*) FROM ai_inference_event),"
        "(SELECT COUNT(*) FROM ai_detection),"
        "(SELECT COUNT(*) FROM ai_alert),"
        "(SELECT COUNT(*) FROM incident),"
        "(SELECT COUNT(*) FROM incident_action_history),"
        "(SELECT COUNT(*) FROM ai_inference_event "
        " WHERE snapshot_file_name IS NOT NULL);"
    ).strip().split("\t")
    keys = tuple(EXPECTED_TARGET_COUNTS)
    if len(output) != len(keys):
        raise CleanupError(f"전체 집계 결과 형식 오류: {output!r}")
    return {key: int(value) for key, value in zip(keys, output)}


def fingerprint(ids: dict[str, list[str]]) -> str:
    value = json.dumps(ids, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def snapshot_rows(root: Path, operation: Path) -> list[dict[str, Any]]:
    rows = query_rows(
        "SELECT e.id,e.session_id,e.snapshot_file_name,e.snapshot_size_bytes "
        "FROM ai_inference_event e "
        f"WHERE {event_condition('e')} "
        "AND e.snapshot_file_name IS NOT NULL ORDER BY e.id;",
        4,
    )
    source_root = (root / "artifacts/backend-data/ai-snapshots").resolve()
    quarantine_root = (operation / "quarantine/files").resolve()
    results: list[dict[str, Any]] = []
    for event_id, session_id, file_name, size_value in rows:
        if not event_id.isdigit():
            raise CleanupError(f"이벤트 ID가 숫자가 아닙니다: {event_id}")
        if file_name != f"event-{event_id}.jpg" or Path(file_name).name != file_name:
            raise CleanupError(f"스냅숏 파일명 검증 실패: {event_id}/{file_name}")
        size_bytes = int(size_value)
        source_path = (source_root / file_name).resolve()
        bucket_start = (int(event_id) // 10_000) * 10_000
        bucket = f"{bucket_start:06d}-{bucket_start + 9999:06d}"
        quarantine_path = (quarantine_root / bucket / file_name).resolve()
        if not is_within(source_path, source_root):
            raise CleanupError(f"스냅숏 경로가 허용 범위를 벗어났습니다: {source_path}")
        if not is_within(quarantine_path, quarantine_root):
            raise CleanupError(f"격리 경로가 허용 범위를 벗어났습니다: {quarantine_path}")
        results.append(
            {
                "event_id": int(event_id),
                "session_id": session_id,
                "file_name": file_name,
                "size_bytes": size_bytes,
                "source_path": str(source_path),
                "quarantine_path": str(quarantine_path),
            }
        )
    return results


def verify_snapshot_sources(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        source = Path(row["source_path"])
        if not source.is_file() or source.is_symlink():
            raise CleanupError(f"원본 스냅숏이 없습니다: {source}")
        if source.stat().st_size != row["size_bytes"]:
            raise CleanupError(f"스냅숏 크기 불일치: {source}")


def verify_quarantine(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        source = Path(row["source_path"])
        quarantined = Path(row["quarantine_path"])
        if source.exists():
            raise CleanupError(f"원본 위치에 격리 대상이 남았습니다: {source}")
        if not quarantined.is_file() or quarantined.is_symlink():
            raise CleanupError(f"격리 파일이 없습니다: {quarantined}")
        if quarantined.stat().st_size != row["size_bytes"]:
            raise CleanupError(f"격리 파일 크기 불일치: {quarantined}")


def manifest_path(operation: Path) -> Path:
    return operation / "manifest/target-snapshots.csv"


def write_manifest(operation: Path, rows: list[dict[str, Any]]) -> Path:
    path = manifest_path(operation)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def load_manifest(operation: Path) -> list[dict[str, Any]]:
    path = manifest_path(operation)
    if not path.is_file():
        raise CleanupError(f"manifest가 없습니다: {path}")
    rows: list[dict[str, Any]] = []
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        for item in csv.DictReader(stream):
            rows.append(
                {
                    "event_id": int(item["event_id"]),
                    "session_id": item["session_id"],
                    "file_name": item["file_name"],
                    "size_bytes": int(item["size_bytes"]),
                    "source_path": item["source_path"],
                    "quarantine_path": item["quarantine_path"],
                }
            )
    return rows


def collect_selection(root: Path, operation: Path, *, require_expected: bool) -> dict[str, Any]:
    ids = query_ids()
    counts = {key: len(ids[key]) for key in ID_FIELDS}
    rows = snapshot_rows(root, operation)
    counts["snapshots"] = len(rows)
    protected_hits = int(
        mysql_query(
            "SELECT "
            f"(SELECT COUNT(*) FROM flight_session WHERE session_id='{PROTECTED_SESSION_ID}' "
            f" AND source_device_id='{DEMO_SOURCE_DEVICE_ID}') + "
            f"(SELECT COUNT(*) FROM ai_inference_event WHERE session_id='{PROTECTED_SESSION_ID}' "
            f" AND {event_condition()});"
        ).strip()
    )
    if protected_hits:
        raise CleanupError("보호된 실제 스마트폰 세션이 정리 대상에 포함됐습니다.")
    if require_expected and counts != EXPECTED_TARGET_COUNTS:
        raise CleanupError(
            "현재 대상 집계가 승인된 범위와 다릅니다.\n"
            f"예상={json.dumps(EXPECTED_TARGET_COUNTS, ensure_ascii=False)}\n"
            f"실제={json.dumps(counts, ensure_ascii=False)}"
        )
    dependencies = foreign_key_dependencies(ids)
    return {
        "counts": counts,
        "snapshotBytes": sum(row["size_bytes"] for row in rows),
        "ids": ids,
        "fingerprint": fingerprint(ids),
        "foreignKeyDependencies": dependencies,
        "snapshotRows": rows,
    }


def create_operation(root: Path) -> Path:
    output_root = (root / "artifacts/presentation-data-cleanup").resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    operation = output_root / f"cleanup-{stamp}"
    if operation.exists():
        raise CleanupError(f"작업 폴더가 이미 존재합니다: {operation}")
    operation.mkdir()
    return operation


def resolve_operation(root: Path, value: str) -> Path:
    operation = Path(value)
    operation = operation.resolve() if operation.is_absolute() else (root / operation).resolve()
    allowed = (root / "artifacts/presentation-data-cleanup").resolve()
    if not is_within(operation, allowed):
        raise CleanupError(f"작업 폴더가 허용 범위를 벗어났습니다: {operation}")
    return operation


def operation_file(operation: Path) -> Path:
    return operation / "operation.json"


def load_operation(root: Path, value: str) -> tuple[Path, dict[str, Any]]:
    operation = resolve_operation(root, value)
    path = operation_file(operation)
    if not path.is_file():
        raise CleanupError(f"operation.json이 없습니다: {path}")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if data.get("schemaVersion") != OPERATION_SCHEMA_VERSION:
        raise CleanupError("지원하지 않는 operation 스키마입니다.")
    if data.get("target") != TARGET_NAME:
        raise CleanupError("발표 데이터 정리 operation이 아닙니다.")
    if data.get("protectedSessionId") != PROTECTED_SESSION_ID:
        raise CleanupError("보호 세션 ID가 승인된 값과 다릅니다.")
    if data.get("expectedCounts") != EXPECTED_TARGET_COUNTS:
        raise CleanupError("operation의 승인 대상 집계가 다릅니다.")
    return operation, data


def ensure_current_matches(
    root: Path,
    operation: Path,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    current = collect_selection(root, operation, require_expected=True)
    if current["fingerprint"] != metadata.get("selectionFingerprint"):
        raise CleanupError("계획 이후 정리 대상 ID가 변경되었습니다.")
    if current["snapshotBytes"] != metadata.get("snapshotBytes"):
        raise CleanupError("계획 이후 스냅숏 총 크기가 변경되었습니다.")
    if current["foreignKeyDependencies"] != metadata.get("foreignKeyDependencies"):
        raise CleanupError("계획 이후 외래 키 연결 상태가 변경되었습니다.")
    totals = total_counts()
    if totals != metadata.get("baselineTotals"):
        raise CleanupError(
            "계획 이후 관련 테이블 전체 건수가 변경되었습니다.\n"
            f"계획={json.dumps(metadata.get('baselineTotals'), ensure_ascii=False)}\n"
            f"현재={json.dumps(totals, ensure_ascii=False)}"
        )
    return current


def sql_list(values: Iterable[str], numeric: bool) -> str:
    items = list(values)
    if not items:
        raise CleanupError("비어 있는 ID 목록은 SQL 조건으로 만들 수 없습니다.")
    if numeric:
        if not all(value.isdigit() for value in items):
            raise CleanupError("숫자 ID 목록에 숫자가 아닌 값이 있습니다.")
        return ",".join(items)
    return ",".join("'" + value.replace("'", "''") + "'" for value in items)


def dump_to(path: Path, table: str | None = None, where: str | None = None) -> None:
    options = [
        "mysqldump",
        "-uroot",
        '-p"$MYSQL_ROOT_PASSWORD"',
        "--single-transaction",
        "--quick",
        "--hex-blob",
        "--no-tablespaces",
        "--default-character-set=utf8mb4",
    ]
    if table is None:
        options += ["--routines", "--triggers", "--events", '"$MYSQL_DATABASE"']
    else:
        options += [
            "--no-create-info",
            "--skip-triggers",
            "--complete-insert",
            '"$MYSQL_DATABASE"',
            table,
        ]
        if where:
            options.append(f"--where={shlex.quote(where)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        run(
            ["docker", "exec", MYSQL_CONTAINER, "sh", "-lc", " ".join(options)],
            binary_stdout=stream,
        )
    if not path.is_file() or path.stat().st_size == 0:
        raise CleanupError(f"DB 백업 파일이 비어 있습니다: {path}")


def create_backups(operation: Path, selection: dict[str, Any]) -> dict[str, str]:
    backup = operation / "backup"
    print("전체 DB 백업 생성...")
    dump_to(backup / "visionflow-full.sql")
    for key in RESTORE_ORDER:
        table, primary_key, numeric = ID_FIELDS[key]
        where = f"{primary_key} IN ({sql_list(selection['ids'][key], numeric)})"
        print(f"대상 백업: {table}")
        dump_to(backup / f"target-{table}.sql", table, where)

    checksums: dict[str, str] = {}
    for path in sorted(backup.glob("*.sql")):
        checksums[path.name] = sha256_file(path)
    (backup / "backup-checksums.sha256").write_text(
        "".join(f"{digest}  {name}\n" for name, digest in checksums.items()),
        encoding="ascii",
    )
    return checksums


def verify_backups(operation: Path, expected: dict[str, str]) -> None:
    backup = operation / "backup"
    if not expected:
        raise CleanupError("백업 checksum 정보가 없습니다.")
    for name, digest in expected.items():
        path = backup / name
        if not path.is_file() or path.stat().st_size == 0:
            raise CleanupError(f"백업 파일이 없습니다: {path}")
        if sha256_file(path) != digest:
            raise CleanupError(f"백업 checksum이 다릅니다: {path}")


def move_to_quarantine(rows: list[dict[str, Any]]) -> None:
    moved: list[dict[str, Any]] = []
    try:
        for row in rows:
            source = Path(row["source_path"])
            target = Path(row["quarantine_path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, target)
            moved.append(row)
    except BaseException:
        for row in reversed(moved):
            source = Path(row["source_path"])
            target = Path(row["quarantine_path"])
            if target.exists() and not source.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target, source)
        raise


def move_to_source(rows: list[dict[str, Any]]) -> None:
    moved: list[dict[str, Any]] = []
    try:
        for row in rows:
            source = Path(row["source_path"])
            target = Path(row["quarantine_path"])
            if source.exists() and target.exists():
                raise CleanupError(f"원본과 격리 파일이 동시에 존재합니다: {source.name}")
            if target.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target, source)
                moved.append(row)
            elif not source.exists():
                raise CleanupError(f"원본과 격리 파일이 모두 없습니다: {source.name}")
    except BaseException:
        for row in reversed(moved):
            source = Path(row["source_path"])
            target = Path(row["quarantine_path"])
            if source.exists() and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(source, target)
        raise


def is_running(container: str) -> bool:
    completed = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", container],
        text=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    return completed.returncode == 0 and completed.stdout.strip() == "true"


def stop_services() -> list[str]:
    running = [name for name in SERVICE_CONTAINERS if is_running(name)]
    for name in running:
        print(f"서비스 중지: {name}")
        run(["docker", "stop", name])
    return running


def health_status(container: str, timeout_seconds: int = 180) -> str:
    deadline = time.time() + timeout_seconds
    latest = "unknown"
    while time.time() < deadline:
        completed = subprocess.run(
            [
                "docker",
                "inspect",
                "-f",
                "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
                container,
            ],
            text=True,
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode == 0:
            latest = completed.stdout.strip()
            if latest in {"healthy", "running"}:
                return latest
        time.sleep(2)
    return latest


def start_services(running: list[str]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for name in SERVICE_START_ORDER:
        if name not in running:
            continue
        print(f"서비스 시작: {name}")
        completed = subprocess.run(
            ["docker", "start", name],
            text=True,
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode != 0:
            statuses[name] = "START_FAILED"
            print(f"경고: {name} 시작 실패: {completed.stderr}", file=sys.stderr)
            continue
        statuses[name] = health_status(name)
        print(f"서비스 상태: {name}={statuses[name]}")
    return statuses


def assert_services_ready(statuses: dict[str, str], completed_stage: str) -> None:
    failed = {
        name: status
        for name, status in statuses.items()
        if status not in {"healthy", "running"}
    }
    if failed:
        raise CleanupError(
            f"{completed_stage} 단계는 끝났지만 서비스 복구를 확인하지 못했습니다: "
            + json.dumps(failed, ensure_ascii=False)
        )


def run_storage_audit(root: Path) -> int | None:
    script = root / "scripts/run-visionflow-storage-audit.bat"
    if not script.is_file():
        return None
    completed = subprocess.run(
        ["cmd.exe", "/d", "/c", str(script)],
        cwd=root,
        check=False,
    )
    return completed.returncode


def execute_delete(selection: dict[str, Any]) -> None:
    ids = selection["ids"]
    sql = " ".join(
        [
            "START TRANSACTION;",
            "DELETE FROM demo_scenario WHERE scenario_id IN "
            f"({sql_list(ids['demoScenarios'], False)});",
            "DELETE FROM incident WHERE id IN "
            f"({sql_list(ids['incidents'], True)});",
            "DELETE FROM ai_inference_event WHERE id IN "
            f"({sql_list(ids['events'], True)});",
            "DELETE FROM drone_telemetry_history WHERE id IN "
            f"({sql_list(ids['telemetry'], True)});",
            "DELETE FROM flight_session WHERE session_id IN "
            f"({sql_list(ids['flightSessions'], False)});",
            "COMMIT;",
        ]
    )
    mysql_query(sql)


def assert_deleted(root: Path, operation: Path, baseline: dict[str, int]) -> None:
    current = collect_selection(root, operation, require_expected=False)
    if any(current["counts"].values()):
        raise CleanupError(
            "삭제 후 대상 데이터가 남았습니다: "
            + json.dumps(current["counts"], ensure_ascii=False)
        )
    expected_remaining = {
        key: baseline[key] - EXPECTED_TARGET_COUNTS[key]
        for key in baseline
    }
    actual = total_counts()
    if actual != expected_remaining:
        raise CleanupError(
            "삭제 후 전체 집계가 예상과 다릅니다.\n"
            f"예상={json.dumps(expected_remaining, ensure_ascii=False)}\n"
            f"실제={json.dumps(actual, ensure_ascii=False)}"
        )


def plan_command(args: argparse.Namespace) -> int:
    if args.confirm != PLAN_TOKEN:
        raise CleanupError(f"계획 생성에는 --confirm {PLAN_TOKEN}이 필요합니다.")
    root = Path(args.root).resolve()
    operation = create_operation(root)
    selection = collect_selection(root, operation, require_expected=True)
    verify_snapshot_sources(selection["snapshotRows"])
    path = write_manifest(operation, selection["snapshotRows"])
    metadata = {
        "schemaVersion": OPERATION_SCHEMA_VERSION,
        "target": TARGET_NAME,
        "status": "PLAN_READY",
        "createdAt": now_utc(),
        "root": str(root),
        "rules": {
            "demoSourceDeviceId": DEMO_SOURCE_DEVICE_ID,
            "presentationSourceLike": PRESENTATION_SOURCE_LIKE,
        },
        "protectedSessionId": PROTECTED_SESSION_ID,
        "expectedCounts": EXPECTED_TARGET_COUNTS,
        "snapshotBytes": selection["snapshotBytes"],
        "selectionFingerprint": selection["fingerprint"],
        "foreignKeyDependencies": selection["foreignKeyDependencies"],
        "baselineTotals": total_counts(),
        "ids": selection["ids"],
        "manifest": str(path),
        "safety": {
            "readOnly": True,
            "databaseMutation": False,
            "filesMoved": False,
        },
    }
    write_json(operation_file(operation), metadata)
    print("VisionFlow presentation cleanup plan: READY")
    print(json.dumps(EXPECTED_TARGET_COUNTS, ensure_ascii=False, indent=2))
    print(f"snapshotBytes={selection['snapshotBytes']}")
    print(f"Operation: {operation}")
    return 0


def quarantine_command(args: argparse.Namespace) -> int:
    if not args.apply or args.confirm != QUARANTINE_TOKEN:
        raise CleanupError(
            f"격리에는 --apply --confirm {QUARANTINE_TOKEN}이 필요합니다."
        )
    root = Path(args.root).resolve()
    operation, metadata = load_operation(root, args.operation)
    if metadata.get("status") != "PLAN_READY":
        raise CleanupError(f"격리 가능한 상태가 아닙니다: {metadata.get('status')}")
    selection = ensure_current_matches(root, operation, metadata)
    rows = load_manifest(operation)
    verify_snapshot_sources(rows)

    running = stop_services()
    failure: BaseException | None = None
    try:
        selection = ensure_current_matches(root, operation, metadata)
        metadata["status"] = "BACKUP_IN_PROGRESS"
        write_json(operation_file(operation), metadata)
        checksums = create_backups(operation, selection)
        metadata["backupChecksums"] = checksums
        metadata["status"] = "BACKUP_COMPLETE"
        write_json(operation_file(operation), metadata)
        move_to_quarantine(rows)
        verify_quarantine(rows)
        metadata["status"] = "QUARANTINED"
        metadata["quarantinedAt"] = now_utc()
        metadata["safety"] = {
            "readOnly": False,
            "databaseMutation": False,
            "filesMoved": True,
        }
        write_json(operation_file(operation), metadata)
    except BaseException as error:
        failure = error
        metadata["status"] = "QUARANTINE_FAILED"
        metadata["failure"] = str(error)
        metadata["failedAt"] = now_utc()
        write_json(operation_file(operation), metadata)
        raise
    finally:
        metadata["serviceStatusAfterQuarantine"] = start_services(running)
        write_json(operation_file(operation), metadata)

    if failure is None:
        assert_services_ready(
            metadata["serviceStatusAfterQuarantine"], "스냅숏 격리"
        )
    print("VisionFlow presentation snapshots: QUARANTINED")
    print(f"Operation: {operation}")
    return 0


def delete_command(args: argparse.Namespace) -> int:
    if not args.apply or args.confirm != DELETE_TOKEN:
        raise CleanupError(
            f"삭제에는 --apply --confirm {DELETE_TOKEN}가 필요합니다."
        )
    root = Path(args.root).resolve()
    operation, metadata = load_operation(root, args.operation)
    if metadata.get("status") != "QUARANTINED":
        raise CleanupError(f"삭제 가능한 상태가 아닙니다: {metadata.get('status')}")
    rows = load_manifest(operation)
    verify_quarantine(rows)
    verify_backups(operation, metadata.get("backupChecksums", {}))
    selection = ensure_current_matches(root, operation, metadata)

    running = stop_services()
    failure: BaseException | None = None
    try:
        selection = ensure_current_matches(root, operation, metadata)
        metadata["status"] = "DB_DELETE_IN_PROGRESS"
        write_json(operation_file(operation), metadata)
        execute_delete(selection)
        assert_deleted(root, operation, metadata["baselineTotals"])
        metadata["status"] = "DB_DELETED"
        metadata["dbDeletedAt"] = now_utc()
        metadata["safety"] = {
            "readOnly": False,
            "databaseMutation": True,
            "filesMoved": True,
            "recoverable": True,
        }
        write_json(operation_file(operation), metadata)
    except BaseException as error:
        failure = error
        metadata["status"] = "DELETE_FAILED"
        metadata["failure"] = str(error)
        metadata["failedAt"] = now_utc()
        write_json(operation_file(operation), metadata)
        raise
    finally:
        metadata["serviceStatusAfterDelete"] = start_services(running)
        write_json(operation_file(operation), metadata)

    if failure is None:
        assert_services_ready(metadata["serviceStatusAfterDelete"], "DB 정리")
    metadata["storageAuditExitCode"] = run_storage_audit(root)
    write_json(operation_file(operation), metadata)
    print("VisionFlow presentation data cleanup: COMPLETE")
    print(f"Operation: {operation}")
    print(f"Quarantine retained: {operation / 'quarantine'}")
    return 0


def restore_command(args: argparse.Namespace) -> int:
    if not args.apply or args.confirm != RESTORE_TOKEN:
        raise CleanupError(
            f"복원에는 --apply --confirm {RESTORE_TOKEN}가 필요합니다."
        )
    root = Path(args.root).resolve()
    operation, metadata = load_operation(root, args.operation)
    status = metadata.get("status")
    if status not in {"QUARANTINED", "DB_DELETED", "DELETE_FAILED"}:
        raise CleanupError(f"복원 가능한 상태가 아닙니다: {status}")
    rows = load_manifest(operation)
    verify_backups(operation, metadata.get("backupChecksums", {}))
    verify_quarantine(rows)

    restore_database = status == "DB_DELETED"
    if status == "DELETE_FAILED":
        current = collect_selection(root, operation, require_expected=False)
        current_counts = current["counts"]
        if current_counts == EXPECTED_TARGET_COUNTS:
            if total_counts() != metadata.get("baselineTotals"):
                raise CleanupError(
                    "삭제 실패 후 대상은 남아 있지만 전체 집계가 기준선과 다릅니다. "
                    "전체 DB 백업을 이용한 수동 복구가 필요합니다."
                )
            restore_database = False
        elif not any(current_counts.values()):
            restore_database = True
        else:
            raise CleanupError(
                "부분 삭제 상태입니다. 자동 대상 복원 대신 전체 DB 백업을 이용한 "
                "수동 복구가 필요합니다: "
                + json.dumps(current_counts, ensure_ascii=False)
            )

    running = stop_services()
    try:
        if restore_database:
            for key in RESTORE_ORDER:
                table = ID_FIELDS[key][0]
                print(f"DB 복원: {table}")
                mysql_import(operation / "backup" / f"target-{table}.sql")
        move_to_source(rows)
        restored = collect_selection(root, operation, require_expected=True)
        verify_snapshot_sources(restored["snapshotRows"])
        if restored["fingerprint"] != metadata.get("selectionFingerprint"):
            raise CleanupError("복원 후 대상 ID fingerprint가 다릅니다.")
        if total_counts() != metadata.get("baselineTotals"):
            raise CleanupError("복원 후 전체 집계가 기준선과 다릅니다.")
        metadata["status"] = "RESTORED"
        metadata["restoredAt"] = now_utc()
        metadata["safety"] = {
            "readOnly": False,
            "databaseMutation": restore_database,
            "filesMoved": True,
            "restored": True,
        }
        write_json(operation_file(operation), metadata)
    finally:
        metadata["serviceStatusAfterRestore"] = start_services(running)
        write_json(operation_file(operation), metadata)

    assert_services_ready(metadata["serviceStatusAfterRestore"], "복원")
    metadata["storageAuditExitCodeAfterRestore"] = run_storage_audit(root)
    write_json(operation_file(operation), metadata)
    print("VisionFlow presentation data restore: COMPLETE")
    return 0


def reconcile_command(args: argparse.Namespace) -> int:
    if args.confirm != RECONCILE_TOKEN:
        raise CleanupError(
            f"실패 상태 조정에는 --confirm {RECONCILE_TOKEN}이 필요합니다."
        )
    root = Path(args.root).resolve()
    operation, metadata = load_operation(root, args.operation)
    status = metadata.get("status")
    if status not in {"DELETE_FAILED", "DB_DELETE_IN_PROGRESS"}:
        raise CleanupError(f"조정 가능한 상태가 아닙니다: {status}")

    rows = load_manifest(operation)
    verify_quarantine(rows)
    verify_backups(operation, metadata.get("backupChecksums", {}))
    assert_deleted(root, operation, metadata["baselineTotals"])

    metadata["status"] = "DB_DELETED"
    metadata["reconciledAt"] = now_utc()
    metadata["reconciledFromStatus"] = status
    metadata["failureResolved"] = metadata.pop("failure", None)
    metadata["safety"] = {
        "readOnly": False,
        "databaseMutation": True,
        "filesMoved": True,
        "recoverable": True,
        "reconciledAfterCommittedDelete": True,
    }
    metadata["storageAuditExitCode"] = run_storage_audit(root)
    write_json(operation_file(operation), metadata)
    print("VisionFlow presentation data cleanup: RECONCILED")
    print("DB 삭제 결과와 격리·백업 상태가 승인된 기준과 일치합니다.")
    print(f"Operation: {operation}")
    return 0


def status_command(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    operation, metadata = load_operation(root, args.operation)
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    print("Current totals:")
    print(json.dumps(total_counts(), ensure_ascii=False, indent=2))
    if metadata.get("status") not in {"DB_DELETED"}:
        current = collect_selection(root, operation, require_expected=False)
        print("Current target:")
        print(json.dumps(current["counts"], ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="VisionFlow 2차 프로젝트 발표·데모 데이터 안전 정리"
    )
    parser.add_argument("--root", default=str(default_root()))
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="읽기 전용 대상 계획 생성")
    plan.add_argument("--confirm", required=True)
    plan.set_defaults(func=plan_command)

    quarantine = subparsers.add_parser("quarantine", help="백업 후 스냅숏 격리")
    quarantine.add_argument("--operation", required=True)
    quarantine.add_argument("--apply", action="store_true")
    quarantine.add_argument("--confirm")
    quarantine.set_defaults(func=quarantine_command)

    delete = subparsers.add_parser("delete", help="격리 검증 후 DB 정리")
    delete.add_argument("--operation", required=True)
    delete.add_argument("--apply", action="store_true")
    delete.add_argument("--confirm")
    delete.set_defaults(func=delete_command)

    restore = subparsers.add_parser("restore", help="DB와 스냅숏 복원")
    restore.add_argument("--operation", required=True)
    restore.add_argument("--apply", action="store_true")
    restore.add_argument("--confirm")
    restore.set_defaults(func=restore_command)

    reconcile = subparsers.add_parser(
        "reconcile", help="커밋 후 사후 검증 실패 상태를 안전하게 확정"
    )
    reconcile.add_argument("--operation", required=True)
    reconcile.add_argument("--confirm")
    reconcile.set_defaults(func=reconcile_command)

    status = subparsers.add_parser("status", help="작업 상태 조회")
    status.add_argument("--operation", required=True)
    status.set_defaults(func=status_command)
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    if shutil.which("docker") is None:
        raise CleanupError("docker 명령을 찾을 수 없습니다.")
    return int(args.func(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("[FAIL] 사용자에 의해 중단되었습니다.", file=sys.stderr)
        raise SystemExit(130)
    except (CleanupError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        raise SystemExit(1)
