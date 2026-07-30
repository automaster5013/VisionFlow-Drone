"""Classify and reversibly quarantine old VisionFlow checksum evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
QUARANTINE_CONFIRMATION = "QUARANTINE_CHECKSUM_EVIDENCE"
RESTORE_CONFIRMATION = "RESTORE_CHECKSUM_EVIDENCE"
DEFAULT_OUTPUT = Path("artifacts/checksum-quarantine")
ARTIFACT_FAMILIES: dict[str, tuple[Path, str]] = {
    "model-promotion": (
        Path("artifacts/model-promotion"),
        "promotion-*",
    ),
    "model-release-prepare": (
        Path("artifacts/model-release"),
        "release-*",
    ),
    "model-release-activation": (
        Path("artifacts/model-release"),
        "activation-*",
    ),
    "model-soak": (
        Path("artifacts/model-soak"),
        "soak-*",
    ),
    "model-soak-decision": (
        Path("artifacts/model-soak-decision"),
        "decision-*",
    ),
    "model-release-signoff": (
        Path("artifacts/model-release-signoff"),
        "signoff-*",
    ),
}


class ChecksumRetentionError(RuntimeError):
    """Raised when checksum evidence cannot be classified or moved safely."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_checksum(value: object) -> bool:
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
        raise ChecksumRetentionError(
            f"프로젝트 밖의 경로입니다: {path}"
        ) from error


def safe_relative_path(value: object) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise ChecksumRetentionError("격리 상대 경로가 비어 있습니다.")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or "\\" in value
        or ".." in path.parts
    ):
        raise ChecksumRetentionError(
            f"안전하지 않은 격리 상대 경로입니다: {value}"
        )
    return path


def parse_sidecar(sidecar: Path) -> dict[str, str]:
    if not sidecar.is_file() or sidecar.is_symlink():
        raise ChecksumRetentionError(
            f"일반 체크섬 파일이 아닙니다: {sidecar.name}"
        )
    recorded: dict[str, str] = {}
    for line in sidecar.read_text(encoding="utf-8-sig").splitlines():
        parts = line.strip().split()
        if (
            len(parts) != 2
            or not is_checksum(parts[0])
            or Path(parts[1]).name != parts[1]
            or parts[1] in recorded
        ):
            raise ChecksumRetentionError(
                f"체크섬 형식이 올바르지 않습니다: {sidecar.name}"
            )
        recorded[parts[1]] = parts[0].lower()
    if not recorded:
        raise ChecksumRetentionError(
            f"체크섬 대상이 없습니다: {sidecar.name}"
        )
    for name, expected in recorded.items():
        target = sidecar.parent / name
        if not target.is_file() or target.is_symlink():
            raise ChecksumRetentionError(
                f"체크섬 대상이 없습니다: {target.name}"
            )
        if sha256_file(target) != expected:
            raise ChecksumRetentionError(
                f"체크섬 대상 SHA-256이 다릅니다: {target.name}"
            )
    return recorded


def directory_files(directory: Path) -> list[Path]:
    files: list[Path] = []
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise ChecksumRetentionError(
                f"증적 폴더에 심볼릭 링크가 있습니다: {path.name}"
            )
        if path.is_file():
            files.append(path)
    if not files:
        raise ChecksumRetentionError(
            f"비어 있는 증적 폴더입니다: {directory.name}"
        )
    return sorted(files, key=lambda path: path.as_posix())


def validate_run(directory: Path) -> tuple[list[Path], Path]:
    files = directory_files(directory)
    sidecars = [path for path in files if path.suffix.lower() == ".sha256"]
    if len(sidecars) != 1:
        raise ChecksumRetentionError(
            f"증적 폴더의 SHA-256 sidecar가 정확히 하나가 아닙니다: "
            f"{directory.name}"
        )
    if any(path.parent != directory for path in files):
        raise ChecksumRetentionError(
            f"증적 폴더에 예상하지 않은 하위 파일이 있습니다: {directory.name}"
        )
    recorded = parse_sidecar(sidecars[0])
    expected = {
        path.name
        for path in files
        if path != sidecars[0]
    }
    if set(recorded) != expected:
        raise ChecksumRetentionError(
            f"증적 폴더의 체크섬 파일 목록이 다릅니다: {directory.name}"
        )
    return files, sidecars[0]


