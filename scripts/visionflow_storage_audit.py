"""Read-only storage audit for VisionFlow MySQL and persistent artifacts."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import shutil
import subprocess
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
SCAN_DIRECTORIES = {
    "backend-data": Path("artifacts/backend-data"),
    "ai-output": Path("artifacts/ai-output"),
    "backups": Path("backups"),
    "acceptance-reports": Path("artifacts/visionflow-acceptance"),
    "ai-benchmarks": Path("artifacts/ai-benchmark"),
    "model-evaluations": Path("artifacts/model-evaluation"),
}
REPORT_CATEGORIES = {
    "acceptance-reports",
    "ai-benchmarks",
    "model-evaluations",
}


class AuditError(RuntimeError):
    """Raised when a full storage audit cannot be completed."""


def run_command(arguments: list[str], *, cwd: Path) -> str:
    result = subprocess.run(
        arguments,
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise AuditError(
            f"명령 실행 실패(exit {result.returncode}): {' '.join(arguments[:4])}\n{detail}"
        )
    return result.stdout.strip()


def compose_arguments(root: Path, environment_file: Path) -> list[str]:
    compose_file = root / "compose.yaml"
    if not compose_file.is_file():
        raise AuditError(f"Compose 파일을 찾을 수 없습니다: {compose_file}")
    if not environment_file.is_file():
        raise AuditError(f"환경 파일을 찾을 수 없습니다: {environment_file}")
    return [
        "docker",
        "compose",
        "--env-file",
        str(environment_file),
        "-f",
        str(compose_file),
    ]


def mysql_container(compose: list[str], root: Path) -> str:
    container_id = run_command([*compose, "ps", "-q", "mysql"], cwd=root)
    if not container_id:
        print("[START] MySQL service for storage audit")
        run_command([*compose, "up", "-d", "--wait", "mysql"], cwd=root)
        container_id = run_command([*compose, "ps", "-q", "mysql"], cwd=root)
    if not container_id:
        raise AuditError("MySQL 컨테이너 ID를 확인할 수 없습니다.")
    return container_id.splitlines()[0].strip()


def mysql_query(container_id: str, root: Path, sql: str) -> list[list[str]]:
    output = run_command(
        [
            "docker",
            "exec",
            "--env",
            f"VISIONFLOW_AUDIT_SQL={sql}",
            container_id,
            "sh",
            "-c",
            'MYSQL_PWD="$MYSQL_PASSWORD" mysql --user="$MYSQL_USER" '
            '--batch --raw --skip-column-names "$MYSQL_DATABASE" '
            '--execute "$VISIONFLOW_AUDIT_SQL"',
        ],
        cwd=root,
    )
    if not output:
        return []
    return [line.split("\t") for line in output.splitlines()]


def collect_database_audit(container_id: str, root: Path) -> dict[str, Any]:
    database_rows = mysql_query(
        container_id,
        root,
        "SELECT DATABASE(), VERSION();",
    )
    if not database_rows or len(database_rows[0]) < 2:
        raise AuditError(
            "MySQL 데이터베이스 이름과 버전을 조회하지 못했습니다."
        )
    database_name, version = database_rows[0][:2]
    if not re.fullmatch(r"[A-Za-z0-9_]+", database_name):
        raise AuditError(f"안전하지 않은 데이터베이스 이름: {database_name!r}")

    table_rows = mysql_query(
        container_id,
        root,
        "SELECT TABLE_NAME, COALESCE(TABLE_ROWS, 0), COALESCE(DATA_LENGTH, 0), "
        "COALESCE(INDEX_LENGTH, 0) FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() ORDER BY DATA_LENGTH + INDEX_LENGTH DESC;",
    )
    tables = []
    for row in table_rows:
        if len(row) < 4:
            continue
        tables.append(
            {
                "tableName": row[0],
                "estimatedRows": int(row[1]),
                "dataBytes": int(row[2]),
                "indexBytes": int(row[3]),
                "totalBytes": int(row[2]) + int(row[3]),
            }
        )

    snapshot_column = mysql_query(
        container_id,
        root,
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ai_inference_event' "
        "AND COLUMN_NAME = 'snapshot_file_name';",
    )
    snapshot_references = []
    snapshot_metadata_available = bool(
        snapshot_column and snapshot_column[0][0] == "1"
    )
    if snapshot_metadata_available:
        reference_rows = mysql_query(
            container_id,
            root,
            "SELECT id, COALESCE(snapshot_file_name, ''), "
            "COALESCE(snapshot_size_bytes, '') FROM ai_inference_event "
            "WHERE snapshot_file_name IS NOT NULL AND snapshot_file_name <> '' "
            "ORDER BY id;",
        )
        for row in reference_rows:
            if len(row) < 3:
                continue
            snapshot_references.append(
                {
                    "eventId": int(row[0]),
                    "fileName": row[1],
                    "expectedSizeBytes": int(row[2]) if row[2] else None,
                }
            )

    return {
        "available": True,
        "databaseName": database_name,
        "version": version,
        "tableCount": len(tables),
        "totalBytes": sum(table["totalBytes"] for table in tables),
        "tables": tables,
        "snapshotMetadataAvailable": snapshot_metadata_available,
        "snapshotReferences": snapshot_references,
    }


def utc_iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def scan_files(root: Path, now: datetime) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    for category, relative_directory in SCAN_DIRECTORIES.items():
        directory = root / relative_directory
        if not directory.exists():
            continue
        if not directory.is_dir():
            warnings.append(f"스캔 경로가 디렉터리가 아닙니다: {relative_directory}")
            continue
        for path in directory.rglob("*"):
            if path.is_symlink():
                warnings.append(f"심볼릭 링크를 제외했습니다: {path.relative_to(root)}")
                continue
            if not path.is_file():
                continue
            stat = path.stat()
            modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
            records.append(
                {
                    "category": category,
                    "path": path.relative_to(root).as_posix(),
                    "fileName": path.name,
                    "extension": path.suffix.lower() or "<none>",
                    "sizeBytes": stat.st_size,
                    "modifiedAt": modified.isoformat(),
                    "ageDays": max(0.0, (now - modified).total_seconds() / 86400.0),
                }
            )
    records.sort(key=lambda item: (item["category"], item["path"]))
    return records, warnings


def summarize_categories(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["category"]].append(record)
    summaries = []
    for category in SCAN_DIRECTORIES:
        category_records = grouped.get(category, [])
        summaries.append(
            {
                "category": category,
                "directory": SCAN_DIRECTORIES[category].as_posix(),
                "fileCount": len(category_records),
                "totalBytes": sum(record["sizeBytes"] for record in category_records),
                "oldestModifiedAt": min(
                    (record["modifiedAt"] for record in category_records),
                    default=None,
                ),
                "newestModifiedAt": max(
                    (record["modifiedAt"] for record in category_records),
                    default=None,
                ),
            }
        )
    return summaries


def reconcile_snapshots(
    root: Path,
    references: list[dict[str, Any]],
) -> dict[str, Any]:
    snapshot_directory = root / "artifacts/backend-data/ai-snapshots"
    actual = {
        path.name: path
        for path in snapshot_directory.glob("*")
        if path.is_file() and not path.is_symlink()
    } if snapshot_directory.is_dir() else {}
    referenced_names: set[str] = set()
    invalid_references = []
    missing_files = []
    size_mismatches = []
    duplicate_names: dict[str, list[int]] = defaultdict(list)

    for reference in references:
        file_name = str(reference["fileName"])
        event_id = int(reference["eventId"])
        if (
            Path(file_name).name != file_name
            or "/" in file_name
            or "\\" in file_name
            or file_name in {"", ".", ".."}
        ):
            invalid_references.append({"eventId": event_id, "fileName": file_name})
            continue
        referenced_names.add(file_name)
        duplicate_names[file_name].append(event_id)
        path = actual.get(file_name)
        if path is None:
            missing_files.append({"eventId": event_id, "fileName": file_name})
            continue
        expected_size = reference.get("expectedSizeBytes")
        if expected_size is not None and path.stat().st_size != expected_size:
            size_mismatches.append(
                {
                    "eventId": event_id,
                    "fileName": file_name,
                    "expectedSizeBytes": expected_size,
                    "actualSizeBytes": path.stat().st_size,
                }
            )

    duplicates = [
        {"fileName": name, "eventIds": event_ids}
        for name, event_ids in duplicate_names.items()
        if len(event_ids) > 1
    ]
    unreferenced = [
        {
            "fileName": name,
            "path": path.relative_to(root).as_posix(),
            "sizeBytes": path.stat().st_size,
            "modifiedAt": utc_iso(path.stat().st_mtime),
        }
        for name, path in sorted(actual.items())
        if name not in referenced_names
    ]
    return {
        "snapshotDirectory": snapshot_directory.relative_to(root).as_posix(),
        "databaseReferenceCount": len(references),
        "actualFileCount": len(actual),
        "missingFiles": missing_files,
        "unreferencedFiles": unreferenced,
        "sizeMismatches": size_mismatches,
        "invalidReferences": invalid_references,
        "duplicateFileNames": duplicates,
    }


def retention_candidates(
    records: list[dict[str, Any]],
    *,
    ai_output_days: int,
    backup_days: int,
    report_days: int,
    minimum_backups: int,
) -> list[dict[str, Any]]:
    backups = sorted(
        (
            record
            for record in records
            if record["category"] == "backups" and record["extension"] == ".zip"
        ),
        key=lambda record: record["modifiedAt"],
        reverse=True,
    )
    protected_backup_paths = {
        record["path"] for record in backups[: max(0, minimum_backups)]
    }
    candidates = []
    for record in records:
        reason = None
        category = record["category"]
        if category == "ai-output" and record["ageDays"] > ai_output_days:
            reason = f"AI 출력 보존기간 {ai_output_days}일 초과"
        elif (
            category == "backups"
            and record["extension"] == ".zip"
            and record["path"] not in protected_backup_paths
            and record["ageDays"] > backup_days
        ):
            reason = (
                f"백업 보존기간 {backup_days}일 초과 및 "
                f"최신 {minimum_backups}개 외"
            )
        elif category in REPORT_CATEGORIES and record["ageDays"] > report_days:
            reason = f"자동 보고서 보존기간 {report_days}일 초과"
        if reason:
            candidates.append(
                {
                    "category": category,
                    "path": record["path"],
                    "sizeBytes": record["sizeBytes"],
                    "ageDays": round(record["ageDays"], 2),
                    "reason": reason,
                }
            )
    return sorted(candidates, key=lambda item: (-item["sizeBytes"], item["path"]))


def determine_status(
    disk_free_percent: float,
    managed_bytes: int,
    snapshots: dict[str, Any] | None,
    *,
    warning_free_percent: float,
    critical_free_percent: float,
    warning_managed_bytes: int,
) -> tuple[str, list[str]]:
    warnings = []
    critical = []
    if disk_free_percent < critical_free_percent:
        critical.append(f"디스크 여유 공간이 {disk_free_percent:.1f}%입니다.")
    elif disk_free_percent < warning_free_percent:
        warnings.append(f"디스크 여유 공간이 {disk_free_percent:.1f}%입니다.")
    if managed_bytes >= warning_managed_bytes:
        warnings.append(f"관리 대상 파일이 {managed_bytes}바이트입니다.")
    if snapshots is not None:
        if snapshots["missingFiles"]:
            critical.append(
                f"DB가 참조하지만 없는 스냅샷 {len(snapshots['missingFiles'])}개"
            )
        if snapshots["invalidReferences"]:
            critical.append(
                "안전하지 않은 스냅샷 참조 "
                f"{len(snapshots['invalidReferences'])}개"
            )
        if snapshots["sizeMismatches"]:
            warnings.append(f"크기가 다른 스냅샷 {len(snapshots['sizeMismatches'])}개")
        if snapshots["unreferencedFiles"]:
            warnings.append(
                "DB가 참조하지 않는 스냅샷 "
                f"{len(snapshots['unreferencedFiles'])}개"
            )
        if snapshots["duplicateFileNames"]:
            warnings.append(f"중복 스냅샷 참조 {len(snapshots['duplicateFileNames'])}개")
    if critical:
        return "CRITICAL", [*critical, *warnings]
    if warnings:
        return "WARNING", warnings
    return "HEALTHY", []


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"


def render_html(report: dict[str, Any]) -> str:
    category_rows = "".join(
        "<tr>"
        f"<td>{html.escape(row['category'])}</td>"
        f"<td>{row['fileCount']}</td>"
        f"<td>{html.escape(format_bytes(row['totalBytes']))}</td>"
        "</tr>"
        for row in report["filesystem"]["categories"]
    )
    table_rows = "".join(
        "<tr>"
        f"<td>{html.escape(row['tableName'])}</td>"
        f"<td>{row['estimatedRows']}</td>"
        f"<td>{html.escape(format_bytes(row['totalBytes']))}</td>"
        "</tr>"
        for row in report["database"].get("tables", [])
    )
    issue_items = "".join(
        f"<li>{html.escape(issue)}</li>" for issue in report["issues"]
    ) or "<li>감지된 저장공간 문제가 없습니다.</li>"
    candidate_rows = "".join(
        "<tr>"
        f"<td>{html.escape(row['category'])}</td>"
        f"<td>{html.escape(row['path'])}</td>"
        f"<td>{html.escape(format_bytes(row['sizeBytes']))}</td>"
        f"<td>{html.escape(row['reason'])}</td>"
        "</tr>"
        for row in report["retention"]["candidates"][:200]
    )
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>VisionFlow Storage Audit</title>
<style>
body{{font-family:Arial,sans-serif;margin:32px;color:#0f172a;background:#f8fafc}}
.card{{background:white;border:1px solid #cbd5e1;border-radius:12px;
padding:20px;margin:16px 0}}
table{{border-collapse:collapse;width:100%}}
th,td{{border-bottom:1px solid #e2e8f0;padding:8px;text-align:left}}
.status{{font-size:24px;font-weight:700}}
code{{background:#e2e8f0;padding:2px 6px;border-radius:4px}}
</style></head><body>
<h1>VisionFlow 저장공간 감사</h1>
<div class="card"><div class="status">상태: {html.escape(report['status'])}</div>
<p>생성: {html.escape(report['generatedAt'])}</p><ul>{issue_items}</ul></div>
<div class="card"><h2>디스크</h2><p>여유: {report['disk']['freePercent']:.2f}%
({html.escape(format_bytes(report['disk']['freeBytes']))})</p></div>
<div class="card"><h2>파일 저장소</h2><table>
<tr><th>구분</th><th>파일</th><th>용량</th></tr>
{category_rows}</table></div>
<div class="card"><h2>MySQL 테이블</h2><table>
<tr><th>테이블</th><th>추정 행</th><th>용량</th></tr>
{table_rows}</table></div>
<div class="card"><h2>보존 정책 드라이런</h2><p>삭제는 실행되지 않았습니다.</p>
<table><tr><th>구분</th><th>경로</th><th>용량</th><th>사유</th></tr>
{candidate_rows}</table></div>
</body></html>"""


