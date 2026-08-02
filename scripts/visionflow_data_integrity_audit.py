from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


MYSQL_CONTAINER = "visionflow-mysql"
FORBIDDEN_SQL = re.compile(
    r"\b(?:INSERT|UPDATE|DELETE|REPLACE|ALTER|DROP|CREATE|TRUNCATE|CALL|LOAD|GRANT|REVOKE|LOCK|UNLOCK)\b",
    re.IGNORECASE,
)


DATABASE_RULES: dict[str, str] = {
    "flight-session-multiple-active-per-drone": """
        SELECT COUNT(*) AS issue_count
        FROM (
            SELECT fs.drone_id
            FROM flight_session fs
            WHERE fs.status = 'ACTIVE'
            GROUP BY fs.drone_id
            HAVING COUNT(*) > 1
        ) duplicate_active_sessions
    """,
    "session-orphan-drone": """
        SELECT COUNT(*) AS issue_count
        FROM drone d
        LEFT JOIN flight_session fs ON fs.session_id = d.flight_session_id
        WHERE d.flight_session_id IS NOT NULL AND fs.session_id IS NULL
    """,
    "session-orphan-telemetry": """
        SELECT COUNT(*) AS issue_count
        FROM drone_telemetry_history h
        LEFT JOIN flight_session fs ON fs.session_id = h.flight_session_id
        WHERE h.flight_session_id IS NOT NULL AND fs.session_id IS NULL
    """,
    "session-orphan-ai-event": """
        SELECT COUNT(*) AS issue_count
        FROM ai_inference_event e
        LEFT JOIN flight_session fs ON fs.session_id = e.session_id
        WHERE e.session_id <> '' AND fs.session_id IS NULL
    """,
    "session-orphan-ai-alert": """
        SELECT COUNT(*) AS issue_count
        FROM ai_alert a
        LEFT JOIN flight_session fs ON fs.session_id = a.session_id
        WHERE a.session_id <> '' AND fs.session_id IS NULL
    """,
    "session-orphan-geofence-event": """
        SELECT COUNT(*) AS issue_count
        FROM drone_geofence_event g
        LEFT JOIN flight_session fs ON fs.session_id = g.flight_session_id
        WHERE g.flight_session_id IS NOT NULL AND fs.session_id IS NULL
    """,
    "session-orphan-incident": """
        SELECT COUNT(*) AS issue_count
        FROM incident i
        LEFT JOIN flight_session fs ON fs.session_id = i.session_id
        WHERE i.session_id IS NOT NULL AND fs.session_id IS NULL
    """,
    "session-orphan-demo": """
        SELECT COUNT(*) AS issue_count
        FROM demo_scenario d
        LEFT JOIN flight_session fs ON fs.session_id = d.flight_session_id
        WHERE fs.session_id IS NULL
    """,
    "session-orphan-work-order": """
        SELECT COUNT(*) AS issue_count
        FROM maintenance_work_order w
        LEFT JOIN flight_session fs ON fs.session_id = w.session_id
        WHERE w.session_id IS NOT NULL AND fs.session_id IS NULL
    """,
    "session-drone-mismatch-drone": """
        SELECT COUNT(*) AS issue_count
        FROM drone d
        JOIN flight_session fs ON fs.session_id = d.flight_session_id
        WHERE fs.drone_id <> d.id
    """,
    "session-drone-mismatch-telemetry": """
        SELECT COUNT(*) AS issue_count
        FROM drone_telemetry_history h
        JOIN flight_session fs ON fs.session_id = h.flight_session_id
        WHERE fs.drone_id <> h.drone_id
    """,
    "session-drone-mismatch-ai-event": """
        SELECT COUNT(*) AS issue_count
        FROM ai_inference_event e
        JOIN flight_session fs ON fs.session_id = e.session_id
        WHERE fs.drone_id <> e.drone_id
    """,
    "session-drone-mismatch-ai-alert": """
        SELECT COUNT(*) AS issue_count
        FROM ai_alert a
        JOIN flight_session fs ON fs.session_id = a.session_id
        WHERE fs.drone_id <> a.drone_id
    """,
    "session-drone-mismatch-geofence-event": """
        SELECT COUNT(*) AS issue_count
        FROM drone_geofence_event g
        JOIN flight_session fs ON fs.session_id = g.flight_session_id
        WHERE fs.drone_id <> g.drone_id
    """,
    "session-drone-mismatch-incident": """
        SELECT COUNT(*) AS issue_count
        FROM incident i
        JOIN flight_session fs ON fs.session_id = i.session_id
        WHERE fs.drone_id <> i.drone_id
    """,
    "session-drone-mismatch-demo": """
        SELECT COUNT(*) AS issue_count
        FROM demo_scenario d
        JOIN flight_session fs ON fs.session_id = d.flight_session_id
        WHERE fs.drone_id <> d.drone_id
    """,
    "session-drone-mismatch-work-order": """
        SELECT COUNT(*) AS issue_count
        FROM maintenance_work_order w
        JOIN flight_session fs ON fs.session_id = w.session_id
        WHERE fs.drone_id <> w.drone_id
    """,
    "session-drone-mismatch-quality": """
        SELECT COUNT(*) AS issue_count
        FROM flight_quality_assessment q
        JOIN flight_session fs ON fs.session_id = q.session_id
        WHERE fs.drone_id <> q.drone_id
    """,
    "drone-orphan-ai-event": """
        SELECT COUNT(*) AS issue_count
        FROM ai_inference_event e
        LEFT JOIN drone d ON d.id = e.drone_id
        WHERE d.id IS NULL
    """,
    "drone-orphan-ai-alert": """
        SELECT COUNT(*) AS issue_count
        FROM ai_alert a
        LEFT JOIN drone d ON d.id = a.drone_id
        WHERE d.id IS NULL
    """,
    "drone-orphan-geofence-event": """
        SELECT COUNT(*) AS issue_count
        FROM drone_geofence_event g
        LEFT JOIN drone d ON d.id = g.drone_id
        WHERE d.id IS NULL
    """,
    "drone-orphan-incident": """
        SELECT COUNT(*) AS issue_count
        FROM incident i
        LEFT JOIN drone d ON d.id = i.drone_id
        WHERE d.id IS NULL
    """,
    "drone-orphan-demo": """
        SELECT COUNT(*) AS issue_count
        FROM demo_scenario s
        LEFT JOIN drone d ON d.id = s.drone_id
        WHERE d.id IS NULL
    """,
    "ai-alert-event-correlation": """
        SELECT COUNT(*) AS issue_count
        FROM ai_alert a
        JOIN ai_inference_event e ON e.id = a.event_id
        WHERE a.drone_id <> e.drone_id OR NOT (a.session_id <=> e.session_id)
    """,
    "incident-source-orphan-ai-alert": """
        SELECT COUNT(*) AS issue_count
        FROM incident i
        LEFT JOIN ai_alert a ON a.id = i.source_id
        WHERE i.source_type = 'AI_ALERT' AND a.id IS NULL
    """,
    "incident-source-orphan-geofence": """
        SELECT COUNT(*) AS issue_count
        FROM incident i
        LEFT JOIN drone_geofence_event g ON g.id = i.source_id
        WHERE i.source_type = 'GEOFENCE' AND g.id IS NULL
    """,
    "incident-source-orphan-flight-quality": """
        SELECT COUNT(*) AS issue_count
        FROM incident i
        LEFT JOIN drone d ON d.id = i.source_id
        WHERE i.source_type = 'FLIGHT_QUALITY' AND d.id IS NULL
    """,
    "incident-source-orphan-flight-gate": """
        SELECT COUNT(*) AS issue_count
        FROM incident i
        LEFT JOIN drone d ON d.id = i.source_id
        WHERE i.source_type = 'FLIGHT_GATE' AND d.id IS NULL
    """,
    "incident-source-mismatch-ai-alert": """
        SELECT COUNT(*) AS issue_count
        FROM incident i
        JOIN ai_alert a ON a.id = i.source_id
        WHERE i.source_type = 'AI_ALERT'
          AND (i.drone_id <> a.drone_id OR NOT (i.session_id <=> a.session_id))
    """,
    "incident-source-mismatch-geofence": """
        SELECT COUNT(*) AS issue_count
        FROM incident i
        JOIN drone_geofence_event g ON g.id = i.source_id
        WHERE i.source_type = 'GEOFENCE'
          AND (i.drone_id <> g.drone_id OR NOT (i.session_id <=> g.flight_session_id))
    """,
    "incident-source-mismatch-flight-quality": """
        SELECT COUNT(*) AS issue_count
        FROM incident i
        WHERE i.source_type = 'FLIGHT_QUALITY' AND i.source_id <> i.drone_id
    """,
    "incident-source-mismatch-flight-gate": """
        SELECT COUNT(*) AS issue_count
        FROM incident i
        WHERE i.source_type = 'FLIGHT_GATE' AND i.source_id <> i.drone_id
    """,
    "demo-orphan-ai-event": """
        SELECT COUNT(*) AS issue_count
        FROM demo_scenario s
        LEFT JOIN ai_inference_event e ON e.id = s.ai_event_id
        WHERE s.ai_event_id IS NOT NULL AND e.id IS NULL
    """,
    "demo-orphan-ai-alert": """
        SELECT COUNT(*) AS issue_count
        FROM demo_scenario s
        LEFT JOIN ai_alert a ON a.id = s.ai_alert_id
        WHERE s.ai_alert_id IS NOT NULL AND a.id IS NULL
    """,
    "demo-orphan-incident": """
        SELECT COUNT(*) AS issue_count
        FROM demo_scenario s
        LEFT JOIN incident i ON i.id = s.incident_id
        WHERE s.incident_id IS NOT NULL AND i.id IS NULL
    """,
    "demo-chain-mismatch-ai-event": """
        SELECT COUNT(*) AS issue_count
        FROM demo_scenario s
        JOIN ai_inference_event e ON e.id = s.ai_event_id
        WHERE e.drone_id <> s.drone_id OR e.session_id <> s.flight_session_id
    """,
    "demo-chain-mismatch-ai-alert": """
        SELECT COUNT(*) AS issue_count
        FROM demo_scenario s
        JOIN ai_alert a ON a.id = s.ai_alert_id
        WHERE a.drone_id <> s.drone_id OR a.session_id <> s.flight_session_id
    """,
    "demo-chain-mismatch-incident": """
        SELECT COUNT(*) AS issue_count
        FROM demo_scenario s
        JOIN incident i ON i.id = s.incident_id
        WHERE i.drone_id <> s.drone_id OR NOT (i.session_id <=> s.flight_session_id)
    """,
    "work-order-assessment-correlation": """
        SELECT COUNT(*) AS issue_count
        FROM maintenance_work_order w
        JOIN flight_quality_assessment q ON q.id = w.source_assessment_id
        WHERE q.drone_id <> w.drone_id OR NOT (q.session_id <=> w.session_id)
    """,
    "snapshot-metadata-partial": """
        SELECT COUNT(*) AS issue_count
        FROM ai_inference_event e
        WHERE (e.snapshot_file_name IS NULL AND (
                  e.snapshot_content_type IS NOT NULL
                  OR e.snapshot_size_bytes IS NOT NULL
                  OR e.snapshot_created_at IS NOT NULL
              ))
           OR (e.snapshot_file_name IS NOT NULL AND (
                  e.snapshot_content_type IS NULL
                  OR e.snapshot_size_bytes IS NULL
                  OR e.snapshot_created_at IS NULL
              ))
    """,
}