def modified_at(path: Path) -> float:
    if path.is_dir():
        return max(item.stat().st_mtime for item in directory_files(path))
    return path.stat().st_mtime


def best_effort_modified_at(path: Path) -> float:
    try:
        return modified_at(path)
    except (ChecksumRetentionError, OSError):
        return path.stat().st_mtime


def age_days(path: Path, now: datetime) -> float:
    timestamp = datetime.fromtimestamp(
        modified_at(path),
        tz=timezone.utc,
    )
    return max(
        0.0,
        (now.astimezone(timezone.utc) - timestamp).total_seconds()
        / 86400.0,
    )


def managed_runs(root: Path) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for family, (parent_relative, pattern) in ARTIFACT_FAMILIES.items():
        parent = (root / parent_relative).resolve()
        if not parent.exists():
            continue
        if not parent.is_dir() or parent.is_symlink():
            raise ChecksumRetentionError(
                f"증적 루트가 일반 폴더가 아닙니다: {parent_relative}"
            )
        for directory in sorted(parent.glob(pattern)):
            if not directory.is_dir() or directory.is_symlink():
                continue
            try:
                files, sidecar = validate_run(directory)
                error = None
            except (ChecksumRetentionError, OSError, UnicodeDecodeError) as exc:
                files = []
                sidecar = None
                error = str(exc)
            runs.append(
                {
                    "kind": "artifact-run",
                    "family": family,
                    "path": directory.resolve(),
                    "files": files,
                    "sidecar": sidecar,
                    "modifiedAt": best_effort_modified_at(directory),
                    "validationError": error,
                }
            )
    return runs


def reference_paths(value: object) -> list[str]:
    result: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == "path" and isinstance(item, str):
                result.append(item)
            result.extend(reference_paths(item))
    elif isinstance(value, list):
        for item in value:
            result.extend(reference_paths(item))
    return result


def containing_run(
    path: Path,
    run_paths: Iterable[Path],
) -> Path | None:
    matches = [
        run
        for run in run_paths
        if path == run or is_within(path, run)
    ]
    return max(matches, key=lambda item: len(item.parts)) if matches else None


def referenced_candidates(
    *,
    root: Path,
    runs: list[dict[str, Any]],
    candidates: set[Path],
) -> set[Path]:
    run_paths = {item["path"] for item in runs}
    protected: set[Path] = set()
    artifacts = (root / "artifacts").resolve()
    if not artifacts.is_dir():
        return protected
    for json_path in artifacts.rglob("*.json"):
        if (
            not json_path.is_file()
            or json_path.is_symlink()
            or json_path.stat().st_size > 5 * 1024 * 1024
        ):
            continue
        owner = containing_run(json_path.resolve(), run_paths)
        if owner in candidates:
            continue
        try:
            value = json.loads(
                json_path.read_text(encoding="utf-8-sig")
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ):
            continue
        for raw_path in reference_paths(value):
            candidate = Path(raw_path)
            if candidate.is_absolute():
                continue
            resolved = (root / candidate).resolve()
            if not is_within(resolved, root):
                continue
            referenced_run = containing_run(resolved, run_paths)
            if referenced_run in candidates:
                protected.add(referenced_run)
    return protected


