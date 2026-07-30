"""Create and independently verify VisionFlow post-closeout source changes."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import stat
import sys
import uuid
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Iterable

try:
    from visionflow_migration_handoff import (
        HandoffError,
        verify_handoff_bytes,
        verify_source_bytes,
    )
    from visionflow_source_release import (
        EXCLUDED_SUFFIXES,
        ROOT_FILE_NAMES,
        ROOT_FILE_PREFIXES,
        SECRET_FILE_NAMES,
        SECRET_PATTERNS,
        SourceReleaseError,
        collect_source_files,
        is_environment_file,
        is_flyway_migration,
        is_frontend_public_image,
        is_gradle_wrapper_jar,
        validate_required_sources,
    )
    from visionflow_transfer_package import (
        READY_STATUS as READY_PACKAGE_STATUS,
        TransferPackageError,
        verify_transfer_package_file,
    )
except ModuleNotFoundError:  # pragma: no cover - package import during tests
    from scripts.visionflow_migration_handoff import (
        HandoffError,
        verify_handoff_bytes,
        verify_source_bytes,
    )
    from scripts.visionflow_source_release import (
        EXCLUDED_SUFFIXES,
        ROOT_FILE_NAMES,
        ROOT_FILE_PREFIXES,
        SECRET_FILE_NAMES,
        SECRET_PATTERNS,
        SourceReleaseError,
        collect_source_files,
        is_environment_file,
        is_flyway_migration,
        is_frontend_public_image,
        is_gradle_wrapper_jar,
        validate_required_sources,
    )
    from scripts.visionflow_transfer_package import (
        READY_STATUS as READY_PACKAGE_STATUS,
        TransferPackageError,
        verify_transfer_package_file,
    )


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
ARCHIVE_ROOT = "VisionFlow-Post-Closeout"
MANIFEST_NAME = f"{ARCHIVE_ROOT}/CHANGESET_MANIFEST.json"
README_NAME = f"{ARCHIVE_ROOT}/README.md"
READY_STATUS = "POST_CLOSEOUT_CHANGES_READY"
NO_CHANGES_STATUS = "POST_CLOSEOUT_NO_CHANGES"
MAX_MANIFEST_BYTES = 5 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 20_002
MAX_ARCHIVE_BYTES = 250 * 1024 * 1024


class PostCloseoutChangesError(RuntimeError):
    """Raised when a post-closeout source changeset is unsafe or inconsistent."""


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


def safe_archive_path(value: Any, title: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise PostCloseoutChangesError(f"{title}가 비어 있습니다.")
    path = PurePosixPath(value)
    if (
        value.startswith(("/", "\\"))
        or "\\" in value
        or ".." in path.parts
        or any(part.endswith(":") for part in path.parts)
    ):
        raise PostCloseoutChangesError(f"안전하지 않은 {title}입니다: {value}")
    return path


def project_path(value: Any, title: str) -> PurePosixPath:
    path = safe_archive_path(value, title)
    allowed_tree = path.parts and path.parts[0] in {
        "01_frontend",
        "02_backend",
        "03_ai-server",
        "scripts",
        "docs",
    }
    allowed_root = (
        len(path.parts) == 1
        and (
            path.name.lower() in ROOT_FILE_NAMES
            or path.name.lower().startswith(ROOT_FILE_PREFIXES)
        )
    )
    if not allowed_tree and not allowed_root:
        raise PostCloseoutChangesError(f"허용되지 않은 {title}입니다: {value}")
    return path


def read_json_bytes(value: bytes, title: str) -> dict[str, Any]:
    if len(value) > MAX_MANIFEST_BYTES:
        raise PostCloseoutChangesError(f"{title} 크기가 허용 범위를 초과했습니다.")
    try:
        result = json.loads(value.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PostCloseoutChangesError(
            f"{title} JSON 형식이 올바르지 않습니다."
        ) from error
    if not isinstance(result, dict):
        raise PostCloseoutChangesError(f"{title} 최상위 값은 객체여야 합니다.")
    return result


def write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def newest_file(directory: Path, pattern: str, title: str) -> Path:
    if not directory.is_dir():
        raise PostCloseoutChangesError(f"{title} 폴더가 없습니다: {directory}")
    candidates = [
        path.resolve()
        for path in directory.glob(pattern)
        if path.is_file() and not path.is_symlink()
    ]
    if not candidates:
        raise PostCloseoutChangesError(f"{title} 파일이 없습니다.")
    return max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))


def resolve_input(
    root: Path,
    value: str | None,
    allowed: Path,
    pattern: str,
    title: str,
) -> Path:
    if value:
        candidate = Path(value)
        path = (
            candidate.resolve()
            if candidate.is_absolute()
            else (root / candidate).resolve()
        )
    else:
        path = newest_file(allowed, pattern, title)
    if not is_within(path, allowed.resolve()) or not path.is_file() or path.is_symlink():
        raise PostCloseoutChangesError(
            f"{title} 경로가 허용 영역을 벗어났습니다: {path}"
        )
    return path


def parse_sidecar(path: Path, title: str) -> str:
    sidecar = path.with_suffix(".sha256")
    if not sidecar.is_file() or sidecar.is_symlink():
        raise PostCloseoutChangesError(
            f"{title} SHA-256 sidecar를 찾을 수 없습니다: {sidecar}"
        )
    try:
        parts = sidecar.read_text(encoding="utf-8-sig").strip().split()
    except UnicodeDecodeError as error:
        raise PostCloseoutChangesError(
            f"{title} SHA-256 sidecar가 UTF-8이 아닙니다."
        ) from error
    if len(parts) != 2 or parts[1] != path.name or not is_checksum(parts[0]):
        raise PostCloseoutChangesError(
            f"{title} SHA-256 sidecar 형식이 올바르지 않습니다."
        )
    actual = sha256_file(path)
    if parts[0].lower() != actual:
        raise PostCloseoutChangesError(
            f"{title} SHA-256이 sidecar와 다릅니다."
        )
    return actual


def load_verified_baseline(root: Path, package_path: Path) -> dict[str, Any]:
    try:
        verified_path, package_manifest = verify_transfer_package_file(
            root,
            str(package_path),
        )
        with zipfile.ZipFile(verified_path, "r") as package_archive:
            handoff_path = str(package_manifest["handoff"]["archivePath"])
            handoff_bytes = package_archive.read(handoff_path)
        handoff_manifest = verify_handoff_bytes(handoff_bytes)
        with zipfile.ZipFile(io.BytesIO(handoff_bytes), "r") as handoff_archive:
            source_path = str(handoff_manifest["source"]["archivePath"])
            source_bytes = handoff_archive.read(source_path)
        source_result = verify_source_bytes(source_bytes)
    except (
        TransferPackageError,
        HandoffError,
        zipfile.BadZipFile,
        KeyError,
    ) as error:
        raise PostCloseoutChangesError(
            f"종결 기준 소스 연결 구조를 검증할 수 없습니다: {error}"
        ) from error

    source_sha = sha256_bytes(source_bytes)
    source_info = handoff_manifest.get("source")
    if (
        package_manifest.get("status") != READY_PACKAGE_STATUS
        or not isinstance(source_info, dict)
        or source_info.get("sha256") != source_sha
        or source_info.get("manifestSha256") != source_result["manifestSha256"]
    ):
        raise PostCloseoutChangesError(
            "종결 이관 패키지와 기준 소스 manifest 연결이 일치하지 않습니다."
        )
    return {
        "packagePath": verified_path,
        "packageManifest": package_manifest,
        "packageSha256": sha256_file(verified_path),
        "sourceArchiveSha256": source_sha,
        "sourceManifestSha256": source_result["manifestSha256"],
        "sourceManifest": source_result["manifest"],
    }


def file_index(entries: Any, title: str) -> dict[str, dict[str, Any]]:
    if not isinstance(entries, list):
        raise PostCloseoutChangesError(f"{title} 파일 목록이 없습니다.")
    result: dict[str, dict[str, Any]] = {}
    for item in entries:
        if not isinstance(item, dict):
            raise PostCloseoutChangesError(f"{title} 파일 항목이 올바르지 않습니다.")
        path = project_path(item.get("path"), f"{title} 파일 경로").as_posix()
        size = item.get("sizeBytes")
        checksum = item.get("sha256")
        if (
            path in result
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or not is_checksum(checksum)
        ):
            raise PostCloseoutChangesError(
                f"{title} 파일 메타데이터가 올바르지 않습니다: {path}"
            )
        result[path] = {
            "path": path,
            "sizeBytes": size,
            "sha256": str(checksum).lower(),
        }
    return result


def canonical_manifest_sha(entries: list[dict[str, Any]]) -> str:
    value = json.dumps(
        entries,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(value)


def compare_sources(
    baseline_entries: list[dict[str, Any]],
    current_entries: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    baseline = file_index(baseline_entries, "기준 소스")
    current = file_index(current_entries, "현재 소스")
    changes: list[dict[str, Any]] = []
    unchanged = 0
    for path in sorted(set(baseline) | set(current)):
        before = baseline.get(path)
        after = current.get(path)
        if before is None:
            changes.append(
                {
                    "path": path,
                    "changeType": "ADDED",
                    "baselineFile": None,
                    "currentFile": after,
                    "archivePath": f"{ARCHIVE_ROOT}/changes/{path}",
                }
            )
        elif after is None:
            changes.append(
                {
                    "path": path,
                    "changeType": "DELETED",
                    "baselineFile": before,
                    "currentFile": None,
                    "archivePath": None,
                }
            )
        elif (
            before["sizeBytes"] != after["sizeBytes"]
            or before["sha256"] != after["sha256"]
        ):
            changes.append(
                {
                    "path": path,
                    "changeType": "MODIFIED",
                    "baselineFile": before,
                    "currentFile": after,
                    "archivePath": f"{ARCHIVE_ROOT}/changes/{path}",
                }
            )
        else:
            unchanged += 1
    return changes, unchanged


def payload_allowed(path: PurePosixPath, size: int) -> bool:
    relative = Path(*path.parts)
    name = relative.name.lower()
    if (
        is_environment_file(relative.name)
        or name in SECRET_FILE_NAMES
        or name.startswith(("credentials.", "secrets."))
    ):
        return False
    suffix = relative.suffix.lower()
    if suffix == ".jar" and is_gradle_wrapper_jar(relative):
        return True
    if suffix == ".sql" and is_flyway_migration(relative):
        return True
    if (
        suffix in {".jpg", ".jpeg", ".png"}
        and is_frontend_public_image(relative, size)
    ):
        return True
    return suffix not in EXCLUDED_SUFFIXES and suffix != ".sql"


def secret_signature(value: bytes) -> str | None:
    if len(value) > 2 * 1024 * 1024 or b"\x00" in value[:8192]:
        return None
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(value):
            return label
    return None


def build_readme(manifest: dict[str, Any]) -> str:
    summary = manifest["summary"]
    return "\n".join(
        [
            "# VisionFlow 종결 이후 변경분",
            "",
            f"- 상태: **{manifest['status']}**",
            f"- 생성 시각: `{manifest['generatedAt']}`",
            f"- 추가: {summary['added']}개",
            f"- 수정: {summary['modified']}개",
            f"- 삭제: {summary['deleted']}개",
            f"- 변경 없음: {summary['unchanged']}개",
            "",
            "이 ZIP은 종결 기준 이관 패키지 이후의 안전한 소스 변경분만 포함합니다.",
            "삭제 파일은 manifest에만 기록되며 자동으로 삭제하지 않습니다.",
            "환경파일, 운영 키, 인증서 개인키, DB, 백업, 미디어, 모델 가중치는 포함하지 않습니다.",
            "",
            "HP OMEN 이관 직전에는 변경분 ZIP만으로 최종 이관을 대신하지 말고,",
            "전체 검증과 최종 이관 패키지를 최신 소스로 다시 생성해야 합니다.",
            "",
        ]
    )


def build_manifest(
    root: Path,
    baseline: dict[str, Any],
    current_entries: list[dict[str, Any]],
    excluded: list[dict[str, str]],
    changes: list[dict[str, Any]],
    unchanged: int,
    now: datetime,
) -> dict[str, Any]:
    package = baseline["packagePath"]
    counts = Counter(item["changeType"] for item in changes)
    payload = [
        item
        for item in changes
        if item["changeType"] in {"ADDED", "MODIFIED"}
    ]
    status = READY_STATUS if changes else NO_CHANGES_STATUS
    reason_counts = Counter(item["reason"] for item in excluded)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "scope": "SECOND_PROJECT_POST_CLOSEOUT",
        "operation": "POST_CLOSEOUT_CHANGESET",
        "changeSetId": str(uuid.uuid4()),
        "generatedAt": now.isoformat(),
        "status": status,
        "baseline": {
            "transferPackagePath": package.relative_to(root).as_posix(),
            "transferPackageSizeBytes": package.stat().st_size,
            "transferPackageSha256": baseline["packageSha256"],
            "packageId": baseline["packageManifest"].get("packageId"),
            "packageStatus": baseline["packageManifest"].get("status"),
            "sourceArchiveSha256": baseline["sourceArchiveSha256"],
            "sourceManifestSha256": baseline["sourceManifestSha256"],
            "sourceFileCount": len(baseline["sourceManifest"]["files"]),
        },
        "currentSource": {
            "fileCount": len(current_entries),
            "totalBytes": sum(item["sizeBytes"] for item in current_entries),
            "canonicalManifestSha256": canonical_manifest_sha(current_entries),
        },
        "changes": changes,
        "excludedSummary": {
            "entries": len(excluded),
            "reasons": dict(sorted(reason_counts.items())),
        },
        "summary": {
            "added": counts["ADDED"],
            "modified": counts["MODIFIED"],
            "deleted": counts["DELETED"],
            "unchanged": unchanged,
            "payloadFiles": len(payload),
            "payloadBytes": sum(
                item["currentFile"]["sizeBytes"] for item in payload
            ),
            "totalChanges": len(changes),
        },
        "safety": {
            "containsEnvironmentFiles": False,
            "containsOperatorKeys": False,
            "containsPrivateKeys": False,
            "containsDatabaseOrBackup": False,
            "containsRuntimeMedia": False,
            "containsModelWeights": False,
            "sourceFilesModified": False,
            "deletedFilesApplied": False,
            "externalTransferPerformed": False,
        },
    }


def validate_file_metadata(value: Any, title: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PostCloseoutChangesError(f"{title} 메타데이터가 없습니다.")
    path = project_path(value.get("path"), f"{title} 경로").as_posix()
    size = value.get("sizeBytes")
    checksum = value.get("sha256")
    if (
        not isinstance(size, int)
        or isinstance(size, bool)
        or size < 0
        or not is_checksum(checksum)
    ):
        raise PostCloseoutChangesError(f"{title} 메타데이터가 올바르지 않습니다.")
    return {
        "path": path,
        "sizeBytes": size,
        "sha256": str(checksum).lower(),
    }


def verify_changeset_bytes(value: bytes | Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(value, "r") as archive:
            infos = [item for item in archive.infolist() if not item.is_dir()]
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                raise PostCloseoutChangesError(
                    "변경분 ZIP 파일 개수가 허용 범위를 초과했습니다."
                )
            names = [item.filename for item in infos]
            if len(names) != len(set(names)):
                raise PostCloseoutChangesError("변경분 ZIP에 중복 경로가 있습니다.")
            for info in infos:
                path = safe_archive_path(info.filename, "변경분 ZIP 내부 경로")
                if not path.as_posix().startswith(f"{ARCHIVE_ROOT}/"):
                    raise PostCloseoutChangesError(
                        f"허용되지 않은 변경분 ZIP 경로입니다: {path}"
                    )
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise PostCloseoutChangesError(
                        f"변경분 ZIP에 심볼릭 링크가 있습니다: {path}"
                    )
            manifest = read_json_bytes(
                archive.read(MANIFEST_NAME),
                "변경분 manifest",
            )
            if (
                manifest.get("schemaVersion") != SCHEMA_VERSION
                or manifest.get("project") != PROJECT_NAME
                or manifest.get("scope") != "SECOND_PROJECT_POST_CLOSEOUT"
                or manifest.get("operation") != "POST_CLOSEOUT_CHANGESET"
                or manifest.get("status")
                not in {READY_STATUS, NO_CHANGES_STATUS}
            ):
                raise PostCloseoutChangesError(
                    "VisionFlow 종결 이후 변경분 ZIP이 아닙니다."
                )
            changes = manifest.get("changes")
            summary = manifest.get("summary")
            safety = manifest.get("safety")
            baseline = manifest.get("baseline")
            current_source = manifest.get("currentSource")
            if not all(
                isinstance(item, dict)
                for item in (summary, safety, baseline, current_source)
            ) or not isinstance(changes, list):
                raise PostCloseoutChangesError(
                    "변경분 manifest 핵심 메타데이터가 없습니다."
                )
            if (
                safety.get("containsEnvironmentFiles") is not False
                or safety.get("containsOperatorKeys") is not False
                or safety.get("containsPrivateKeys") is not False
                or safety.get("containsDatabaseOrBackup") is not False
                or safety.get("containsRuntimeMedia") is not False
                or safety.get("containsModelWeights") is not False
                or safety.get("sourceFilesModified") is not False
                or safety.get("deletedFilesApplied") is not False
                or safety.get("externalTransferPerformed") is not False
            ):
                raise PostCloseoutChangesError(
                    "변경분 ZIP 안전 메타데이터가 올바르지 않습니다."
                )

            expected = {MANIFEST_NAME, README_NAME}
            seen: set[str] = set()
            counts: Counter[str] = Counter()
            payload_bytes = 0
            for item in changes:
                if not isinstance(item, dict):
                    raise PostCloseoutChangesError(
                        "변경분 항목이 객체가 아닙니다."
                    )
                path = project_path(
                    item.get("path"),
                    "변경 소스 경로",
                ).as_posix()
                if path in seen:
                    raise PostCloseoutChangesError(
                        f"변경분 manifest에 중복 파일이 있습니다: {path}"
                    )
                seen.add(path)
                change_type = item.get("changeType")
                if change_type not in {"ADDED", "MODIFIED", "DELETED"}:
                    raise PostCloseoutChangesError(
                        f"변경 유형이 올바르지 않습니다: {path}"
                    )
                counts[change_type] += 1
                before = item.get("baselineFile")
                after = item.get("currentFile")
                archive_path = item.get("archivePath")

                if change_type == "ADDED":
                    if before is not None:
                        raise PostCloseoutChangesError(
                            f"추가 파일에 기준 메타데이터가 있습니다: {path}"
                        )
                    current = validate_file_metadata(after, "추가 파일")
                elif change_type == "MODIFIED":
                    previous = validate_file_metadata(before, "수정 전 파일")
                    current = validate_file_metadata(after, "수정 후 파일")
                    if previous["path"] != path or current["path"] != path:
                        raise PostCloseoutChangesError(
                            f"수정 파일 경로가 일치하지 않습니다: {path}"
                        )
                    if (
                        previous["sizeBytes"] == current["sizeBytes"]
                        and previous["sha256"] == current["sha256"]
                    ):
                        raise PostCloseoutChangesError(
                            f"수정 파일 내용이 기준과 같습니다: {path}"
                        )
                else:
                    previous = validate_file_metadata(before, "삭제 전 파일")
                    if (
                        previous["path"] != path
                        or after is not None
                        or archive_path is not None
                    ):
                        raise PostCloseoutChangesError(
                            f"삭제 파일 메타데이터가 올바르지 않습니다: {path}"
                        )
                    continue

                if current["path"] != path:
                    raise PostCloseoutChangesError(
                        f"현재 파일 경로가 일치하지 않습니다: {path}"
                    )
                expected_archive = f"{ARCHIVE_ROOT}/changes/{path}"
                if archive_path != expected_archive:
                    raise PostCloseoutChangesError(
                        f"변경 파일 ZIP 경로가 올바르지 않습니다: {path}"
                    )
                expected.add(expected_archive)
                data = archive.read(expected_archive)
                if (
                    len(data) != current["sizeBytes"]
                    or sha256_bytes(data) != current["sha256"]
                ):
                    raise PostCloseoutChangesError(
                        f"변경 파일 무결성이 다릅니다: {path}"
                    )
                relative = safe_archive_path(path, "변경 파일 경로")
                if not payload_allowed(relative, len(data)):
                    raise PostCloseoutChangesError(
                        f"이관 금지 파일이 변경분 ZIP에 있습니다: {path}"
                    )
                signature = secret_signature(data)
                if signature:
                    raise PostCloseoutChangesError(
                        f"고신뢰 비밀정보 패턴이 변경분 ZIP에 있습니다: "
                        f"{path} ({signature})"
                    )
                payload_bytes += len(data)

            if set(names) != expected:
                raise PostCloseoutChangesError(
                    "변경분 ZIP 파일 목록이 manifest와 다릅니다."
                )
            if payload_bytes > MAX_ARCHIVE_BYTES:
                raise PostCloseoutChangesError(
                    "변경분 ZIP payload 용량이 허용 범위를 초과했습니다."
                )
            expected_summary = {
                "added": counts["ADDED"],
                "modified": counts["MODIFIED"],
                "deleted": counts["DELETED"],
                "unchanged": summary.get("unchanged"),
                "payloadFiles": counts["ADDED"] + counts["MODIFIED"],
                "payloadBytes": payload_bytes,
                "totalChanges": len(changes),
            }
            if (
                not isinstance(summary.get("unchanged"), int)
                or isinstance(summary.get("unchanged"), bool)
                or summary.get("unchanged") < 0
                or summary != expected_summary
            ):
                raise PostCloseoutChangesError(
                    "변경분 ZIP 집계가 상세 항목과 일치하지 않습니다."
                )
            expected_status = (
                READY_STATUS if changes else NO_CHANGES_STATUS
            )
            if manifest["status"] != expected_status:
                raise PostCloseoutChangesError(
                    "변경분 ZIP 상태와 변경 개수가 일치하지 않습니다."
                )
            baseline_count = baseline.get("sourceFileCount")
            current_count = current_source.get("fileCount")
            if (
                not isinstance(baseline_count, int)
                or isinstance(baseline_count, bool)
                or not isinstance(current_count, int)
                or isinstance(current_count, bool)
                or baseline_count
                != summary["unchanged"]
                + summary["modified"]
                + summary["deleted"]
                or current_count
                != summary["unchanged"]
                + summary["modified"]
                + summary["added"]
            ):
                raise PostCloseoutChangesError(
                    "변경분 ZIP 기준·현재 파일 개수가 일치하지 않습니다."
                )
            readme = archive.read(README_NAME).decode("utf-8-sig")
            if manifest["status"] not in readme:
                raise PostCloseoutChangesError(
                    "변경분 ZIP README와 manifest 상태가 일치하지 않습니다."
                )
            return manifest
    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError) as error:
        raise PostCloseoutChangesError(
            "변경분 ZIP 또는 내부 manifest가 손상되었습니다."
        ) from error


def verify_changeset_file(
    root: Path,
    value: str,
) -> tuple[Path, dict[str, Any]]:
    bundle = resolve_input(
        root,
        value,
        root / "artifacts/post-closeout-changes",
        "visionflow-post-closeout-changes-*.zip",
        "종결 이후 변경분 ZIP",
    )
    outer_sha = parse_sidecar(bundle, "종결 이후 변경분 ZIP")
    manifest = verify_changeset_bytes(bundle)
    if outer_sha != sha256_file(bundle):
        raise PostCloseoutChangesError(
            "변경분 ZIP 검증 중 파일이 변경됐습니다."
        )
    baseline_meta = manifest.get("baseline")
    if not isinstance(baseline_meta, dict):
        raise PostCloseoutChangesError(
            "변경분 ZIP 기준선 메타데이터가 없습니다."
        )
    package = resolve_input(
        root,
        str(baseline_meta.get("transferPackagePath")),
        root / "artifacts/transfer-package",
        "visionflow-transfer-package-*.zip",
        "종결 기준 이관 패키지",
    )
    if (
        package.stat().st_size
        != baseline_meta.get("transferPackageSizeBytes")
        or sha256_file(package)
        != baseline_meta.get("transferPackageSha256")
    ):
        raise PostCloseoutChangesError(
            "변경분 ZIP과 종결 기준 이관 패키지 동일성이 다릅니다."
        )
    baseline = load_verified_baseline(root, package)
    if (
        baseline["packageManifest"].get("packageId")
        != baseline_meta.get("packageId")
        or baseline["packageManifest"].get("status")
        != baseline_meta.get("packageStatus")
        or baseline["sourceArchiveSha256"]
        != baseline_meta.get("sourceArchiveSha256")
        or baseline["sourceManifestSha256"]
        != baseline_meta.get("sourceManifestSha256")
    ):
        raise PostCloseoutChangesError(
            "변경분 ZIP이 다른 종결 기준 소스를 참조합니다."
        )
    baseline_files = file_index(
        baseline["sourceManifest"].get("files"),
        "종결 기준 소스",
    )
    if baseline_meta.get("sourceFileCount") != len(baseline_files):
        raise PostCloseoutChangesError(
            "변경분 ZIP의 종결 기준 소스 파일 개수가 다릅니다."
        )
    for item in manifest["changes"]:
        path = item["path"]
        change_type = item["changeType"]
        recorded = item.get("baselineFile")
        if change_type == "ADDED":
            if path in baseline_files:
                raise PostCloseoutChangesError(
                    f"추가 파일이 종결 기준 소스에 이미 있습니다: {path}"
                )
        elif path not in baseline_files or recorded != baseline_files[path]:
            raise PostCloseoutChangesError(
                f"변경 파일의 종결 기준 메타데이터가 다릅니다: {path}"
            )
    return bundle, manifest


def create_changeset(
    root: Path,
    package_path: Path,
    *,
    output_root: Path,
    now: datetime,
    max_file_bytes: int,
    max_files: int,
    max_total_bytes: int,
) -> tuple[Path, Path, dict[str, Any]]:
    allowed = (root / "artifacts/post-closeout-changes").resolve()
    output = output_root.resolve()
    if not is_within(output, allowed):
        raise PostCloseoutChangesError(
            "출력 폴더는 artifacts/post-closeout-changes 내부여야 합니다."
        )
    if max_file_bytes <= 0 or max_files <= 0 or max_total_bytes <= 0:
        raise PostCloseoutChangesError(
            "파일 크기·개수·총 용량 제한은 양수여야 합니다."
        )
    baseline = load_verified_baseline(root, package_path)
    try:
        current_entries, excluded = collect_source_files(
            root,
            max_file_bytes=max_file_bytes,
            max_files=max_files,
            max_total_bytes=max_total_bytes,
        )
        validate_required_sources(current_entries)
    except SourceReleaseError as error:
        raise PostCloseoutChangesError(str(error)) from error
    changes, unchanged = compare_sources(
        baseline["sourceManifest"].get("files"),
        current_entries,
    )
    manifest = build_manifest(
        root,
        baseline,
        current_entries,
        excluded,
        changes,
        unchanged,
        now,
    )
    output.mkdir(parents=True, exist_ok=True)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    bundle = output / f"visionflow-post-closeout-changes-{timestamp}.zip"
    if bundle.exists():
        bundle = output / (
            f"visionflow-post-closeout-changes-{timestamp}-"
            f"{uuid.uuid4().hex[:8]}.zip"
        )
    sidecar = bundle.with_suffix(".sha256")
    temporary = bundle.with_suffix(bundle.suffix + ".tmp")
    try:
        manifest_bytes = json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        readme_bytes = build_readme(manifest).encode("utf-8")
        with zipfile.ZipFile(
            temporary,
            "w",
            zipfile.ZIP_DEFLATED,
            allowZip64=True,
        ) as archive:
            for item in changes:
                if item["changeType"] not in {"ADDED", "MODIFIED"}:
                    continue
                relative = PurePosixPath(item["path"])
                source = root.joinpath(*relative.parts)
                if (
                    not source.is_file()
                    or source.is_symlink()
                    or source.stat().st_size
                    != item["currentFile"]["sizeBytes"]
                    or sha256_file(source)
                    != item["currentFile"]["sha256"]
                ):
                    raise PostCloseoutChangesError(
                        f"변경분 생성 중 소스 파일이 변경됐습니다: {relative}"
                    )
                archive.write(source, item["archivePath"])
            archive.writestr(MANIFEST_NAME, manifest_bytes)
            archive.writestr(README_NAME, readme_bytes)
        os.replace(temporary, bundle)
        write_text_atomic(
            sidecar,
            f"{sha256_file(bundle)}  {bundle.name}\n",
        )
        verify_changeset_file(root, str(bundle))
        return bundle, sidecar, manifest
    except Exception:
        temporary.unlink(missing_ok=True)
        bundle.unlink(missing_ok=True)
        sidecar.unlink(missing_ok=True)
        raise


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="VisionFlow post-closeout source changes"
    )
    parser.add_argument("--root", default=str(default_root))
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser(
        "create",
        help="종결 기준 이후 안전 소스 변경분 생성",
    )
    create.add_argument("--package")
    create.add_argument(
        "--output",
        default="artifacts/post-closeout-changes",
    )
    create.add_argument("--max-file-size-mb", type=int, default=10)
    create.add_argument("--max-files", type=int, default=20000)
    create.add_argument("--max-total-size-mb", type=int, default=250)
    verify = subparsers.add_parser(
        "verify",
        help="기존 변경분 ZIP 독립 재검증",
    )
    verify.add_argument("--bundle", required=True)
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    args = build_parser(default_root).parse_args(arguments)
    root = Path(args.root).resolve()
    try:
        if not root.is_dir():
            raise PostCloseoutChangesError(
                f"프로젝트 루트를 찾을 수 없습니다: {root}"
            )
        if args.command == "create":
            package = resolve_input(
                root,
                args.package,
                root / "artifacts/transfer-package",
                "visionflow-transfer-package-*.zip",
                "종결 기준 이관 패키지",
            )
            output_value = Path(args.output)
            output = (
                output_value.resolve()
                if output_value.is_absolute()
                else (root / output_value).resolve()
            )
            bundle, sidecar, manifest = create_changeset(
                root,
                package,
                output_root=output,
                now=datetime.now(timezone.utc),
                max_file_bytes=args.max_file_size_mb * 1024 * 1024,
                max_files=args.max_files,
                max_total_bytes=args.max_total_size_mb * 1024 * 1024,
            )
            summary = manifest["summary"]
            print("VisionFlow post-closeout changes: CREATED")
            print(f"Status: {manifest['status']}")
            print(
                "Changes: "
                f"added={summary['added']}, "
                f"modified={summary['modified']}, "
                f"deleted={summary['deleted']}"
            )
            print(f"Bundle: {bundle}")
            print(f"SHA-256: {sidecar}")
        else:
            bundle, manifest = verify_changeset_file(root, args.bundle)
            print("VisionFlow post-closeout changes: VERIFIED")
            print(f"Status: {manifest['status']}")
            print(f"Bundle: {bundle}")
        return 0
    except (
        PostCloseoutChangesError,
        TransferPackageError,
        HandoffError,
        SourceReleaseError,
        FileNotFoundError,
        OSError,
    ) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