EXPECTED_TABLES = {
    "ai_alert",
    "ai_inference_event",
    "demo_scenario",
    "drone",
    "drone_geofence_event",
    "drone_telemetry_history",
    "flight_quality_assessment",
    "flight_session",
    "incident",
    "maintenance_work_order",
}


class AuditError(RuntimeError):
    pass


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 최상위 값이 객체가 아닙니다: {path}")
    return value


def run_command(arguments: list[str], *, timeout: int = 120) -> str:
    completed = subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise AuditError(f"명령 실패(exit {completed.returncode}): {detail}")
    return completed.stdout.strip()


def require_running_container(container: str) -> None:
    state = run_command(
        ["docker", "inspect", "--format", "{{.State.Running}}", container],
        timeout=30,
    )
    if state.lower() != "true":
        raise AuditError(f"실행 중인 MySQL 컨테이너가 아닙니다: {container}")


def validate_select(sql: str) -> str:
    normalized = " ".join(sql.split()).strip().rstrip(";")
    if not normalized.upper().startswith("SELECT "):
        raise AuditError("SELECT 이외 SQL은 허용되지 않습니다.")
    if FORBIDDEN_SQL.search(normalized) or ";" in normalized:
        raise AuditError("변경 가능 SQL 또는 복수 statement는 허용되지 않습니다.")
    return normalized