def patch_sidecars(
    *,
    root: Path,
    min_age_days: float,
    now: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    eligible: list[dict[str, Any]] = []
    broken: list[dict[str, Any]] = []
    for sidecar in sorted(root.glob("*.sha256")):
        if not sidecar.is_file() or sidecar.is_symlink():
            continue
        try:
            targets = parse_sidecar(sidecar)
            validation_error = None
        except (ChecksumRetentionError, OSError, UnicodeDecodeError) as error:
            targets = {}
            validation_error = str(error)
        item = {
            "kind": "patch-sidecar",
            "family": "root-patch-checksum",
            "path": sidecar.resolve(),
            "targetCount": len(targets),
            "ageDays": round(age_days(sidecar, now), 3),
            "classification": (
                "VERIFIED_REDUNDANT"
                if validation_error is None
                else "UNVERIFIED_OR_ORPHANED"
            ),
            "validationError": validation_error,
        }
        if item["ageDays"] >= min_age_days:
            eligible.append(item)
        elif validation_error:
            broken.append(item)
    return eligible, broken


def build_plan(
    *,
    root: Path,
    min_age_days: float,
    keep_per_family: int,
    include_patch_sidecars: bool,
    now: datetime,
) -> dict[str, Any]:
    if min_age_days < 0:
        raise ChecksumRetentionError("최소 보존 일수는 0 이상이어야 합니다.")
    if keep_per_family < 1:
        raise ChecksumRetentionError(
            "증적 종류별 최소 보존 개수는 1 이상이어야 합니다."
        )
    root = root.resolve()
    runs = managed_runs(root)
    valid_runs = [
        item for item in runs if item["validationError"] is None
    ]
    broken_runs = [
        item for item in runs if item["validationError"] is not None
    ]
    candidates: set[Path] = set()
    retained_latest: set[Path] = set()
    for family in ARTIFACT_FAMILIES:
        family_runs = sorted(
            [
                item
                for item in valid_runs
                if item["family"] == family
            ],
            key=lambda item: (
                item["modifiedAt"],
                item["path"].as_posix(),
            ),
            reverse=True,
        )
        retained_latest.update(
            item["path"] for item in family_runs[:keep_per_family]
        )
        candidates.update(
            item["path"]
            for item in family_runs[keep_per_family:]
            if age_days(item["path"], now) >= min_age_days
        )

    while True:
        protected = referenced_candidates(
            root=root,
            runs=runs,
            candidates=candidates,
        )
        if not protected:
            break
        candidates.difference_update(protected)

    by_path = {item["path"]: item for item in valid_runs}
    artifact_candidates = []
    for path in sorted(candidates, key=lambda item: item.as_posix()):
        item = by_path[path]
        artifact_candidates.append(
            {
                "kind": "artifact-run",
                "family": item["family"],
                "path": relative_path(root, path),
                "fileCount": len(item["files"]),
                "totalBytes": sum(
                    file.stat().st_size for file in item["files"]
                ),
                "ageDays": round(age_days(path, now), 3),
            }
        )

    patch_candidates: list[dict[str, Any]] = []
    broken_patch: list[dict[str, Any]] = []
    if include_patch_sidecars:
        patch_eligible, broken_patch = patch_sidecars(
            root=root,
            min_age_days=min_age_days,
            now=now,
        )
        patch_candidates = [
            {
                "kind": item["kind"],
                "family": item["family"],
                "path": relative_path(root, item["path"]),
                "fileCount": 1,
                "totalBytes": item["path"].stat().st_size,
                "ageDays": item["ageDays"],
                "targetCount": item["targetCount"],
                "classification": item["classification"],
                "detail": item["validationError"],
            }
            for item in patch_eligible
        ]

    broken = [
        {
            "kind": item["kind"],
            "family": item["family"],
            "path": relative_path(root, item["path"]),
            "detail": item["validationError"],
        }
        for item in broken_runs + broken_patch
    ]
    candidates_list = artifact_candidates + patch_candidates
    return {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "operation": "CHECKSUM_RETENTION_PLAN",
        "generatedAt": now.astimezone(timezone.utc).isoformat(),
        "status": (
            "REVIEW_REQUIRED" if broken_runs else "READY"
        ),
        "policy": {
            "minAgeDays": min_age_days,
            "keepPerFamily": keep_per_family,
            "includePatchSidecars": include_patch_sidecars,
            "permanentDelete": False,
        },
        "summary": {
            "managedArtifactRuns": len(runs),
            "latestProtectedRuns": len(retained_latest),
            "eligibleArtifactRuns": len(artifact_candidates),
            "eligiblePatchSidecars": len(patch_candidates),
            "eligibleItems": len(candidates_list),
            "eligibleBytes": sum(
                item["totalBytes"] for item in candidates_list
            ),
            "brokenItems": len(broken),
        },
        "candidates": candidates_list,
        "broken": broken,
        "safety": {
            "dryRun": True,
            "referencedRunsProtected": True,
            "latestRunsProtected": True,
            "artifactSidecarsMovedWithRun": True,
            "permanentDelete": False,
        },
    }


def item_files(root: Path, item: Mapping[str, Any]) -> list[Path]:
    relative = safe_relative_path(item.get("path"))
    source = root.joinpath(*relative.parts).resolve()
    if not is_within(source, root):
        raise ChecksumRetentionError("정리 후보가 프로젝트 밖에 있습니다.")
    if item.get("kind") == "artifact-run":
        if not source.is_dir() or source.is_symlink():
            raise ChecksumRetentionError(
                f"증적 정리 후보 폴더가 없습니다: {relative}"
            )
        files, _ = validate_run(source)
        return files
    if item.get("kind") == "patch-sidecar":
        if not source.is_file() or source.is_symlink():
            raise ChecksumRetentionError(
                f"일반 체크섬 파일이 아닙니다: {relative}"
            )
        return [source]
    raise ChecksumRetentionError(
        f"지원하지 않는 정리 후보 종류입니다: {item.get('kind')}"
    )


def manifest_group(
    *,
    root: Path,
    item: Mapping[str, Any],
) -> dict[str, Any]:
    relative = safe_relative_path(item.get("path"))
    source = root.joinpath(*relative.parts).resolve()
    files = item_files(root, item)
    entries = []
    for path in files:
        file_relative = (
            path.relative_to(source).as_posix()
            if source.is_dir()
            else path.name
        )
        entries.append(
            {
                "path": file_relative,
                "sizeBytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return {
        "kind": item.get("kind"),
        "family": item.get("family"),
        "classification": item.get("classification"),
        "originalPath": relative.as_posix(),
        "quarantinePath": f"files/{relative.as_posix()}",
        "fileCount": len(entries),
        "totalBytes": sum(entry["sizeBytes"] for entry in entries),
        "files": entries,
    }


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )


def quarantine(
    *,
    root: Path,
    plan: Mapping[str, Any],
    confirmation: str,
    output_root: Path,
    now: datetime,
) -> tuple[Path | None, dict[str, Any]]:
    if confirmation != QUARANTINE_CONFIRMATION:
        raise ChecksumRetentionError(
            f"실제 격리에는 --confirm {QUARANTINE_CONFIRMATION}이 필요합니다."
        )
    if plan.get("status") != "READY":
        raise ChecksumRetentionError(
            "손상된 증적 sidecar가 있어 격리를 실행할 수 없습니다."
        )
    root = root.resolve()
    output_root = output_root.resolve()
    allowed_output = (root / DEFAULT_OUTPUT).resolve()
    if not is_within(output_root, allowed_output):
        raise ChecksumRetentionError(
            "격리 출력은 artifacts/checksum-quarantine 안에 있어야 합니다."
        )
    candidates = plan.get("candidates")
    if not isinstance(candidates, list):
        raise ChecksumRetentionError("체크섬 정리 후보 목록이 없습니다.")
    if not candidates:
        return None, {
            "schemaVersion": SCHEMA_VERSION,
            "project": PROJECT_NAME,
            "operation": "CHECKSUM_RETENTION_QUARANTINE",
            "status": "NO_CANDIDATES",
            "createdAt": now.astimezone(timezone.utc).isoformat(),
            "groupCount": 0,
            "fileCount": 0,
            "totalBytes": 0,
            "groups": [],
        }
    groups = [
        manifest_group(root=root, item=item)
        for item in candidates
        if isinstance(item, Mapping)
    ]
    if len(groups) != len(candidates):
        raise ChecksumRetentionError("체크섬 정리 후보 형식이 다릅니다.")
    timestamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_directory = output_root / f"quarantine-{timestamp}"
    if run_directory.exists():
        run_directory = output_root / (
            f"quarantine-{timestamp}-{uuid.uuid4().hex[:8]}"
        )
    run_directory.mkdir(parents=True, exist_ok=False)
    moved: list[tuple[Path, Path]] = []
    try:
        for group in groups:
            source_relative = safe_relative_path(group["originalPath"])
            quarantine_relative = safe_relative_path(
                group["quarantinePath"]
            )
            source = root.joinpath(*source_relative.parts).resolve()
            destination = run_directory.joinpath(
                *quarantine_relative.parts
            ).resolve()
            if not is_within(destination, run_directory):
                raise ChecksumRetentionError(
                    "격리 대상 경로가 실행 폴더 밖에 있습니다."
                )
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            moved.append((source, destination))
    except Exception as error:
        rollback_errors: list[str] = []
        for source, destination in reversed(moved):
            try:
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), str(source))
            except OSError as rollback_error:
                rollback_errors.append(str(rollback_error))
        raise ChecksumRetentionError(
            f"체크섬 증적 격리 실패. rollbackErrors={rollback_errors}"
        ) from error

    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "operation": "CHECKSUM_RETENTION_QUARANTINE",
        "status": "COMPLETED",
        "createdAt": now.astimezone(timezone.utc).isoformat(),
        "policy": plan.get("policy"),
        "groupCount": len(groups),
        "fileCount": sum(group["fileCount"] for group in groups),
        "totalBytes": sum(group["totalBytes"] for group in groups),
        "groups": groups,
        "safety": {
            "permanentDelete": False,
            "restoreSupported": True,
        },
    }
    manifest_path = run_directory / "quarantine-manifest.json"
    write_json(manifest_path, manifest)
    return manifest_path, manifest


