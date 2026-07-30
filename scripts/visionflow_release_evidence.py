"""Create a verified, minimal VisionFlow release evidence ZIP."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

try:
    from visionflow_hp_omen_transfer_day import (
        TransferDayError,
        verify_checkpoint as verify_transfer_day_checkpoint,
    )
    from visionflow_transfer_rehearsal import (
        TransferRehearsalError,
        verify_report as verify_transfer_rehearsal_report,
    )
except ModuleNotFoundError:  # pragma: no cover - package import during tests
    from scripts.visionflow_hp_omen_transfer_day import (
        TransferDayError,
        verify_checkpoint as verify_transfer_day_checkpoint,
    )
    from scripts.visionflow_transfer_rehearsal import (
        TransferRehearsalError,
        verify_report as verify_transfer_rehearsal_report,
    )


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
SCOPE = "SECOND_PROJECT_DIGITAL_TWIN"
READY_STATUSES = {"READY", "READY_WITH_DEFERRED", "READY_WITH_WARNINGS"}
EVIDENCE_POLICIES = {
    "acceptance-demo": {
        "root": Path("artifacts/visionflow-acceptance"),
        "include": True,
        "archive": "evidence/acceptance-demo.json",
        "suffix": ".json",
    },
    "maintenance-operations": {
        "root": Path("artifacts/maintenance-acceptance"),
        "include": True,
        "archive": "evidence/maintenance-operations.json",
        "suffix": ".json",
    },
    "verified-backup": {
        "root": Path("backups"),
        "include": False,
        "archive": None,
        "suffix": ".zip",
    },
    "storage-audit": {
        "root": Path("artifacts/storage-audit"),
        "include": True,
        "archive": "evidence/storage-audit.json",
        "suffix": ".json",
    },
    "retention-recovery-drill": {
        "root": Path("artifacts/retention-drill"),
        "include": True,
        "archive": "evidence/retention-recovery-drill.json",
        "suffix": ".json",
    },
    "ai-cpu-baseline": {
        "root": Path("artifacts/ai-benchmark"),
        "include": True,
        "archive": "evidence/ai-cpu-baseline.json",
        "suffix": ".json",
    },
    "csp-report-only-observation": {
        "root": Path("artifacts/csp-observability"),
        "include": True,
        "archive": "evidence/csp-report-only-observation.json",
        "suffix": ".json",
    },
    "smartphone-real-sensor-https": {
        "root": Path("artifacts/mobile-readiness"),
        "include": True,
        "archive": "evidence/smartphone-real-sensor-https.json",
        "suffix": ".json",
    },
}
OPTIONAL_EVIDENCE_KEYS = {"smartphone-real-sensor-https"}
REQUIRED_EVIDENCE_KEYS = set(EVIDENCE_POLICIES) - OPTIONAL_EVIDENCE_KEYS
SUPPLEMENTAL_POLICIES = {
    "machine-readiness": {
        "title": "LG GRAM 장비 준비도",
        "root": Path("artifacts/machine-readiness"),
        "pattern": "visionflow-machine-baseline-*.json",
        "archive": "supplemental/machine-readiness.json",
        "operation": "MACHINE_READINESS_PROFILE",
        "statuses": {"BASELINE_READY", "BASELINE_READY_WITH_DEFERRED"},
    },
    "cold-start-rehearsal": {
        "title": "콜드 스타트 소스 복원 리허설",
        "root": Path("artifacts/cold-start-rehearsal"),
        "pattern": "visionflow-cold-start-rehearsal-*.json",
        "archive": "supplemental/cold-start-rehearsal.json",
        "operation": "COLD_START_REHEARSAL",
        "statuses": {"COLD_START_READY", "COLD_START_READY_WITH_DEFERRED"},
    },
    "transfer-readiness": {
        "title": "최종 이전 준비도",
        "root": Path("artifacts/transfer-readiness"),
        "pattern": "visionflow-transfer-readiness-*.json",
        "archive": "supplemental/transfer-readiness.json",
        "operation": "TRANSFER_READINESS_GATE",
        "statuses": {"TRANSFER_READY", "TRANSFER_READY_WITH_DEFERRED"},
    },
    "offline-transfer-rehearsal": {
        "title": "오프라인 이관 리허설",
        "root": Path("artifacts/transfer-rehearsal"),
        "pattern": "visionflow-transfer-rehearsal-*.json",
        "archive": "supplemental/offline-transfer-rehearsal.json",
        "operation": "OFFLINE_TRANSFER_REHEARSAL",
        "statuses": {"OFFLINE_TRANSFER_REHEARSAL_READY_WITH_DEFERRED"},
    },
    "hp-omen-transfer-day": {
        "title": "HP OMEN 이관 당일 체크포인트",
        "root": Path("artifacts/hp-omen-transfer-day"),
        "pattern": "checkpoint-*/visionflow-hp-omen-transfer-day.json",
        "archive": "supplemental/hp-omen-transfer-day.json",
        "operation": "HP_OMEN_TRANSFER_DAY",
        "statuses": {"TRANSFER_DAY_READY_WITH_DEFERRED"},
    },
}
SUPPLEMENTAL_MAX_AGE = timedelta(days=30)
FUTURE_TOLERANCE = timedelta(minutes=10)
MAX_SUPPLEMENTAL_JSON_BYTES = 5 * 1024 * 1024
BANNED_ARCHIVE_SUFFIXES = {
    ".env",
    ".sql",
    ".pt",
    ".pth",
    ".onnx",
    ".jpg",
    ".jpeg",
    ".png",
    ".mp4",
    ".avi",
    ".mov",
}


class EvidenceBundleError(RuntimeError):
    """Raised when a release evidence bundle would be unsafe or inconsistent."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def safe_relative_path(value: Any) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise EvidenceBundleError("증빙 경로가 비어 있습니다.")
    path = PurePosixPath(value)
    if value.startswith(("/", "\\")) or "\\" in value or ".." in path.parts:
        raise EvidenceBundleError(f"안전하지 않은 증빙 경로입니다: {value}")
    return path


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise EvidenceBundleError(f"JSON 형식이 올바르지 않습니다: {path}") from error
    if not isinstance(value, dict):
        raise EvidenceBundleError(f"JSON 최상위 값은 객체여야 합니다: {path}")
    return value


