"""Prepare, activate, and verify a VisionFlow HP OMEN workspace."""

from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping, Sequence

try:
    from visionflow_backup import BackupError, verify_archive
    from visionflow_gpu_preflight_evidence import (
        READY_STATUS as GPU_PREFLIGHT_STATUS,
        GpuPreflightEvidenceError,
        verify_evidence as verify_gpu_preflight_evidence,
    )
    from visionflow_machine_readiness import (
        MachineReadinessError,
        read_profile,
        verify_extracted_source,
    )
    from visionflow_migration_handoff import (
        HandoffError,
        verify_handoff_bytes,
        verify_source_bytes,
    )
    from visionflow_transfer_package import (
        READY_STATUS as TRANSFER_PACKAGE_STATUS,
        TransferPackageError,
        verify_transfer_package_bytes,
        verify_transfer_package_file,
    )
except ModuleNotFoundError:  # pragma: no cover - package import during tests
    from scripts.visionflow_backup import BackupError, verify_archive
    from scripts.visionflow_gpu_preflight_evidence import (
        READY_STATUS as GPU_PREFLIGHT_STATUS,
        GpuPreflightEvidenceError,
        verify_evidence as verify_gpu_preflight_evidence,
    )
    from scripts.visionflow_machine_readiness import (
        MachineReadinessError,
        read_profile,
        verify_extracted_source,
    )
    from scripts.visionflow_migration_handoff import (
        HandoffError,
        verify_handoff_bytes,
        verify_source_bytes,
    )
    from scripts.visionflow_transfer_package import (
        READY_STATUS as TRANSFER_PACKAGE_STATUS,
        TransferPackageError,
        verify_transfer_package_bytes,
        verify_transfer_package_file,
    )


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
PREPARE_OPERATION = "HP_OMEN_WORKSPACE_PREPARE"
PREFLIGHT_OPERATION = "HP_OMEN_ACTIVATION_PREFLIGHT"
ACTIVATE_OPERATION = "HP_OMEN_RUNTIME_ACTIVATION"
RECOVERY_OPERATION = "HP_OMEN_ACTIVATION_RECOVERY"
PREPARED_STATUS = "HP_OMEN_WORKSPACE_PREPARED_WITH_DEFERRED"
PREFLIGHT_STATUS = "HP_OMEN_ACTIVATION_PREFLIGHT_READY"
PREFLIGHT_BLOCKED_STATUS = "HP_OMEN_ACTIVATION_PREFLIGHT_BLOCKED"
ACTIVATED_STATUS = "HP_OMEN_RUNTIME_READY_WITH_DEFERRED"
RECOVERED_STATUS = "HP_OMEN_PRE_ACTIVATION_STATE_RECOVERED"
PREPARE_CONFIRMATION = "PREPARE_HP_OMEN_WORKSPACE"
ACTIVATE_CONFIRMATION = "ACTIVATE_HP_OMEN_WITH_DB_RESTORE"
RECOVERY_CONFIRMATION = "RECOVER_FAILED_HP_OMEN_ACTIVATION"
REPORT_ROOT = Path("artifacts/hp-omen-restore")
MODEL_DEFAULT = Path("03_ai-server/visionflow-ai/models/best.pt")
REQUIRED_ACCEPTANCE_KEYS = (
    "VISIONFLOW_ACCEPTANCE_VIEWER_KEY",
    "VISIONFLOW_ACCEPTANCE_OPERATOR_KEY",
    "VISIONFLOW_ACCEPTANCE_ADMIN_KEY",
)
ACTIVATION_SCRIPTS = {
    "restore": "run-visionflow-restore.bat",
    "gpu-stack": "run-visionflow-gpu-preflight.bat",
    "target-profile": "run-visionflow-machine-profile.bat",
    "machine-comparison": "run-visionflow-machine-compare.bat",
    "acceptance": "run-visionflow-acceptance.bat",
    "benchmark": "run-visionflow-ai-benchmark.bat",
}
ACTIVATION_STEPS = (
    ("restore", "검증된 MySQL·영속 증적 복원"),
    ("gpu-stack", "RTX GPU·best.pt 검증 및 전체 스택 기동"),
    ("target-profile", "HP OMEN 대상 장비 프로필"),
    ("machine-comparison", "LG GRAM·HP OMEN 소스 및 도구 비교"),
    ("acceptance", "Demo·RBAC·브라우저 세션 통합 인수 테스트"),
    ("benchmark", "HP OMEN GPU AI 성능 기준선"),
)
PREFLIGHT_CHECKS = (
    ("windows-target", "Windows HP OMEN 대상 환경"),
    ("prepared-workspace", "검증된 새 HP 작업공간"),
    ("environment-file", "HP 전용 .env.docker"),
    ("gpu-compose", "GPU Compose 오버레이"),
    ("best-model", "파인튜닝 best.pt"),
    ("activation-scripts", "최초 구동 필수 스크립트"),
    ("acceptance-keys", "통합 인수 테스트 역할 키"),
)


class HpOmenRestoreError(RuntimeError):
    """Raised when an HP OMEN restore operation cannot proceed safely."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    output: str


Runner = Callable[[Sequence[str], Path, int], CommandResult]


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_checksum(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as error:
        raise HpOmenRestoreError(
            f"산출물 경로가 HP 작업공간 밖에 있습니다: {path}"
        ) from error


def write_bytes_atomic(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(value)
    os.replace(temporary, path)


def write_text_atomic(
    path: Path,
    value: str,
    *,
    encoding: str = "utf-8",
) -> None:
    write_bytes_atomic(path, value.encode(encoding))


def read_json(path: Path, title: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise HpOmenRestoreError(f"{title} 파일을 찾을 수 없습니다: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HpOmenRestoreError(
            f"{title} JSON 형식이 올바르지 않습니다."
        ) from error
    if not isinstance(value, dict):
        raise HpOmenRestoreError(f"{title} 최상위 값은 객체여야 합니다.")
    return value


def parse_single_sidecar(path: Path, title: str) -> str:
    sidecar = path.with_suffix(".sha256")
    if not sidecar.is_file() or sidecar.is_symlink():
        raise HpOmenRestoreError(f"{title} sidecar가 없습니다: {sidecar}")
    try:
        lines = [
            line.strip().split()
            for line in sidecar.read_text(
                encoding="utf-8-sig"
            ).splitlines()
            if line.strip()
        ]
    except UnicodeDecodeError as error:
        raise HpOmenRestoreError(
            f"{title} sidecar가 UTF-8이 아닙니다."
        ) from error
    if (
        len(lines) != 1
        or len(lines[0]) != 2
        or lines[0][1] != path.name
        or not is_checksum(lines[0][0])
    ):
        raise HpOmenRestoreError(f"{title} sidecar 형식이 올바르지 않습니다.")
    expected = lines[0][0].lower()
    if sha256_file(path) != expected:
        raise HpOmenRestoreError(f"{title} SHA-256이 sidecar와 다릅니다.")
    return expected


def write_multi_sidecar(sidecar: Path, paths: Sequence[Path]) -> None:
    write_text_atomic(
        sidecar,
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in paths),
    )


def verify_multi_sidecar(
    sidecar: Path,
    expected: Sequence[Path],
    title: str,
) -> None:
    if not sidecar.is_file() or sidecar.is_symlink():
        raise HpOmenRestoreError(f"{title} sidecar가 없습니다: {sidecar}")
    try:
        lines = [
            line.strip().split()
            for line in sidecar.read_text(
                encoding="utf-8-sig"
            ).splitlines()
            if line.strip()
        ]
    except UnicodeDecodeError as error:
        raise HpOmenRestoreError(
            f"{title} sidecar가 UTF-8이 아닙니다."
        ) from error
    if len(lines) != len(expected) or any(
        len(parts) != 2 for parts in lines
    ):
        raise HpOmenRestoreError(f"{title} sidecar 형식이 올바르지 않습니다.")
    recorded = {parts[1]: parts[0].lower() for parts in lines}
    if set(recorded) != {path.name for path in expected}:
        raise HpOmenRestoreError(f"{title} sidecar 파일 목록이 다릅니다.")
    for path in expected:
        if (
            not is_checksum(recorded[path.name])
            or recorded[path.name] != sha256_file(path)
        ):
            raise HpOmenRestoreError(
                f"{title} SHA-256이 다릅니다: {path.name}"
            )


def safe_relative(value: Any, title: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise HpOmenRestoreError(f"{title} 경로가 비어 있습니다.")
    path = PurePosixPath(value)
    if (
        value.startswith(("/", "\\"))
        or "\\" in value
        or ".." in path.parts
        or path.is_absolute()
    ):
        raise HpOmenRestoreError(f"{title} 경로가 안전하지 않습니다: {value}")
    return path


def archive_read(
    archive: zipfile.ZipFile,
    value: Any,
    title: str,
) -> bytes:
    path = safe_relative(value, title).as_posix()
    try:
        return archive.read(path)
    except KeyError as error:
        raise HpOmenRestoreError(
            f"{title} 파일이 ZIP에 없습니다: {path}"
        ) from error


def resolve_package(value: str) -> Path:
    package = Path(value).resolve()
    if (
        not package.is_file()
        or package.is_symlink()
        or package.suffix.lower() != ".zip"
    ):
        raise HpOmenRestoreError(
            f"최종 이관 패키지를 찾을 수 없습니다: {package}"
        )
    return package


def inspect_package(
    value: str,
) -> tuple[Path, dict[str, Any], str]:
    package = resolve_package(value)
    checksum = parse_single_sidecar(package, "최종 이관 패키지")
    manifest = verify_transfer_package_bytes(package)
    if manifest.get("status") != TRANSFER_PACKAGE_STATUS:
        raise HpOmenRestoreError(
            "HP OMEN 복원에 사용할 수 있는 최종 이관 패키지가 아닙니다."
        )
    return package, manifest, checksum


def artifact_entry(root: Path, key: str, path: Path) -> dict[str, Any]:
    return {
        "key": key,
        "path": relative_path(root, path),
        "sizeBytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def copy_verified_bytes(
    destination_root: Path,
    relative_directory: str,
    source_name: str,
    value: bytes,
) -> Path:
    name = Path(source_name).name
    if name != source_name or not name:
        raise HpOmenRestoreError(
            f"추출 파일명이 올바르지 않습니다: {source_name}"
        )
    target = destination_root / relative_directory / name
    write_bytes_atomic(target, value)
    return target


def extract_source(
    destination: Path,
    source_bytes: bytes,
    source_result: dict[str, Any],
) -> None:
    manifest = source_result.get("manifest")
    if not isinstance(manifest, dict) or not isinstance(
        manifest.get("files"), list
    ):
        raise HpOmenRestoreError("안전 소스 manifest가 없습니다.")
    with zipfile.ZipFile(io.BytesIO(source_bytes), "r") as archive:
        for item in manifest["files"]:
            if not isinstance(item, dict):
                raise HpOmenRestoreError(
                    "안전 소스 manifest 파일 항목이 올바르지 않습니다."
                )
            relative = safe_relative(item.get("path"), "안전 소스")
            archive_path = f"VisionFlow-Drone/{relative.as_posix()}"
            value = archive.read(archive_path)
            target = destination.joinpath(*relative.parts)
            write_bytes_atomic(target, value)
        manifest_bytes = archive.read(
            "VisionFlow-Drone/SOURCE_MANIFEST.json"
        )
        readme_bytes = archive.read(
            "VisionFlow-Drone/README-MIGRATION.md"
        )
    write_bytes_atomic(destination / "SOURCE_MANIFEST.json", manifest_bytes)
    write_bytes_atomic(destination / "README-MIGRATION.md", readme_bytes)


def render_prepare_html(report: dict[str, Any]) -> str:
    artifacts = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['key']))}</td>"
        f"<td>{html.escape(str(item['path']))}</td>"
        f"<td><code>{html.escape(str(item['sha256']))}</code></td>"
        "</tr>"
        for item in report["artifacts"]
    )
    deferred = "".join(
        "<li>"
        f"<strong>{html.escape(str(item['status']))}</strong> "
        f"{html.escape(str(item['key']))}: "
        f"{html.escape(str(item['reason']))}"
        "</li>"
        for item in report["deferred"]
    )
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VisionFlow HP OMEN 작업공간 준비</title><style>
body{{margin:0;background:#eef3f8;color:#0f172a;font-family:Arial,'Noto Sans KR',sans-serif}}
main{{max-width:1100px;margin:32px auto;padding:0 20px}}section{{background:#fff;border:1px solid #dbe4ee;border-radius:16px;padding:24px;margin:16px 0}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid #e2e8f0;text-align:left}}code{{word-break:break-all}}
.status{{color:#047857;font-weight:800}}</style></head><body><main>
<section><h1>HP OMEN 작업공간 준비</h1><p class="status">{html.escape(report['status'])}</p><p>{html.escape(report['generatedAt'])}</p></section>
<section><h2>검증된 산출물</h2><table><tr><th>종류</th><th>경로</th><th>SHA-256</th></tr>{artifacts}</table></section>
<section><h2>HP에서 계속할 항목</h2><ul>{deferred}</ul></section>
<section><h2>안전</h2><p>기존 대상 폴더 덮어쓰기, DB 변경, Docker 실행, 영구 삭제, 외부 전송을 수행하지 않았습니다.</p></section>
</main></body></html>"""