def verify_quarantine_group(
    *,
    root: Path,
    run_directory: Path,
    group: Mapping[str, Any],
) -> tuple[Path, Path]:
    original_relative = safe_relative_path(group.get("originalPath"))
    quarantine_relative = safe_relative_path(group.get("quarantinePath"))
    destination = root.joinpath(*original_relative.parts).resolve()
    source = run_directory.joinpath(*quarantine_relative.parts).resolve()
    if not is_within(destination, root) or not is_within(
        source,
        run_directory,
    ):
        raise ChecksumRetentionError("격리 복원 경로가 허용 범위 밖입니다.")
    if destination.exists():
        raise ChecksumRetentionError(
            f"복원 대상이 이미 존재합니다: {original_relative}"
        )
    files = group.get("files")
    if (
        not isinstance(files, list)
        or group.get("fileCount") != len(files)
    ):
        raise ChecksumRetentionError("격리 manifest 파일 목록이 다릅니다.")
    source_is_directory = group.get("kind") == "artifact-run"
    if source_is_directory:
        if not source.is_dir() or source.is_symlink():
            raise ChecksumRetentionError(
                f"격리 증적 폴더가 없습니다: {source.name}"
            )
    elif group.get("kind") == "patch-sidecar":
        if not source.is_file() or source.is_symlink():
            raise ChecksumRetentionError(
                f"격리 체크섬 파일이 없습니다: {source.name}"
            )
    else:
        raise ChecksumRetentionError("격리 manifest 종류가 올바르지 않습니다.")
    for entry in files:
        if not isinstance(entry, Mapping):
            raise ChecksumRetentionError("격리 파일 항목이 올바르지 않습니다.")
        relative = safe_relative_path(entry.get("path"))
        path = (
            source.joinpath(*relative.parts)
            if source_is_directory
            else source
        )
        if not path.is_file() or path.is_symlink():
            raise ChecksumRetentionError(
                f"격리 파일이 없습니다: {relative}"
            )
        if (
            path.stat().st_size != entry.get("sizeBytes")
            or sha256_file(path) != entry.get("sha256")
        ):
            raise ChecksumRetentionError(
                f"격리 파일 동일성이 다릅니다: {relative}"
            )
    return source, destination


