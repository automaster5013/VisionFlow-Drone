"""Run a reversible VisionFlow retention quarantine and recovery drill."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable

from visionflow_retention import (
    RetentionError,
    quarantine_candidates,
    resolve_input,
    restore_quarantine,
    safe_relative_path,
    sha256_file,
)


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
EXECUTE_CONFIRMATION = "RUN_RESTORE_DRILL"
AcceptanceRunner = Callable[[Path, Path, int], dict[str, Any]]


class DrillError(RuntimeError):
    """Raised when the recovery drill cannot proceed safely."""


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


def create_run_directory(root: Path, output_root: Path, now: datetime) -> Path:
    allowed_root = (root / "artifacts/retention-drill").resolve()
    resolved_output = output_root.resolve()
    if not is_within(resolved_output, allowed_root):
        raise DrillError("출력 폴더는 artifacts/retention-drill 내부여야 합니다.")
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    run_directory = resolved_output / f"drill-{timestamp}"
    if run_directory.exists():
        run_directory = resolved_output / f"drill-{timestamp}-{uuid.uuid4().hex[:8]}"
    run_directory.mkdir(parents=True)
    return run_directory


def acceptance_command(root: Path) -> list[str]:
    script = (root / "scripts/run-visionflow-acceptance.bat").resolve()
    if not script.is_file():
        raise DrillError(f"인수 테스트 배치를 찾을 수 없습니다: {script}")
    if os.name == "nt":
        return ["cmd.exe", "/d", "/c", str(script)]
    return [str(script)]


def run_acceptance(root: Path, log_file: Path, timeout_seconds: int) -> dict[str, Any]:
    command = acceptance_command(root)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        output = completed.stdout
        if completed.stderr:
            output += "\n[stderr]\n" + completed.stderr
        log_file.write_text(output, encoding="utf-8")
        return {
            "status": "PASSED" if completed.returncode == 0 else "FAILED",
            "exitCode": completed.returncode,
            "timedOut": False,
            "durationMs": round((time.monotonic() - started) * 1000),
            "log": str(log_file),
        }
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout or ""
        stderr = error.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        log_file.write_text(
            stdout + ("\n[stderr]\n" + stderr if stderr else ""),
            encoding="utf-8",
        )
        return {
            "status": "TIMED_OUT",
            "exitCode": None,
            "timedOut": True,
            "durationMs": round((time.monotonic() - started) * 1000),
            "log": str(log_file),
        }


def verify_restored_files(root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for entry in manifest.get("files", []):
        relative = safe_relative_path(entry.get("originalPath"))
        path = root.joinpath(*PurePosixPath(relative).parts).resolve()
        expected_size = entry.get("sizeBytes")
        expected_checksum = str(entry.get("sha256", "")).lower()
        exists = path.is_file() and not path.is_symlink()
        size_matches = exists and path.stat().st_size == expected_size
        checksum_matches = size_matches and sha256_file(path).lower() == expected_checksum
        results.append(
            {
                "path": relative.as_posix(),
                "exists": exists,
                "sizeMatches": size_matches,
                "checksumMatches": checksum_matches,
                "status": "RESTORED" if checksum_matches else "INVALID",
            }
        )
    return results


def run_recovery_drill(
    root: Path,
    audit_file: Path,
    backup_file: Path,
    *,
    execute: bool,
    confirmation: str,
    output_root: Path,
    timeout_seconds: int,
    max_audit_age_hours: float,
    max_backup_age_days: float,
    now: datetime,
    runner: AcceptanceRunner = run_acceptance,
) -> tuple[Path, dict[str, Any], int]:
    if execute and confirmation != EXECUTE_CONFIRMATION:
        raise DrillError(
            f"복구 리허설 실행에는 --confirm {EXECUTE_CONFIRMATION}이 필요합니다."
        )
    run_directory = create_run_directory(root, output_root, now)
    report_path = run_directory / "retention-recovery-drill.json"
    report: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "operation": "RETENTION_RECOVERY_DRILL",
        "startedAt": now.isoformat(),
        "mode": "EXECUTE" if execute else "PLAN",
        "status": "RUNNING",
        "sourceAudit": str(audit_file),
        "safetyBackup": str(backup_file),
        "stages": [],
    }
    write_json(report_path, report)

    plan_path, plan = quarantine_candidates(
        root,
        audit_file,
        backup_file,
        max_audit_age_hours=max_audit_age_hours,
        max_backup_age_days=max_backup_age_days,
        apply=False,
        confirmation="",
        output_root=root / "artifacts/retention-quarantine",
        now=now,
    )
    report["stages"].append(
        {
            "name": "PREFLIGHT",
            "status": plan["status"],
            "result": str(plan_path),
            "eligibleCount": plan.get("eligibleCount", 0),
            "eligibleBytes": plan.get("eligibleBytes", 0),
        }
    )
    if plan.get("eligibleCount", 0) == 0:
        report["status"] = "NO_CANDIDATES"
        report["completedAt"] = datetime.now(timezone.utc).isoformat()
        write_json(report_path, report)
        return report_path, report, 0
    if not execute:
        report["status"] = "PLAN_COMPLETE"
        report["completedAt"] = datetime.now(timezone.utc).isoformat()
        write_json(report_path, report)
        return report_path, report, 0

    acceptance_command(root)
    manifest_path: Path | None = None
    manifest: dict[str, Any] | None = None
    quarantine_error: str | None = None
    acceptance_result: dict[str, Any] = {
        "status": "NOT_RUN",
        "exitCode": None,
        "timedOut": False,
    }
    interrupted = False
    restore_result: Path | None = None
    restore_error: str | None = None
    restored_files: list[dict[str, Any]] = []
    try:
        try:
            manifest_path, manifest = quarantine_candidates(
                root,
                audit_file,
                backup_file,
                max_audit_age_hours=max_audit_age_hours,
                max_backup_age_days=max_backup_age_days,
                apply=True,
                confirmation="QUARANTINE",
                output_root=root / "artifacts/retention-quarantine",
                now=datetime.now(timezone.utc),
            )
        except Exception as error:
            quarantine_error = str(error)
            report["stages"].append(
                {
                    "name": "QUARANTINE",
                    "status": "FAILED",
                    "error": quarantine_error,
                }
            )
        if manifest_path is not None and manifest is not None:
            report["stages"].append(
                {
                    "name": "QUARANTINE",
                    "status": "COMPLETED",
                    "manifest": str(manifest_path),
                    "fileCount": manifest.get("fileCount", 0),
                    "totalBytes": manifest.get("totalBytes", 0),
                }
            )
            try:
                acceptance_result = runner(
                    root,
                    run_directory / "acceptance.log",
                    timeout_seconds,
                )
            except KeyboardInterrupt:
                interrupted = True
                acceptance_result = {
                    "status": "INTERRUPTED",
                    "exitCode": None,
                    "timedOut": False,
                    "error": "사용자에 의해 인수 테스트가 중단되었습니다.",
                }
            except Exception as error:
                acceptance_result = {
                    "status": "ERROR",
                    "exitCode": None,
                    "timedOut": False,
                    "error": str(error),
                }
            report["stages"].append({"name": "ACCEPTANCE", **acceptance_result})
    finally:
        if manifest_path is not None and manifest is not None:
            try:
                restore_result = restore_quarantine(
                    root,
                    manifest_path,
                    "RESTORE_FILES",
                )
                restored_files = verify_restored_files(root, manifest)
                if not all(item["status"] == "RESTORED" for item in restored_files):
                    raise DrillError("복원 후 파일 무결성 검증에 실패했습니다.")
            except Exception as error:
                restore_error = str(error)

    if manifest_path is None or manifest is None:
        report["status"] = "QUARANTINE_FAILED"
        report["error"] = quarantine_error
        report["completedAt"] = datetime.now(timezone.utc).isoformat()
        write_json(report_path, report)
        return report_path, report, 1

    report["stages"].append(
        {
            "name": "RESTORE",
            "status": "FAILED" if restore_error else "COMPLETED",
            "result": str(restore_result) if restore_result else None,
            "error": restore_error,
            "files": restored_files,
        }
    )
    if restore_error:
        report["status"] = "RESTORE_FAILED"
        exit_code = 2
    elif interrupted:
        report["status"] = "INTERRUPTED_RESTORED"
        exit_code = 130
    elif acceptance_result.get("status") == "PASSED":
        report["status"] = "PASSED"
        exit_code = 0
    else:
        report["status"] = "ACCEPTANCE_FAILED_RESTORED"
        exit_code = 1
    report["completedAt"] = datetime.now(timezone.utc).isoformat()
    write_json(report_path, report)
    return report_path, report, exit_code


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VisionFlow retention recovery drill")
    parser.add_argument("--root", default=str(default_root))
    parser.add_argument("--audit", required=True)
    parser.add_argument("--backup", required=True)
    parser.add_argument("--output", default="artifacts/retention-drill")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--max-audit-age-hours", type=float, default=24.0)
    parser.add_argument("--max-backup-age-days", type=float, default=7.0)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm", default="")
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    args = build_parser(default_root).parse_args(arguments)
    root = Path(args.root).resolve()
    try:
        if args.timeout_seconds <= 0:
            raise DrillError("인수 테스트 제한 시간은 양수여야 합니다.")
        if args.max_audit_age_hours <= 0 or args.max_backup_age_days <= 0:
            raise DrillError("감사/백업 최대 허용 시간은 양수여야 합니다.")
        report_path, report, exit_code = run_recovery_drill(
            root,
            resolve_input(root, args.audit),
            resolve_input(root, args.backup),
            execute=args.execute,
            confirmation=args.confirm,
            output_root=resolve_input(root, args.output),
            timeout_seconds=args.timeout_seconds,
            max_audit_age_hours=args.max_audit_age_hours,
            max_backup_age_days=args.max_backup_age_days,
            now=datetime.now(timezone.utc),
        )
        print(f"VisionFlow retention recovery drill: {report['status']}")
        print(f"Report: {report_path}")
        return exit_code
    except (DrillError, RetentionError, FileNotFoundError, OSError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("[FAIL] 사용자에 의해 중단되었습니다.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