def write_prepare_report(
    root: Path,
    report: dict[str, Any],
    now: datetime,
) -> tuple[Path, Path, Path]:
    output = root / REPORT_ROOT
    output.mkdir(parents=True, exist_ok=True)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    base = output / f"visionflow-hp-omen-prepare-{timestamp}"
    if base.with_suffix(".json").exists():
        base = output / (
            f"visionflow-hp-omen-prepare-{timestamp}-{uuid.uuid4().hex[:8]}"
        )
    json_path = base.with_suffix(".json")
    html_path = base.with_suffix(".html")
    sidecar = base.with_suffix(".sha256")
    write_text_atomic(
        json_path,
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    write_text_atomic(html_path, render_prepare_html(report))
    write_multi_sidecar(sidecar, [json_path, html_path])
    return json_path, html_path, sidecar


def prepare_workspace(
    package_value: str,
    destination_value: str,
    *,
    confirmation: str,
    now: datetime,
) -> tuple[Path, dict[str, Any]]:
    if confirmation != PREPARE_CONFIRMATION:
        raise HpOmenRestoreError(
            "새 HP 작업공간 생성에는 "
            f"--confirm {PREPARE_CONFIRMATION}이 필요합니다."
        )
    package, package_manifest, package_sha = inspect_package(package_value)
    destination = Path(destination_value).resolve()
    if destination.exists():
        raise HpOmenRestoreError(
            "대상 작업공간이 이미 존재합니다. 덮어쓰지 않으므로 "
            f"존재하지 않는 새 경로를 지정하세요: {destination}"
        )
    parent = destination.parent
    if (
        not parent.is_dir()
        or parent.is_symlink()
        or destination == parent
    ):
        raise HpOmenRestoreError(
            f"대상 작업공간의 부모 폴더가 올바르지 않습니다: {parent}"
        )
    staging = parent / (
        f".{destination.name}.visionflow-prepare-{uuid.uuid4().hex[:8]}"
    )
    staging.mkdir()
    try:
        with zipfile.ZipFile(package, "r") as outer:
            handoff_meta = package_manifest["handoff"]
            readiness_meta = package_manifest["transferReadiness"]
            backup_meta = package_manifest["databaseBackup"]
            handoff_bytes = archive_read(
                outer,
                handoff_meta.get("archivePath"),
                "마이그레이션 핸드오프",
            )
            handoff_sidecar_bytes = archive_read(
                outer,
                handoff_meta.get("sidecarArchivePath"),
                "마이그레이션 핸드오프 sidecar",
            )
            readiness_bytes = archive_read(
                outer,
                readiness_meta.get("archivePath"),
                "전송 준비도",
            )
            readiness_sidecar_bytes = archive_read(
                outer,
                readiness_meta.get("sidecarArchivePath"),
                "전송 준비도 sidecar",
            )
            readiness_html_bytes = archive_read(
                outer,
                readiness_meta.get("htmlArchivePath"),
                "전송 준비도 HTML",
            )
            backup_bytes = archive_read(
                outer,
                backup_meta.get("archivePath"),
                "MySQL 백업",
            )
            backup_sidecar_bytes = archive_read(
                outer,
                backup_meta.get("sidecarArchivePath"),
                "MySQL 백업 sidecar",
            )

        handoff_manifest = verify_handoff_bytes(handoff_bytes)
        with zipfile.ZipFile(io.BytesIO(handoff_bytes), "r") as handoff_zip:
            source_meta = handoff_manifest["source"]
            evidence_meta = handoff_manifest["evidence"]
            baseline_meta = handoff_manifest["baseline"]
            source_bytes = archive_read(
                handoff_zip,
                source_meta.get("archivePath"),
                "안전 소스 ZIP",
            )
            source_sidecar_bytes = archive_read(
                handoff_zip,
                source_meta.get("sidecarArchivePath"),
                "안전 소스 sidecar",
            )
            evidence_bytes = archive_read(
                handoff_zip,
                evidence_meta.get("archivePath"),
                "릴리스 증빙 ZIP",
            )
            evidence_sidecar_bytes = archive_read(
                handoff_zip,
                evidence_meta.get("sidecarArchivePath"),
                "릴리스 증빙 sidecar",
            )
            baseline_bytes = archive_read(
                handoff_zip,
                baseline_meta.get("archivePath"),
                "LG machine baseline",
            )
            baseline_sidecar_bytes = archive_read(
                handoff_zip,
                baseline_meta.get("sidecarArchivePath"),
                "LG machine baseline sidecar",
            )
            baseline_html_bytes = archive_read(
                handoff_zip,
                baseline_meta.get("htmlArchivePath"),
                "LG machine baseline HTML",
            )

        source_result = verify_source_bytes(source_bytes)
        extract_source(staging, source_bytes, source_result)
        artifacts: dict[str, Path] = {}

        package_target = staging / (
            "artifacts/transfer-package/" + package.name
        )
        package_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(package, package_target)
        write_text_atomic(
            package_target.with_suffix(".sha256"),
            f"{package_sha}  {package_target.name}\n",
        )
        artifacts["transfer-package"] = package_target

        artifacts["migration-handoff"] = copy_verified_bytes(
            staging,
            "artifacts/migration-handoff",
            Path(str(handoff_meta["archivePath"])).name,
            handoff_bytes,
        )
        copy_verified_bytes(
            staging,
            "artifacts/migration-handoff",
            Path(str(handoff_meta["sidecarArchivePath"])).name,
            handoff_sidecar_bytes,
        )
        artifacts["transfer-readiness"] = copy_verified_bytes(
            staging,
            "artifacts/transfer-readiness",
            Path(str(readiness_meta["archivePath"])).name,
            readiness_bytes,
        )
        copy_verified_bytes(
            staging,
            "artifacts/transfer-readiness",
            Path(str(readiness_meta["sidecarArchivePath"])).name,
            readiness_sidecar_bytes,
        )
        copy_verified_bytes(
            staging,
            "artifacts/transfer-readiness",
            Path(str(readiness_meta["htmlArchivePath"])).name,
            readiness_html_bytes,
        )
        artifacts["database-backup"] = copy_verified_bytes(
            staging,
            "backups",
            Path(str(backup_meta["archivePath"])).name,
            backup_bytes,
        )
        copy_verified_bytes(
            staging,
            "backups",
            Path(str(backup_meta["sidecarArchivePath"])).name,
            backup_sidecar_bytes,
        )
        artifacts["source-release"] = copy_verified_bytes(
            staging,
            "artifacts/source-release",
            Path(str(source_meta["archivePath"])).name,
            source_bytes,
        )
        copy_verified_bytes(
            staging,
            "artifacts/source-release",
            Path(str(source_meta["sidecarArchivePath"])).name,
            source_sidecar_bytes,
        )
        artifacts["release-evidence"] = copy_verified_bytes(
            staging,
            "artifacts/release-evidence",
            Path(str(evidence_meta["archivePath"])).name,
            evidence_bytes,
        )
        copy_verified_bytes(
            staging,
            "artifacts/release-evidence",
            Path(str(evidence_meta["sidecarArchivePath"])).name,
            evidence_sidecar_bytes,
        )
        artifacts["lg-baseline"] = copy_verified_bytes(
            staging,
            "artifacts/machine-readiness",
            Path(str(baseline_meta["archivePath"])).name,
            baseline_bytes,
        )
        copy_verified_bytes(
            staging,
            "artifacts/machine-readiness",
            Path(str(baseline_meta["sidecarArchivePath"])).name,
            baseline_sidecar_bytes,
        )
        copy_verified_bytes(
            staging,
            "artifacts/machine-readiness",
            Path(str(baseline_meta["htmlArchivePath"])).name,
            baseline_html_bytes,
        )

        source_identity = verify_extracted_source(
            staging,
            staging / "SOURCE_MANIFEST.json",
        )
        verified_package, verified_manifest = verify_transfer_package_file(
            staging,
            relative_path(staging, package_target),
        )
        backup_verification = verify_archive(artifacts["database-backup"])
        baseline_profile = read_profile(
            staging,
            relative_path(staging, artifacts["lg-baseline"]),
            "baseline",
        )
        baseline_source = baseline_profile.get("sourceIdentity")
        if (
            verified_package != package_target
            or verified_manifest.get("status") != TRANSFER_PACKAGE_STATUS
            or not isinstance(baseline_source, dict)
            or baseline_source.get("manifestSha256")
            != source_identity.get("manifestSha256")
            or package_manifest["databaseBackup"].get("sha256")
            != sha256_file(artifacts["database-backup"])
            or backup_verification.get("status") != "VALID"
        ):
            raise HpOmenRestoreError(
                "준비된 HP 작업공간의 소스·기준선·백업 연결이 다릅니다."
            )

        report = {
            "schemaVersion": SCHEMA_VERSION,
            "project": PROJECT_NAME,
            "scope": "HP_OMEN_TARGET_RESTORE",
            "operation": PREPARE_OPERATION,
            "prepareId": str(uuid.uuid4()),
            "generatedAt": now.isoformat(),
            "status": PREPARED_STATUS,
            "sourcePackage": {
                "fileName": package.name,
                "sizeBytes": package.stat().st_size,
                "sha256": package_sha,
                "status": package_manifest.get("status"),
            },
            "sourceIdentity": source_identity,
            "artifacts": [
                artifact_entry(staging, key, path)
                for key, path in artifacts.items()
            ],
            "databaseBackup": {
                "status": backup_verification.get("status"),
                "databaseName": backup_verification.get("databaseName"),
                "fileCount": backup_verification.get("fileCount"),
                "payloadBytes": backup_verification.get("payloadBytes"),
            },
            "deferred": [
                {
                    "key": "environment-file",
                    "status": "DEFERRED",
                    "reason": "HP 전용 .env.docker를 안전하게 별도 작성",
                },
                {
                    "key": "gpu-best-model",
                    "status": "DEFERRED",
                    "reason": "RTX 5060 드라이버와 best.pt 별도 배치 후 검증",
                },
                {
                    "key": "database-restore",
                    "status": "DEFERRED",
                    "reason": "activate 단계의 별도 확인 문자열 후 실행",
                },
                {
                    "key": "hp-target-smartphone-https-revalidation",
                    "status": "DEFERRED",
                    "reason": "HP 런타임 안정화 후 새 LAN IP·인증서 접속 재검증",
                },
                {
                    "key": "dji-mini4-pro",
                    "status": "OUT_OF_SCOPE",
                    "reason": "DJI 전용 RTSP·기체 종속 연동은 3차 프로젝트",
                },
            ],
            "safety": {
                "existingDestinationOverwritten": False,
                "databaseMutation": False,
                "dockerStarted": False,
                "permanentDelete": False,
                "externalTransferPerformed": False,
                "environmentValuesRecorded": False,
                "modelWeightsIncluded": False,
            },
        }
        report_path, _, _ = write_prepare_report(staging, report, now)
        verify_prepare_report(staging, relative_path(staging, report_path))
        os.replace(staging, destination)
        final_report = destination / report_path.relative_to(staging)
        return final_report, report
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def resolve_report(root: Path, value: str) -> Path:
    candidate = Path(value)
    path = (
        candidate.resolve()
        if candidate.is_absolute()
        else (root / candidate).resolve()
    )
    allowed = (root / REPORT_ROOT).resolve()
    if (
        not is_within(path, allowed)
        or not path.is_file()
        or path.is_symlink()
        or path.suffix.lower() != ".json"
    ):
        raise HpOmenRestoreError(
            f"HP OMEN 보고서 경로가 허용 영역을 벗어났습니다: {path}"
        )
    return path


def artifact_map(
    root: Path,
    report: dict[str, Any],
) -> dict[str, Path]:
    source = report.get("artifacts")
    if not isinstance(source, list):
        raise HpOmenRestoreError("HP OMEN 산출물 목록이 없습니다.")
    result: dict[str, Path] = {}
    for item in source:
        if not isinstance(item, dict):
            raise HpOmenRestoreError("HP OMEN 산출물 항목이 올바르지 않습니다.")
        key = item.get("key")
        relative = item.get("path")
        if (
            not isinstance(key, str)
            or key in result
            or not isinstance(relative, str)
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
        ):
            raise HpOmenRestoreError("HP OMEN 산출물 경로가 올바르지 않습니다.")
        path = (root / relative).resolve()
        if (
            not is_within(path, root.resolve())
            or not path.is_file()
            or path.is_symlink()
            or path.stat().st_size != item.get("sizeBytes")
            or not is_checksum(item.get("sha256"))
            or sha256_file(path) != item.get("sha256")
        ):
            raise HpOmenRestoreError(
                f"HP OMEN 산출물 동일성이 다릅니다: {relative}"
            )
        result[key] = path
    return result


def verify_prepare_report(
    root: Path,
    value: str,
) -> tuple[Path, dict[str, Any]]:
    report_path = resolve_report(root, value)
    report = read_json(report_path, "HP OMEN 작업공간 준비 보고서")
    html_path = report_path.with_suffix(".html")
    verify_multi_sidecar(
        report_path.with_suffix(".sha256"),
        [report_path, html_path],
        "HP OMEN 작업공간 준비 보고서",
    )
    if (
        report.get("schemaVersion") != SCHEMA_VERSION
        or report.get("project") != PROJECT_NAME
        or report.get("operation") != PREPARE_OPERATION
        or report.get("status") != PREPARED_STATUS
    ):
        raise HpOmenRestoreError(
            "VisionFlow HP OMEN 작업공간 준비 완료 보고서가 아닙니다."
        )
    safety = report.get("safety")
    if (
        not isinstance(safety, dict)
        or safety.get("existingDestinationOverwritten") is not False
        or safety.get("databaseMutation") is not False
        or safety.get("dockerStarted") is not False
        or safety.get("permanentDelete") is not False
        or safety.get("externalTransferPerformed") is not False
        or safety.get("environmentValuesRecorded") is not False
        or safety.get("modelWeightsIncluded") is not False
    ):
        raise HpOmenRestoreError(
            "HP OMEN 작업공간 준비 안전 메타데이터가 올바르지 않습니다."
        )
    artifacts = artifact_map(root, report)
    required = {
        "transfer-package",
        "migration-handoff",
        "transfer-readiness",
        "database-backup",
        "source-release",
        "release-evidence",
        "lg-baseline",
    }
    if set(artifacts) != required:
        raise HpOmenRestoreError(
            "HP OMEN 작업공간 준비 산출물 종류가 다릅니다."
        )
    try:
        source_identity = verify_extracted_source(
            root,
            root / "SOURCE_MANIFEST.json",
        )
        _, package_manifest = verify_transfer_package_file(
            root,
            relative_path(root, artifacts["transfer-package"]),
        )
        backup = verify_archive(artifacts["database-backup"])
        baseline = read_profile(
            root,
            relative_path(root, artifacts["lg-baseline"]),
            "baseline",
        )
    except (
        BackupError,
        MachineReadinessError,
        TransferPackageError,
    ) as error:
        raise HpOmenRestoreError(str(error)) from error
    baseline_source = baseline.get("sourceIdentity")
    if (
        package_manifest.get("status") != TRANSFER_PACKAGE_STATUS
        or package_manifest.get("databaseBackup", {}).get("sha256")
        != sha256_file(artifacts["database-backup"])
        or backup.get("status") != "VALID"
        or not isinstance(baseline_source, dict)
        or baseline_source.get("manifestSha256")
        != source_identity.get("manifestSha256")
        or report.get("sourceIdentity") != source_identity
    ):
        raise HpOmenRestoreError(
            "HP OMEN 작업공간 준비 보고서의 교차 연결이 다릅니다."
        )
    source_package = report.get("sourcePackage")
    if (
        not isinstance(source_package, dict)
        or source_package.get("sha256")
        != sha256_file(artifacts["transfer-package"])
        or source_package.get("status") != TRANSFER_PACKAGE_STATUS
    ):
        raise HpOmenRestoreError(
            "HP OMEN 원본 이관 패키지 동일성이 다릅니다."
        )
    try:
        html_value = html_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise HpOmenRestoreError(
            "HP OMEN 작업공간 준비 HTML이 UTF-8이 아닙니다."
        ) from error
    if html_value != render_prepare_html(report):
        raise HpOmenRestoreError(
            "HP OMEN 작업공간 준비 JSON과 HTML이 일치하지 않습니다."
        )
    if any(
        token in html_value.lower()
        for token in ("<script", "<iframe", "<object", "<embed", "javascript:")
    ):
        raise HpOmenRestoreError(
            "HP OMEN 작업공간 준비 HTML에 실행 가능한 콘텐츠가 있습니다."
        )
    return report_path, report


def default_runner(
    command: Sequence[str],
    root: Path,
    timeout_seconds: int,
) -> CommandResult:
    try:
        completed = subprocess.run(
            list(command),
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
        return CommandResult(completed.returncode, output)
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout or ""
        stderr = error.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        output = stdout
        if stderr:
            output += "\n[stderr]\n" + stderr
        output += f"\n[TIMEOUT] {timeout_seconds} seconds\n"
        return CommandResult(124, output)


def command_for_batch(
    root: Path,
    script_name: str,
    arguments: Sequence[str],
    *,
    platform_name: str,
) -> list[str]:
    script = (root / "scripts" / script_name).resolve()
    if platform_name == "nt":
        return [
            os.environ.get("COMSPEC", "cmd.exe"),
            "/d",
            "/c",
            str(script),
            *arguments,
        ]
    return [str(script), *arguments]


def artifact_candidates(root: Path, pattern: str) -> set[Path]:
    return {
        path.resolve()
        for path in root.glob(pattern)
        if path.is_file() and not path.is_symlink()
    }


def run_activation_step(
    root: Path,
    run_directory: Path,
    *,
    key: str,
    command: Sequence[str],
    pattern: str | None,
    timeout_seconds: int,
    runner: Runner,
) -> tuple[dict[str, Any], Path | None]:
    before = artifact_candidates(root, pattern) if pattern else set()
    title = dict(ACTIVATION_STEPS)[key]
    print(f"[RUN] {title}")
    started = time.monotonic()
    result = runner(command, root, timeout_seconds)
    duration = round((time.monotonic() - started) * 1000)
    log_path = run_directory / f"{key}.log"
    write_text_atomic(log_path, result.output)
    if result.output:
        print(result.output, end="" if result.output.endswith("\n") else "\n")
    error: str | None = None
    artifact: Path | None = None
    created: list[Path] = []
    if pattern:
        created = sorted(
            artifact_candidates(root, pattern) - before,
            key=lambda path: (path.stat().st_mtime_ns, path.name),
        )
        if len(created) == 1:
            artifact = created[0]
    if result.returncode != 0:
        error = f"명령 종료 코드가 {result.returncode}입니다."
    elif pattern:
        if len(created) != 1:
            error = (
                f"새 산출물이 정확히 1개여야 하지만 {len(created)}개입니다: "
                f"{pattern}"
            )
        else:
            artifact = created[0]
    return (
        {
            "key": key,
            "title": title,
            "status": "PASS" if error is None else "FAILED",
            "exitCode": result.returncode,
            "durationMs": duration,
            "logPath": relative_path(root, log_path),
            "artifactPath": (
                relative_path(root, artifact) if artifact else None
            ),
            "error": error,
        },
        artifact,
    )


def newest_prepare_report(root: Path) -> Path:
    candidates = [
        path.resolve()
        for path in (root / REPORT_ROOT).glob(
            "visionflow-hp-omen-prepare-*.json"
        )
        if path.is_file() and not path.is_symlink()
    ]
    if not candidates:
        raise HpOmenRestoreError(
            "HP OMEN 작업공간 준비 보고서를 찾을 수 없습니다."
        )
    return max(
        candidates,
        key=lambda path: (path.stat().st_mtime_ns, path.name),
    )


def evaluate_activation_readiness(
    root: Path,
    *,
    prepare_report_value: str | None,
    model_value: str,
    environment: Mapping[str, str],
    platform_name: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    titles = dict(PREFLIGHT_CHECKS)
    checks: list[dict[str, Any]] = []
    context: dict[str, Any] = {}

    def record(
        key: str,
        *,
        error: str | None = None,
        detail: str | None = None,
    ) -> None:
        checks.append(
            {
                "key": key,
                "title": titles[key],
                "status": "PASS" if error is None else "BLOCKED",
                "detail": detail if error is None else error,
            }
        )

    if platform_name == "nt":
        record(
            "windows-target",
            detail="Windows 대상 장비로 확인했습니다.",
        )
    else:
        record(
            "windows-target",
            error=(
                "HP OMEN 런타임 활성화는 Windows 대상 장비에서만 "
                "지원합니다."
            ),
        )

    try:
        report_path = (
            resolve_report(root, prepare_report_value)
            if prepare_report_value
            else newest_prepare_report(root)
        )
        _, prepare_report = verify_prepare_report(
            root,
            relative_path(root, report_path),
        )
        prepared_artifacts = artifact_map(root, prepare_report)
        context.update(
            {
                "preparePath": report_path,
                "prepareReport": prepare_report,
                "preparedArtifacts": prepared_artifacts,
            }
        )
        record(
            "prepared-workspace",
            detail=relative_path(root, report_path),
        )
    except (
        HpOmenRestoreError,
        BackupError,
        MachineReadinessError,
        TransferPackageError,
        FileNotFoundError,
        OSError,
        zipfile.BadZipFile,
        KeyError,
    ) as error:
        record("prepared-workspace", error=str(error))

    environment_file = (root / ".env.docker").resolve()
    if environment_file.is_file() and not environment_file.is_symlink():
        context["environmentFile"] = environment_file
        record("environment-file", detail=".env.docker")
    else:
        record(
            "environment-file",
            error=(
                "HP 전용 .env.docker가 없습니다. 예제에서 새로 작성하세요."
            ),
        )

    gpu_compose = (root / "compose.gpu.yaml").resolve()
    if gpu_compose.is_file() and not gpu_compose.is_symlink():
        context["gpuCompose"] = gpu_compose
        record("gpu-compose", detail="compose.gpu.yaml")
    else:
        record(
            "gpu-compose",
            error="GPU Compose 오버레이가 없습니다: compose.gpu.yaml",
        )

    model_relative = Path(model_value)
    expected_model_directory = (
        root / "03_ai-server/visionflow-ai/models"
    ).resolve()
    if (
        model_relative.is_absolute()
        or ".." in model_relative.parts
    ):
        record(
            "best-model",
            error="best.pt 경로는 HP 프로젝트 내부여야 합니다.",
        )
    else:
        model = (root / model_relative).resolve()
        if (
            not is_within(model, root.resolve())
            or model.parent != expected_model_directory
            or not model.is_file()
            or model.is_symlink()
            or model.suffix.lower() != ".pt"
        ):
            record(
                "best-model",
                error=f"best.pt를 찾을 수 없습니다: {model}",
            )
        else:
            context["model"] = model
            record(
                "best-model",
                detail=(
                    f"{relative_path(root, model)} "
                    f"({model.stat().st_size} bytes, "
                    f"SHA-256 {sha256_file(model)})"
                ),
            )

    missing_scripts = [
        name
        for name in ACTIVATION_SCRIPTS.values()
        if not (root / "scripts" / name).is_file()
        or (root / "scripts" / name).is_symlink()
    ]
    if missing_scripts:
        record(
            "activation-scripts",
            error=(
                "HP 활성화 필수 스크립트가 없습니다: "
                f"{sorted(missing_scripts)}"
            ),
        )
    else:
        context["activationScripts"] = tuple(
            ACTIVATION_SCRIPTS.values()
        )
        record(
            "activation-scripts",
            detail=f"{len(ACTIVATION_SCRIPTS)}개 스크립트 확인",
        )

    missing_keys = [
        key
        for key in REQUIRED_ACCEPTANCE_KEYS
        if not str(environment.get(key, "")).strip()
    ]
    if missing_keys:
        record(
            "acceptance-keys",
            error=(
                "통합 인수 테스트용 역할 키 환경변수가 없습니다: "
                f"{missing_keys}"
            ),
        )
    else:
        context["acceptanceKeyNames"] = REQUIRED_ACCEPTANCE_KEYS
        record(
            "acceptance-keys",
            detail=(
                "VIEWER·OPERATOR·ADMIN 역할 키 존재 여부 확인 "
                "(값은 기록하지 않음)"
            ),
        )
    return checks, context


def validate_activation_preflight(
    root: Path,
    *,
    prepare_report_value: str | None,
    model_value: str,
    confirmation: str,
    environment: Mapping[str, str],
    platform_name: str,
) -> tuple[Path, dict[str, Any], Path, dict[str, Path]]:
    if confirmation != ACTIVATE_CONFIRMATION:
        raise HpOmenRestoreError(
            "HP DB 복원과 GPU 스택 기동에는 "
            f"--confirm {ACTIVATE_CONFIRMATION}이 필요합니다."
        )
    checks, context = evaluate_activation_readiness(
        root,
        prepare_report_value=prepare_report_value,
        model_value=model_value,
        environment=environment,
        platform_name=platform_name,
    )
    failed = [item for item in checks if item["status"] != "PASS"]
    if failed:
        raise HpOmenRestoreError(
            f"{failed[0]['title']}: {failed[0]['detail']}"
        )
    return (
        context["preparePath"],
        context["prepareReport"],
        context["model"],
        context["preparedArtifacts"],
    )


def render_preflight_html(report: dict[str, Any]) -> str:
    checks = "".join(
        "<tr>"
        f"<td>{index}</td>"
        f"<td>{html.escape(str(item['title']))}</td>"
        f"<td>{html.escape(str(item['status']))}</td>"
        f"<td>{html.escape(str(item['detail']))}</td>"
        "</tr>"
        for index, item in enumerate(report["checks"], start=1)
    )
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VisionFlow HP OMEN 활성화 사전점검</title><style>
body{{margin:0;background:#eef3f8;color:#0f172a;font-family:Arial,'Noto Sans KR',sans-serif}}main{{max-width:1100px;margin:32px auto;padding:0 20px}}
section{{background:#fff;border:1px solid #dbe4ee;border-radius:16px;padding:24px;margin:16px 0}}table{{width:100%;border-collapse:collapse}}
th,td{{padding:10px;border-bottom:1px solid #e2e8f0;text-align:left;vertical-align:top}}.ready{{color:#047857;font-weight:800}}.blocked{{color:#b91c1c;font-weight:800}}</style></head>
<body><main><section><h1>HP OMEN 활성화 사전점검</h1><p class="{'ready' if report['status'] == PREFLIGHT_STATUS else 'blocked'}">{html.escape(report['status'])}</p>
<p>{html.escape(report['generatedAt'])}</p></section><section><h2>점검 결과</h2><table><tr><th>#</th><th>항목</th><th>상태</th><th>내용</th></tr>{checks}</table></section>
<section><h2>안전</h2><p>MySQL 복원, Docker·서비스 기동, 영구 삭제를 수행하지 않았고 환경값·운영자 키·모델 원본을 보고서에 기록하지 않았습니다.</p></section></main></body></html>"""


def write_preflight_report(
    root: Path,
    report: dict[str, Any],
    now: datetime,
) -> tuple[Path, Path, Path]:
    output = root / REPORT_ROOT
    output.mkdir(parents=True, exist_ok=True)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    base = output / f"visionflow-hp-omen-preflight-{timestamp}"
    if base.with_suffix(".json").exists():
        base = output / (
            f"visionflow-hp-omen-preflight-{timestamp}-"
            f"{uuid.uuid4().hex[:8]}"
        )
    json_path = base.with_suffix(".json")
    html_path = base.with_suffix(".html")
    sidecar = base.with_suffix(".sha256")
    write_text_atomic(
        json_path,
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    write_text_atomic(html_path, render_preflight_html(report))
    write_multi_sidecar(sidecar, [json_path, html_path])
    return json_path, html_path, sidecar


def create_activation_preflight(
    root: Path,
    *,
    prepare_report_value: str | None,
    model_value: str,
    environment: Mapping[str, str],
    platform_name: str,
    now: datetime,
) -> tuple[Path, dict[str, Any], int]:
    checks, context = evaluate_activation_readiness(
        root,
        prepare_report_value=prepare_report_value,
        model_value=model_value,
        environment=environment,
        platform_name=platform_name,
    )
    blocking = sum(item["status"] != "PASS" for item in checks)
    prepare_path = context.get("preparePath")
    model = context.get("model")
    report: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "scope": "HP_OMEN_TARGET_RESTORE",
        "operation": PREFLIGHT_OPERATION,
        "preflightId": str(uuid.uuid4()),
        "generatedAt": now.isoformat(),
        "status": (
            PREFLIGHT_STATUS
            if blocking == 0
            else PREFLIGHT_BLOCKED_STATUS
        ),
        "prepareReport": (
            artifact_entry(root, "prepare-report", prepare_path)
            if isinstance(prepare_path, Path)
            else None
        ),
        "model": (
            {
                "path": relative_path(root, model),
                "sizeBytes": model.stat().st_size,
                "sha256": sha256_file(model),
            }
            if isinstance(model, Path)
            else None
        ),
        "inputs": {
            "environmentFile": ".env.docker",
            "gpuCompose": "compose.gpu.yaml",
            "requiredScripts": sorted(ACTIVATION_SCRIPTS.values()),
            "acceptanceKeyNames": list(REQUIRED_ACCEPTANCE_KEYS),
        },
        "checks": checks,
        "summary": {
            "total": len(PREFLIGHT_CHECKS),
            "passed": len(PREFLIGHT_CHECKS) - blocking,
            "blocking": blocking,
        },
        "safety": {
            "databaseMutation": False,
            "dockerStarted": False,
            "serviceStarted": False,
            "permanentDelete": False,
            "environmentValuesRecorded": False,
            "operatorKeysRecorded": False,
            "modelWeightsIncluded": False,
        },
    }
    report_path, _, _ = write_preflight_report(root, report, now)
    if blocking == 0:
        verify_activation_preflight_report(
            root,
            relative_path(root, report_path),
            environment=environment,
            platform_name=platform_name,
        )
    return report_path, report, 0 if blocking == 0 else 1


def verify_activation_preflight_report(
    root: Path,
    value: str,
    *,
    environment: Mapping[str, str],
    platform_name: str,
) -> tuple[Path, dict[str, Any]]:
    report_path = resolve_report(root, value)
    report = read_json(report_path, "HP OMEN 활성화 사전점검 보고서")
    html_path = report_path.with_suffix(".html")
    verify_multi_sidecar(
        report_path.with_suffix(".sha256"),
        [report_path, html_path],
        "HP OMEN 활성화 사전점검 보고서",
    )
    if (
        report.get("schemaVersion") != SCHEMA_VERSION
        or report.get("project") != PROJECT_NAME
        or report.get("operation") != PREFLIGHT_OPERATION
        or report.get("status") != PREFLIGHT_STATUS
    ):
        raise HpOmenRestoreError(
            "VisionFlow HP OMEN 활성화 사전점검 통과 보고서가 아닙니다."
        )
    checks = report.get("checks")
    summary = report.get("summary")
    if (
        not isinstance(checks, list)
        or [item.get("key") for item in checks] != [
            key for key, _ in PREFLIGHT_CHECKS
        ]
        or any(item.get("status") != "PASS" for item in checks)
        or not isinstance(summary, dict)
        or summary.get("total") != len(PREFLIGHT_CHECKS)
        or summary.get("passed") != len(PREFLIGHT_CHECKS)
        or summary.get("blocking") != 0
    ):
        raise HpOmenRestoreError(
            "HP OMEN 활성화 사전점검 집계가 올바르지 않습니다."
        )
    safety = report.get("safety")
    if (
        not isinstance(safety, dict)
        or safety.get("databaseMutation") is not False
        or safety.get("dockerStarted") is not False
        or safety.get("serviceStarted") is not False
        or safety.get("permanentDelete") is not False
        or safety.get("environmentValuesRecorded") is not False
        or safety.get("operatorKeysRecorded") is not False
        or safety.get("modelWeightsIncluded") is not False
    ):
        raise HpOmenRestoreError(
            "HP OMEN 활성화 사전점검 안전 메타데이터가 올바르지 않습니다."
        )
    inputs = report.get("inputs")
    if (
        not isinstance(inputs, dict)
        or inputs.get("environmentFile") != ".env.docker"
        or inputs.get("gpuCompose") != "compose.gpu.yaml"
        or inputs.get("requiredScripts")
        != sorted(ACTIVATION_SCRIPTS.values())
        or inputs.get("acceptanceKeyNames")
        != list(REQUIRED_ACCEPTANCE_KEYS)
    ):
        raise HpOmenRestoreError(
            "HP OMEN 활성화 사전점검 입력 메타데이터가 올바르지 않습니다."
        )
    prepare_meta = report.get("prepareReport")
    model_meta = report.get("model")
    if not isinstance(prepare_meta, dict) or not isinstance(model_meta, dict):
        raise HpOmenRestoreError(
            "HP OMEN 활성화 사전점검 핵심 입력 참조가 없습니다."
        )
    prepare_path = (root / str(prepare_meta.get("path"))).resolve()
    model_path = (root / str(model_meta.get("path"))).resolve()
    if (
        not prepare_path.is_file()
        or prepare_path.stat().st_size != prepare_meta.get("sizeBytes")
        or sha256_file(prepare_path) != prepare_meta.get("sha256")
        or not is_within(model_path, root.resolve())
        or not model_path.is_file()
        or model_path.is_symlink()
        or model_path.stat().st_size != model_meta.get("sizeBytes")
        or sha256_file(model_path) != model_meta.get("sha256")
    ):
        raise HpOmenRestoreError(
            "HP OMEN 활성화 사전점검 핵심 입력 동일성이 다릅니다."
        )
    current_checks, current_context = evaluate_activation_readiness(
        root,
        prepare_report_value=relative_path(root, prepare_path),
        model_value=relative_path(root, model_path),
        environment=environment,
        platform_name=platform_name,
    )
    if (
        any(item["status"] != "PASS" for item in current_checks)
        or current_context.get("preparePath") != prepare_path
        or current_context.get("model") != model_path
    ):
        raise HpOmenRestoreError(
            "현재 HP OMEN 활성화 사전조건이 더 이상 통과 상태가 아닙니다."
        )
    try:
        html_value = html_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise HpOmenRestoreError(
            "HP OMEN 활성화 사전점검 HTML이 UTF-8이 아닙니다."
        ) from error
    if html_value != render_preflight_html(report):
        raise HpOmenRestoreError(
            "HP OMEN 활성화 사전점검 JSON과 HTML이 일치하지 않습니다."
        )
    return report_path, report


def render_activation_html(report: dict[str, Any]) -> str:
    steps = "".join(
        "<tr>"
        f"<td>{index}</td><td>{html.escape(str(item['title']))}</td>"
        f"<td>{html.escape(str(item['status']))}</td>"
        f"<td>{html.escape(str(item.get('artifactPath') or '-'))}</td>"
        "</tr>"
        for index, item in enumerate(report["steps"], start=1)
    )
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VisionFlow HP OMEN 최초 구동</title><style>
body{{margin:0;background:#eef3f8;color:#0f172a;font-family:Arial,'Noto Sans KR',sans-serif}}main{{max-width:1100px;margin:32px auto;padding:0 20px}}
section{{background:#fff;border:1px solid #dbe4ee;border-radius:16px;padding:24px;margin:16px 0}}table{{width:100%;border-collapse:collapse}}
th,td{{padding:10px;border-bottom:1px solid #e2e8f0;text-align:left}}.ready{{color:#047857;font-weight:800}}.failed{{color:#b91c1c;font-weight:800}}</style></head>
<body><main><section><h1>HP OMEN 최초 구동</h1><p class="{'ready' if report['status'] == ACTIVATED_STATUS else 'failed'}">{html.escape(report['status'])}</p>
<p>{html.escape(report['generatedAt'])}</p></section><section><h2>실행 단계</h2><table><tr><th>#</th><th>단계</th><th>상태</th><th>산출물</th></tr>{steps}</table></section>
<section><h2>안전</h2><p>DB 복원 전 안전 백업을 생성했으며 환경값·키·모델 원본은 보고서에 기록하지 않았습니다.</p></section></main></body></html>"""


def write_activation_report(
    run_directory: Path,
    report: dict[str, Any],
) -> tuple[Path, Path, Path]:
    json_path = run_directory / "visionflow-hp-omen-activation.json"
    html_path = run_directory / "visionflow-hp-omen-activation.html"
    sidecar = run_directory / "visionflow-hp-omen-activation.sha256"
    write_text_atomic(
        json_path,
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    write_text_atomic(html_path, render_activation_html(report))
    write_multi_sidecar(sidecar, [json_path, html_path])
    return json_path, html_path, sidecar


def validate_target_profile(root: Path, path: Path) -> dict[str, Any]:
    profile = read_profile(
        root,
        relative_path(root, path),
        "target",
    )
    if (
        profile.get("operation") != "MACHINE_READINESS_PROFILE"
        or profile.get("role") != "target"
        or profile.get("status") != "TARGET_READY"
        or profile.get("summary", {}).get("blocking") != 0
    ):
        raise HpOmenRestoreError(
            "HP OMEN 대상 프로필이 TARGET_READY가 아닙니다."
        )
    return profile


def validate_comparison(path: Path) -> dict[str, Any]:
    comparison = read_json(path, "LG·HP 장비 비교")
    if (
        comparison.get("operation") != "MACHINE_READINESS_COMPARISON"
        or comparison.get("status")
        not in {"COMPATIBLE", "COMPATIBLE_WITH_VERSION_DIFFERENCES"}
        or comparison.get("summary", {}).get("blocking") != 0
        or comparison.get("sourceIdentity", {}).get("status") != "MATCH"
    ):
        raise HpOmenRestoreError(
            "LG GRAM·HP OMEN 장비 비교가 호환 상태가 아닙니다."
        )
    return comparison


def validate_acceptance(path: Path) -> dict[str, Any]:
    acceptance = read_json(path, "HP OMEN 통합 인수 테스트")
    configuration = acceptance.get("configuration")
    summary = acceptance.get("summary")
    if (
        not isinstance(configuration, dict)
        or any(
            configuration.get(key) is not True
            for key in ("runDemo", "runRbac", "runSession")
        )
        or not isinstance(summary, dict)
        or not isinstance(summary.get("total"), int)
        or summary.get("total", 0) <= 0
        or summary.get("passed") != summary.get("total")
        or summary.get("failed") != 0
    ):
        raise HpOmenRestoreError(
            "HP OMEN 통합 인수 테스트가 모두 통과하지 않았습니다."
        )
    return acceptance


def validate_gpu_preflight(
    root: Path,
    path: Path,
) -> dict[str, Any]:
    try:
        _, evidence = verify_gpu_preflight_evidence(
            root=root,
            report_path=path,
        )
    except GpuPreflightEvidenceError as error:
        raise HpOmenRestoreError(str(error)) from error
    if evidence.get("status") != GPU_PREFLIGHT_STATUS:
        raise HpOmenRestoreError(
            "HP OMEN GPU 사전점검 증적이 GPU_MODEL_READY가 아닙니다."
        )
    return evidence


def execute_activation(
    root: Path,
    *,
    prepare_report_value: str | None,
    model_value: str,
    confirmation: str,
    drone_id: int,
    run_benchmark: bool,
    timeout_seconds: int,
    environment: Mapping[str, str],
    now: datetime,
    runner: Runner = default_runner,
    platform_name: str = os.name,
) -> tuple[Path, dict[str, Any], int]:
    if drone_id <= 0 or timeout_seconds <= 0:
        raise HpOmenRestoreError(
            "드론 ID와 단계 제한 시간은 양수여야 합니다."
        )
    (
        prepare_path,
        prepare_report,
        model,
        prepared_artifacts,
    ) = validate_activation_preflight(
        root,
        prepare_report_value=prepare_report_value,
        model_value=model_value,
        confirmation=confirmation,
        environment=environment,
        platform_name=platform_name,
    )
    activation_lineage = validate_activation_start_lineage(root)
    output = root / REPORT_ROOT
    output.mkdir(parents=True, exist_ok=True)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    run_directory = output / f"activation-{timestamp}"
    if run_directory.exists():
        run_directory = output / (
            f"activation-{timestamp}-{uuid.uuid4().hex[:8]}"
        )
    run_directory.mkdir()
    report: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "scope": "HP_OMEN_TARGET_RESTORE",
        "operation": ACTIVATE_OPERATION,
        "activationId": str(uuid.uuid4()),
        "generatedAt": now.isoformat(),
        "completedAt": None,
        "status": "RUNNING",
        "prepareReport": artifact_entry(
            root,
            "prepare-report",
            prepare_path,
        ),
        "activationLineage": activation_lineage,
        "model": {
            "path": relative_path(root, model),
            "sizeBytes": model.stat().st_size,
            "sha256": sha256_file(model),
        },
        "steps": [],
        "artifacts": [],
        "summary": {},
        "deferred": [],
        "safety": {
            "databaseRestored": False,
            "preRestoreSafetyBackupCreated": False,
            "dockerGpuStackStarted": False,
            "gpuEvidenceCreated": False,
            "permanentDelete": False,
            "externalTransferPerformed": False,
            "environmentValuesRecorded": False,
            "operatorKeysRecorded": False,
            "modelWeightsIncluded": False,
        },
    }
    produced: dict[str, Path] = {}
    exit_code = 1

    def run(
        key: str,
        arguments: Sequence[str],
        *,
        pattern: str | None,
    ) -> Path | None:
        command = command_for_batch(
            root,
            ACTIVATION_SCRIPTS[key],
            arguments,
            platform_name=platform_name,
        )
        step, artifact = run_activation_step(
            root,
            run_directory,
            key=key,
            command=command,
            pattern=pattern,
            timeout_seconds=timeout_seconds,
            runner=runner,
        )
        report["steps"].append(step)
        if artifact is not None:
            produced[key] = artifact
        if step["status"] != "PASS":
            raise HpOmenRestoreError(
                f"{step['title']} 실패: {step['error']}"
            )
        return artifact

    try:
        backup = prepared_artifacts["database-backup"]
        safety_backup = run(
            "restore",
            [
                "--environment-file",
                ".env.docker",
                "--backup",
                relative_path(root, backup),
                "--confirm",
                "RESTORE",
            ],
            pattern="backups/pre-restore/visionflow-backup-*.zip",
        )
        assert safety_backup is not None
        report["safety"]["databaseRestored"] = True
        report["safety"]["preRestoreSafetyBackupCreated"] = True

        gpu_preflight = run(
            "gpu-stack",
            [
                "-EnvironmentFile",
                ".env.docker",
                "-ModelFile",
                model.name,
                "-StartStack",
            ],
            pattern=(
                "artifacts/gpu-readiness/gpu-preflight-*/"
                "visionflow-gpu-preflight.json"
            ),
        )
        assert gpu_preflight is not None
        gpu_preflight_report = validate_gpu_preflight(
            root,
            gpu_preflight,
        )
        report["safety"]["dockerGpuStackStarted"] = True
        report["safety"]["gpuEvidenceCreated"] = True

        target = run(
            "target-profile",
            [
                "--role",
                "target",
                "--expect-gpu",
                "--expect-model",
                "--model",
                relative_path(root, model),
            ],
            pattern=(
                "artifacts/machine-readiness/"
                "visionflow-machine-target-*.json"
            ),
        )
        assert target is not None
        target_profile = validate_target_profile(root, target)

        baseline = prepared_artifacts["lg-baseline"]
        comparison = run(
            "machine-comparison",
            [
                "--baseline",
                relative_path(root, baseline),
                "--target",
                relative_path(root, target),
            ],
            pattern=(
                "artifacts/machine-readiness/"
                "visionflow-machine-comparison-*.json"
            ),
        )
        assert comparison is not None
        comparison_report = validate_comparison(comparison)

        acceptance = run(
            "acceptance",
            [
                "-RunDemo",
                "-RunRbac",
                "-RunSession",
                "-DroneId",
                str(drone_id),
            ],
            pattern=(
                "artifacts/visionflow-acceptance/"
                "visionflow-acceptance-*.json"
            ),
        )
        assert acceptance is not None
        acceptance_report = validate_acceptance(acceptance)

        benchmark: Path | None = None
        if run_benchmark:
            benchmark = run(
                "benchmark",
                [],
                pattern=(
                    "artifacts/ai-benchmark/"
                    "visionflow-ai-benchmark-*.json"
                ),
            )
            assert benchmark is not None
        else:
            report["steps"].append(
                {
                    "key": "benchmark",
                    "title": dict(ACTIVATION_STEPS)["benchmark"],
                    "status": "DEFERRED",
                    "exitCode": None,
                    "durationMs": 0,
                    "logPath": None,
                    "artifactPath": None,
                    "error": None,
                }
            )

        final_artifacts = {
            "pre-restore-safety-backup": safety_backup,
            "gpu-preflight": gpu_preflight,
            "target-profile": target,
            "machine-comparison": comparison,
            "acceptance": acceptance,
        }
        if benchmark is not None:
            final_artifacts["gpu-benchmark"] = benchmark
        report["artifacts"] = [
            artifact_entry(root, key, path)
            for key, path in final_artifacts.items()
        ]
        report["runtime"] = {
            "gpuPreflightStatus": gpu_preflight_report.get("status"),
            "targetProfileStatus": target_profile.get("status"),
            "comparisonStatus": comparison_report.get("status"),
            "acceptancePassed": acceptance_report.get(
                "summary", {}
            ).get("passed"),
            "benchmarkExecuted": benchmark is not None,
        }
        report["deferred"] = [
            *(
                []
                if benchmark is not None
                else [
                    {
                        "key": "gpu-ai-benchmark",
                        "status": "DEFERRED",
                        "reason": "동일 입력 영상이 준비된 뒤 별도 측정",
                    }
                ]
            ),
            {
                "key": "hp-target-smartphone-https-revalidation",
                "status": "DEFERRED",
                "reason": "HP 런타임 안정화 후 새 LAN IP·인증서 접속 재검증",
            },
            {
                "key": "model-accuracy-evaluation",
                "status": "DEFERRED",
                "reason": "검증 데이터셋 별도 이관 후 best.pt 정확도 평가",
            },
            {
                "key": "dji-mini4-pro",
                "status": "OUT_OF_SCOPE",
                "reason": "DJI 전용 RTSP·기체 종속 연동은 3차 프로젝트",
            },
        ]
        report["status"] = ACTIVATED_STATUS
        exit_code = 0
    except (HpOmenRestoreError, KeyboardInterrupt) as error:
        report["status"] = "HP_OMEN_RUNTIME_ACTIVATION_FAILED"
        report["error"] = (
            str(error)
            if not isinstance(error, KeyboardInterrupt)
            else "사용자에 의해 중단되었습니다."
        )
        exit_code = 130 if isinstance(error, KeyboardInterrupt) else 1
    finally:
        artifact_keys = {
            "restore": "pre-restore-safety-backup",
            "gpu-stack": "gpu-preflight",
            "target-profile": "target-profile",
            "machine-comparison": "machine-comparison",
            "acceptance": "acceptance",
            "benchmark": "gpu-benchmark",
        }
        report["artifacts"] = [
            artifact_entry(root, artifact_keys[key], path)
            for key, path in produced.items()
        ]
        if "restore" in produced:
            report["safety"]["preRestoreSafetyBackupCreated"] = True
        report["completedAt"] = datetime.now(timezone.utc).isoformat()
        report["summary"] = {
            "total": len(ACTIVATION_STEPS),
            "passed": sum(
                item["status"] == "PASS" for item in report["steps"]
            ),
            "deferred": sum(
                item["status"] == "DEFERRED" for item in report["steps"]
            ),
            "failed": sum(
                item["status"] == "FAILED" for item in report["steps"]
            ),
            "blocking": 0 if exit_code == 0 else 1,
        }
        report_path, _, _ = write_activation_report(
            run_directory,
            report,
        )
    return report_path, report, exit_code


def verify_activation_report(
    root: Path,
    value: str,
) -> tuple[Path, dict[str, Any]]:
    report_path = resolve_report(root, value)
    report = read_json(report_path, "HP OMEN 최초 구동 보고서")
    html_path = report_path.with_suffix(".html")
    verify_multi_sidecar(
        report_path.with_suffix(".sha256"),
        [report_path, html_path],
        "HP OMEN 최초 구동 보고서",
    )
    if (
        report.get("schemaVersion") != SCHEMA_VERSION
        or report.get("project") != PROJECT_NAME
        or report.get("operation") != ACTIVATE_OPERATION
        or report.get("status") != ACTIVATED_STATUS
    ):
        raise HpOmenRestoreError(
            "VisionFlow HP OMEN 최초 구동 완료 보고서가 아닙니다."
        )
    steps = report.get("steps")
    summary = report.get("summary")
    if (
        not isinstance(steps, list)
        or len(steps) != len(ACTIVATION_STEPS)
        or any(
            not isinstance(item, dict)
            or item.get("status") not in {"PASS", "DEFERRED"}
            for item in steps
        )
        or not isinstance(summary, dict)
        or summary.get("total") != len(ACTIVATION_STEPS)
        or summary.get("failed") != 0
        or summary.get("blocking") != 0
    ):
        raise HpOmenRestoreError(
            "HP OMEN 최초 구동 단계 집계가 올바르지 않습니다."
        )
    safety = report.get("safety")
    if (
        not isinstance(safety, dict)
        or safety.get("databaseRestored") is not True
        or safety.get("preRestoreSafetyBackupCreated") is not True
        or safety.get("dockerGpuStackStarted") is not True
        or safety.get("gpuEvidenceCreated") is not True
        or safety.get("permanentDelete") is not False
        or safety.get("externalTransferPerformed") is not False
        or safety.get("environmentValuesRecorded") is not False
        or safety.get("operatorKeysRecorded") is not False
        or safety.get("modelWeightsIncluded") is not False
    ):
        raise HpOmenRestoreError(
            "HP OMEN 최초 구동 안전 메타데이터가 올바르지 않습니다."
        )
    prepare_meta = report.get("prepareReport")
    if not isinstance(prepare_meta, dict):
        raise HpOmenRestoreError(
            "HP OMEN 작업공간 준비 보고서 참조가 없습니다."
        )
    prepare_path = (root / str(prepare_meta.get("path"))).resolve()
    if (
        not prepare_path.is_file()
        or prepare_path.stat().st_size != prepare_meta.get("sizeBytes")
        or sha256_file(prepare_path) != prepare_meta.get("sha256")
    ):
        raise HpOmenRestoreError(
            "HP OMEN 작업공간 준비 보고서 동일성이 다릅니다."
        )
    verify_prepare_report(root, relative_path(root, prepare_path))
    artifacts = artifact_map(root, report)
    required = {
        "pre-restore-safety-backup",
        "gpu-preflight",
        "target-profile",
        "machine-comparison",
        "acceptance",
    }
    if not required.issubset(artifacts) or (
        set(artifacts) - required != set()
        and set(artifacts) - required != {"gpu-benchmark"}
    ):
        raise HpOmenRestoreError(
            "HP OMEN 최초 구동 산출물 종류가 다릅니다."
        )
    try:
        backup_status = verify_archive(
            artifacts["pre-restore-safety-backup"]
        ).get("status")
        target = validate_target_profile(
            root,
            artifacts["target-profile"],
        )
    except (BackupError, MachineReadinessError) as error:
        raise HpOmenRestoreError(str(error)) from error
    if backup_status != "VALID":
        raise HpOmenRestoreError("복원 전 안전 백업 검증에 실패했습니다.")
    comparison = validate_comparison(artifacts["machine-comparison"])
    gpu_preflight = validate_gpu_preflight(
        root,
        artifacts["gpu-preflight"],
    )
    acceptance = validate_acceptance(artifacts["acceptance"])
    runtime = report.get("runtime")
    if (
        not isinstance(runtime, dict)
        or runtime.get("gpuPreflightStatus")
        != gpu_preflight.get("status")
        or runtime.get("targetProfileStatus") != target.get("status")
        or runtime.get("comparisonStatus") != comparison.get("status")
        or runtime.get("acceptancePassed")
        != acceptance.get("summary", {}).get("passed")
        or runtime.get("benchmarkExecuted")
        != ("gpu-benchmark" in artifacts)
    ):
        raise HpOmenRestoreError(
            "HP OMEN 최초 구동 런타임 교차 검증 정보가 다릅니다."
        )
    verify_activation_lineage_metadata(
        root,
        report.get("activationLineage"),
    )
    model = report.get("model")
    if not isinstance(model, dict):
        raise HpOmenRestoreError("best.pt 메타데이터가 없습니다.")
    model_path = (root / str(model.get("path"))).resolve()
    if (
        not is_within(model_path, root.resolve())
        or not model_path.is_file()
        or model_path.is_symlink()
        or model_path.stat().st_size != model.get("sizeBytes")
        or sha256_file(model_path) != model.get("sha256")
    ):
        raise HpOmenRestoreError("best.pt 동일성이 다릅니다.")
    try:
        html_value = html_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise HpOmenRestoreError(
            "HP OMEN 최초 구동 HTML이 UTF-8이 아닙니다."
        ) from error
    if html_value != render_activation_html(report):
        raise HpOmenRestoreError(
            "HP OMEN 최초 구동 JSON과 HTML이 일치하지 않습니다."
        )
    return report_path, report


def validate_failed_activation_recovery_source(
    root: Path,
    value: str,
) -> tuple[Path, dict[str, Any], Path]:
    report_path = resolve_report(root, value)
    report = read_json(report_path, "HP OMEN 실패 활성화 보고서")
    html_path = report_path.with_suffix(".html")
    verify_multi_sidecar(
        report_path.with_suffix(".sha256"),
        [report_path, html_path],
        "HP OMEN 실패 활성화 보고서",
    )
    if (
        report.get("schemaVersion") != SCHEMA_VERSION
        or report.get("project") != PROJECT_NAME
        or report.get("operation") != ACTIVATE_OPERATION
        or report.get("status") != "HP_OMEN_RUNTIME_ACTIVATION_FAILED"
        or not isinstance(report.get("error"), str)
        or not report["error"].strip()
    ):
        raise HpOmenRestoreError(
            "복구 가능한 HP OMEN 실패 활성화 보고서가 아닙니다."
        )
    safety = report.get("safety")
    if (
        not isinstance(safety, dict)
        or safety.get("preRestoreSafetyBackupCreated") is not True
        or safety.get("permanentDelete") is not False
        or safety.get("externalTransferPerformed") is not False
        or safety.get("environmentValuesRecorded") is not False
        or safety.get("operatorKeysRecorded") is not False
        or safety.get("modelWeightsIncluded") is not False
    ):
        raise HpOmenRestoreError(
            "DB 복원 시도 전에 생성된 안전 백업이 보고서에 보존된 "
            "경우에만 복구할 수 있습니다."
        )
    prepare_meta = report.get("prepareReport")
    if not isinstance(prepare_meta, dict):
        raise HpOmenRestoreError(
            "실패 활성화 보고서의 준비 보고서 참조가 없습니다."
        )
    prepare_path = (root / str(prepare_meta.get("path"))).resolve()
    if (
        not prepare_path.is_file()
        or prepare_path.stat().st_size != prepare_meta.get("sizeBytes")
        or sha256_file(prepare_path) != prepare_meta.get("sha256")
    ):
        raise HpOmenRestoreError(
            "실패 활성화 보고서의 준비 보고서 동일성이 다릅니다."
        )
    verify_prepare_report(root, relative_path(root, prepare_path))
    artifacts = artifact_map(root, report)
    allowed = {
        "pre-restore-safety-backup",
        "gpu-preflight",
        "target-profile",
        "machine-comparison",
        "acceptance",
        "gpu-benchmark",
    }
    if (
        "pre-restore-safety-backup" not in artifacts
        or not set(artifacts).issubset(allowed)
    ):
        raise HpOmenRestoreError(
            "실패 활성화 보고서에 복구용 안전 백업이 없습니다."
        )
    safety_backup = artifacts["pre-restore-safety-backup"]
    try:
        backup = verify_archive(safety_backup)
    except BackupError as error:
        raise HpOmenRestoreError(str(error)) from error
    if backup.get("status") != "VALID":
        raise HpOmenRestoreError(
            "복구용 사전 활성화 안전 백업이 유효하지 않습니다."
        )
    try:
        html_value = html_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise HpOmenRestoreError(
            "실패 활성화 보고서 HTML이 UTF-8이 아닙니다."
        ) from error
    if html_value != render_activation_html(report):
        raise HpOmenRestoreError(
            "실패 활성화 보고서 JSON과 HTML이 일치하지 않습니다."
        )
    return report_path, report, safety_backup


def render_recovery_html(report: dict[str, Any]) -> str:
    step = report["step"]
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VisionFlow HP OMEN 활성화 실패 복구</title><style>
body{{margin:0;background:#eef3f8;color:#0f172a;font-family:Arial,'Noto Sans KR',sans-serif}}main{{max-width:1000px;margin:32px auto;padding:0 20px}}
section{{background:#fff;border:1px solid #dbe4ee;border-radius:16px;padding:24px;margin:16px 0}}.ready{{color:#047857;font-weight:800}}.failed{{color:#b91c1c;font-weight:800}}code{{word-break:break-all}}</style></head>
<body><main><section><h1>HP OMEN 활성화 실패 복구</h1><p class="{'ready' if report['status'] == RECOVERED_STATUS else 'failed'}">{html.escape(report['status'])}</p>
<p>{html.escape(report['generatedAt'])}</p></section><section><h2>복구 단계</h2><p><strong>{html.escape(str(step['status']))}</strong> {html.escape(str(step['title']))}</p>
<p>{html.escape(str(step.get('error') or '오류 없음'))}</p></section><section><h2>복구 원본</h2><p><code>{html.escape(str(report['rollbackSource']['path']))}</code></p></section>
<section><h2>안전</h2><p>실패 활성화 이전의 검증된 안전 백업으로만 복구했으며 환경값·운영자 키·백업 내용은 보고서에 기록하지 않았습니다.</p></section></main></body></html>"""


def write_recovery_report(
    run_directory: Path,
    report: dict[str, Any],
) -> tuple[Path, Path, Path]:
    json_path = run_directory / "visionflow-hp-omen-recovery.json"
    html_path = run_directory / "visionflow-hp-omen-recovery.html"
    sidecar = run_directory / "visionflow-hp-omen-recovery.sha256"
    write_text_atomic(
        json_path,
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    write_text_atomic(html_path, render_recovery_html(report))
    write_multi_sidecar(sidecar, [json_path, html_path])
    return json_path, html_path, sidecar


def execute_activation_recovery(
    root: Path,
    *,
    failed_report_value: str,
    confirmation: str,
    timeout_seconds: int,
    now: datetime,
    runner: Runner = default_runner,
    platform_name: str = os.name,
) -> tuple[Path, dict[str, Any], int]:
    if confirmation != RECOVERY_CONFIRMATION:
        raise HpOmenRestoreError(
            "실패한 HP 활성화 이전 상태 복구에는 "
            f"--confirm {RECOVERY_CONFIRMATION}가 필요합니다."
        )
    if platform_name != "nt":
        raise HpOmenRestoreError(
            "HP OMEN 활성화 복구는 Windows 대상 장비에서만 지원합니다."
        )
    if timeout_seconds <= 0:
        raise HpOmenRestoreError("복구 단계 제한 시간은 양수여야 합니다.")
    failed_path, _, rollback_source = (
        validate_failed_activation_recovery_source(
            root,
            failed_report_value,
        )
    )
    environment_file = (root / ".env.docker").resolve()
    restore_script = (
        root / "scripts" / ACTIVATION_SCRIPTS["restore"]
    ).resolve()
    if (
        not environment_file.is_file()
        or environment_file.is_symlink()
        or not restore_script.is_file()
        or restore_script.is_symlink()
    ):
        raise HpOmenRestoreError(
            "복구에 필요한 .env.docker 또는 복원 스크립트가 없습니다."
        )
    output = root / REPORT_ROOT
    output.mkdir(parents=True, exist_ok=True)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    run_directory = output / f"recovery-{timestamp}"
    if run_directory.exists():
        run_directory = output / (
            f"recovery-{timestamp}-{uuid.uuid4().hex[:8]}"
        )
    run_directory.mkdir()
    report: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "scope": "HP_OMEN_TARGET_RESTORE",
        "operation": RECOVERY_OPERATION,
        "recoveryId": str(uuid.uuid4()),
        "generatedAt": now.isoformat(),
        "completedAt": None,
        "status": "RUNNING",
        "failedActivationReport": artifact_entry(
            root,
            "failed-activation-report",
            failed_path,
        ),
        "rollbackSource": artifact_entry(
            root,
            "rollback-source-backup",
            rollback_source,
        ),
        "step": {
            "key": "restore-pre-activation-state",
            "title": "실패 활성화 이전 MySQL·영속 증적 상태 복구",
            "status": "PENDING",
            "exitCode": None,
            "durationMs": 0,
            "logPath": None,
            "error": None,
        },
        "artifacts": [],
        "summary": {},
        "safety": {
            "recoveryAttempted": False,
            "databaseRestoredToPreActivation": False,
            "recoverySafetyBackupCreated": False,
            "permanentDelete": False,
            "environmentValuesRecorded": False,
            "operatorKeysRecorded": False,
            "backupContentsRecorded": False,
        },
    }
    before = artifact_candidates(
        root,
        "backups/pre-restore/visionflow-backup-*.zip",
    )
    recovery_safety: Path | None = None
    exit_code = 1
    try:
        command = command_for_batch(
            root,
            ACTIVATION_SCRIPTS["restore"],
            [
                "--environment-file",
                ".env.docker",
                "--backup",
                relative_path(root, rollback_source),
                "--confirm",
                "RESTORE",
            ],
            platform_name=platform_name,
        )
        print("[RUN] 실패 활성화 이전 상태 복구")
        report["safety"]["recoveryAttempted"] = True
        started = time.monotonic()
        result = runner(command, root, timeout_seconds)
        duration = round((time.monotonic() - started) * 1000)
        log_path = run_directory / "recovery.log"
        write_text_atomic(log_path, result.output)
        created = sorted(
            artifact_candidates(
                root,
                "backups/pre-restore/visionflow-backup-*.zip",
            )
            - before,
            key=lambda path: (path.stat().st_mtime_ns, path.name),
        )
        if len(created) == 1:
            recovery_safety = created[0]
        error: str | None = None
        if result.returncode != 0:
            error = f"복구 명령 종료 코드가 {result.returncode}입니다."
        elif len(created) != 1:
            error = (
                "복구 직전 안전 백업이 정확히 1개 생성되어야 하지만 "
                f"{len(created)}개입니다."
            )
        elif verify_archive(recovery_safety).get("status") != "VALID":
            error = "복구 직전 안전 백업 검증에 실패했습니다."
        report["step"] = {
            "key": "restore-pre-activation-state",
            "title": "실패 활성화 이전 MySQL·영속 증적 상태 복구",
            "status": "PASS" if error is None else "FAILED",
            "exitCode": result.returncode,
            "durationMs": duration,
            "logPath": relative_path(root, log_path),
            "error": error,
        }
        if error is not None:
            raise HpOmenRestoreError(error)
        report["safety"]["databaseRestoredToPreActivation"] = True
        report["safety"]["recoverySafetyBackupCreated"] = True
        report["status"] = RECOVERED_STATUS
        exit_code = 0
    except (
        HpOmenRestoreError,
        BackupError,
        KeyboardInterrupt,
    ) as error:
        report["status"] = "HP_OMEN_ACTIVATION_RECOVERY_FAILED"
        report["error"] = (
            str(error)
            if not isinstance(error, KeyboardInterrupt)
            else "사용자에 의해 중단되었습니다."
        )
        exit_code = 130 if isinstance(error, KeyboardInterrupt) else 1
    finally:
        report["completedAt"] = datetime.now(timezone.utc).isoformat()
        artifacts = {
            "failed-activation-report": failed_path,
            "rollback-source-backup": rollback_source,
        }
        if recovery_safety is not None:
            artifacts["recovery-pre-restore-backup"] = recovery_safety
        report["artifacts"] = [
            artifact_entry(root, key, path)
            for key, path in artifacts.items()
        ]
        report["summary"] = {
            "total": 1,
            "passed": int(report["step"]["status"] == "PASS"),
            "failed": int(report["step"]["status"] == "FAILED"),
            "blocking": 0 if exit_code == 0 else 1,
        }
        report_path, _, _ = write_recovery_report(
            run_directory,
            report,
        )
    if exit_code == 0:
        verify_recovery_report(root, relative_path(root, report_path))
    return report_path, report, exit_code


def verify_recovery_report(
    root: Path,
    value: str,
) -> tuple[Path, dict[str, Any]]:
    report_path = resolve_report(root, value)
    report = read_json(report_path, "HP OMEN 활성화 복구 보고서")
    html_path = report_path.with_suffix(".html")
    verify_multi_sidecar(
        report_path.with_suffix(".sha256"),
        [report_path, html_path],
        "HP OMEN 활성화 복구 보고서",
    )
    if (
        report.get("schemaVersion") != SCHEMA_VERSION
        or report.get("project") != PROJECT_NAME
        or report.get("operation") != RECOVERY_OPERATION
        or report.get("status") != RECOVERED_STATUS
    ):
        raise HpOmenRestoreError(
            "VisionFlow HP OMEN 활성화 복구 완료 보고서가 아닙니다."
        )
    step = report.get("step")
    summary = report.get("summary")
    safety = report.get("safety")
    if (
        not isinstance(step, dict)
        or step.get("status") != "PASS"
        or step.get("exitCode") != 0
        or not isinstance(summary, dict)
        or summary.get("total") != 1
        or summary.get("passed") != 1
        or summary.get("failed") != 0
        or summary.get("blocking") != 0
        or not isinstance(safety, dict)
        or safety.get("recoveryAttempted") is not True
        or safety.get("databaseRestoredToPreActivation") is not True
        or safety.get("recoverySafetyBackupCreated") is not True
        or safety.get("permanentDelete") is not False
        or safety.get("environmentValuesRecorded") is not False
        or safety.get("operatorKeysRecorded") is not False
        or safety.get("backupContentsRecorded") is not False
    ):
        raise HpOmenRestoreError(
            "HP OMEN 활성화 복구 결과 또는 안전 메타데이터가 올바르지 "
            "않습니다."
        )
    artifacts = artifact_map(root, report)
    required = {
        "failed-activation-report",
        "rollback-source-backup",
        "recovery-pre-restore-backup",
    }
    if set(artifacts) != required:
        raise HpOmenRestoreError(
            "HP OMEN 활성화 복구 산출물 종류가 다릅니다."
        )
    failed_path, _, rollback_source = (
        validate_failed_activation_recovery_source(
            root,
            relative_path(root, artifacts["failed-activation-report"]),
        )
    )
    if (
        failed_path != artifacts["failed-activation-report"]
        or rollback_source != artifacts["rollback-source-backup"]
    ):
        raise HpOmenRestoreError(
            "HP OMEN 활성화 복구 원본 연결이 다릅니다."
        )
    try:
        recovery_backup = verify_archive(
            artifacts["recovery-pre-restore-backup"]
        )
    except BackupError as error:
        raise HpOmenRestoreError(str(error)) from error
    if recovery_backup.get("status") != "VALID":
        raise HpOmenRestoreError(
            "HP OMEN 복구 직전 안전 백업이 유효하지 않습니다."
        )
    rollback_meta = report.get("rollbackSource")
    failed_meta = report.get("failedActivationReport")
    if (
        not isinstance(rollback_meta, dict)
        or not isinstance(failed_meta, dict)
        or rollback_meta.get("sha256") != sha256_file(rollback_source)
        or failed_meta.get("sha256") != sha256_file(failed_path)
    ):
        raise HpOmenRestoreError(
            "HP OMEN 활성화 복구 메타데이터 연결이 다릅니다."
        )
    try:
        html_value = html_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise HpOmenRestoreError(
            "HP OMEN 활성화 복구 HTML이 UTF-8이 아닙니다."
        ) from error
    if html_value != render_recovery_html(report):
        raise HpOmenRestoreError(
            "HP OMEN 활성화 복구 JSON과 HTML이 일치하지 않습니다."
        )
    return report_path, report


def latest_report_path(
    root: Path,
    pattern: str,
    title: str,
) -> Path | None:
    candidates = [
        path.resolve()
        for path in (root / REPORT_ROOT).glob(pattern)
        if path.is_file() and not path.is_symlink()
    ]
    if not candidates:
        return None
    latest = max(
        candidates,
        key=lambda path: (path.stat().st_mtime_ns, path.name),
    )
    if not is_within(latest, (root / REPORT_ROOT).resolve()):
        raise HpOmenRestoreError(f"{title} 경로가 허용 영역 밖입니다.")
    return latest


def resolve_lineage_artifact(
    root: Path,
    value: Any,
    expected_key: str,
    title: str,
) -> Path:
    if not isinstance(value, dict) or value.get("key") != expected_key:
        raise HpOmenRestoreError(f"{title} 메타데이터가 없습니다.")
    relative = value.get("path")
    if (
        not isinstance(relative, str)
        or Path(relative).is_absolute()
        or ".." in Path(relative).parts
    ):
        raise HpOmenRestoreError(f"{title} 경로가 올바르지 않습니다.")
    path = (root / relative).resolve()
    if (
        not is_within(path, (root / REPORT_ROOT).resolve())
        or not path.is_file()
        or path.is_symlink()
        or path.stat().st_size != value.get("sizeBytes")
        or not is_checksum(value.get("sha256"))
        or sha256_file(path) != value.get("sha256")
    ):
        raise HpOmenRestoreError(f"{title} 동일성이 다릅니다.")
    return path


def verify_activation_lineage_metadata(
    root: Path,
    value: Any,
) -> None:
    if not isinstance(value, dict):
        raise HpOmenRestoreError(
            "HP OMEN 활성화 실행 이력 메타데이터가 없습니다."
        )
    status = value.get("status")
    if status == "FIRST_ACTIVATION":
        if (
            value.get("previousFailedActivation") is not None
            or value.get("recoveryReport") is not None
        ):
            raise HpOmenRestoreError(
                "최초 활성화 실행 이력 참조가 올바르지 않습니다."
            )
        return
    if status != "RECOVERED_RETRY_READY":
        raise HpOmenRestoreError(
            "지원하지 않는 HP OMEN 활성화 실행 이력 상태입니다."
        )
    failed_path = resolve_lineage_artifact(
        root,
        value.get("previousFailedActivation"),
        "previous-failed-activation",
        "이전 실패 활성화 보고서",
    )
    recovery_path = resolve_lineage_artifact(
        root,
        value.get("recoveryReport"),
        "successful-recovery-report",
        "성공 복구 보고서",
    )
    validated_failed, _, _ = validate_failed_activation_recovery_source(
        root,
        relative_path(root, failed_path),
    )
    validated_recovery, recovery = verify_recovery_report(
        root,
        relative_path(root, recovery_path),
    )
    failed_meta = recovery.get("failedActivationReport")
    if (
        validated_failed != failed_path
        or validated_recovery != recovery_path
        or not isinstance(failed_meta, dict)
        or failed_meta.get("path") != relative_path(root, failed_path)
        or failed_meta.get("sha256") != sha256_file(failed_path)
    ):
        raise HpOmenRestoreError(
            "HP OMEN 활성화 재시도 복구 연결이 다릅니다."
        )


def validate_activation_start_lineage(root: Path) -> dict[str, Any]:
    latest_activation = latest_report_path(
        root,
        "activation-*/visionflow-hp-omen-activation.json",
        "최신 HP OMEN 활성화 보고서",
    )
    if latest_activation is None:
        return {
            "status": "FIRST_ACTIVATION",
            "previousFailedActivation": None,
            "recoveryReport": None,
        }
    activation = read_json(
        latest_activation,
        "최신 HP OMEN 활성화 보고서",
    )
    if activation.get("operation") != ACTIVATE_OPERATION:
        raise HpOmenRestoreError(
            "최신 HP OMEN 활성화 보고서 operation이 올바르지 않습니다."
        )
    status = activation.get("status")
    if status == ACTIVATED_STATUS:
        verify_activation_report(
            root,
            relative_path(root, latest_activation),
        )
        raise HpOmenRestoreError(
            "HP OMEN 최초 활성화가 이미 완료되었습니다. 모델 변경은 "
            "별도 모델 릴리스 절차를 사용하세요."
        )
    if status != "HP_OMEN_RUNTIME_ACTIVATION_FAILED":
        raise HpOmenRestoreError(
            "최신 HP OMEN 활성화 상태를 판별할 수 없습니다."
        )
    failed_path, _, _ = validate_failed_activation_recovery_source(
        root,
        relative_path(root, latest_activation),
    )
    latest_recovery = latest_report_path(
        root,
        "recovery-*/visionflow-hp-omen-recovery.json",
        "최신 HP OMEN 활성화 복구 보고서",
    )
    if latest_recovery is None:
        raise HpOmenRestoreError(
            "이전 HP OMEN 활성화 실패가 아직 복구되지 않았습니다. "
            "실패 보고서로 recover를 먼저 완료하세요."
        )
    recovery_path, recovery = verify_recovery_report(
        root,
        relative_path(root, latest_recovery),
    )
    failed_meta = recovery.get("failedActivationReport")
    if (
        not isinstance(failed_meta, dict)
        or failed_meta.get("path") != relative_path(root, failed_path)
        or failed_meta.get("sha256") != sha256_file(failed_path)
    ):
        raise HpOmenRestoreError(
            "최신 성공 복구가 최신 실패 활성화 보고서와 연결되지 않습니다."
        )
    lineage = {
        "status": "RECOVERED_RETRY_READY",
        "previousFailedActivation": artifact_entry(
            root,
            "previous-failed-activation",
            failed_path,
        ),
        "recoveryReport": artifact_entry(
            root,
            "successful-recovery-report",
            recovery_path,
        ),
    }
    verify_activation_lineage_metadata(root, lineage)
    return lineage


def build_plan() -> list[dict[str, Any]]:
    return [
        {
            "order": 1,
            "mode": "READ_ONLY",
            "title": "최종 이관 패키지·sidecar·중첩 ZIP 전체 검증",
        },
        {
            "order": 2,
            "mode": "PREPARE_CONFIRMATION",
            "title": "존재하지 않는 새 HP 작업공간에 안전 소스와 증적 추출",
        },
        {
            "order": 3,
            "mode": "MANUAL",
            "title": "HP 전용 .env.docker와 best.pt 별도 배치",
        },
        {
            "order": 4,
            "mode": "PREFLIGHT",
            "title": (
                "DB·Docker 변경 없이 준비 보고서·환경파일·best.pt·"
                "역할 키 사전점검"
            ),
        },
        {
            "order": 5,
            "mode": "ACTIVATE_CONFIRMATION",
            "title": "복원 전 안전 백업 후 MySQL·영속 증적 복원",
        },
        {
            "order": 6,
            "mode": "RUN",
            "title": (
                "RTX GPU·best.pt 증적 생성·검증과 전체 Docker 스택 기동"
            ),
        },
        {
            "order": 7,
            "mode": "RUN",
            "title": "HP target 프로필·LG 비교·통합 인수 테스트",
        },
        {
            "order": 8,
            "mode": "OPTIONAL",
            "title": "고정 입력 영상이 준비된 경우 GPU AI 벤치마크",
        },
        {
            "order": 9,
            "mode": "RECOVERY_CONFIRMATION",
            "title": (
                "활성화 실패 시 보고서에 연결된 안전 백업으로 "
                "사전 활성화 상태 복구"
            ),
        },
    ]


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="VisionFlow HP OMEN restore and first-run orchestrator"
    )
    parser.add_argument("--root", default=str(default_root))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("plan", help="변경 없이 HP 이관 실행 순서 출력")
    inspect = subparsers.add_parser(
        "inspect",
        help="최종 이관 패키지를 읽기 전용으로 검증",
    )
    inspect.add_argument("--package", required=True)
    prepare = subparsers.add_parser(
        "prepare",
        help="새 HP 작업공간에 검증된 소스와 증적 준비",
    )
    prepare.add_argument("--package", required=True)
    prepare.add_argument("--destination", required=True)
    prepare.add_argument("--confirm", default="")
    preflight = subparsers.add_parser(
        "preflight",
        help="DB·Docker 변경 전 HP 활성화 사전조건 점검",
    )
    preflight.add_argument("--prepare-report")
    preflight.add_argument("--model", default=MODEL_DEFAULT.as_posix())
    activate = subparsers.add_parser(
        "activate",
        help="HP에서 DB 복원·GPU 스택·통합 검증 실행",
    )
    activate.add_argument("--prepare-report")
    activate.add_argument("--model", default=MODEL_DEFAULT.as_posix())
    activate.add_argument("--confirm", default="")
    activate.add_argument("--drone-id", type=int, default=1)
    activate.add_argument("--run-benchmark", action="store_true")
    activate.add_argument("--timeout-seconds", type=int, default=1800)
    recover = subparsers.add_parser(
        "recover",
        help="실패 활성화 보고서의 안전 백업으로 이전 상태 복구",
    )
    recover.add_argument("--report", required=True)
    recover.add_argument("--confirm", default="")
    recover.add_argument("--timeout-seconds", type=int, default=1800)
    verify = subparsers.add_parser(
        "verify",
        help="준비 또는 최초 구동 보고서를 독립 재검증",
    )
    verify.add_argument("--report", required=True)
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    args = build_parser(default_root).parse_args(arguments)
    root = Path(args.root).resolve()
    try:
        if args.command == "plan":
            print("VisionFlow HP OMEN restore: PLAN")
            for item in build_plan():
                print(
                    f"{item['order']:02d}. [{item['mode']}] {item['title']}"
                )
            print("No file, database, Docker, or service was changed.")
            return 0
        if args.command == "inspect":
            package, manifest, checksum = inspect_package(args.package)
            print("VisionFlow HP OMEN transfer package: VERIFIED")
            print(f"Status : {manifest['status']}")
            print(f"Package: {package}")
            print(f"SHA-256: {checksum}")
            return 0
        if args.command == "prepare":
            report_path, report = prepare_workspace(
                args.package,
                args.destination,
                confirmation=args.confirm,
                now=datetime.now(timezone.utc),
            )
            print(f"VisionFlow HP OMEN prepare: {report['status']}")
            print(f"Workspace: {Path(args.destination).resolve()}")
            print(f"Report   : {report_path}")
            return 0
        if args.command == "preflight":
            report_path, report, exit_code = create_activation_preflight(
                root,
                prepare_report_value=args.prepare_report,
                model_value=args.model,
                environment=os.environ,
                platform_name=os.name,
                now=datetime.now(timezone.utc),
            )
            print(
                "VisionFlow HP OMEN activation preflight: "
                f"{report['status']}"
            )
            print(f"Report: {report_path}")
            return exit_code
        if args.command == "activate":
            report_path, report, exit_code = execute_activation(
                root,
                prepare_report_value=args.prepare_report,
                model_value=args.model,
                confirmation=args.confirm,
                drone_id=args.drone_id,
                run_benchmark=args.run_benchmark,
                timeout_seconds=args.timeout_seconds,
                environment=os.environ,
                now=datetime.now(timezone.utc),
            )
            print(f"VisionFlow HP OMEN activation: {report['status']}")
            print(f"Report: {report_path}")
            return exit_code
        if args.command == "recover":
            report_path, report, exit_code = execute_activation_recovery(
                root,
                failed_report_value=args.report,
                confirmation=args.confirm,
                timeout_seconds=args.timeout_seconds,
                now=datetime.now(timezone.utc),
            )
            print(
                "VisionFlow HP OMEN activation recovery: "
                f"{report['status']}"
            )
            print(f"Report: {report_path}")
            return exit_code
        report_path = resolve_report(root, args.report)
        report = read_json(report_path, "HP OMEN 보고서")
        if report.get("operation") == PREPARE_OPERATION:
            verified_path, verified = verify_prepare_report(
                root,
                relative_path(root, report_path),
            )
        elif report.get("operation") == PREFLIGHT_OPERATION:
            verified_path, verified = verify_activation_preflight_report(
                root,
                relative_path(root, report_path),
                environment=os.environ,
                platform_name=os.name,
            )
        elif report.get("operation") == ACTIVATE_OPERATION:
            verified_path, verified = verify_activation_report(
                root,
                relative_path(root, report_path),
            )
        elif report.get("operation") == RECOVERY_OPERATION:
            verified_path, verified = verify_recovery_report(
                root,
                relative_path(root, report_path),
            )
        else:
            raise HpOmenRestoreError(
                "지원하지 않는 HP OMEN 보고서 operation입니다."
            )
        print("VisionFlow HP OMEN restore report: VERIFIED")
        print(f"Status: {verified['status']}")
        print(f"Report: {verified_path}")
        return 0
    except (
        HpOmenRestoreError,
        BackupError,
        MachineReadinessError,
        HandoffError,
        TransferPackageError,
        FileNotFoundError,
        OSError,
        zipfile.BadZipFile,
        KeyError,
    ) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