def restore(
    *,
    root: Path,
    manifest_path: Path,
    confirmation: str,
    now: datetime,
) -> Path:
    if confirmation != RESTORE_CONFIRMATION:
        raise ChecksumRetentionError(
            f"격리 복원에는 --confirm {RESTORE_CONFIRMATION}이 필요합니다."
        )
    root = root.resolve()
    manifest_path = manifest_path.resolve()
    quarantine_root = (root / DEFAULT_OUTPUT).resolve()
    if not is_within(manifest_path, quarantine_root):
        raise ChecksumRetentionError(
            "격리 manifest가 checksum-quarantine 밖에 있습니다."
        )
    try:
        manifest = json.loads(
            manifest_path.read_text(encoding="utf-8-sig")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ChecksumRetentionError(
            "격리 manifest를 읽을 수 없습니다."
        ) from error
    if (
        not isinstance(manifest, Mapping)
        or manifest.get("schemaVersion") != SCHEMA_VERSION
        or manifest.get("project") != PROJECT_NAME
        or manifest.get("operation") != "CHECKSUM_RETENTION_QUARANTINE"
        or manifest.get("status") != "COMPLETED"
    ):
        raise ChecksumRetentionError("완료된 체크섬 격리 manifest가 아닙니다.")
    groups = manifest.get("groups")
    if (
        not isinstance(groups, list)
        or manifest.get("groupCount") != len(groups)
    ):
        raise ChecksumRetentionError("격리 manifest 그룹 목록이 다릅니다.")
    run_directory = manifest_path.parent.resolve()
    prepared = [
        verify_quarantine_group(
            root=root,
            run_directory=run_directory,
            group=group,
        )
        for group in groups
        if isinstance(group, Mapping)
    ]
    if len(prepared) != len(groups):
        raise ChecksumRetentionError("격리 manifest 그룹 형식이 다릅니다.")
    restored: list[tuple[Path, Path]] = []
    try:
        for source, destination in prepared:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            restored.append((source, destination))
    except Exception as error:
        rollback_errors: list[str] = []
        for source, destination in reversed(restored):
            try:
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), str(source))
            except OSError as rollback_error:
                rollback_errors.append(str(rollback_error))
        raise ChecksumRetentionError(
            f"체크섬 증적 복원 실패. rollbackErrors={rollback_errors}"
        ) from error
    result_path = run_directory / (
        "restore-result-"
        + now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + ".json"
    )
    write_json(
        result_path,
        {
            "schemaVersion": SCHEMA_VERSION,
            "project": PROJECT_NAME,
            "operation": "CHECKSUM_RETENTION_RESTORE",
            "status": "COMPLETED",
            "restoredAt": now.astimezone(timezone.utc).isoformat(),
            "groupCount": len(restored),
        },
    )
    return result_path


