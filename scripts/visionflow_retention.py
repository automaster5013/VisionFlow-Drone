"""Guarded, reversible retention enforcement for VisionFlow audit candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
ALLOWED_CATEGORY_ROOTS = {
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


class RetentionError(RuntimeError):
    """Raised when a retention operation is unsafe or inconsistent."""


def sha256_stream(stream: Any) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return sha256_stream(stream)


def parse_datetime(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise RetentionError(f"{label} 시각이 없습니다.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RetentionError(
            f"{label} 시각 형식이 올바르지 않습니다: {value}"
        ) from error
    if parsed.tzinfo is None:
        raise RetentionError(f"{label} 시각에 시간대가 없습니다.")
    return parsed.astimezone(timezone.utc)


def resolve_input(root: Path, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def safe_relative_path(value: Any) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise RetentionError("후보 파일 경로가 비어 있습니다.")
    path = PurePosixPath(value)
    if value.startswith(("/", "\\")) or "\\" in value or ".." in path.parts:
        raise RetentionError(f"안전하지 않은 후보 경로입니다: {value}")
    return path


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def load_audit_report(
    audit_file: Path,
    root: Path,
    *,
    max_age_hours: float,
    now: datetime,
) -> dict[str, Any]:
    if not audit_file.is_file():
        raise RetentionError(f"저장공간 감사 JSON을 찾을 수 없습니다: {audit_file}")
    try:
        report = json.loads(audit_file.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise RetentionError("저장공간 감사 JSON이 올바르지 않습니다.") from error
    if not isinstance(report, dict):
        raise RetentionError("감사 보고서 최상위 값은 객체여야 합니다.")
    if report.get("schemaVersion") != SCHEMA_VERSION:
        raise RetentionError("지원하지 않는 감사 보고서 스키마입니다.")
    if report.get("project") != PROJECT_NAME:
        raise RetentionError("VisionFlow 저장공간 감사 보고서가 아닙니다.")
    if report.get("status") == "CRITICAL":
        raise RetentionError(
            "CRITICAL 감사 결과에서는 보존 정책을 실행할 수 없습니다."
        )
    generated_at = parse_datetime(report.get("generatedAt"), "감사 보고서")
    age_hours = (now - generated_at).total_seconds() / 3600.0
    if age_hours < -0.1 or age_hours > max_age_hours:
        raise RetentionError(
            "감사 보고서가 너무 오래됐거나 미래 시각입니다: "
            f"{age_hours:.2f}시간"
        )
    disk = report.get("disk")
    if not isinstance(disk, dict) or not isinstance(disk.get("root"), str):
        raise RetentionError(
            "감사 보고서의 프로젝트 루트가 올바르지 않습니다."
        )
    if Path(disk["root"]).resolve() != root:
        raise RetentionError(
            f"감사 대상 루트가 현재 프로젝트와 다릅니다: {disk['root']}"
        )
    retention = report.get("retention")
    if not isinstance(retention, dict) or retention.get("dryRunOnly") is not True:
        raise RetentionError("삭제 없는 저장공간 감사 보고서가 아닙니다.")
    if not isinstance(retention.get("policy"), dict):
        raise RetentionError("감사 보고서의 보존 정책이 올바르지 않습니다.")
    candidates = retention.get("candidates")
    if not isinstance(candidates, list):
        raise RetentionError(
            "감사 보고서의 정리 후보 목록이 올바르지 않습니다."
        )
    if retention.get("candidateCount") != len(candidates):
        raise RetentionError("감사 보고서의 후보 개수가 일치하지 않습니다.")
    return report


def safe_zip_names(archive: zipfile.ZipFile) -> list[str]:
    names = [info.filename for info in archive.infolist() if not info.is_dir()]
    if len(names) != len(set(names)):
        raise RetentionError("백업 ZIP에 중복된 경로가 있습니다.")
    for name in names:
        path = PurePosixPath(name)
        if name.startswith(("/", "\\")) or "\\" in name or ".." in path.parts:
            raise RetentionError(
                f"백업 ZIP에 안전하지 않은 경로가 있습니다: {name}"
            )
    return names


def verify_backup(backup_file: Path, *, max_age_days: float, now: datetime) -> dict[str, Any]:
    if not backup_file.is_file():
        raise RetentionError(f"VisionFlow 백업 ZIP을 찾을 수 없습니다: {backup_file}")
    try:
        with zipfile.ZipFile(backup_file, "r") as archive:
            names = safe_zip_names(archive)
            if "manifest.json" not in names:
                raise RetentionError("백업 ZIP에 manifest.json이 없습니다.")
            manifest = json.loads(archive.read("manifest.json").decode("utf-8-sig"))
            if not isinstance(manifest, dict):
                raise RetentionError("백업 manifest가 올바르지 않습니다.")
            if manifest.get("schemaVersion") != SCHEMA_VERSION:
                raise RetentionError("지원하지 않는 백업 스키마입니다.")
            if manifest.get("project") != PROJECT_NAME:
                raise RetentionError("VisionFlow 백업 파일이 아닙니다.")
            created_at = parse_datetime(manifest.get("createdAt"), "백업")
            age_days = (now - created_at).total_seconds() / 86400.0
            if age_days < -0.1 or age_days > max_age_days:
                raise RetentionError(
                    f"백업이 너무 오래됐거나 미래 시각입니다: {age_days:.2f}일"
                )
            entries = manifest.get("files")
            if not isinstance(entries, list):
                raise RetentionError(
                    "백업 manifest의 파일 목록이 올바르지 않습니다."
                )
            expected: dict[str, dict[str, Any]] = {}
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                    raise RetentionError(
                        "백업 manifest에 잘못된 파일 항목이 있습니다."
                    )
                path = entry["path"]
                if path in expected:
                    raise RetentionError(f"백업 manifest 경로가 중복되었습니다: {path}")
                size = entry.get("sizeBytes")
                checksum = entry.get("sha256")
                if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                    raise RetentionError(
                        f"백업 파일 크기가 올바르지 않습니다: {path}"
                    )
                if (
                    not isinstance(checksum, str)
                    or len(checksum) != 64
                    or any(character not in "0123456789abcdefABCDEF" for character in checksum)
                ):
                    raise RetentionError(f"백업 SHA-256이 올바르지 않습니다: {path}")
                expected[path] = entry
            actual = set(names) - {"manifest.json"}
            if actual != set(expected) or "database/visionflow.sql" not in expected:
                raise RetentionError(
                    "백업 파일 목록 또는 MySQL 덤프가 올바르지 않습니다."
                )
            for path, entry in expected.items():
                info = archive.getinfo(path)
                if info.file_size != entry["sizeBytes"]:
                    raise RetentionError(f"백업 파일 크기가 다릅니다: {path}")
                with archive.open(path, "r") as stream:
                    checksum = sha256_stream(stream)
                if checksum.lower() != entry["sha256"].lower():
                    raise RetentionError(f"백업 SHA-256이 다릅니다: {path}")
            return {
                "status": "VALID",
                "createdAt": created_at.isoformat(),
                "ageDays": age_days,
                "sha256": sha256_file(backup_file),
                "manifest": manifest,
            }
    except zipfile.BadZipFile as error:
        raise RetentionError(
            f"손상되었거나 올바르지 않은 백업 ZIP: {backup_file}"
        ) from error


def current_protected_backups(root: Path, minimum_backups: int) -> set[Path]:
    backup_root = (root / ALLOWED_CATEGORY_ROOTS["backups"]).resolve()
    if not backup_root.is_dir():
        return set()
    backups = sorted(
        (
            path.resolve()
            for path in backup_root.rglob("*.zip")
            if path.is_file() and not path.is_symlink()
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return set(backups[: max(0, minimum_backups)])


def candidate_threshold_days(category: str, policy: dict[str, Any]) -> int:
    key = {
        "ai-output": "aiOutputDays",
        "backups": "backupDays",
    }.get(category)
    if category in REPORT_CATEGORIES:
        key = "reportDays"
    value = policy.get(key) if key else None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise RetentionError(f"{category} 보존기간이 올바르지 않습니다.")
    return value


def validate_candidates(
    root: Path,
    report: dict[str, Any],
    backup_file: Path,
    *,
    now: datetime,
) -> list[dict[str, Any]]:
    retention = report["retention"]
    policy = retention["policy"]
    minimum_backups = policy.get("minimumBackups")
    if not isinstance(minimum_backups, int) or minimum_backups < 0:
        raise RetentionError("minimumBackups가 올바르지 않습니다.")
    protected_backups = current_protected_backups(root, minimum_backups)
    selected_backup = backup_file.resolve()
    seen: set[Path] = set()
    results = []

    for index, candidate in enumerate(retention["candidates"]):
        if not isinstance(candidate, dict):
            raise RetentionError(f"후보 #{index}가 객체가 아닙니다.")
        category = candidate.get("category")
        if category not in ALLOWED_CATEGORY_ROOTS:
            raise RetentionError(f"허용되지 않은 후보 범주입니다: {category}")
        relative = safe_relative_path(candidate.get("path"))
        path = root.joinpath(*relative.parts).resolve()
        allowed_root = (root / ALLOWED_CATEGORY_ROOTS[category]).resolve()
        if not is_within(path, allowed_root):
            raise RetentionError(f"후보가 허용된 경로를 벗어났습니다: {relative}")
        if path in seen:
            raise RetentionError(f"후보 경로가 중복되었습니다: {relative}")
        seen.add(path)
        expected_size = candidate.get("sizeBytes")
        if (
            not isinstance(expected_size, int)
            or isinstance(expected_size, bool)
            or expected_size < 0
        ):
            raise RetentionError(f"후보 크기가 올바르지 않습니다: {relative}")

        status = "ELIGIBLE"
        detail = "재검증 통과"
        current_size = None
        current_age_days = None
        if not path.is_file() or path.is_symlink():
            status = "MISSING_OR_NOT_REGULAR"
            detail = "현재 일반 파일이 아니거나 존재하지 않음"
        else:
            stat = path.stat()
            current_size = stat.st_size
            current_age_days = max(
                0.0,
                (now.timestamp() - stat.st_mtime) / 86400.0,
            )
            threshold_days = candidate_threshold_days(category, policy)
            if current_size != expected_size:
                status = "CHANGED_SIZE"
                detail = f"감사 후 크기 변경: {expected_size} -> {current_size}"
            elif current_age_days <= threshold_days:
                status = "TOO_NEW"
                detail = f"현재 보존기간 {threshold_days}일 이내"
            elif path == selected_backup:
                status = "SELECTED_SAFETY_BACKUP"
                detail = "이번 실행의 안전 백업이므로 보호"
            elif category == "backups" and path in protected_backups:
                status = "PROTECTED_LATEST_BACKUP"
                detail = f"최신 백업 {minimum_backups}개 보호 규칙"
        results.append(
            {
                "category": category,
                "path": relative.as_posix(),
                "absolutePath": str(path),
                "expectedSizeBytes": expected_size,
                "currentSizeBytes": current_size,
                "currentAgeDays": (
                    round(current_age_days, 3) if current_age_days is not None else None
                ),
                "status": status,
                "detail": detail,
            }
        )
    return results


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def build_execution_plan(
    root: Path,
    audit_file: Path,
    backup_file: Path,
    *,
    max_audit_age_hours: float,
    max_backup_age_days: float,
    now: datetime,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    report = load_audit_report(
        audit_file,
        root,
        max_age_hours=max_audit_age_hours,
        now=now,
    )
    backup = verify_backup(
        backup_file,
        max_age_days=max_backup_age_days,
        now=now,
    )
    candidates = validate_candidates(root, report, backup_file, now=now)
    return report, backup, candidates


def quarantine_candidates(
    root: Path,
    audit_file: Path,
    backup_file: Path,
    *,
    max_audit_age_hours: float,
    max_backup_age_days: float,
    apply: bool,
    confirmation: str,
    output_root: Path,
    now: datetime,
) -> tuple[Path, dict[str, Any]]:
    allowed_output_root = (root / "artifacts/retention-quarantine").resolve()
    if not is_within(output_root.resolve(), allowed_output_root):
        raise RetentionError(
            "출력 폴더는 artifacts/retention-quarantine 내부여야 합니다."
        )
    audit, backup, candidates = build_execution_plan(
        root,
        audit_file,
        backup_file,
        max_audit_age_hours=max_audit_age_hours,
        max_backup_age_days=max_backup_age_days,
        now=now,
    )
    blocked = [candidate for candidate in candidates if candidate["status"] != "ELIGIBLE"]
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    run_directory = output_root / f"retention-{timestamp}"
    if run_directory.exists():
        run_directory = output_root / f"retention-{timestamp}-{uuid.uuid4().hex[:8]}"
    run_directory.mkdir(parents=True)

    plan = {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "generatedAt": now.isoformat(),
        "mode": "APPLY" if apply else "DRY_RUN",
        "status": "BLOCKED" if blocked else "READY",
        "sourceAudit": {
            "path": str(audit_file),
            "sha256": sha256_file(audit_file),
            "generatedAt": audit["generatedAt"],
        },
        "safetyBackup": {
            "path": str(backup_file),
            "sha256": backup["sha256"],
            "createdAt": backup["createdAt"],
            "ageDays": backup["ageDays"],
        },
        "candidateCount": len(candidates),
        "eligibleCount": len(candidates) - len(blocked),
        "blockedCount": len(blocked),
        "eligibleBytes": sum(
            candidate["expectedSizeBytes"]
            for candidate in candidates
            if candidate["status"] == "ELIGIBLE"
        ),
        "candidates": candidates,
    }
    plan_path = run_directory / "retention-plan.json"
    write_json(plan_path, plan)
    if blocked:
        raise RetentionError(
            f"재검증을 통과하지 못한 후보가 {len(blocked)}개입니다. "
            "감사를 다시 실행하세요."
        )
    if not apply or not candidates:
        plan["status"] = "NO_CHANGES" if not candidates else "DRY_RUN_COMPLETE"
        write_json(plan_path, plan)
        return plan_path, plan
    if confirmation != "QUARANTINE":
        raise RetentionError("실제 격리에는 --confirm QUARANTINE이 필요합니다.")

    moved: list[dict[str, Any]] = []
    files_root = run_directory / "files"
    try:
        for candidate in candidates:
            source = Path(candidate["absolutePath"])
            relative = PurePosixPath(candidate["path"])
            destination = files_root.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            checksum = sha256_file(source)
            original_modified_at = datetime.fromtimestamp(
                source.stat().st_mtime,
                timezone.utc,
            ).isoformat()
            shutil.move(str(source), str(destination))
            moved.append(
                {
                    "category": candidate["category"],
                    "originalPath": relative.as_posix(),
                    "quarantinePath": destination.relative_to(run_directory).as_posix(),
                    "sizeBytes": destination.stat().st_size,
                    "sha256": checksum,
                    "originalModifiedAt": original_modified_at,
                    "movedAt": datetime.now(timezone.utc).isoformat(),
                }
            )
    except Exception as error:
        rollback_errors = []
        for entry in reversed(moved):
            source = run_directory.joinpath(*PurePosixPath(entry["quarantinePath"]).parts)
            destination = root.joinpath(*PurePosixPath(entry["originalPath"]).parts)
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(destination))
            except OSError as rollback_error:
                rollback_errors.append(str(rollback_error))
        plan["status"] = "ROLLED_BACK" if not rollback_errors else "ROLLBACK_FAILED"
        plan["error"] = str(error)
        plan["rollbackErrors"] = rollback_errors
        write_json(plan_path, plan)
        raise RetentionError(
            f"격리 이동 실패. rollbackErrors={rollback_errors}"
        ) from error

    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "operation": "RETENTION_QUARANTINE",
        "status": "COMPLETED",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "sourceAudit": plan["sourceAudit"],
        "safetyBackup": plan["safetyBackup"],
        "fileCount": len(moved),
        "totalBytes": sum(entry["sizeBytes"] for entry in moved),
        "files": moved,
    }
    manifest_path = run_directory / "quarantine-manifest.json"
    write_json(manifest_path, manifest)
    plan["status"] = "QUARANTINED"
    plan["quarantineManifest"] = str(manifest_path)
    write_json(plan_path, plan)
    return manifest_path, manifest


def load_quarantine_manifest(manifest_file: Path) -> dict[str, Any]:
    if not manifest_file.is_file():
        raise RetentionError(f"격리 manifest를 찾을 수 없습니다: {manifest_file}")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8-sig"))
    if not isinstance(manifest, dict):
        raise RetentionError("격리 manifest 최상위 값이 올바르지 않습니다.")
    if manifest.get("schemaVersion") != SCHEMA_VERSION:
        raise RetentionError("지원하지 않는 격리 manifest 스키마입니다.")
    if manifest.get("project") != PROJECT_NAME:
        raise RetentionError("VisionFlow 격리 manifest가 아닙니다.")
    if manifest.get("operation") != "RETENTION_QUARANTINE":
        raise RetentionError("보존 정책 격리 manifest가 아닙니다.")
    if manifest.get("status") != "COMPLETED":
        raise RetentionError("완료된 격리 manifest가 아닙니다.")
    files = manifest.get("files")
    if not isinstance(files, list) or manifest.get("fileCount") != len(files):
        raise RetentionError("격리 manifest 파일 목록이 올바르지 않습니다.")
    return manifest


def restore_quarantine(
    root: Path,
    manifest_file: Path,
    confirmation: str,
) -> Path:
    if confirmation != "RESTORE_FILES":
        raise RetentionError("격리 복원에는 --confirm RESTORE_FILES가 필요합니다.")
    quarantine_root = (root / "artifacts/retention-quarantine").resolve()
    if not is_within(manifest_file.resolve(), quarantine_root):
        raise RetentionError("격리 manifest가 retention-quarantine 폴더 밖에 있습니다.")
    manifest = load_quarantine_manifest(manifest_file)
    run_directory = manifest_file.parent.resolve()
    prepared = []
    seen: set[Path] = set()
    for entry in manifest["files"]:
        if not isinstance(entry, dict):
            raise RetentionError("격리 manifest 파일 항목이 올바르지 않습니다.")
        original_relative = safe_relative_path(entry.get("originalPath"))
        quarantine_relative = safe_relative_path(entry.get("quarantinePath"))
        destination = root.joinpath(*original_relative.parts).resolve()
        source = run_directory.joinpath(*quarantine_relative.parts).resolve()
        if not is_within(source, run_directory):
            raise RetentionError(f"격리 경로가 실행 폴더를 벗어났습니다: {source}")
        category = entry.get("category")
        if category not in ALLOWED_CATEGORY_ROOTS:
            raise RetentionError(f"허용되지 않은 복원 범주입니다: {category}")
        allowed_root = (root / ALLOWED_CATEGORY_ROOTS[category]).resolve()
        if not is_within(destination, allowed_root):
            raise RetentionError(
                f"복원 경로가 허용 영역을 벗어났습니다: {destination}"
            )
        if destination in seen:
            raise RetentionError(f"복원 경로가 중복되었습니다: {destination}")
        seen.add(destination)
        if destination.exists():
            raise RetentionError(
                f"원래 경로가 이미 존재하여 덮어쓸 수 없습니다: {destination}"
            )
        if not source.is_file() or source.is_symlink():
            raise RetentionError(
                f"격리 파일이 없거나 일반 파일이 아닙니다: {source}"
            )
        if source.stat().st_size != entry.get("sizeBytes"):
            raise RetentionError(f"격리 파일 크기가 다릅니다: {source}")
        if sha256_file(source).lower() != str(entry.get("sha256", "")).lower():
            raise RetentionError(f"격리 파일 SHA-256이 다릅니다: {source}")
        prepared.append((source, destination, entry))

    restored = []
    try:
        for source, destination, entry in prepared:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            modified = parse_datetime(entry.get("originalModifiedAt"), "원본 수정")
            os.utime(destination, (modified.timestamp(), modified.timestamp()))
            restored.append((source, destination))
    except Exception as error:
        rollback_errors = []
        for source, destination in reversed(restored):
            try:
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), str(source))
            except OSError as rollback_error:
                rollback_errors.append(str(rollback_error))
        raise RetentionError(
            f"격리 복원 실패. rollbackErrors={rollback_errors}"
        ) from error

    result = {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "operation": "RETENTION_RESTORE",
        "status": "COMPLETED",
        "restoredAt": datetime.now(timezone.utc).isoformat(),
        "sourceManifest": str(manifest_file),
        "fileCount": len(restored),
    }
    result_path = run_directory / (
        "restore-result-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json"
    )
    write_json(result_path, result)
    return result_path


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VisionFlow retention quarantine")
    parser.add_argument("--root", default=str(default_root))
    subparsers = parser.add_subparsers(dest="command", required=True)

    quarantine = subparsers.add_parser("quarantine")
    quarantine.add_argument("--audit", required=True)
    quarantine.add_argument("--backup", required=True)
    quarantine.add_argument("--output", default="artifacts/retention-quarantine")
    quarantine.add_argument("--max-audit-age-hours", type=float, default=24.0)
    quarantine.add_argument("--max-backup-age-days", type=float, default=7.0)
    quarantine.add_argument("--apply", action="store_true")
    quarantine.add_argument("--confirm", default="")

    restore = subparsers.add_parser("restore")
    restore.add_argument("--manifest", required=True)
    restore.add_argument("--confirm", default="")
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    args = build_parser(default_root).parse_args(arguments)
    root = Path(args.root).resolve()
    try:
        if args.command == "quarantine":
            if args.max_audit_age_hours <= 0 or args.max_backup_age_days <= 0:
                raise RetentionError(
                    "감사/백업 최대 허용 시간은 양수여야 합니다."
                )
            audit_file = resolve_input(root, args.audit)
            backup_file = resolve_input(root, args.backup)
            output_root = resolve_input(root, args.output)
            quarantine_root = (root / "artifacts/retention-quarantine").resolve()
            if not is_within(output_root, quarantine_root):
                raise RetentionError(
                    "출력 폴더는 artifacts/retention-quarantine 내부여야 합니다."
                )
            result_path, result = quarantine_candidates(
                root,
                audit_file,
                backup_file,
                max_audit_age_hours=args.max_audit_age_hours,
                max_backup_age_days=args.max_backup_age_days,
                apply=args.apply,
                confirmation=args.confirm,
                output_root=output_root,
                now=datetime.now(timezone.utc),
            )
            print(f"VisionFlow retention: {result['status']}")
            print(f"Result: {result_path}")
            print(f"Files: {result.get('fileCount', result.get('eligibleCount', 0))}")
        elif args.command == "restore":
            manifest_file = resolve_input(root, args.manifest)
            result_path = restore_quarantine(root, manifest_file, args.confirm)
            print("VisionFlow retention restore: COMPLETED")
            print(f"Result: {result_path}")
        return 0
    except (RetentionError, FileNotFoundError, OSError, json.JSONDecodeError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