def generate_report(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    root = Path(args.root).resolve()
    now = datetime.now(timezone.utc)
    records, scan_warnings = scan_files(root, now)
    categories = summarize_categories(records)
    disk = shutil.disk_usage(root)
    free_percent = (disk.free / disk.total * 100.0) if disk.total else 0.0
    managed_bytes = sum(record["sizeBytes"] for record in records)

    database: dict[str, Any] = {
        "available": False,
        "reason": "filesystem-only mode",
        "tables": [],
        "snapshotReferences": [],
    }
    snapshots = None
    if not args.filesystem_only:
        environment_file = (
            Path(args.environment_file).resolve()
            if Path(args.environment_file).is_absolute()
            else (root / args.environment_file).resolve()
        )
        compose = compose_arguments(root, environment_file)
        container_id = mysql_container(compose, root)
        database = collect_database_audit(container_id, root)
        if database["snapshotMetadataAvailable"]:
            snapshots = reconcile_snapshots(root, database["snapshotReferences"])

    candidates = retention_candidates(
        records,
        ai_output_days=args.ai_output_days,
        backup_days=args.backup_days,
        report_days=args.report_days,
        minimum_backups=args.minimum_backups,
    )
    status, issues = determine_status(
        free_percent,
        managed_bytes,
        snapshots,
        warning_free_percent=args.warning_free_percent,
        critical_free_percent=args.critical_free_percent,
        warning_managed_bytes=int(args.warning_managed_gb * 1024**3),
    )
    issues.extend(scan_warnings)
    if scan_warnings and status == "HEALTHY":
        status = "WARNING"

    report = {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "generatedAt": now.isoformat(),
        "status": status,
        "issues": issues,
        "disk": {
            "root": str(root),
            "totalBytes": disk.total,
            "usedBytes": disk.used,
            "freeBytes": disk.free,
            "freePercent": free_percent,
        },
        "filesystem": {
            "managedBytes": managed_bytes,
            "fileCount": len(records),
            "categories": categories,
        },
        "database": database,
        "snapshots": snapshots,
        "retention": {
            "dryRunOnly": True,
            "policy": {
                "aiOutputDays": args.ai_output_days,
                "backupDays": args.backup_days,
                "reportDays": args.report_days,
                "minimumBackups": args.minimum_backups,
            },
            "candidateCount": len(candidates),
            "candidateBytes": sum(item["sizeBytes"] for item in candidates),
            "candidates": candidates,
        },
    }

    output_root = (
        Path(args.output).resolve()
        if Path(args.output).is_absolute()
        else (root / args.output).resolve()
    )
    output_root.mkdir(parents=True, exist_ok=True)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    output_directory = output_root / f"storage-audit-{timestamp}"
    if output_directory.exists():
        output_directory = output_root / f"storage-audit-{timestamp}-{uuid.uuid4().hex[:8]}"
    output_directory.mkdir()
    (output_directory / "storage-audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_directory / "storage-audit.html").write_text(
        render_html(report),
        encoding="utf-8",
    )
    write_csv(
        output_directory / "storage-categories.csv",
        categories,
        [
            "category",
            "directory",
            "fileCount",
            "totalBytes",
            "oldestModifiedAt",
            "newestModifiedAt",
        ],
    )
    write_csv(
        output_directory / "retention-candidates.csv",
        candidates,
        ["category", "path", "sizeBytes", "ageDays", "reason"],
    )
    if database.get("tables"):
        write_csv(
            output_directory / "mysql-table-sizes.csv",
            database["tables"],
            ["tableName", "estimatedRows", "dataBytes", "indexBytes", "totalBytes"],
        )
    return output_directory, report


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VisionFlow read-only storage audit")
    parser.add_argument("--root", default=str(default_root))
    parser.add_argument("--environment-file", default=".env.docker")
    parser.add_argument("--output", default="artifacts/storage-audit")
    parser.add_argument("--filesystem-only", action="store_true")
    parser.add_argument("--ai-output-days", type=int, default=14)
    parser.add_argument("--backup-days", type=int, default=30)
    parser.add_argument("--report-days", type=int, default=30)
    parser.add_argument("--minimum-backups", type=int, default=3)
    parser.add_argument("--warning-free-percent", type=float, default=20.0)
    parser.add_argument("--critical-free-percent", type=float, default=10.0)
    parser.add_argument("--warning-managed-gb", type=float, default=10.0)
    parser.add_argument(
        "--fail-on",
        choices=("none", "warning", "critical"),
        default="none",
    )
    return parser


def validate_arguments(args: argparse.Namespace) -> None:
    if min(args.ai_output_days, args.backup_days, args.report_days) < 0:
        raise AuditError("보존기간은 0일 이상이어야 합니다.")
    if args.minimum_backups < 0:
        raise AuditError("minimum-backups는 0 이상이어야 합니다.")
    if not 0 <= args.critical_free_percent <= args.warning_free_percent <= 100:
        raise AuditError(
            "디스크 임계값은 0 <= critical <= warning <= 100이어야 합니다."
        )
    if args.warning_managed_gb < 0:
        raise AuditError("warning-managed-gb는 0 이상이어야 합니다.")


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    args = build_parser(default_root).parse_args(arguments)
    try:
        validate_arguments(args)
        output_directory, report = generate_report(args)
        print(f"VisionFlow storage audit: {report['status']}")
        print(f"Report: {output_directory / 'storage-audit.html'}")
        print(
            "Retention dry-run: "
            f"{report['retention']['candidateCount']} files, "
            f"{format_bytes(report['retention']['candidateBytes'])}"
        )
        if args.fail_on == "warning" and report["status"] in {"WARNING", "CRITICAL"}:
            return 2
        if args.fail_on == "critical" and report["status"] == "CRITICAL":
            return 3
        return 0
    except (AuditError, FileNotFoundError, OSError, ValueError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