def mysql_query(container: str, sql: str) -> list[list[str]]:
    select_sql = validate_select(sql)
    wrapped = (
        "SET SESSION TRANSACTION READ ONLY; "
        "START TRANSACTION READ ONLY; "
        f"{select_sql}; COMMIT;"
    )
    output = run_command(
        [
            "docker",
            "exec",
            "--env",
            f"VISIONFLOW_AUDIT_SQL={wrapped}",
            container,
            "sh",
            "-c",
            'MYSQL_PWD="$MYSQL_PASSWORD" mysql --user="$MYSQL_USER" '
            '--batch --raw --skip-column-names "$MYSQL_DATABASE" '
            '--execute "$VISIONFLOW_AUDIT_SQL"',
        ]
    )
    return [line.split("\t") for line in output.splitlines() if line]


def build_rule_query() -> str:
    parts = []
    for key, sql in DATABASE_RULES.items():
        validated = validate_select(sql)
        escaped_key = key.replace("'", "''")
        parts.append(
            f"SELECT '{escaped_key}' AS rule_key, q.issue_count "
            f"FROM ({validated}) q"
        )
    return " UNION ALL ".join(parts)


def collect_database(
    query: Callable[[str], list[list[str]]],
) -> tuple[dict[str, Any], dict[str, int], list[dict[str, Any]]]:
    metadata_rows = query("SELECT DATABASE(), VERSION()")
    if not metadata_rows or len(metadata_rows[0]) < 2:
        raise AuditError("MySQL database metadata를 읽지 못했습니다.")
    database_name, version = metadata_rows[0][:2]

    table_rows = query(
        "SELECT TABLE_NAME FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() ORDER BY TABLE_NAME"
    )
    tables = {row[0] for row in table_rows if row}
    missing_tables = sorted(EXPECTED_TABLES - tables)

    result_rows = query(build_rule_query())
    counts: dict[str, int] = {}
    for row in result_rows:
        if len(row) != 2 or row[0] in counts:
            raise AuditError("데이터 정합성 rule 결과 형식이 올바르지 않습니다.")
        counts[row[0]] = int(row[1])
    missing_rules = sorted(set(DATABASE_RULES) - set(counts))
    unexpected_rules = sorted(set(counts) - set(DATABASE_RULES))
    if missing_rules or unexpected_rules:
        raise AuditError(
            f"rule 결과 불일치: missing={missing_rules}, unexpected={unexpected_rules}"
        )

    snapshot_rows = query(
        "SELECT id, snapshot_file_name, snapshot_size_bytes "
        "FROM ai_inference_event "
        "WHERE snapshot_file_name IS NOT NULL AND snapshot_file_name <> '' "
        "ORDER BY id"
    )
    references = []
    for row in snapshot_rows:
        if len(row) != 3:
            raise AuditError("snapshot reference 결과 형식이 올바르지 않습니다.")
        references.append(
            {
                "eventId": int(row[0]),
                "fileName": row[1],
                "expectedSizeBytes": int(row[2]) if row[2] not in {"", "NULL"} else None,
            }
        )
    return (
        {
            "available": True,
            "databaseName": database_name,
            "version": version,
            "observedTableCount": len(tables),
            "requiredTables": sorted(EXPECTED_TABLES),
            "missingRequiredTables": missing_tables,
        },
        counts,
        references,
    )