def write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def write_json(path: Path, value: dict[str, Any]) -> None:
    write_text_atomic(path, json.dumps(value, ensure_ascii=False, indent=2))


def newest_readiness_report(root: Path) -> Path | None:
    report_root = (root / "artifacts/release-readiness").resolve()
    if not report_root.is_dir():
        return None
    candidates = [
        path.resolve()
        for path in report_root.glob("visionflow-release-readiness-*.json")
        if path.is_file() and not path.is_symlink()
    ]
    return max(candidates, key=lambda path: path.stat().st_mtime, default=None)


def newest_supplemental_report(
    root: Path,
    policy: dict[str, Any],
) -> Path | None:
    report_root = (root / policy["root"]).resolve()
    if not report_root.is_dir():
        return None
    candidates = [
        path.resolve()
        for path in report_root.glob(policy["pattern"])
        if path.is_file() and not path.is_symlink()
    ]
    return max(
        candidates,
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        default=None,
    )


def parse_sidecar(path: Path, expected_name: str, title: str) -> str:
    if not path.is_file() or path.is_symlink():
        raise EvidenceBundleError(f"{title} SHA-256 sidecar가 없습니다: {path}")
    parts = path.read_text(encoding="utf-8-sig").strip().split()
    if len(parts) != 2 or parts[1] != expected_name:
        raise EvidenceBundleError(f"{title} SHA-256 sidecar 형식이 올바르지 않습니다.")
    checksum = parts[0].lower()
    if len(checksum) != 64 or any(
        character not in "0123456789abcdef" for character in checksum
    ):
        raise EvidenceBundleError(f"{title} SHA-256 값이 올바르지 않습니다.")
    return checksum


def verify_sidecar(path: Path, title: str) -> str:
    expected = parse_sidecar(path.with_suffix(".sha256"), path.name, title)
    actual = sha256_file(path)
    if actual != expected:
        raise EvidenceBundleError(f"{title} SHA-256이 sidecar와 다릅니다.")
    return actual


