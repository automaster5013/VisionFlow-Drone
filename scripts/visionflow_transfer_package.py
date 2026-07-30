"""Create and independently verify the final VisionFlow offline transfer package."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import shutil
import stat
import sys
import tempfile
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Iterable

try:
    from visionflow_backup import BackupError, verify_archive
    from visionflow_migration_handoff import (
        HandoffError,
        verify_handoff_bytes,
        verify_handoff_file,
    )
except ModuleNotFoundError:  # pragma: no cover - package import during unit tests
    from scripts.visionflow_backup import BackupError, verify_archive
    from scripts.visionflow_migration_handoff import (
        HandoffError,
        verify_handoff_bytes,
        verify_handoff_file,
    )


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
ARCHIVE_ROOT = "VisionFlow-Transfer-Package"
MANIFEST_NAME = f"{ARCHIVE_ROOT}/TRANSFER_PACKAGE_MANIFEST.json"
README_NAME = f"{ARCHIVE_ROOT}/README.md"
READY_STATUS = "TRANSFER_PACKAGE_READY_WITH_DEFERRED"
READY_TRANSFER_STATUSES = {"TRANSFER_READY", "TRANSFER_READY_WITH_DEFERRED"}
SMARTPHONE_E2E_STATUSES = {"PASS", "DEFERRED"}
CONFIRMATION = "INCLUDE_VERIFIED_BACKUP"
MAX_JSON_BYTES = 5 * 1024 * 1024
FUTURE_TOLERANCE = timedelta(minutes=10)
SENSITIVE_SUFFIXES = {
    ".env",
    ".key",
    ".pem",
    ".p12",
    ".pfx",
    ".jks",
    ".keystore",
    ".pt",
    ".pth",
    ".onnx",
    ".engine",
    ".tflite",
}
SENSITIVE_NAMES = {
    "id_rsa",
    "id_ed25519",
    "rootca-key.pem",
    "credentials.json",
    "secrets.json",
}


class TransferPackageError(RuntimeError):
    """Raised when transfer package inputs or archive content are unsafe."""


def sha256_stream(stream: BinaryIO) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return sha256_stream(stream)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def is_checksum(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def safe_archive_path(value: Any, title: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise TransferPackageError(f"{title}가 비어 있습니다.")
    path = PurePosixPath(value)
    if value.startswith(("/", "\\")) or "\\" in value or ".." in path.parts:
        raise TransferPackageError(f"안전하지 않은 {title}입니다: {value}")
    return path


def safe_project_relative(value: Any, title: str) -> PurePosixPath:
    path = safe_archive_path(value, title)
    if path.parts and path.parts[0].endswith(":"):
        raise TransferPackageError(f"안전하지 않은 {title}입니다: {value}")
    return path


def read_json_bytes(value: bytes, title: str) -> dict[str, Any]:
    if len(value) > MAX_JSON_BYTES:
        raise TransferPackageError(f"{title} 크기가 허용 범위를 초과했습니다.")
    try:
        result = json.loads(value.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TransferPackageError(f"{title} JSON 형식이 올바르지 않습니다.") from error
    if not isinstance(result, dict):
        raise TransferPackageError(f"{title} 최상위 값은 객체여야 합니다.")
    return result


def parse_timestamp(value: Any, title: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise TransferPackageError(f"{title} 생성 시각이 없습니다.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise TransferPackageError(f"{title} 생성 시각 형식이 올바르지 않습니다.") from error
    if parsed.tzinfo is None:
        raise TransferPackageError(f"{title} 생성 시각에 시간대가 없습니다.")
    return parsed.astimezone(timezone.utc)


def parse_sidecar_bytes(value: bytes, expected_name: str, title: str) -> str:
    try:
        parts = value.decode("utf-8-sig").strip().split()
    except UnicodeDecodeError as error:
        raise TransferPackageError(f"{title} sidecar가 UTF-8이 아닙니다.") from error
    if len(parts) != 2 or parts[1] != expected_name:
        raise TransferPackageError(f"{title} sidecar 형식이 올바르지 않습니다.")
    checksum = parts[0].lower()
    if not is_checksum(checksum):
        raise TransferPackageError(f"{title} sidecar SHA-256이 올바르지 않습니다.")
    return checksum


def verify_file_sidecar(path: Path, title: str) -> tuple[Path, str]:
    sidecar = path.with_suffix(".sha256")
    if not sidecar.is_file() or sidecar.is_symlink():
        raise TransferPackageError(f"{title} sidecar를 찾을 수 없습니다: {sidecar}")
    expected = parse_sidecar_bytes(sidecar.read_bytes(), path.name, title)
    actual = sha256_file(path)
    if expected != actual:
        raise TransferPackageError(f"{title} SHA-256이 sidecar와 다릅니다.")
    return sidecar, actual


def write_text_atomic(path: Path, value: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding=encoding)
    os.replace(temporary, path)


def newest_file(directory: Path, pattern: str, title: str) -> Path:
    if not directory.is_dir():
        raise TransferPackageError(f"{title} 폴더가 없습니다: {directory}")
    candidates = [
        path.resolve()
        for path in directory.glob(pattern)
        if path.is_file() and not path.is_symlink()
    ]
    if not candidates:
        raise TransferPackageError(f"{title} 파일이 없습니다.")
    return max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))


def resolve_allowed(
    root: Path,
    value: str | None,
    allowed: Path,
    pattern: str,
    title: str,
) -> Path:
    if value:
        candidate = Path(value)
        path = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    else:
        path = newest_file(allowed, pattern, title)
    if not is_within(path, allowed.resolve()) or not path.is_file() or path.is_symlink():
        raise TransferPackageError(f"{title} 경로가 허용 영역을 벗어났습니다: {path}")
    return path


def resolve_recorded_path(root: Path, value: Any, allowed: Path, title: str) -> Path:
    relative = safe_project_relative(value, title)
    path = root.joinpath(*relative.parts).resolve()
    if not is_within(path, allowed.resolve()) or not path.is_file() or path.is_symlink():
        raise TransferPackageError(f"{title} 경로가 허용 영역을 벗어났습니다: {path}")
    return path


def validate_report_html(path: Path, status_value: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise TransferPackageError(f"전송 준비도 HTML을 찾을 수 없습니다: {path}")
    if path.stat().st_size > 2 * 1024 * 1024:
        raise TransferPackageError("전송 준비도 HTML 크기가 허용 범위를 초과했습니다.")
    try:
        value = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise TransferPackageError("전송 준비도 HTML이 UTF-8이 아닙니다.") from error
    lowered = value.lower()
    if any(token in lowered for token in ("<script", "<iframe", "<object", "<embed", "javascript:")):
        raise TransferPackageError("전송 준비도 HTML에 실행 가능한 콘텐츠가 있습니다.")
    if status_value not in value:
        raise TransferPackageError("전송 준비도 JSON과 HTML 상태가 일치하지 않습니다.")


def validate_readiness_report(
    report: dict[str, Any],
    *,
    now: datetime | None,
    max_age_hours: float | None,
) -> float | None:
    if (
        report.get("schemaVersion") != SCHEMA_VERSION
        or report.get("project") != PROJECT_NAME
        or report.get("scope") != "SECOND_PROJECT_DIGITAL_TWIN"
        or report.get("operation") != "TRANSFER_READINESS_GATE"
    ):
        raise TransferPackageError("VisionFlow 전송 준비도 보고서가 아닙니다.")
    status_value = report.get("status")
    summary = report.get("summary")
    checks = report.get("checks")
    safety = report.get("safety")
    handoff = report.get("handoff")
    if status_value not in READY_TRANSFER_STATUSES:
        raise TransferPackageError(f"전송 준비 상태가 패키징 조건을 충족하지 않습니다: {status_value}")
    if not isinstance(summary, dict) or summary.get("blocking") != 0:
        raise TransferPackageError("전송 준비도 보고서에 차단 항목이 있습니다.")
    if (
        not isinstance(checks, list)
        or not checks
        or any(not isinstance(item, dict) or item.get("status") != "PASS" for item in checks)
    ):
        raise TransferPackageError("전송 준비도 검사가 모두 PASS가 아닙니다.")
    if (
        not isinstance(safety, dict)
        or safety.get("readOnlyInputs") is not True
        or safety.get("databaseMutation") is not False
        or safety.get("dockerStarted") is not False
        or safety.get("externalTransferPerformed") is not False
    ):
        raise TransferPackageError("전송 준비도 안전 메타데이터가 올바르지 않습니다.")
    if (
        not isinstance(handoff, dict)
        or not isinstance(handoff.get("path"), str)
        or not is_checksum(handoff.get("sha256"))
        or handoff.get("smartphoneE2eStatus") not in SMARTPHONE_E2E_STATUSES
    ):
        raise TransferPackageError("전송 준비도 핸드오프 메타데이터가 올바르지 않습니다.")
    generated = parse_timestamp(report.get("generatedAt"), "전송 준비도")
    if now is None or max_age_hours is None:
        return None
    age = now.astimezone(timezone.utc) - generated
    if not timedelta(0) - FUTURE_TOLERANCE <= age <= timedelta(hours=max_age_hours):
        raise TransferPackageError(
            f"전송 준비도 보고서가 {max_age_hours:g}시간 유효 범위를 벗어났습니다: "
            f"{age.total_seconds() / 3600:.2f}시간"
        )
    return age.total_seconds() / 3600


def verify_readiness_file(
    path: Path,
    *,
    now: datetime,
    max_age_hours: float,
) -> dict[str, Any]:
    sidecar, checksum = verify_file_sidecar(path, "전송 준비도 JSON")
    report = read_json_bytes(path.read_bytes(), "전송 준비도 JSON")
    age_hours = validate_readiness_report(
        report,
        now=now,
        max_age_hours=max_age_hours,
    )
    html_path = path.with_suffix(".html")
    validate_report_html(html_path, str(report["status"]))
    return {
        "path": path,
        "sidecar": sidecar,
        "html": html_path,
        "sha256": checksum,
        "report": report,
        "ageHours": round(float(age_hours), 3),
    }


def ensure_backup_manifest_safe(manifest: dict[str, Any]) -> None:
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise TransferPackageError("백업 manifest 파일 목록이 없습니다.")
    for entry in entries:
        if not isinstance(entry, dict):
            raise TransferPackageError("백업 manifest 파일 항목이 올바르지 않습니다.")
        path = safe_archive_path(entry.get("path"), "백업 내부 경로")
        for part in path.parts:
            lowered = part.lower()
            suffix = Path(lowered).suffix
            if (
                lowered.startswith(".env")
                or lowered in SENSITIVE_NAMES
                or suffix in SENSITIVE_SUFFIXES
            ):
                raise TransferPackageError(
                    f"백업에 이관 금지 설정·키·모델 파일이 포함돼 있습니다: {path.as_posix()}"
                )


def resolve_handoff(
    root: Path,
    readiness: dict[str, Any],
    value: str | None,
) -> dict[str, Any]:
    recorded = resolve_recorded_path(
        root,
        readiness["report"]["handoff"]["path"],
        root / "artifacts/migration-handoff",
        "전송 준비도 핸드오프",
    )
    if value:
        selected = resolve_allowed(
            root,
            value,
            root / "artifacts/migration-handoff",
            "visionflow-migration-handoff-*.zip",
            "마이그레이션 핸드오프",
        )
        if selected != recorded:
            raise TransferPackageError("지정한 핸드오프가 전송 준비도 보고서의 핸드오프와 다릅니다.")
    else:
        selected = recorded
    try:
        path, manifest = verify_handoff_file(root, str(selected))
    except HandoffError as error:
        raise TransferPackageError(str(error)) from error
    checksum = sha256_file(path)
    if checksum != str(readiness["report"]["handoff"]["sha256"]).lower():
        raise TransferPackageError("전송 준비도와 실제 핸드오프 SHA-256이 다릅니다.")
    return {
        "path": path,
        "sidecar": path.with_suffix(".sha256"),
        "sha256": checksum,
        "manifest": manifest,
    }


def resolve_backup(
    root: Path,
    handoff: dict[str, Any],
    value: str | None,
) -> dict[str, Any]:
    metadata = handoff["manifest"].get("verifiedMySqlBackup")
    if not isinstance(metadata, dict) or metadata.get("included") is not False:
        raise TransferPackageError("핸드오프에 검증된 MySQL 백업 메타데이터가 없습니다.")
    if value:
        path = resolve_allowed(
            root,
            value,
            root / "backups",
            "visionflow-backup-*.zip",
            "MySQL 백업",
        )
    else:
        path = resolve_recorded_path(
            root,
            metadata.get("sourcePath"),
            root / "backups",
            "핸드오프 MySQL 백업",
        )
    expected_size = metadata.get("sizeBytes")
    expected_sha = str(metadata.get("sha256", "")).lower()
    if (
        not isinstance(expected_size, int)
        or isinstance(expected_size, bool)
        or expected_size < 0
        or not is_checksum(expected_sha)
    ):
        raise TransferPackageError("핸드오프 MySQL 백업 메타데이터가 올바르지 않습니다.")
    if path.stat().st_size != expected_size:
        raise TransferPackageError("MySQL 백업 크기가 핸드오프 메타데이터와 다릅니다.")
    actual_sha = sha256_file(path)
    if actual_sha != expected_sha:
        raise TransferPackageError("MySQL 백업 SHA-256이 핸드오프 메타데이터와 다릅니다.")
    try:
        verification = verify_archive(path)
    except (BackupError, OSError, json.JSONDecodeError) as error:
        raise TransferPackageError(str(error)) from error
    ensure_backup_manifest_safe(verification["manifest"])
    return {
        "path": path,
        "sha256": actual_sha,
        "verification": verification,
        "metadata": metadata,
    }


def file_entry(path: Path, archive_path: str) -> dict[str, Any]:
    return {
        "archivePath": safe_archive_path(archive_path, "패키지 파일 경로").as_posix(),
        "sizeBytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def build_readme(
    readiness: dict[str, Any],
    handoff: dict[str, Any],
    backup: dict[str, Any],
) -> str:
    return "\n".join(
        [
            "# VisionFlow HP OMEN 최종 오프라인 이관 세트",
            "",
            f"- 패키지 상태: **{READY_STATUS}**",
            f"- 전송 준비도: **{readiness['report']['status']}**",
            f"- LG baseline: **{handoff['manifest']['baseline']['status']}**",
            f"- 릴리스 증빙: **{handoff['manifest']['evidence']['readinessStatus']}**",
            f"- 스마트폰 실센서 HTTPS E2E: **{handoff['manifest']['evidence']['smartphoneE2eStatus']}**",
            f"- MySQL 백업: `{backup['path'].name}`",
            "",
            "## 보안 주의",
            "",
            "이 패키지에는 실제 MySQL 백업과 AI 스냅샷 등 운영 데이터가 포함될 수 있습니다.",
            "공개 저장소·공개 링크에 업로드하지 말고 암호화된 외장 매체나 접근 통제 저장소로만 옮기세요.",
            "`.env`, 운영자 키, 인증서 개인키, 모델 가중치는 포함하지 않습니다.",
            "",
            "## HP OMEN 적용 순서",
            "",
            "1. 바깥 `.sha256`과 패키지 ZIP을 함께 복사합니다.",
            "2. `run-visionflow-transfer-package-verify.bat --bundle <실제 ZIP 경로>`로 검증합니다.",
            "3. `handoff/`의 마이그레이션 핸드오프를 검증하고 안전 소스를 풉니다.",
            "4. `database/`의 백업을 프로젝트 `backups/`에 복사한 뒤 백업 검증기를 실행합니다.",
            "5. `.env.docker.example`에서 HP OMEN 전용 `.env.docker`를 새로 작성합니다.",
            "6. MySQL 복원과 Docker 콜드 스타트를 수행한 뒤 acceptance를 실행합니다.",
            "7. `best.pt` 이식과 HP OMEN의 새 LAN IP·인증서 HTTPS 재확인을 진행합니다.",
            "",
            "DJI Mini 4 Pro 전용 연동은 3차 프로젝트 범위입니다.",
            "",
        ]
    )


def create_transfer_package(
    root: Path,
    *,
    readiness_value: str | None,
    handoff_value: str | None,
    backup_value: str | None,
    output_root: Path,
    max_readiness_age_hours: float,
    confirmation: str,
    now: datetime,
) -> tuple[Path, Path, dict[str, Any]]:
    if confirmation != CONFIRMATION:
        raise TransferPackageError(
            f"실제 MySQL 백업 포함에는 --confirm {CONFIRMATION}이 필요합니다."
        )
    if max_readiness_age_hours <= 0:
        raise TransferPackageError("전송 준비도 최대 유효시간은 양수여야 합니다.")
    allowed_output = (root / "artifacts/transfer-package").resolve()
    output = output_root.resolve()
    if not is_within(output, allowed_output):
        raise TransferPackageError("출력 폴더는 artifacts/transfer-package 내부여야 합니다.")

    readiness_path = resolve_allowed(
        root,
        readiness_value,
        root / "artifacts/transfer-readiness",
        "visionflow-transfer-readiness-*.json",
        "전송 준비도 JSON",
    )
    readiness = verify_readiness_file(
        readiness_path,
        now=now,
        max_age_hours=max_readiness_age_hours,
    )
    handoff = resolve_handoff(root, readiness, handoff_value)
    backup = resolve_backup(root, handoff, backup_value)

    output.mkdir(parents=True, exist_ok=True)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    bundle = output / f"visionflow-transfer-package-{timestamp}.zip"
    if bundle.exists():
        bundle = output / f"visionflow-transfer-package-{timestamp}-{uuid.uuid4().hex[:8]}.zip"
    sidecar = bundle.with_suffix(".sha256")
    staging = output / f".transfer-package-{uuid.uuid4().hex}"
    staging.mkdir()
    temporary_bundle = bundle.with_suffix(".tmp")
    try:
        readme = staging / "README.md"
        readme.write_text(
            build_readme(readiness, handoff, backup),
            encoding="utf-8",
        )
        backup_sidecar = staging / f"{backup['path'].stem}.sha256"
        backup_sidecar.write_text(
            f"{backup['sha256']}  {backup['path'].name}\n",
            encoding="utf-8",
        )
        sources = [
            (readme, README_NAME),
            (
                handoff["path"],
                f"{ARCHIVE_ROOT}/handoff/{handoff['path'].name}",
            ),
            (
                handoff["sidecar"],
                f"{ARCHIVE_ROOT}/handoff/{handoff['sidecar'].name}",
            ),
            (
                readiness["path"],
                f"{ARCHIVE_ROOT}/readiness/{readiness['path'].name}",
            ),
            (
                readiness["sidecar"],
                f"{ARCHIVE_ROOT}/readiness/{readiness['sidecar'].name}",
            ),
            (
                readiness["html"],
                f"{ARCHIVE_ROOT}/readiness/{readiness['html'].name}",
            ),
            (
                backup["path"],
                f"{ARCHIVE_ROOT}/database/{backup['path'].name}",
            ),
            (
                backup_sidecar,
                f"{ARCHIVE_ROOT}/database/{backup_sidecar.name}",
            ),
        ]
        files = [file_entry(path, archive_path) for path, archive_path in sources]
        by_name = {Path(item["archivePath"]).name: item["archivePath"] for item in files}
        manifest = {
            "schemaVersion": SCHEMA_VERSION,
            "project": PROJECT_NAME,
            "scope": "SECOND_PROJECT_DIGITAL_TWIN",
            "operation": "TRANSFER_PACKAGE",
            "packageId": str(uuid.uuid4()),
            "generatedAt": now.isoformat(),
            "status": READY_STATUS,
            "files": files,
            "handoff": {
                "archivePath": by_name[handoff["path"].name],
                "sidecarArchivePath": by_name[handoff["sidecar"].name],
                "sourcePath": handoff["path"].relative_to(root).as_posix(),
                "sha256": handoff["sha256"],
                "baselineStatus": handoff["manifest"]["baseline"]["status"],
                "releaseReadinessStatus": handoff["manifest"]["evidence"]["readinessStatus"],
                "smartphoneE2eStatus": handoff["manifest"]["evidence"]["smartphoneE2eStatus"],
            },
            "transferReadiness": {
                "archivePath": by_name[readiness["path"].name],
                "sidecarArchivePath": by_name[readiness["sidecar"].name],
                "htmlArchivePath": by_name[readiness["html"].name],
                "sourcePath": readiness["path"].relative_to(root).as_posix(),
                "sha256": readiness["sha256"],
                "status": readiness["report"]["status"],
                "ageHoursAtPackaging": readiness["ageHours"],
                "maxAgeHours": max_readiness_age_hours,
                "handoffSha256": readiness["report"]["handoff"]["sha256"],
                "smartphoneE2eStatus": readiness["report"]["handoff"][
                    "smartphoneE2eStatus"
                ],
            },
            "databaseBackup": {
                "archivePath": by_name[backup["path"].name],
                "sidecarArchivePath": by_name[backup_sidecar.name],
                "recordedSourcePath": backup["metadata"]["sourcePath"],
                "selectedSourcePath": backup["path"].relative_to(root).as_posix(),
                "sizeBytes": backup["path"].stat().st_size,
                "sha256": backup["sha256"],
                "internalStatus": backup["verification"]["status"],
                "databaseName": backup["verification"]["databaseName"],
                "createdAt": backup["verification"]["createdAt"],
                "fileCount": backup["verification"]["fileCount"],
            },
            "deferred": [
                {"key": "hp-omen-runtime-restore", "status": "DEFERRED"},
                {"key": "gpu-best-model", "status": "DEFERRED"},
                {
                    "key": "hp-target-smartphone-https-revalidation",
                    "status": "DEFERRED",
                },
                {"key": "dji-mini4-pro", "status": "OUT_OF_SCOPE"},
            ],
            "safety": {
                "containsOperationalDatabaseBackup": True,
                "containsEnvironmentFiles": False,
                "containsOperatorKeys": False,
                "containsPrivateKeys": False,
                "containsModelWeights": False,
                "originalInputsModified": False,
                "externalTransferPerformed": False,
            },
        }
        manifest_path = staging / "TRANSFER_PACKAGE_MANIFEST.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        with zipfile.ZipFile(
            temporary_bundle,
            "w",
            zipfile.ZIP_DEFLATED,
            allowZip64=True,
        ) as archive:
            for source, archive_path in sources:
                compression = (
                    zipfile.ZIP_STORED
                    if source.suffix.lower() == ".zip"
                    else zipfile.ZIP_DEFLATED
                )
                archive.write(source, archive_path, compress_type=compression)
            archive.write(manifest_path, MANIFEST_NAME)
        os.replace(temporary_bundle, bundle)
        write_text_atomic(sidecar, f"{sha256_file(bundle)}  {bundle.name}\n")
        verify_transfer_package_file(root, str(bundle))
        return bundle, sidecar, manifest
    except Exception:
        temporary_bundle.unlink(missing_ok=True)
        bundle.unlink(missing_ok=True)
        sidecar.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def validate_file_entry(entry: Any) -> tuple[str, int, str]:
    if not isinstance(entry, dict):
        raise TransferPackageError("패키지 파일 항목이 객체가 아닙니다.")
    path = safe_archive_path(entry.get("archivePath"), "패키지 파일 경로").as_posix()
    size = entry.get("sizeBytes")
    checksum = str(entry.get("sha256", "")).lower()
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise TransferPackageError(f"패키지 파일 크기가 올바르지 않습니다: {path}")
    if not is_checksum(checksum):
        raise TransferPackageError(f"패키지 파일 SHA-256이 올바르지 않습니다: {path}")
    return path, size, checksum


def read_archive_entry(archive: zipfile.ZipFile, name: str, title: str) -> bytes:
    try:
        return archive.read(name)
    except KeyError as error:
        raise TransferPackageError(f"{title} 파일이 패키지에 없습니다: {name}") from error


def verify_transfer_package_bytes(
    value: bytes | Path,
) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(value, "r") as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise TransferPackageError("이관 패키지에 중복 경로가 있습니다.")
            for info in infos:
                path = safe_archive_path(info.filename, "이관 패키지 내부 경로")
                if not path.as_posix().startswith(f"{ARCHIVE_ROOT}/"):
                    raise TransferPackageError(f"허용되지 않은 이관 패키지 경로입니다: {path}")
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise TransferPackageError(f"이관 패키지에 심볼릭 링크가 있습니다: {path}")

            manifest = read_json_bytes(
                read_archive_entry(archive, MANIFEST_NAME, "패키지 manifest"),
                "TRANSFER_PACKAGE_MANIFEST.json",
            )
            if (
                manifest.get("schemaVersion") != SCHEMA_VERSION
                or manifest.get("project") != PROJECT_NAME
                or manifest.get("scope") != "SECOND_PROJECT_DIGITAL_TWIN"
                or manifest.get("operation") != "TRANSFER_PACKAGE"
                or manifest.get("status") != READY_STATUS
            ):
                raise TransferPackageError("VisionFlow 최종 이관 패키지가 아닙니다.")
            files = manifest.get("files")
            if not isinstance(files, list):
                raise TransferPackageError("이관 패키지 파일 목록이 없습니다.")
            expected = {MANIFEST_NAME}
            entries: dict[str, tuple[int, str]] = {}
            for entry in files:
                archive_path, size, checksum = validate_file_entry(entry)
                if archive_path in expected:
                    raise TransferPackageError(f"패키지 manifest에 중복 경로가 있습니다: {archive_path}")
                expected.add(archive_path)
                entries[archive_path] = (size, checksum)
                info = archive.getinfo(archive_path)
                if info.file_size != size:
                    raise TransferPackageError(f"패키지 파일 크기가 다릅니다: {archive_path}")
                with archive.open(archive_path, "r") as stream:
                    if sha256_stream(stream) != checksum:
                        raise TransferPackageError(f"패키지 파일 SHA-256이 다릅니다: {archive_path}")
            if set(names) != expected:
                raise TransferPackageError("이관 패키지 파일 목록이 manifest와 다릅니다.")

            handoff = manifest.get("handoff")
            readiness = manifest.get("transferReadiness")
            backup = manifest.get("databaseBackup")
            safety = manifest.get("safety")
            if not all(isinstance(item, dict) for item in (handoff, readiness, backup, safety)):
                raise TransferPackageError("이관 패키지 교차 검증 메타데이터가 없습니다.")
            referenced = {
                README_NAME,
                handoff.get("archivePath"),
                handoff.get("sidecarArchivePath"),
                readiness.get("archivePath"),
                readiness.get("sidecarArchivePath"),
                readiness.get("htmlArchivePath"),
                backup.get("archivePath"),
                backup.get("sidecarArchivePath"),
            }
            if None in referenced or referenced != set(entries):
                raise TransferPackageError("이관 패키지 파일 참조가 manifest와 다릅니다.")
            if (
                safety.get("containsOperationalDatabaseBackup") is not True
                or safety.get("containsEnvironmentFiles") is not False
                or safety.get("containsOperatorKeys") is not False
                or safety.get("containsPrivateKeys") is not False
                or safety.get("containsModelWeights") is not False
                or safety.get("originalInputsModified") is not False
            ):
                raise TransferPackageError("이관 패키지 안전 메타데이터가 올바르지 않습니다.")

            handoff_path = str(handoff["archivePath"])
            handoff_bytes = read_archive_entry(archive, handoff_path, "핸드오프")
            handoff_sha = sha256_bytes(handoff_bytes)
            if handoff_sha != handoff.get("sha256"):
                raise TransferPackageError("패키지 핸드오프 SHA-256 메타데이터가 다릅니다.")
            if parse_sidecar_bytes(
                read_archive_entry(archive, str(handoff["sidecarArchivePath"]), "핸드오프 sidecar"),
                Path(handoff_path).name,
                "핸드오프",
            ) != handoff_sha:
                raise TransferPackageError("패키지 핸드오프 sidecar가 실제 파일과 다릅니다.")
            try:
                handoff_manifest = verify_handoff_bytes(handoff_bytes)
            except HandoffError as error:
                raise TransferPackageError(str(error)) from error

            readiness_path = str(readiness["archivePath"])
            readiness_bytes = read_archive_entry(archive, readiness_path, "전송 준비도")
            readiness_sha = sha256_bytes(readiness_bytes)
            if readiness_sha != readiness.get("sha256"):
                raise TransferPackageError("패키지 전송 준비도 SHA-256 메타데이터가 다릅니다.")
            if parse_sidecar_bytes(
                read_archive_entry(
                    archive,
                    str(readiness["sidecarArchivePath"]),
                    "전송 준비도 sidecar",
                ),
                Path(readiness_path).name,
                "전송 준비도",
            ) != readiness_sha:
                raise TransferPackageError("패키지 전송 준비도 sidecar가 실제 파일과 다릅니다.")
            readiness_report = read_json_bytes(readiness_bytes, "전송 준비도 JSON")
            validate_readiness_report(readiness_report, now=None, max_age_hours=None)
            html_bytes = read_archive_entry(
                archive,
                str(readiness["htmlArchivePath"]),
                "전송 준비도 HTML",
            )
            try:
                html_value = html_bytes.decode("utf-8-sig")
            except UnicodeDecodeError as error:
                raise TransferPackageError("패키지 전송 준비도 HTML이 UTF-8이 아닙니다.") from error
            if str(readiness_report["status"]) not in html_value:
                raise TransferPackageError("패키지 전송 준비도 JSON과 HTML 상태가 다릅니다.")
            if (
                readiness_report["handoff"].get("sha256") != handoff_sha
                or readiness.get("handoffSha256") != handoff_sha
                or readiness.get("status") != readiness_report.get("status")
            ):
                raise TransferPackageError("패키지 전송 준비도와 핸드오프 동일성이 다릅니다.")
            handoff_smartphone_status = handoff_manifest["evidence"].get(
                "smartphoneE2eStatus"
            )
            if (
                handoff.get("smartphoneE2eStatus")
                != handoff_smartphone_status
                or readiness_report["handoff"].get("smartphoneE2eStatus")
                != handoff_smartphone_status
                or readiness.get("smartphoneE2eStatus")
                != handoff_smartphone_status
            ):
                raise TransferPackageError(
                    "패키지 스마트폰 E2E 증적 계보가 핸드오프·전송 준비도와 다릅니다."
                )
            age_at_packaging = readiness.get("ageHoursAtPackaging")
            max_age = readiness.get("maxAgeHours")
            if (
                not isinstance(age_at_packaging, (int, float))
                or isinstance(age_at_packaging, bool)
                or not isinstance(max_age, (int, float))
                or isinstance(max_age, bool)
                or age_at_packaging < -FUTURE_TOLERANCE.total_seconds() / 3600
                or age_at_packaging > max_age
            ):
                raise TransferPackageError("패키징 시점의 전송 준비도 유효시간이 올바르지 않습니다.")

            backup_path = str(backup["archivePath"])
            backup_sha = str(backup.get("sha256", "")).lower()
            if not is_checksum(backup_sha):
                raise TransferPackageError("패키지 MySQL 백업 SHA-256 메타데이터가 올바르지 않습니다.")
            if parse_sidecar_bytes(
                read_archive_entry(archive, str(backup["sidecarArchivePath"]), "백업 sidecar"),
                Path(backup_path).name,
                "MySQL 백업",
            ) != backup_sha:
                raise TransferPackageError("패키지 MySQL 백업 sidecar가 실제 파일과 다릅니다.")
            if entries[backup_path][1] != backup_sha:
                raise TransferPackageError("패키지 MySQL 백업 파일 항목과 메타데이터가 다릅니다.")
            with tempfile.TemporaryDirectory(prefix="visionflow-transfer-verify-") as directory:
                extracted = Path(directory) / Path(backup_path).name
                with archive.open(backup_path, "r") as source, extracted.open("wb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
                try:
                    verification = verify_archive(extracted)
                except (BackupError, OSError, json.JSONDecodeError) as error:
                    raise TransferPackageError(str(error)) from error
                ensure_backup_manifest_safe(verification["manifest"])
            handoff_backup = handoff_manifest.get("verifiedMySqlBackup")
            if (
                not isinstance(handoff_backup, dict)
                or handoff_backup.get("sha256") != backup_sha
                or handoff_backup.get("sizeBytes") != backup.get("sizeBytes")
                or verification.get("status") != backup.get("internalStatus")
                or verification.get("databaseName") != backup.get("databaseName")
                or verification.get("fileCount") != backup.get("fileCount")
            ):
                raise TransferPackageError("핸드오프·패키지·MySQL 백업 메타데이터가 다릅니다.")
            return manifest
    except (zipfile.BadZipFile, KeyError) as error:
        raise TransferPackageError("이관 패키지 ZIP 또는 manifest가 손상되었습니다.") from error


def verify_transfer_package_file(root: Path, value: str) -> tuple[Path, dict[str, Any]]:
    candidate = Path(value)
    bundle = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    allowed = (root / "artifacts/transfer-package").resolve()
    if not is_within(bundle, allowed) or not bundle.is_file() or bundle.is_symlink():
        raise TransferPackageError(f"이관 패키지 경로가 허용 영역을 벗어났습니다: {bundle}")
    _, checksum = verify_file_sidecar(bundle, "최종 이관 패키지")
    manifest = verify_transfer_package_bytes(bundle)
    if checksum != sha256_file(bundle):
        raise TransferPackageError("이관 패키지 검증 중 파일이 변경됐습니다.")
    return bundle, manifest


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VisionFlow final offline transfer package")
    parser.add_argument("--root", default=str(default_root))
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create", help="최종 오프라인 이관 ZIP 생성")
    create.add_argument("--readiness")
    create.add_argument("--handoff")
    create.add_argument("--backup")
    create.add_argument("--output", default="artifacts/transfer-package")
    create.add_argument("--max-readiness-age-hours", type=float, default=24.0)
    create.add_argument("--confirm", default="")
    verify = subparsers.add_parser("verify", help="기존 최종 이관 ZIP 독립 재검증")
    verify.add_argument("--bundle", required=True)
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    args = build_parser(default_root).parse_args(arguments)
    root = Path(args.root).resolve()
    try:
        if not root.is_dir():
            raise TransferPackageError(f"프로젝트 루트를 찾을 수 없습니다: {root}")
        if args.command == "create":
            output_value = Path(args.output)
            output = (
                output_value.resolve()
                if output_value.is_absolute()
                else (root / output_value).resolve()
            )
            bundle, sidecar, manifest = create_transfer_package(
                root,
                readiness_value=args.readiness,
                handoff_value=args.handoff,
                backup_value=args.backup,
                output_root=output,
                max_readiness_age_hours=args.max_readiness_age_hours,
                confirmation=args.confirm,
                now=datetime.now(timezone.utc),
            )
            print("VisionFlow transfer package: CREATED")
            print(f"Status: {manifest['status']}")
            print(f"Bundle: {bundle}")
            print(f"SHA-256: {sidecar}")
            print("[SENSITIVE] 실제 MySQL 백업이 포함됐습니다. 공개 저장소에 업로드하지 마세요.")
        else:
            bundle, manifest = verify_transfer_package_file(root, args.bundle)
            print("VisionFlow transfer package: VERIFIED")
            print(f"Status: {manifest['status']}")
            print(f"Bundle: {bundle}")
        return 0
    except (
        TransferPackageError,
        HandoffError,
        BackupError,
        FileNotFoundError,
        OSError,
    ) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