def hash_prefix(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def inspect_snapshots(
    root: Path,
    references: list[dict[str, Any]],
    snapshot_relative: str,
) -> tuple[dict[str, Any], dict[str, int]]:
    directory = root / Path(snapshot_relative)
    actual = {
        path.name: path
        for path in directory.glob("*")
        if path.is_file() and not path.is_symlink()
    } if directory.is_dir() else {}
    referenced: set[str] = set()
    name_events: dict[str, list[int]] = {}
    invalid = []
    missing = []
    size_mismatch = []

    for reference in references:
        name = str(reference["fileName"])
        event_id = int(reference["eventId"])
        if (
            not name
            or name in {".", ".."}
            or Path(name).name != name
            or "/" in name
            or "\\" in name
        ):
            invalid.append({"eventId": event_id, "fileNameSha256Prefix": hash_prefix(name)})
            continue
        referenced.add(name)
        name_events.setdefault(name, []).append(event_id)
        path = actual.get(name)
        if path is None:
            missing.append({"eventId": event_id, "fileNameSha256Prefix": hash_prefix(name)})
            continue
        expected_size = reference.get("expectedSizeBytes")
        if expected_size is not None and path.stat().st_size != expected_size:
            size_mismatch.append(
                {
                    "eventId": event_id,
                    "fileNameSha256Prefix": hash_prefix(name),
                    "expectedSizeBytes": expected_size,
                    "actualSizeBytes": path.stat().st_size,
                }
            )

    duplicate = [name for name, event_ids in name_events.items() if len(event_ids) > 1]
    unreferenced = sorted(set(actual) - referenced)
    counts = {
        "snapshot-invalid-reference": len(invalid),
        "snapshot-missing-file": len(missing),
        "snapshot-size-mismatch": len(size_mismatch),
        "snapshot-duplicate-reference": len(duplicate),
        "snapshot-unreferenced-file": len(unreferenced),
    }
    details = {
        "directory": snapshot_relative,
        "databaseReferenceCount": len(references),
        "actualFileCount": len(actual),
        "invalidReferences": invalid[:20],
        "missingFiles": missing[:20],
        "sizeMismatches": size_mismatch[:20],
        "duplicateReferenceHashes": [hash_prefix(name) for name in duplicate[:20]],
        "unreferencedFileHashes": [hash_prefix(name) for name in unreferenced[:20]],
        "fileNamesCollected": False,
    }
    return details, counts


def evaluate(
    policy: dict[str, Any],
    database: dict[str, Any],
    counts: dict[str, int],
    snapshots: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    policy_rules = policy.get("rules")
    if not isinstance(policy_rules, list):
        raise ValueError("policy rules 값이 배열이 아닙니다.")
    expected = {
        str(row.get("key")): row
        for row in policy_rules
        if isinstance(row, dict) and row.get("key")
    }
    actual_keys = set(counts)
    if actual_keys != set(expected):
        raise ValueError(
            "policy rule 구성이 다릅니다: "
            f"missing={sorted(set(expected) - actual_keys)}, "
            f"unexpected={sorted(actual_keys - set(expected))}"
        )

    rows = []
    for key in sorted(expected):
        rule = expected[key]
        maximum = int(rule.get("maxFindings", 0))
        severity = str(rule.get("severity", "CRITICAL")).upper()
        if severity not in {"ADVISORY", "CRITICAL"}:
            raise ValueError(f"허용되지 않은 severity: {key}={severity}")
        findings = counts[key]
        rows.append(
            {
                "key": key,
                "category": str(rule.get("category", "unspecified")),
                "severity": severity,
                "maxFindings": maximum,
                "findings": findings,
                "status": "PASS" if findings <= maximum else severity,
            }
        )

    if database["missingRequiredTables"]:
        rows.append(
            {
                "key": "schema-required-tables",
                "category": "schema",
                "severity": "CRITICAL",
                "maxFindings": 0,
                "findings": len(database["missingRequiredTables"]),
                "status": "CRITICAL",
            }
        )
    else:
        rows.append(
            {
                "key": "schema-required-tables",
                "category": "schema",
                "severity": "CRITICAL",
                "maxFindings": 0,
                "findings": 0,
                "status": "PASS",
            }
        )

    statuses = {row["status"] for row in rows}
    if "CRITICAL" in statuses:
        status = "DATA_INTEGRITY_BLOCKED"
    elif "ADVISORY" in statuses:
        status = "DATA_INTEGRITY_ADVISORY"
    else:
        status = "DATA_INTEGRITY_HEALTHY"
    return status, rows


def render_markdown(report: dict[str, Any]) -> str:
    rows = [
        "| 상태 | 규칙 | 범주 | 탐지 | 허용 |",
        "| --- | --- | --- | ---: | ---: |",
    ]
    for item in report["rules"]:
        rows.append(
            f"| {item['status']} | `{item['key']}` | {item['category']} | "
            f"{item['findings']} | {item['maxFindings']} |"
        )
    return (
        "# VisionFlow 데이터 정합성 감사\n\n"
        f"- 생성: `{report['generatedAt']}`\n"
        f"- 상태: **{report['status']}**\n"
        f"- DB 규칙: {report['summary']['databaseRules']}\n"
        f"- 전체 탐지: {report['summary']['findings']}\n\n"
        "## 규칙별 결과\n\n"
        + "\n".join(rows)
        + "\n\n> MySQL READ ONLY transaction과 파일 메타데이터 조회만 사용합니다.\n"
    )


def render_html(report: dict[str, Any]) -> str:
    rows = "".join(
        "<tr><td>{}</td><td><code>{}</code></td><td>{}</td><td>{}</td></tr>".format(
            html.escape(item["status"]),
            html.escape(item["key"]),
            html.escape(item["category"]),
            item["findings"],
        )
        for item in report["rules"]
    )
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VisionFlow Data Integrity Audit</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;background:#f4f7fb;color:#172033;margin:0}}main{{max-width:1200px;margin:auto;padding:28px}}section{{background:white;border:1px solid #dbe3ef;border-radius:14px;padding:20px;margin-top:18px}}.hero{{background:#071126;color:white}}table{{border-collapse:collapse;width:100%}}th,td{{border-bottom:1px solid #e5eaf2;padding:8px;text-align:left}}th{{background:#f8fafc}}</style></head>
<body><main><section class="hero"><h1>VisionFlow 데이터 정합성 감사</h1><strong>{html.escape(report['status'])}</strong><p>{html.escape(report['generatedAt'])}</p></section>
<section><table><thead><tr><th>상태</th><th>규칙</th><th>범주</th><th>탐지</th></tr></thead><tbody>{rows}</tbody></table></section></main></body></html>"""


def write_reports(root: Path, output: Path | None, report: dict[str, Any]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("audit-%Y%m%dT%H%M%SZ")
    directory = output if output is not None else root / "artifacts/data-integrity-audit" / stamp
    if not directory.is_absolute():
        directory = root / directory
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "visionflow-data-integrity-audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (directory / "visionflow-data-integrity-audit.md").write_text(
        render_markdown(report), encoding="utf-8"
    )
    (directory / "visionflow-data-integrity-audit.html").write_text(
        render_html(report), encoding="utf-8"
    )
    return directory


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="VisionFlow MySQL·snapshot 읽기 전용 데이터 정합성 감사"
    )
    parser.add_argument("--root", type=Path, default=script_dir.parent)
    parser.add_argument("--container", default=MYSQL_CONTAINER)
    parser.add_argument(
        "--policy",
        type=Path,
        default=script_dir / "visionflow_data_integrity_policy.json",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    try:
        policy = read_object(args.policy.resolve())
        require_running_container(args.container)
        database, database_counts, references = collect_database(
            lambda sql: mysql_query(args.container, sql)
        )
        snapshot_relative = str(
            policy.get("snapshotDirectory", "artifacts/backend-data/ai-snapshots")
        )
        snapshots, snapshot_counts = inspect_snapshots(
            root, references, snapshot_relative
        )
        all_counts = {**database_counts, **snapshot_counts}
        status, rules = evaluate(policy, database, all_counts, snapshots)
        now = datetime.now(timezone.utc)
        report = {
            "schemaVersion": 1,
            "project": "visionflow",
            "scope": "RUNTIME_DATA_INTEGRITY",
            "generatedAt": now.isoformat(),
            "status": status,
            "readOnly": True,
            "summary": {
                "databaseRules": len(DATABASE_RULES),
                "snapshotRules": len(snapshot_counts),
                "findings": sum(row["findings"] for row in rules),
                "criticalRules": sum(row["status"] == "CRITICAL" for row in rules),
                "advisoryRules": sum(row["status"] == "ADVISORY" for row in rules),
            },
            "database": database,
            "snapshots": snapshots,
            "rules": rules,
            "safety": {
                "databaseMutation": False,
                "transactionMode": "READ ONLY",
                "containerMutation": False,
                "serviceRestart": False,
                "credentialValueCollection": False,
                "snapshotFileContentRead": False,
                "fileNamesCollected": False,
                "writesOnlyReports": True,
            },
        }
        output_dir = write_reports(root, args.output, report)
    except (AuditError, OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        print(f"VisionFlow data integrity audit: ERROR\n[FAIL] {error}", file=sys.stderr)
        return 2

    print(f"VisionFlow data integrity audit: {report['status']}")
    print(
        f"Rules: Database={report['summary']['databaseRules']}, "
        f"Snapshots={report['summary']['snapshotRules']}, "
        f"Findings={report['summary']['findings']}"
    )
    for row in report["rules"]:
        if row["status"] != "PASS":
            print(
                f"[{row['status']}] {row['key']}: "
                f"{row['findings']} findings (allowed {row['maxFindings']})"
            )
    print(f"JSON report: {output_dir / 'visionflow-data-integrity-audit.json'}")
    print(f"HTML report: {output_dir / 'visionflow-data-integrity-audit.html'}")
    print(f"Markdown report: {output_dir / 'visionflow-data-integrity-audit.md'}")
    print("Safety: MySQL READ ONLY; reports only; no credential or snapshot content access")
    if status == "DATA_INTEGRITY_BLOCKED":
        return 1
    if status == "DATA_INTEGRITY_ADVISORY" and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
