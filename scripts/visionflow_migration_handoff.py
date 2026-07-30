"""Create and verify a cross-checked VisionFlow migration handoff bundle."""

from __future__ import annotations

import argparse
import hashlib
import io
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
ARCHIVE_ROOT = "VisionFlow-Handoff"
SOURCE_MANIFEST = "VisionFlow-Drone/SOURCE_MANIFEST.json"
READY_EVIDENCE = {"READY", "READY_WITH_DEFERRED", "READY_WITH_WARNINGS"}
READY_BASELINE = {"BASELINE_READY", "BASELINE_READY_WITH_DEFERRED"}
SMARTPHONE_E2E_ARCHIVE_PATH = "evidence/smartphone-real-sensor-https.json"
MAX_MANIFEST_BYTES = 5 * 1024 * 1024


class HandoffError(RuntimeError):
    """Raised when handoff inputs or output are unsafe or inconsistent."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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


def write_text_atomic(path: Path, value: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding=encoding)
    os.replace(temporary, path)


def read_json_bytes(value: bytes, title: str) -> dict[str, Any]:
    if len(value) > MAX_MANIFEST_BYTES:
        raise HandoffError(f"{title} 크기가 허용 범위를 초과했습니다.")
    try:
        result = json.loads(value.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HandoffError(f"{title} JSON 형식이 올바르지 않습니다.") from error
    if not isinstance(result, dict):
        raise HandoffError(f"{title} 최상위 값은 객체여야 합니다.")
    return result


def read_json_file(path: Path, title: str) -> dict[str, Any]:
    return read_json_bytes(path.read_bytes(), title)


def safe_archive_name(value: Any, title: str = "ZIP 경로") -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise HandoffError(f"{title}가 비어 있습니다.")
    path = PurePosixPath(value)
    if value.startswith(("/", "\\")) or "\\" in value or ".." in path.parts:
        raise HandoffError(f"안전하지 않은 {title}입니다: {value}")
    return path


def safe_zip_names(archive: zipfile.ZipFile, title: str) -> list[str]:
    names = [item.filename for item in archive.infolist() if not item.is_dir()]
    if len(names) != len(set(names)):
        raise HandoffError(f"{title}에 중복 경로가 있습니다.")
    for name in names:
        safe_archive_name(name, f"{title} 내부 경로")
    return names


def parse_sidecar_bytes(value: bytes, expected_name: str, title: str) -> str:
    try:
        parts = value.decode("utf-8-sig").strip().split()
    except UnicodeDecodeError as error:
        raise HandoffError(f"{title} sidecar가 UTF-8이 아닙니다.") from error
    if len(parts) != 2 or parts[1] != expected_name:
        raise HandoffError(f"{title} sidecar 형식이 올바르지 않습니다.")
    checksum = parts[0].lower()
    if len(checksum) != 64 or any(char not in "0123456789abcdef" for char in checksum):
        raise HandoffError(f"{title} SHA-256 값이 올바르지 않습니다.")
    return checksum


def verify_file_sidecar(path: Path, title: str) -> tuple[Path, str]:
    sidecar = path.with_suffix(".sha256")
    if not sidecar.is_file() or sidecar.is_symlink():
        raise HandoffError(f"{title} sidecar를 찾을 수 없습니다: {sidecar}")
    expected = parse_sidecar_bytes(sidecar.read_bytes(), path.name, title)
    actual = sha256_file(path)
    if actual != expected:
        raise HandoffError(f"{title} SHA-256이 sidecar와 다릅니다.")
    return sidecar, actual


def validate_file_entry(entry: Any, title: str) -> tuple[str, int, str]:
    if not isinstance(entry, dict):
        raise HandoffError(f"{title} 파일 항목이 객체가 아닙니다.")
    path = safe_archive_name(entry.get("archivePath") or entry.get("path"), title).as_posix()
    size = entry.get("sizeBytes")
    checksum = str(entry.get("sha256", "")).lower()
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise HandoffError(f"{title} 파일 크기가 올바르지 않습니다: {path}")
    if len(checksum) != 64 or any(char not in "0123456789abcdef" for char in checksum):
        raise HandoffError(f"{title} SHA-256이 올바르지 않습니다: {path}")
    return path, size, checksum


def verify_source_bytes(value: bytes) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(io.BytesIO(value), "r") as archive:
            names = safe_zip_names(archive, "안전 소스 ZIP")
            manifest_bytes = archive.read(SOURCE_MANIFEST)
            manifest = read_json_bytes(manifest_bytes, "소스 manifest")
            if (
                manifest.get("schemaVersion") != SCHEMA_VERSION
                or manifest.get("project") != PROJECT_NAME
                or manifest.get("operation") != "PORTABLE_SOURCE_RELEASE"
            ):
                raise HandoffError("VisionFlow 안전 소스 manifest가 아닙니다.")
            files = manifest.get("files")
            summary = manifest.get("summary")
            if not isinstance(files, list) or not isinstance(summary, dict):
                raise HandoffError("소스 manifest 파일 목록이 올바르지 않습니다.")
            if summary.get("includedFiles") != len(files):
                raise HandoffError("소스 manifest 파일 개수가 일치하지 않습니다.")
            expected = {SOURCE_MANIFEST, "VisionFlow-Drone/README-MIGRATION.md"}
            seen: set[str] = set()
            for entry in files:
                path, size, checksum = validate_file_entry(entry, "소스 manifest")
                if path in seen:
                    raise HandoffError(f"소스 manifest에 중복 파일이 있습니다: {path}")
                seen.add(path)
                archive_path = f"VisionFlow-Drone/{path}"
                expected.add(archive_path)
                data = archive.read(archive_path)
                if len(data) != size or sha256_bytes(data) != checksum:
                    raise HandoffError(f"소스 ZIP 내부 파일 무결성이 다릅니다: {path}")
            if set(names) != expected:
                raise HandoffError("소스 ZIP 파일 목록이 SOURCE_MANIFEST.json과 다릅니다.")
            return {
                "manifest": manifest,
                "manifestSha256": sha256_bytes(manifest_bytes),
                "fileCount": len(files),
            }
    except (zipfile.BadZipFile, KeyError) as error:
        raise HandoffError("안전 소스 ZIP 또는 내부 manifest가 손상되었습니다.") from error


def verify_evidence_bytes(value: bytes) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(io.BytesIO(value), "r") as archive:
            names = safe_zip_names(archive, "릴리스 증빙 ZIP")
            manifest_bytes = archive.read("evidence-manifest.json")
            manifest = read_json_bytes(manifest_bytes, "증빙 manifest")
            if (
                manifest.get("schemaVersion") != SCHEMA_VERSION
                or manifest.get("project") != PROJECT_NAME
                or manifest.get("scope") != "SECOND_PROJECT_DIGITAL_TWIN"
                or manifest.get("operation") != "RELEASE_EVIDENCE_BUNDLE"
            ):
                raise HandoffError("VisionFlow 2차 프로젝트 릴리스 증빙이 아닙니다.")
            readiness = manifest.get("readiness")
            if not isinstance(readiness, dict) or readiness.get("status") not in READY_EVIDENCE:
                raise HandoffError("릴리스 증빙의 준비 상태가 핸드오프 조건을 충족하지 않습니다.")
            included = manifest.get("includedFiles")
            if not isinstance(included, list):
                raise HandoffError("증빙 manifest 포함 파일 목록이 없습니다.")
            expected = {"evidence-manifest.json"}
            seen: dict[str, tuple[int, str]] = {}
            for entry in included:
                path, size, checksum = validate_file_entry(entry, "증빙 manifest")
                if path in seen:
                    raise HandoffError(f"증빙 manifest에 중복 파일이 있습니다: {path}")
                seen[path] = (size, checksum)
                expected.add(path)
                data = archive.read(path)
                if len(data) != size or sha256_bytes(data) != checksum:
                    raise HandoffError(f"증빙 ZIP 내부 파일 무결성이 다릅니다: {path}")
            if set(names) != expected:
                raise HandoffError("증빙 ZIP 파일 목록이 manifest와 다릅니다.")
            evidence = manifest.get("evidence")
            backup = next(
                (
                    item
                    for item in evidence or []
                    if isinstance(item, dict) and item.get("key") == "verified-backup"
                ),
                None,
            )
            if not isinstance(backup, dict) or backup.get("included") is not False:
                raise HandoffError("MySQL 검증 백업 제외 메타데이터가 없습니다.")
            mobile_entries = [
                item
                for item in evidence or []
                if isinstance(item, dict)
                and item.get("key") == "smartphone-real-sensor-https"
            ]
            if len(mobile_entries) > 1:
                raise HandoffError("스마트폰 E2E 증빙 메타데이터가 중복됐습니다.")
            smartphone_e2e_status = "DEFERRED"
            if mobile_entries:
                mobile = mobile_entries[0]
                mobile_size = mobile.get("sourceSizeBytes")
                mobile_sha = str(mobile.get("sourceSha256", "")).lower()
                if (
                    mobile.get("included") is not True
                    or mobile.get("archivePath") != SMARTPHONE_E2E_ARCHIVE_PATH
                    or not isinstance(mobile_size, int)
                    or isinstance(mobile_size, bool)
                    or mobile_size < 0
                    or len(mobile_sha) != 64
                    or any(char not in "0123456789abcdef" for char in mobile_sha)
                    or seen.get(SMARTPHONE_E2E_ARCHIVE_PATH)
                    != (mobile_size, mobile_sha)
                ):
                    raise HandoffError(
                        "스마트폰 E2E 증빙 메타데이터와 포함 파일이 일치하지 않습니다."
                    )
                smartphone_e2e_status = "PASS"
            backup_path = safe_archive_name(backup.get("sourcePath"), "MySQL 백업 메타데이터 경로")
            backup_size = backup.get("sourceSizeBytes")
            backup_sha = str(backup.get("sourceSha256", "")).lower()
            if (
                not isinstance(backup_size, int)
                or isinstance(backup_size, bool)
                or backup_size < 0
                or len(backup_sha) != 64
                or any(char not in "0123456789abcdef" for char in backup_sha)
            ):
                raise HandoffError("MySQL 검증 백업 메타데이터가 올바르지 않습니다.")
            return {
                "manifest": manifest,
                "manifestSha256": sha256_bytes(manifest_bytes),
                "readinessStatus": readiness["status"],
                "smartphoneE2eStatus": smartphone_e2e_status,
                "backup": {
                    "included": False,
                    "sourcePath": backup_path.as_posix(),
                    "sizeBytes": backup_size,
                    "sha256": backup_sha,
                },
            }
    except (zipfile.BadZipFile, KeyError) as error:
        raise HandoffError("릴리스 증빙 ZIP 또는 내부 manifest가 손상되었습니다.") from error


def validate_baseline_bytes(
    json_bytes: bytes,
    html_bytes: bytes,
    *,
    source_sha256: str,
    source_manifest_sha256: str,
) -> dict[str, Any]:
    profile = read_json_bytes(json_bytes, "LG baseline 프로필")
    if (
        profile.get("schemaVersion") != SCHEMA_VERSION
        or profile.get("project") != PROJECT_NAME
        or profile.get("operation") != "MACHINE_READINESS_PROFILE"
        or profile.get("role") != "baseline"
    ):
        raise HandoffError("VisionFlow baseline 장비 프로필이 아닙니다.")
    if profile.get("status") not in READY_BASELINE:
        raise HandoffError(f"baseline 상태가 핸드오프 조건을 충족하지 않습니다: {profile.get('status')}")
    summary = profile.get("summary")
    if not isinstance(summary, dict) or summary.get("blocking") != 0:
        raise HandoffError("baseline 프로필에 차단 항목이 있습니다.")
    identity = profile.get("sourceIdentity")
    if not isinstance(identity, dict) or identity.get("status") != "PASS":
        raise HandoffError("baseline 소스 동일성 검증이 통과하지 않았습니다.")
    if identity.get("archiveSha256") != source_sha256:
        raise HandoffError("baseline이 참조한 소스 ZIP과 포함 소스 ZIP이 다릅니다.")
    if identity.get("manifestSha256") != source_manifest_sha256:
        raise HandoffError("baseline이 참조한 SOURCE_MANIFEST와 포함 소스 manifest가 다릅니다.")
    try:
        html_text = html_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise HandoffError("baseline HTML이 UTF-8이 아닙니다.") from error
    lowered = html_text.lower()
    if any(token in lowered for token in ("<script", "<iframe", "<object", "<embed", "javascript:")):
        raise HandoffError("baseline HTML에 실행 가능한 콘텐츠가 있습니다.")
    if profile["status"] not in html_text:
        raise HandoffError("baseline HTML과 JSON 상태가 일치하지 않습니다.")
    return profile


def newest_file(root: Path, pattern: str, title: str) -> Path:
    if not root.is_dir():
        raise HandoffError(f"{title} 폴더가 없습니다: {root}")
    candidates = [path.resolve() for path in root.glob(pattern) if path.is_file() and not path.is_symlink()]
    if not candidates:
        raise HandoffError(f"{title} 파일을 찾을 수 없습니다.")
    return max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))


def resolve_input(root: Path, value: str | None, allowed: Path, pattern: str, title: str) -> Path:
    if value:
        candidate = Path(value)
        path = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    else:
        path = newest_file(allowed, pattern, title)
    if not is_within(path, allowed.resolve()) or not path.is_file() or path.is_symlink():
        raise HandoffError(f"{title} 경로가 허용 영역을 벗어났습니다: {path}")
    return path


def load_inputs(
    root: Path,
    source_value: str | None,
    evidence_value: str | None,
    baseline_value: str | None,
) -> dict[str, Any]:
    source = resolve_input(
        root,
        source_value,
        root / "artifacts/source-release",
        "visionflow-source-release-*.zip",
        "안전 소스 ZIP",
    )
    source_sidecar, source_sha = verify_file_sidecar(source, "안전 소스 ZIP")
    source_result = verify_source_bytes(source.read_bytes())

    evidence = resolve_input(
        root,
        evidence_value,
        root / "artifacts/release-evidence",
        "visionflow-release-evidence-*.zip",
        "릴리스 증빙 ZIP",
    )
    evidence_sidecar, evidence_sha = verify_file_sidecar(evidence, "릴리스 증빙 ZIP")
    evidence_result = verify_evidence_bytes(evidence.read_bytes())

    baseline = resolve_input(
        root,
        baseline_value,
        root / "artifacts/machine-readiness",
        "visionflow-machine-baseline-*.json",
        "LG baseline 프로필",
    )
    baseline_sidecar, baseline_sha = verify_file_sidecar(baseline, "LG baseline 프로필")
    baseline_html = baseline.with_suffix(".html")
    if not baseline_html.is_file() or baseline_html.is_symlink():
        raise HandoffError(f"LG baseline HTML을 찾을 수 없습니다: {baseline_html}")
    baseline_profile = validate_baseline_bytes(
        baseline.read_bytes(),
        baseline_html.read_bytes(),
        source_sha256=source_sha,
        source_manifest_sha256=source_result["manifestSha256"],
    )
    return {
        "source": source,
        "sourceSidecar": source_sidecar,
        "sourceSha256": source_sha,
        "sourceResult": source_result,
        "evidence": evidence,
        "evidenceSidecar": evidence_sidecar,
        "evidenceSha256": evidence_sha,
        "evidenceResult": evidence_result,
        "baseline": baseline,
        "baselineSidecar": baseline_sidecar,
        "baselineHtml": baseline_html,
        "baselineSha256": baseline_sha,
        "baselineProfile": baseline_profile,
    }


def build_readme(inputs: dict[str, Any]) -> str:
    profile = inputs["baselineProfile"]
    backup = inputs["evidenceResult"]["backup"]
    return "\n".join(
        [
            "# VisionFlow HP OMEN 마이그레이션 핸드오프",
            "",
            f"- LG GRAM baseline: **{profile['status']}**",
            f"- 릴리스 증빙: **{inputs['evidenceResult']['readinessStatus']}**",
            f"- 스마트폰 실센서 HTTPS E2E: **{inputs['evidenceResult']['smartphoneE2eStatus']}**",
            f"- 소스 파일 수: {inputs['sourceResult']['fileCount']}개",
            "- 안전 소스·릴리스 증빙·baseline의 SHA-256과 내부 manifest 교차 검증 완료",
            "",
            "## HP OMEN 이동 순서",
            "",
            "1. 이 ZIP의 outer SHA-256 sidecar를 검증합니다.",
            "2. `source/`의 안전 소스 ZIP을 별도 작업 폴더에 압축 해제합니다.",
            "3. 검증된 MySQL 백업 원본과 `best.pt`는 보안 경로로 따로 복사합니다.",
            "4. `.env`는 예제 파일에서 새로 작성하며 이 번들에서 찾거나 복원하지 않습니다.",
            "5. HP OMEN에서 machine target 프로필을 생성한 뒤 LG baseline과 비교합니다.",
            "6. GPU 및 `best.pt`, HP OMEN의 새 LAN IP·인증서 HTTPS 재확인은 이동 후 진행합니다.",
            "",
            "## 별도 이관 대상(번들 미포함)",
            "",
            f"- MySQL 백업: `{backup['sourcePath']}`",
            f"- MySQL 백업 SHA-256: `{backup['sha256']}`",
            "- `best.pt`: HP OMEN 이동 시 별도 검증 및 체크섬 기록",
            "- `.env`, 인증서, 비밀값: 대상 장비에서 안전하게 재구성",
            "",
            "DJI Mini 4 Pro 전용 연동은 3차 프로젝트 범위이며 이 핸드오프에 포함하지 않습니다.",
            "",
        ]
    )


def manifest_file_entry(path: Path, archive_path: str) -> dict[str, Any]:
    return {
        "archivePath": archive_path,
        "sizeBytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def verify_handoff_bytes(value: bytes) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(io.BytesIO(value), "r") as archive:
            names = safe_zip_names(archive, "마이그레이션 핸드오프 ZIP")
            manifest_name = f"{ARCHIVE_ROOT}/HANDOFF_MANIFEST.json"
            manifest = read_json_bytes(archive.read(manifest_name), "핸드오프 manifest")
            if (
                manifest.get("schemaVersion") != SCHEMA_VERSION
                or manifest.get("project") != PROJECT_NAME
                or manifest.get("operation") != "MIGRATION_HANDOFF"
            ):
                raise HandoffError("VisionFlow 마이그레이션 핸드오프가 아닙니다.")
            files = manifest.get("files")
            if not isinstance(files, list):
                raise HandoffError("핸드오프 manifest 파일 목록이 없습니다.")
            expected = {manifest_name}
            data_by_path: dict[str, bytes] = {}
            for entry in files:
                path, size, checksum = validate_file_entry(entry, "핸드오프 manifest")
                if not path.startswith(f"{ARCHIVE_ROOT}/") or path in expected:
                    raise HandoffError(f"핸드오프 manifest 경로가 올바르지 않습니다: {path}")
                expected.add(path)
                data = archive.read(path)
                data_by_path[path] = data
                if len(data) != size or sha256_bytes(data) != checksum:
                    raise HandoffError(f"핸드오프 내부 파일 무결성이 다릅니다: {path}")
            if set(names) != expected:
                raise HandoffError("핸드오프 ZIP 파일 목록이 manifest와 다릅니다.")

            source_info = manifest.get("source")
            evidence_info = manifest.get("evidence")
            baseline_info = manifest.get("baseline")
            if not all(isinstance(item, dict) for item in (source_info, evidence_info, baseline_info)):
                raise HandoffError("핸드오프 교차 검증 정보가 없습니다.")
            source_path = source_info.get("archivePath")
            evidence_path = evidence_info.get("archivePath")
            baseline_path = baseline_info.get("archivePath")
            baseline_html_path = baseline_info.get("htmlArchivePath")
            source_bytes = data_by_path[source_path]
            evidence_bytes = data_by_path[evidence_path]
            baseline_bytes = data_by_path[baseline_path]
            baseline_html_bytes = data_by_path[baseline_html_path]

            source_result = verify_source_bytes(source_bytes)
            evidence_result = verify_evidence_bytes(evidence_bytes)
            source_sha = sha256_bytes(source_bytes)
            if source_sha != source_info.get("sha256"):
                raise HandoffError("핸드오프 소스 SHA-256 메타데이터가 다릅니다.")
            if source_result["manifestSha256"] != source_info.get("manifestSha256"):
                raise HandoffError("핸드오프 소스 manifest SHA-256이 다릅니다.")
            if sha256_bytes(evidence_bytes) != evidence_info.get("sha256"):
                raise HandoffError("핸드오프 증빙 SHA-256 메타데이터가 다릅니다.")
            if evidence_result["manifestSha256"] != evidence_info.get("manifestSha256"):
                raise HandoffError("핸드오프 증빙 manifest SHA-256이 다릅니다.")
            if (
                evidence_info.get("smartphoneE2eStatus")
                != evidence_result["smartphoneE2eStatus"]
            ):
                raise HandoffError("핸드오프 스마트폰 E2E 상태가 증빙 manifest와 다릅니다.")
            if sha256_bytes(baseline_bytes) != baseline_info.get("sha256"):
                raise HandoffError("핸드오프 baseline SHA-256 메타데이터가 다릅니다.")
            validate_baseline_bytes(
                baseline_bytes,
                baseline_html_bytes,
                source_sha256=source_sha,
                source_manifest_sha256=source_result["manifestSha256"],
            )
            source_sidecar_path = source_info.get("sidecarArchivePath")
            evidence_sidecar_path = evidence_info.get("sidecarArchivePath")
            baseline_sidecar_path = baseline_info.get("sidecarArchivePath")
            if parse_sidecar_bytes(
                data_by_path[source_sidecar_path], Path(source_path).name, "소스 ZIP"
            ) != source_sha:
                raise HandoffError("포함된 소스 ZIP sidecar가 실제 파일과 다릅니다.")
            if parse_sidecar_bytes(
                data_by_path[evidence_sidecar_path], Path(evidence_path).name, "증빙 ZIP"
            ) != sha256_bytes(evidence_bytes):
                raise HandoffError("포함된 증빙 ZIP sidecar가 실제 파일과 다릅니다.")
            if parse_sidecar_bytes(
                data_by_path[baseline_sidecar_path], Path(baseline_path).name, "baseline"
            ) != sha256_bytes(baseline_bytes):
                raise HandoffError("포함된 baseline sidecar가 실제 파일과 다릅니다.")
            if evidence_result["backup"] != manifest.get("verifiedMySqlBackup"):
                raise HandoffError("MySQL 백업 메타데이터가 증빙 manifest와 다릅니다.")
            return manifest
    except (zipfile.BadZipFile, KeyError) as error:
        raise HandoffError("핸드오프 ZIP 또는 내부 manifest가 손상되었습니다.") from error


def create_handoff(
    root: Path,
    *,
    output_root: Path,
    source: str | None = None,
    evidence: str | None = None,
    baseline: str | None = None,
    now: datetime,
) -> tuple[Path, Path, dict[str, Any]]:
    allowed_output = (root / "artifacts/migration-handoff").resolve()
    resolved_output = output_root.resolve()
    if not is_within(resolved_output, allowed_output):
        raise HandoffError("출력 폴더는 artifacts/migration-handoff 내부여야 합니다.")
    inputs = load_inputs(root, source, evidence, baseline)
    resolved_output.mkdir(parents=True, exist_ok=True)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    bundle = resolved_output / f"visionflow-migration-handoff-{timestamp}.zip"
    if bundle.exists():
        bundle = resolved_output / f"visionflow-migration-handoff-{timestamp}-{uuid.uuid4().hex[:8]}.zip"
    sidecar = bundle.with_suffix(".sha256")
    staging = resolved_output / f".staging-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        readme = staging / "README.md"
        write_text_atomic(readme, build_readme(inputs))
        sources = [
            (readme, f"{ARCHIVE_ROOT}/README.md"),
            (inputs["source"], f"{ARCHIVE_ROOT}/source/{inputs['source'].name}"),
            (inputs["sourceSidecar"], f"{ARCHIVE_ROOT}/source/{inputs['sourceSidecar'].name}"),
            (inputs["evidence"], f"{ARCHIVE_ROOT}/evidence/{inputs['evidence'].name}"),
            (inputs["evidenceSidecar"], f"{ARCHIVE_ROOT}/evidence/{inputs['evidenceSidecar'].name}"),
            (inputs["baseline"], f"{ARCHIVE_ROOT}/baseline/{inputs['baseline'].name}"),
            (inputs["baselineSidecar"], f"{ARCHIVE_ROOT}/baseline/{inputs['baselineSidecar'].name}"),
            (inputs["baselineHtml"], f"{ARCHIVE_ROOT}/baseline/{inputs['baselineHtml'].name}"),
        ]
        files = [manifest_file_entry(path, archive_path) for path, archive_path in sources]
        archive_paths = {path.name: archive_path for path, archive_path in sources}
        profile = inputs["baselineProfile"]
        manifest = {
            "schemaVersion": SCHEMA_VERSION,
            "project": PROJECT_NAME,
            "scope": "SECOND_PROJECT_DIGITAL_TWIN",
            "operation": "MIGRATION_HANDOFF",
            "createdAt": now.isoformat(),
            "source": {
                "archivePath": archive_paths[inputs["source"].name],
                "sidecarArchivePath": archive_paths[inputs["sourceSidecar"].name],
                "sha256": inputs["sourceSha256"],
                "manifestSha256": inputs["sourceResult"]["manifestSha256"],
                "fileCount": inputs["sourceResult"]["fileCount"],
            },
            "evidence": {
                "archivePath": archive_paths[inputs["evidence"].name],
                "sidecarArchivePath": archive_paths[inputs["evidenceSidecar"].name],
                "sha256": inputs["evidenceSha256"],
                "manifestSha256": inputs["evidenceResult"]["manifestSha256"],
                "readinessStatus": inputs["evidenceResult"]["readinessStatus"],
                "smartphoneE2eStatus": inputs["evidenceResult"]["smartphoneE2eStatus"],
            },
            "baseline": {
                "archivePath": archive_paths[inputs["baseline"].name],
                "sidecarArchivePath": archive_paths[inputs["baselineSidecar"].name],
                "htmlArchivePath": archive_paths[inputs["baselineHtml"].name],
                "sha256": inputs["baselineSha256"],
                "profileId": profile.get("profileId"),
                "status": profile["status"],
            },
            "verifiedMySqlBackup": inputs["evidenceResult"]["backup"],
            "files": files,
            "excludedContent": [
                "MySQL backup archives and SQL dumps",
                "environment, secret, and certificate files",
                "AI model weights",
                "images and videos",
            ],
            "deferred": [
                {
                    "key": "hp-target-smartphone-https-revalidation",
                    "status": "DEFERRED",
                },
                {"key": "gpu-best-model", "status": "DEFERRED"},
                {"key": "dji-mini4-pro", "status": "OUT_OF_SCOPE"},
            ],
        }
        manifest_path = staging / "HANDOFF_MANIFEST.json"
        write_text_atomic(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for path, archive_path in sources:
                archive.write(path, archive_path)
            archive.write(manifest_path, f"{ARCHIVE_ROOT}/HANDOFF_MANIFEST.json")
        verify_handoff_bytes(bundle.read_bytes())
        checksum = sha256_file(bundle)
        write_text_atomic(sidecar, f"{checksum}  {bundle.name}\n")
        return bundle, sidecar, manifest
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def verify_handoff_file(root: Path, value: str) -> tuple[Path, dict[str, Any]]:
    candidate = Path(value)
    bundle = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    allowed = (root / "artifacts/migration-handoff").resolve()
    if not is_within(bundle, allowed) or not bundle.is_file() or bundle.is_symlink():
        raise HandoffError(f"핸드오프 ZIP 경로가 허용 영역을 벗어났습니다: {bundle}")
    _, actual = verify_file_sidecar(bundle, "마이그레이션 핸드오프 ZIP")
    manifest = verify_handoff_bytes(bundle.read_bytes())
    if actual != sha256_file(bundle):
        raise HandoffError("핸드오프 ZIP 검증 중 파일이 변경됐습니다.")
    return bundle, manifest


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VisionFlow migration handoff")
    parser.add_argument("--root", default=str(default_root))
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create", help="교차 검증 후 핸드오프 ZIP 생성")
    create.add_argument("--source")
    create.add_argument("--evidence")
    create.add_argument("--baseline")
    create.add_argument("--output", default="artifacts/migration-handoff")
    verify = subparsers.add_parser("verify", help="기존 핸드오프 ZIP 재검증")
    verify.add_argument("--bundle", required=True)
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    args = build_parser(default_root).parse_args(arguments)
    root = Path(args.root).resolve()
    try:
        if not root.is_dir():
            raise HandoffError(f"프로젝트 루트를 찾을 수 없습니다: {root}")
        if args.command == "create":
            output = Path(args.output)
            output_root = output.resolve() if output.is_absolute() else (root / output).resolve()
            bundle, sidecar, manifest = create_handoff(
                root,
                output_root=output_root,
                source=args.source,
                evidence=args.evidence,
                baseline=args.baseline,
                now=datetime.now(timezone.utc),
            )
            print("VisionFlow migration handoff: CREATED")
            print(f"Baseline: {manifest['baseline']['status']}")
            print(f"Bundle: {bundle}")
            print(f"SHA-256: {sidecar}")
        else:
            bundle, manifest = verify_handoff_file(root, args.bundle)
            print("VisionFlow migration handoff: VERIFIED")
            print(f"Baseline: {manifest['baseline']['status']}")
            print(f"Bundle: {bundle}")
        return 0
    except (HandoffError, FileNotFoundError, OSError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