def print_plan(plan: Mapping[str, Any]) -> None:
    summary = plan["summary"]
    print(f"VisionFlow checksum retention: {plan['status']}")
    print(
        "Protected latest artifact runs: "
        f"{summary['latestProtectedRuns']}"
    )
    print(
        "Eligible old artifact runs : "
        f"{summary['eligibleArtifactRuns']}"
    )
    print(
        "Eligible patch checksums   : "
        f"{summary['eligiblePatchSidecars']}"
    )
    print(f"Broken items              : {summary['brokenItems']}")
    print("No file was deleted or moved.")


def add_policy_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-age-days", type=float, default=14.0)
    parser.add_argument("--keep-per-family", type=int, default=3)
    parser.add_argument(
        "--exclude-patch-sidecars",
        action="store_true",
    )


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="VisionFlow checksum and evidence retention"
    )
    parser.add_argument("--root", default=str(default_root))
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan_parser = subparsers.add_parser("plan")
    add_policy_arguments(plan_parser)
    apply_parser = subparsers.add_parser("apply")
    add_policy_arguments(apply_parser)
    apply_parser.add_argument("--confirm", default="")
    apply_parser.add_argument("--output", default=DEFAULT_OUTPUT.as_posix())
    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("--manifest", required=True)
    restore_parser.add_argument("--confirm", default="")
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    args = build_parser(default_root).parse_args(arguments)
    root = Path(args.root).resolve()
    try:
        if args.command == "restore":
            manifest = Path(args.manifest)
            if not manifest.is_absolute():
                manifest = root / manifest
            result = restore(
                root=root,
                manifest_path=manifest,
                confirmation=args.confirm,
                now=datetime.now(timezone.utc),
            )
            print("VisionFlow checksum retention restore: COMPLETED")
            print(f"Result: {result}")
            return 0

        plan = build_plan(
            root=root,
            min_age_days=args.min_age_days,
            keep_per_family=args.keep_per_family,
            include_patch_sidecars=not args.exclude_patch_sidecars,
            now=datetime.now(timezone.utc),
        )
        if args.command == "plan":
            print_plan(plan)
            return 0 if plan["status"] == "READY" else 1

        output = Path(args.output)
        if not output.is_absolute():
            output = root / output
        manifest_path, manifest = quarantine(
            root=root,
            plan=plan,
            confirmation=args.confirm,
            output_root=output,
            now=datetime.now(timezone.utc),
        )
        print(f"VisionFlow checksum retention: {manifest['status']}")
        if manifest_path:
            print(f"Manifest: {manifest_path}")
        print(f"Groups: {manifest['groupCount']}")
        print(f"Files : {manifest['fileCount']}")
        return 0
    except (
        ChecksumRetentionError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