def parse_generated_at(value: Any, title: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise EvidenceBundleError(f"{title} 생성 시각이 없습니다.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise EvidenceBundleError(f"{title} 생성 시각 형식이 올바르지 않습니다.") from error
    if parsed.tzinfo is None:
        raise EvidenceBundleError(f"{title} 생성 시각에 시간대가 없습니다.")
    return parsed.astimezone(timezone.utc)


def validate_supplemental_report(
    report: dict[str, Any],
    policy: dict[str, Any],
    *,
    now: datetime,
) -> None:
    title = str(policy["title"])
    if (
        report.get("schemaVersion") != SCHEMA_VERSION
        or report.get("project") != PROJECT_NAME
        or report.get("operation") != policy["operation"]
    ):
        raise EvidenceBundleError(f"{title} 보고서 식별 정보가 올바르지 않습니다.")
    if report.get("status") not in policy["statuses"]:
        raise EvidenceBundleError(
            f"{title} 상태가 준비 완료가 아닙니다: {report.get('status')}"
        )
    generated = parse_generated_at(report.get("generatedAt"), title)
    age = now.astimezone(timezone.utc) - generated
    if age < -FUTURE_TOLERANCE or age > SUPPLEMENTAL_MAX_AGE:
        raise EvidenceBundleError(f"{title} 보고서가 너무 오래됐거나 미래 시각입니다.")
    operation = report["operation"]
    if operation not in {
        "OFFLINE_TRANSFER_REHEARSAL",
        "HP_OMEN_TRANSFER_DAY",
    }:
        summary = report.get("summary")
        if not isinstance(summary, dict) or summary.get("blocking") != 0:
            raise EvidenceBundleError(f"{title} 보고서에 차단 항목이 있습니다.")

    if operation == "MACHINE_READINESS_PROFILE":
        if report.get("role") != "baseline":
            raise EvidenceBundleError("장비 준비도 보고서가 baseline 역할이 아닙니다.")
        source_identity = report.get("sourceIdentity")
        if (
            not isinstance(source_identity, dict)
            or source_identity.get("status") != "PASS"
        ):
            raise EvidenceBundleError("장비 준비도 소스 동일성 검증이 PASS가 아닙니다.")
    elif operation == "COLD_START_REHEARSAL":
        safety = report.get("safety")
        if (
            not isinstance(safety, dict)
            or safety.get("databaseMutation") is not False
            or safety.get("dockerStarted") is not False
            or safety.get("originalHandoffModified") is not False
        ):
            raise EvidenceBundleError("콜드 스타트 리허설이 비파괴 검증이 아닙니다.")
    elif operation == "TRANSFER_READINESS_GATE":
        safety = report.get("safety")
        if (
            not isinstance(safety, dict)
            or safety.get("databaseMutation") is not False
            or safety.get("externalTransferPerformed") is not False
        ):
            raise EvidenceBundleError("이전 준비도 검증이 비파괴 검증이 아닙니다.")
    elif operation == "OFFLINE_TRANSFER_REHEARSAL":
        safety = report.get("safety")
        if (
            not isinstance(safety, dict)
            or safety.get("databaseMutation") is not False
            or safety.get("dockerStarted") is not False
            or safety.get("gpuExecuted") is not False
            or safety.get("externalTransferPerformed") is not False
            or safety.get("temporaryWorkspaceRemoved") is not True
            or safety.get("sourceFilesModified") is not False
        ):
            raise EvidenceBundleError("오프라인 이관 리허설이 비파괴 검증이 아닙니다.")
    elif operation == "HP_OMEN_TRANSFER_DAY":
        safety = report.get("safety")
        if (
            not isinstance(safety, dict)
            or safety.get("permanentDelete") is not False
            or safety.get("environmentValuesRecorded") is not False
            or safety.get("operatorKeysRecorded") is not False
            or safety.get("modelWeightsIncluded") is not False
            or safety.get("absolutePathsRecorded") is not False
            or safety.get("activationRequiresExplicitConfirmation") is not True
        ):
            raise EvidenceBundleError(
                "HP OMEN 이관 당일 체크포인트 안전 정보가 올바르지 않습니다."
            )
        if not isinstance(report.get("activationReport"), dict):
            raise EvidenceBundleError(
                "HP OMEN 이관 당일 체크포인트에 활성화 증적이 없습니다."
            )


def verify_supplemental_source(
    root: Path,
    path: Path,
    policy: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    operation = policy["operation"]
    relative = path.relative_to(root).as_posix()
    try:
        if operation == "OFFLINE_TRANSFER_REHEARSAL":
            _, report = verify_transfer_rehearsal_report(root, relative)
            return sha256_file(path), report
        if operation == "HP_OMEN_TRANSFER_DAY":
            _, report = verify_transfer_day_checkpoint(
                root,
                relative,
                environment={},
                platform_name=sys.platform,
            )
            return sha256_file(path), report
    except (TransferRehearsalError, TransferDayError) as error:
        raise EvidenceBundleError(str(error)) from error
    checksum = verify_sidecar(path, str(policy["title"]))
    return checksum, read_json(path)


def collect_supplemental_evidence(
    root: Path,
    *,
    now: datetime,
) -> list[dict[str, Any]]:
    entries = []
    for key, policy in SUPPLEMENTAL_POLICIES.items():
        path = newest_supplemental_report(root, policy)
        if path is None:
            entries.append(
                {
                    "key": key,
                    "title": policy["title"],
                    "status": "DEFERRED",
                    "included": False,
                    "archivePath": None,
                    "reason": (
                        f"{policy['root'].as_posix()}에 검증 보고서가 없어 "
                        "이번 번들에는 포함하지 않음"
                    ),
                }
            )
            continue
        allowed_root = (root / policy["root"]).resolve()
        if not is_within(path, allowed_root):
            raise EvidenceBundleError(
                f"{policy['title']} 경로가 허용 영역을 벗어났습니다."
            )
        if path.stat().st_size > MAX_SUPPLEMENTAL_JSON_BYTES:
            raise EvidenceBundleError(
                f"{policy['title']} 보고서 크기가 허용 범위를 초과했습니다."
            )
        checksum, report = verify_supplemental_source(root, path, policy)
        validate_supplemental_report(report, policy, now=now)
        entries.append(
            {
                "key": key,
                "title": policy["title"],
                "status": "PASS",
                "sourcePath": path.relative_to(root).as_posix(),
                "sourceSizeBytes": path.stat().st_size,
                "sourceSha256": checksum,
                "included": True,
                "archivePath": policy["archive"],
                "reason": None,
            }
        )
    return entries


def resolve_report(root: Path, value: str | None) -> Path:
    report_root = (root / "artifacts/release-readiness").resolve()
    if value:
        path = Path(value)
        report = path.resolve() if path.is_absolute() else (root / path).resolve()
    else:
        report = newest_readiness_report(root)
        if report is None:
            raise EvidenceBundleError("릴리스 준비도 JSON 보고서가 없습니다.")
    if not is_within(report, report_root):
        raise EvidenceBundleError(f"릴리스 보고서가 허용 경로를 벗어났습니다: {report}")
    if not report.is_file() or report.is_symlink():
        raise EvidenceBundleError(f"릴리스 준비도 보고서를 찾을 수 없습니다: {report}")
    return report


def validate_readiness_report(report: dict[str, Any]) -> None:
    if report.get("schemaVersion") != SCHEMA_VERSION:
        raise EvidenceBundleError("지원하지 않는 릴리스 준비도 스키마입니다.")
    if report.get("project") != PROJECT_NAME or report.get("scope") != SCOPE:
        raise EvidenceBundleError("VisionFlow 2차 프로젝트 릴리스 보고서가 아닙니다.")
    if report.get("status") not in READY_STATUSES:
        raise EvidenceBundleError(
            f"릴리스 준비 상태가 번들 생성 조건을 충족하지 않습니다: {report.get('status')}"
        )
    summary = report.get("summary")
    if not isinstance(summary, dict) or summary.get("blocked") != 0:
        raise EvidenceBundleError("차단 항목이 있는 릴리스 준비도 보고서입니다.")
    safety = report.get("safety")
    if not isinstance(safety, dict):
        raise EvidenceBundleError("릴리스 준비도 안전 정보가 없습니다.")
    if (
        safety.get("readOnly") is not True
        or safety.get("permanentDelete") is not False
        or safety.get("databaseMutation") is not False
    ):
        raise EvidenceBundleError("읽기 전용 릴리스 준비도 보고서가 아닙니다.")
    checks = report.get("checks")
    if not isinstance(checks, list):
        raise EvidenceBundleError("필수 릴리스 증빙 개수가 올바르지 않습니다.")
    keys = {
        item.get("key")
        for item in checks
        if isinstance(item, dict)
    }
    if (
        not REQUIRED_EVIDENCE_KEYS.issubset(keys)
        or not keys.issubset(EVIDENCE_POLICIES)
        or len(keys) != len(checks)
    ):
        raise EvidenceBundleError("필수 릴리스 증빙 개수가 올바르지 않습니다.")


def validate_evidence(
    root: Path,
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    entries = []
    for check in report["checks"]:
        if not isinstance(check, dict):
            raise EvidenceBundleError("릴리스 검증 항목이 객체가 아닙니다.")
        key = check.get("key")
        if key not in EVIDENCE_POLICIES or key in seen:
            raise EvidenceBundleError(f"알 수 없거나 중복된 릴리스 증빙입니다: {key}")
        seen.add(key)
        if check.get("requirement") != "REQUIRED":
            raise EvidenceBundleError(f"필수 증빙 표시가 올바르지 않습니다: {key}")
        if check.get("status") not in {"PASS", "WARNING"}:
            raise EvidenceBundleError(f"통과하지 않은 릴리스 증빙입니다: {key}")
        evidence = check.get("evidence")
        if not isinstance(evidence, dict):
            raise EvidenceBundleError(f"증빙 파일 정보가 없습니다: {key}")
        relative = safe_relative_path(evidence.get("path"))
        path = root.joinpath(*relative.parts).resolve()
        policy = EVIDENCE_POLICIES[key]
        allowed_root = (root / policy["root"]).resolve()
        if not is_within(path, allowed_root):
            raise EvidenceBundleError(f"증빙 경로가 허용 영역을 벗어났습니다: {relative}")
        if path.suffix.lower() != policy["suffix"]:
            raise EvidenceBundleError(f"증빙 확장자가 올바르지 않습니다: {relative}")
        if not path.is_file() or path.is_symlink():
            raise EvidenceBundleError(f"증빙 파일을 찾을 수 없습니다: {relative}")
        expected_size = evidence.get("sizeBytes")
        expected_checksum = evidence.get("sha256")
        if not isinstance(expected_size, int) or isinstance(expected_size, bool):
            raise EvidenceBundleError(f"증빙 크기가 올바르지 않습니다: {relative}")
        if path.stat().st_size != expected_size:
            raise EvidenceBundleError(f"릴리스 판정 후 증빙 크기가 변경됐습니다: {relative}")
        checksum = sha256_file(path)
        if not isinstance(expected_checksum, str) or checksum != expected_checksum.lower():
            raise EvidenceBundleError(f"릴리스 판정 후 증빙 SHA-256이 변경됐습니다: {relative}")
        if policy["include"]:
            read_json(path)
        entries.append(
            {
                "key": key,
                "sourcePath": relative.as_posix(),
                "sourceSizeBytes": expected_size,
                "sourceSha256": checksum,
                "included": policy["include"],
                "archivePath": policy["archive"],
                "exclusionReason": (
                    None
                    if policy["include"]
                    else "MySQL 백업 원본은 크기와 SHA-256만 기록하고 번들에는 포함하지 않음"
                ),
            }
        )
    if not REQUIRED_EVIDENCE_KEYS.issubset(seen):
        missing = sorted(REQUIRED_EVIDENCE_KEYS - seen)
        raise EvidenceBundleError(f"필수 릴리스 증빙이 누락됐습니다: {missing}")
    return entries


def validate_readiness_html(path: Path, expected_status: str) -> None:
    if path.stat().st_size > 2 * 1024 * 1024:
        raise EvidenceBundleError("릴리스 준비도 HTML이 허용 크기를 초과했습니다.")
    try:
        content = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise EvidenceBundleError("릴리스 준비도 HTML이 UTF-8이 아닙니다.") from error
    lowered = content.lower()
    banned_tokens = ("<script", "<iframe", "<object", "<embed", "javascript:")
    if any(token in lowered for token in banned_tokens):
        raise EvidenceBundleError("릴리스 준비도 HTML에 실행 가능한 콘텐츠가 있습니다.")
    if expected_status not in content:
        raise EvidenceBundleError("릴리스 준비도 HTML과 JSON 상태가 일치하지 않습니다.")


def build_readme(
    report: dict[str, Any],
    entries: list[dict[str, Any]],
    supplemental: list[dict[str, Any]],
) -> str:
    lines = [
        "# VisionFlow 2차 프로젝트 릴리스 증빙",
        "",
        f"- 릴리스 상태: **{report['status']}**",
        f"- 준비도 생성 시각: `{report.get('generatedAt', '-')}`",
        f"- 필수 증빙: {len(entries)}개",
        "- MySQL 백업 원본: 번들 제외, manifest에 크기와 SHA-256만 기록",
        "",
        "## 포함 증빙",
        "",
    ]
    for entry in entries:
        state = "포함" if entry["included"] else "체크섬만 기록"
        lines.append(f"- `{entry['key']}`: {state}")
    lines.extend(["", "## 보조 증빙", ""])
    for entry in supplemental:
        state = (
            "검증 후 포함"
            if entry["included"]
            else f"{entry['status']} — {entry['reason']}"
        )
        lines.append(f"- `{entry['key']}`: {state}")
    lines.extend(["", "## 보류 및 범위 제외", ""])
    for item in report.get("deferred", []):
        if isinstance(item, dict):
            lines.append(
                f"- **{item.get('title', item.get('key', '-'))}**: "
                f"{item.get('status', '-')} — {item.get('reason', '-')}"
            )
    lines.extend(
        [
            "",
            "이 번들은 발표·인수인계용 읽기 전용 증빙입니다. ",
            "SQL, 백업 ZIP, 영상, 탐지 이미지, 모델 가중치, `.env`를 포함하지 않습니다.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_archive_entries(names: list[str]) -> None:
    if len(names) != len(set(names)):
        raise EvidenceBundleError("증빙 ZIP에 중복 경로가 있습니다.")
    for name in names:
        path = PurePosixPath(name)
        if name.startswith(("/", "\\")) or "\\" in name or ".." in path.parts:
            raise EvidenceBundleError(f"증빙 ZIP 경로가 안전하지 않습니다: {name}")
        lowered = name.lower()
        if Path(lowered).suffix in BANNED_ARCHIVE_SUFFIXES or Path(lowered).name.startswith(".env"):
            raise EvidenceBundleError(f"증빙 ZIP에 금지된 파일이 있습니다: {name}")


def verify_bundle(bundle: Path, manifest: dict[str, Any]) -> None:
    try:
        with zipfile.ZipFile(bundle, "r") as archive:
            names = [info.filename for info in archive.infolist() if not info.is_dir()]
            validate_archive_entries(names)
            expected = {
                "README.md",
                "evidence-manifest.json",
                "release-readiness/report.json",
                "release-readiness/report.html",
                *(
                    entry["archivePath"]
                    for entry in manifest["evidence"]
                    if entry["included"]
                ),
                *(
                    entry["archivePath"]
                    for entry in manifest["supplementalEvidence"]
                    if entry["included"]
                ),
            }
            if set(names) != expected:
                raise EvidenceBundleError("증빙 ZIP 파일 목록이 manifest와 다릅니다.")
            archived_manifest = json.loads(
                archive.read("evidence-manifest.json").decode("utf-8-sig")
            )
            if archived_manifest != manifest:
                raise EvidenceBundleError("증빙 ZIP 내부 manifest가 다릅니다.")
            for item in manifest["includedFiles"]:
                data = archive.read(item["archivePath"])
                checksum = hashlib.sha256(data).hexdigest()
                if len(data) != item["sizeBytes"] or checksum != item["sha256"]:
                    raise EvidenceBundleError(
                        f"증빙 ZIP 내부 파일 무결성이 다릅니다: {item['archivePath']}"
                    )
    except zipfile.BadZipFile as error:
        raise EvidenceBundleError("생성된 증빙 ZIP이 손상되었습니다.") from error


def create_bundle(
    root: Path,
    report_path: Path,
    *,
    output_root: Path,
    now: datetime,
) -> tuple[Path, Path, dict[str, Any]]:
    report = read_json(report_path)
    validate_readiness_report(report)
    entries = validate_evidence(root, report)
    supplemental = collect_supplemental_evidence(root, now=now)
    report_html = report_path.with_suffix(".html")
    if not report_html.is_file() or report_html.is_symlink():
        raise EvidenceBundleError(f"릴리스 준비도 HTML을 찾을 수 없습니다: {report_html}")
    validate_readiness_html(report_html, report["status"])

    allowed_output = (root / "artifacts/release-evidence").resolve()
    resolved_output = output_root.resolve()
    if not is_within(resolved_output, allowed_output):
        raise EvidenceBundleError(
            "출력 폴더는 artifacts/release-evidence 내부여야 합니다."
        )
    resolved_output.mkdir(parents=True, exist_ok=True)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    bundle = resolved_output / f"visionflow-release-evidence-{timestamp}.zip"
    if bundle.exists():
        bundle = resolved_output / (
            f"visionflow-release-evidence-{timestamp}-{uuid.uuid4().hex[:8]}.zip"
        )
    sidecar = bundle.with_suffix(".sha256")
    staging = resolved_output / f".staging-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        included_sources = [
            (report_path, "release-readiness/report.json"),
            (report_html, "release-readiness/report.html"),
        ]
        for entry in entries:
            if entry["included"]:
                source = root.joinpath(*PurePosixPath(entry["sourcePath"]).parts)
                included_sources.append((source, entry["archivePath"]))
        for entry in supplemental:
            if entry["included"]:
                source = root.joinpath(*PurePosixPath(entry["sourcePath"]).parts)
                included_sources.append((source, entry["archivePath"]))
        readme_path = staging / "README.md"
        write_text_atomic(
            readme_path,
            build_readme(report, entries, supplemental),
        )
        included_sources.append((readme_path, "README.md"))

        included_files = []
        for source, archive_path in included_sources:
            included_files.append(
                {
                    "archivePath": archive_path,
                    "sizeBytes": source.stat().st_size,
                    "sha256": sha256_file(source),
                }
            )
        manifest = {
            "schemaVersion": SCHEMA_VERSION,
            "project": PROJECT_NAME,
            "scope": SCOPE,
            "operation": "RELEASE_EVIDENCE_BUNDLE",
            "createdAt": now.isoformat(),
            "readiness": {
                "status": report["status"],
                "sourcePath": report_path.relative_to(root).as_posix(),
                "sourceSha256": sha256_file(report_path),
            },
            "evidence": entries,
            "supplementalEvidence": supplemental,
            "includedFiles": included_files,
            "excludedContent": [
                "MySQL backup ZIP and SQL dumps",
                "environment and secret files",
                "AI model weights",
                "images and videos",
            ],
        }
        manifest_path = staging / "evidence-manifest.json"
        write_json(manifest_path, manifest)

        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
            for source, archive_path in included_sources:
                archive.write(source, archive_path)
            archive.write(manifest_path, "evidence-manifest.json")
        verify_bundle(bundle, manifest)
        checksum = sha256_file(bundle)
        write_text_atomic(sidecar, f"{checksum}  {bundle.name}\n")
        return bundle, sidecar, manifest
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VisionFlow release evidence bundle")
    parser.add_argument("--root", default=str(default_root))
    parser.add_argument("--report")
    parser.add_argument("--output", default="artifacts/release-evidence")
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    args = build_parser(default_root).parse_args(arguments)
    root = Path(args.root).resolve()
    try:
        if not root.is_dir():
            raise EvidenceBundleError(f"프로젝트 루트를 찾을 수 없습니다: {root}")
        report_path = resolve_report(root, args.report)
        output = Path(args.output)
        output_root = output.resolve() if output.is_absolute() else (root / output).resolve()
        bundle, sidecar, manifest = create_bundle(
            root,
            report_path,
            output_root=output_root,
            now=datetime.now(timezone.utc),
        )
        print("VisionFlow release evidence: CREATED")
        print(f"Readiness: {manifest['readiness']['status']}")
        print(f"Bundle: {bundle}")
        print(f"SHA-256: {sidecar}")
        return 0
    except (EvidenceBundleError, FileNotFoundError, OSError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
