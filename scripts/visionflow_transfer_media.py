"""Stage and verify a self-contained VisionFlow transfer media directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

try:
    from visionflow_hp_omen_restore import (
        HpOmenRestoreError,
        inspect_package,
    )
    from visionflow_transfer_package import TransferPackageError
except ModuleNotFoundError:  # pragma: no cover - package import during tests
    from scripts.visionflow_hp_omen_restore import (
        HpOmenRestoreError,
        inspect_package,
    )
    from scripts.visionflow_transfer_package import TransferPackageError


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
OPERATION = "TRANSFER_MEDIA_STAGING"
READY_STATUS = "TRANSFER_MEDIA_READY_WITH_DEFERRED"
CONFIRMATION = "STAGE_VERIFIED_TRANSFER_MEDIA"
PACKAGE_DIRECTORY = PurePosixPath("package")
EVIDENCE_DIRECTORY = PurePosixPath("evidence")
TOOLS_DIRECTORY = PurePosixPath("tools/scripts")
MANIFEST_NAME = "TRANSFER_MEDIA_MANIFEST.json"
README_NAME = "README.md"

BOOTSTRAP_FILES = (
    "run-visionflow-hp-omen-transfer-day.bat",
    "run-visionflow-hp-omen-restore.bat",
    "run-visionflow-hp-omen-restore-verify.bat",
    "visionflow_hp_omen_transfer_day.py",
    "visionflow_hp_omen_restore.py",
    "visionflow_backup.py",
    "visionflow_gpu_preflight_evidence.py",
    "visionflow_machine_readiness.py",
    "visionflow_migration_handoff.py",
    "visionflow_transfer_package.py",
)


class TransferMediaError(RuntimeError):
    """Raised when transfer media staging or verification is unsafe."""


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


def write_text_atomic(
    path: Path,
    value: str,
    *,
    encoding: str = "utf-8",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding=encoding)
    os.replace(temporary, path)


def read_json(path: Path, title: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise TransferMediaError(f"{title} 파일을 찾을 수 없습니다: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TransferMediaError(
            f"{title} JSON 형식이 올바르지 않습니다."
        ) from error
    if not isinstance(value, dict):
        raise TransferMediaError(f"{title} 최상위 값은 객체여야 합니다.")
    return value


def safe_relative(value: Any, title: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise TransferMediaError(f"{title} 경로가 비어 있습니다.")
    path = PurePosixPath(value)
    if (
        value.startswith(("/", "\\"))
        or "\\" in value
        or path.is_absolute()
        or ".." in path.parts
        or "." in path.parts
    ):
        raise TransferMediaError(f"{title} 경로가 안전하지 않습니다: {value}")
    return path


def media_path(media_root: Path, value: Any, title: str) -> Path:
    relative = safe_relative(value, title)
    path = (media_root / Path(*relative.parts)).resolve()
    if not is_within(path, media_root.resolve()):
        raise TransferMediaError(f"{title} 경로가 매체 밖에 있습니다: {value}")
    return path


def file_entry(media_root: Path, key: str, path: Path) -> dict[str, Any]:
    try:
        relative = path.resolve().relative_to(media_root.resolve()).as_posix()
    except ValueError as error:
        raise TransferMediaError(
            f"매체 파일 경로가 매체 밖에 있습니다: {path}"
        ) from error
    return {
        "key": key,
        "path": relative,
        "sizeBytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def verify_file_entry(
    media_root: Path,
    entry: Any,
    *,
    expected_key: str,
    expected_path: str | None = None,
) -> Path:
    if not isinstance(entry, dict) or entry.get("key") != expected_key:
        raise TransferMediaError(
            f"매체 manifest의 {expected_key} 항목이 올바르지 않습니다."
        )
    path_value = entry.get("path")
    if expected_path is not None and path_value != expected_path:
        raise TransferMediaError(
            f"{expected_key} 경로가 예상값과 다릅니다: {path_value}"
        )
    path = media_path(media_root, path_value, expected_key)
    checksum = entry.get("sha256")
    size = entry.get("sizeBytes")
    if (
        not path.is_file()
        or path.is_symlink()
        or not isinstance(size, int)
        or isinstance(size, bool)
        or size < 0
        or path.stat().st_size != size
        or not is_checksum(checksum)
        or sha256_file(path) != str(checksum).lower()
    ):
        raise TransferMediaError(
            f"매체 파일 크기 또는 SHA-256이 다릅니다: {path_value}"
        )
    return path


def resolve_package(root: Path, value: str | None) -> Path:
    allowed = (root / "artifacts/transfer-package").resolve()
    if value:
        candidate = Path(value)
        package = (
            candidate.resolve()
            if candidate.is_absolute()
            else (root / candidate).resolve()
        )
    else:
        candidates = [
            path.resolve()
            for path in allowed.glob("visionflow-transfer-package-*.zip")
            if path.is_file() and not path.is_symlink()
        ]
        if not candidates:
            raise TransferMediaError(
                "최종 이관 패키지를 찾을 수 없습니다. "
                "이관 전 전체 갱신을 먼저 실행하세요."
            )
        package = max(
            candidates,
            key=lambda path: (path.stat().st_mtime_ns, path.name),
        )
    if (
        not is_within(package, allowed)
        or not package.is_file()
        or package.is_symlink()
        or package.suffix.lower() != ".zip"
        or not package.name.startswith("visionflow-transfer-package-")
    ):
        raise TransferMediaError(
            f"허용된 최종 이관 패키지가 아닙니다: {package}"
        )
    try:
        inspect_package(str(package))
    except (
        HpOmenRestoreError,
        TransferPackageError,
        FileNotFoundError,
        OSError,
    ) as error:
        raise TransferMediaError(str(error)) from error
    return package


def resolve_release_evidence(root: Path, value: str | None) -> Path:
    allowed = (root / "artifacts/release-evidence").resolve()
    if value:
        candidate = Path(value)
        bundle = (
            candidate.resolve()
            if candidate.is_absolute()
            else (root / candidate).resolve()
        )
    else:
        candidates = [
            path.resolve()
            for path in allowed.glob("visionflow-release-evidence-*.zip")
            if path.is_file() and not path.is_symlink()
        ]
        if not candidates:
            raise TransferMediaError(
                "릴리스 증빙 ZIP을 찾을 수 없습니다. "
                "릴리스 증빙을 다시 생성하세요."
            )
        bundle = max(
            candidates,
            key=lambda path: (path.stat().st_mtime_ns, path.name),
        )
    if (
        not is_within(bundle, allowed)
        or not bundle.is_file()
        or bundle.is_symlink()
        or bundle.suffix.lower() != ".zip"
        or not bundle.name.startswith("visionflow-release-evidence-")
    ):
        raise TransferMediaError(
            f"허용된 릴리스 증빙 ZIP이 아닙니다: {bundle}"
        )
    sidecar = bundle.with_suffix(".sha256")
    if not sidecar.is_file() or sidecar.is_symlink():
        raise TransferMediaError("릴리스 증빙 SHA-256 sidecar가 없습니다.")
    parts = sidecar.read_text(encoding="utf-8-sig").strip().split()
    if (
        len(parts) != 2
        or parts[1] != bundle.name
        or not is_checksum(parts[0])
        or parts[0].lower() != sha256_file(bundle)
    ):
        raise TransferMediaError("릴리스 증빙 SHA-256이 일치하지 않습니다.")
    return bundle


def resolve_bootstrap_files(root: Path) -> list[Path]:
    scripts = (root / "scripts").resolve()
    resolved: list[Path] = []
    for name in BOOTSTRAP_FILES:
        path = (scripts / name).resolve()
        if (
            not is_within(path, scripts)
            or not path.is_file()
            or path.is_symlink()
        ):
            raise TransferMediaError(
                f"HP OMEN 복원 필수 도구가 없습니다: scripts/{name}"
            )
        resolved.append(path)
    return resolved


def render_readme(package_name: str, evidence_name: str) -> str:
    return f"""# VisionFlow HP OMEN 이관 매체

이 폴더는 LG GRAM에서 검증된 최종 이관 패키지와 HP OMEN 부트스트랩 도구를
빠짐없이 함께 옮기기 위해 생성되었습니다.

## 포함된 민감 정보

`package/{package_name}`에는 실제 MySQL 백업과 운영 증적이 포함됩니다.
공개 Git 저장소, 공개 클라우드, 공용 메신저에 업로드하지 마세요.

`evidence/{evidence_name}`에는 SOURCE 이관 리허설이 포함된 릴리스 증빙이
들어 있습니다. HP OMEN TARGET 게이트에서 이 파일을 사용합니다.

## HP OMEN에서 첫 검증

이 매체의 루트에서 다음 명령을 실행합니다.

```bat
tools\\scripts\\run-visionflow-hp-omen-transfer-day.bat bootstrap ^
  --package "package\\{package_name}" ^
  --workspace "C:\\VisionFlow-Drone" ^
  --confirm PREPARE_HP_OMEN_WORKSPACE
```

작업공간 준비 후 같은 명령의 `resume`과 `status`로 체크포인트를 이어갑니다.
세부 절차는 최종 패키지 안의 `docs\\HP_OMEN_TRANSFER_DAY.md`를 확인하세요.

HP 활성화와 TARGET 릴리스 증빙 재생성이 끝난 뒤 다음 SOURCE 증빙을 지정해 최종
게이트를 실행합니다.

```bat
C:\\VisionFlow-Drone\\scripts\\run-visionflow-transfer-day-gate.bat target ^
  --source-release-evidence "evidence\\{evidence_name}"
```

## 주의

- `.env.docker`, 운영자 키, 인증서 개인키, `best.pt`는 포함하지 않습니다.
- 스마트폰 실센서 검증과 GPU `best.pt` 성능 검증은 HP 런타임 준비 후 진행합니다.
- DJI Mini 4 Pro 전용 연동은 3차 프로젝트 범위입니다.
"""


def build_plan() -> list[dict[str, Any]]:
    return [
        {
            "order": 1,
            "mode": "READ_ONLY",
            "title": "최신 이관 패키지·릴리스 증빙과 sidecar 검증",
        },
        {
            "order": 2,
            "mode": "READ_ONLY",
            "title": "HP OMEN 체크포인트·복원용 최소 부트스트랩 도구 확인",
        },
        {
            "order": 3,
            "mode": "CONFIRMATION",
            "title": "존재하지 않는 새 이관 매체 폴더에 원자적으로 복사",
        },
        {
            "order": 4,
            "mode": "VERIFY",
            "title": "패키지·릴리스 증빙 복사본과 부트스트랩 도구 재검증",
        },
        {
            "order": 5,
            "mode": "MANUAL",
            "title": "암호화된 외장 SSD를 안전하게 분리해 HP OMEN으로 이동",
        },
    ]


def verify_media(value: str | Path) -> tuple[Path, dict[str, Any]]:
    media_root = Path(value).resolve()
    if (
        not media_root.is_dir()
        or media_root.is_symlink()
        or media_root.parent == media_root
    ):
        raise TransferMediaError(
            f"이관 매체 폴더를 찾을 수 없습니다: {media_root}"
        )
    manifest = read_json(
        media_root / MANIFEST_NAME,
        "이관 매체 manifest",
    )
    if (
        manifest.get("schemaVersion") != SCHEMA_VERSION
        or manifest.get("project") != PROJECT_NAME
        or manifest.get("operation") != OPERATION
        or manifest.get("status") != READY_STATUS
    ):
        raise TransferMediaError(
            "이관 매체 manifest 상태 또는 형식이 올바르지 않습니다."
        )

    package_entry = manifest.get("package")
    if not isinstance(package_entry, dict):
        raise TransferMediaError("이관 매체 package 메타데이터가 없습니다.")
    package_name = package_entry.get("fileName")
    if (
        not isinstance(package_name, str)
        or Path(package_name).name != package_name
        or not package_name.startswith("visionflow-transfer-package-")
        or not package_name.endswith(".zip")
    ):
        raise TransferMediaError("이관 패키지 파일명이 올바르지 않습니다.")
    package_path = verify_file_entry(
        media_root,
        package_entry.get("archive"),
        expected_key="transfer-package",
        expected_path=(PACKAGE_DIRECTORY / package_name).as_posix(),
    )
    sidecar_name = Path(package_name).with_suffix(".sha256").name
    verify_file_entry(
        media_root,
        package_entry.get("sidecar"),
        expected_key="transfer-package-sidecar",
        expected_path=(PACKAGE_DIRECTORY / sidecar_name).as_posix(),
    )

    release_entry = manifest.get("releaseEvidence")
    if not isinstance(release_entry, dict):
        raise TransferMediaError(
            "이관 매체 releaseEvidence 메타데이터가 없습니다."
        )
    release_name = release_entry.get("fileName")
    if (
        not isinstance(release_name, str)
        or Path(release_name).name != release_name
        or not release_name.startswith("visionflow-release-evidence-")
        or not release_name.endswith(".zip")
    ):
        raise TransferMediaError("릴리스 증빙 파일명이 올바르지 않습니다.")
    release_path = verify_file_entry(
        media_root,
        release_entry.get("archive"),
        expected_key="release-evidence",
        expected_path=(EVIDENCE_DIRECTORY / release_name).as_posix(),
    )
    release_sidecar_name = Path(release_name).with_suffix(".sha256").name
    release_sidecar = verify_file_entry(
        media_root,
        release_entry.get("sidecar"),
        expected_key="release-evidence-sidecar",
        expected_path=(
            EVIDENCE_DIRECTORY / release_sidecar_name
        ).as_posix(),
    )
    release_parts = release_sidecar.read_text(
        encoding="utf-8-sig"
    ).strip().split()
    release_checksum = sha256_file(release_path)
    if (
        len(release_parts) != 2
        or release_parts[1] != release_name
        or not is_checksum(release_parts[0])
        or release_parts[0].lower() != release_checksum
        or release_entry.get("sha256") != release_checksum
        or release_entry.get("sizeBytes") != release_path.stat().st_size
    ):
        raise TransferMediaError(
            "이관 매체 릴리스 증빙 요약과 sidecar가 다릅니다."
        )

    tools = manifest.get("tools")
    if not isinstance(tools, list) or len(tools) != len(BOOTSTRAP_FILES):
        raise TransferMediaError("부트스트랩 도구 목록이 올바르지 않습니다.")
    entries_by_key: dict[str, dict[str, Any]] = {}
    for entry in tools:
        if not isinstance(entry, dict) or not isinstance(
            entry.get("key"), str
        ):
            raise TransferMediaError("부트스트랩 도구 항목이 올바르지 않습니다.")
        key = str(entry["key"])
        if key in entries_by_key:
            raise TransferMediaError(f"부트스트랩 도구가 중복됐습니다: {key}")
        entries_by_key[key] = entry
    if set(entries_by_key) != set(BOOTSTRAP_FILES):
        raise TransferMediaError("필수 부트스트랩 도구 구성이 다릅니다.")
    for name in BOOTSTRAP_FILES:
        verify_file_entry(
            media_root,
            entries_by_key[name],
            expected_key=name,
            expected_path=(TOOLS_DIRECTORY / name).as_posix(),
        )

    expected_files = {
        README_NAME,
        MANIFEST_NAME,
        (PACKAGE_DIRECTORY / package_name).as_posix(),
        (PACKAGE_DIRECTORY / sidecar_name).as_posix(),
        (EVIDENCE_DIRECTORY / release_name).as_posix(),
        (EVIDENCE_DIRECTORY / release_sidecar_name).as_posix(),
        *{
            (TOOLS_DIRECTORY / name).as_posix()
            for name in BOOTSTRAP_FILES
        },
    }
    actual_files = {
        path.relative_to(media_root).as_posix()
        for path in media_root.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if actual_files != expected_files:
        missing = sorted(expected_files - actual_files)
        unexpected = sorted(actual_files - expected_files)
        raise TransferMediaError(
            "이관 매체 파일 구성이 다릅니다. "
            f"missing={missing}, unexpected={unexpected}"
        )

    try:
        _, package_manifest, checksum = inspect_package(str(package_path))
    except (
        HpOmenRestoreError,
        TransferPackageError,
        FileNotFoundError,
        OSError,
    ) as error:
        raise TransferMediaError(str(error)) from error
    if (
        package_entry.get("status") != package_manifest.get("status")
        or package_entry.get("sha256") != checksum
        or package_entry.get("sizeBytes") != package_path.stat().st_size
    ):
        raise TransferMediaError(
            "이관 패키지 요약과 실제 검증 결과가 다릅니다."
        )
    safety = manifest.get("safety")
    if (
        not isinstance(safety, dict)
        or safety.get("containsOperationalDatabaseBackup") is not True
        or safety.get("containsReleaseEvidence") is not True
        or safety.get("containsEnvironmentFiles") is not False
        or safety.get("containsOperatorKeys") is not False
        or safety.get("containsCertificatePrivateKeys") is not False
        or safety.get("containsModelWeights") is not False
        or safety.get("destinationWasNew") is not True
    ):
        raise TransferMediaError("이관 매체 안전 메타데이터가 올바르지 않습니다.")
    return media_root, manifest


def stage_media(
    root: Path,
    *,
    package_value: str | None,
    release_evidence_value: str | None,
    destination_value: str,
    confirmation: str,
    now: datetime,
) -> tuple[Path, dict[str, Any]]:
    root = root.resolve()
    if confirmation != CONFIRMATION:
        raise TransferMediaError(
            f"이관 매체 생성에는 --confirm {CONFIRMATION}이 필요합니다."
        )
    package = resolve_package(root, package_value)
    release_evidence = resolve_release_evidence(
        root,
        release_evidence_value,
    )
    bootstrap_files = resolve_bootstrap_files(root)
    destination = Path(destination_value).resolve()
    if destination.exists() or destination.is_symlink():
        raise TransferMediaError(
            f"대상 폴더가 이미 존재합니다. 새 경로를 사용하세요: {destination}"
        )
    if is_within(destination, root):
        raise TransferMediaError(
            "이관 매체 대상은 프로젝트 폴더 밖의 새 경로여야 합니다."
        )
    parent = destination.parent
    if not parent.is_dir() or parent.is_symlink():
        raise TransferMediaError(
            f"이관 매체 대상의 상위 폴더를 찾을 수 없습니다: {parent}"
        )

    try:
        source_package, package_manifest, checksum = inspect_package(
            str(package)
        )
    except (
        HpOmenRestoreError,
        TransferPackageError,
        FileNotFoundError,
        OSError,
    ) as error:
        raise TransferMediaError(str(error)) from error
    source_sidecar = source_package.with_suffix(".sha256")
    release_sidecar = release_evidence.with_suffix(".sha256")
    temporary = parent / f".{destination.name}.tmp-{uuid.uuid4().hex}"
    if temporary.exists():
        raise TransferMediaError(
            f"임시 이관 폴더가 이미 존재합니다: {temporary}"
        )

    try:
        package_directory = temporary / Path(*PACKAGE_DIRECTORY.parts)
        evidence_directory = temporary / Path(*EVIDENCE_DIRECTORY.parts)
        tools_directory = temporary / Path(*TOOLS_DIRECTORY.parts)
        package_directory.mkdir(parents=True)
        evidence_directory.mkdir(parents=True)
        tools_directory.mkdir(parents=True)
        copied_package = package_directory / source_package.name
        copied_sidecar = package_directory / source_sidecar.name
        shutil.copy2(source_package, copied_package)
        shutil.copy2(source_sidecar, copied_sidecar)
        copied_evidence = evidence_directory / release_evidence.name
        copied_evidence_sidecar = evidence_directory / release_sidecar.name
        shutil.copy2(release_evidence, copied_evidence)
        shutil.copy2(release_sidecar, copied_evidence_sidecar)
        copied_tools: list[Path] = []
        for source in bootstrap_files:
            target = tools_directory / source.name
            shutil.copy2(source, target)
            copied_tools.append(target)
        write_text_atomic(
            temporary / README_NAME,
            render_readme(source_package.name, release_evidence.name),
        )
        manifest: dict[str, Any] = {
            "schemaVersion": SCHEMA_VERSION,
            "project": PROJECT_NAME,
            "scope": "LG_GRAM_TO_HP_OMEN_OFFLINE_TRANSFER",
            "operation": OPERATION,
            "mediaId": str(uuid.uuid4()),
            "generatedAt": now.isoformat(),
            "status": READY_STATUS,
            "package": {
                "fileName": copied_package.name,
                "status": package_manifest.get("status"),
                "sizeBytes": copied_package.stat().st_size,
                "sha256": checksum,
                "archive": file_entry(
                    temporary,
                    "transfer-package",
                    copied_package,
                ),
                "sidecar": file_entry(
                    temporary,
                    "transfer-package-sidecar",
                    copied_sidecar,
                ),
            },
            "releaseEvidence": {
                "fileName": copied_evidence.name,
                "sizeBytes": copied_evidence.stat().st_size,
                "sha256": sha256_file(copied_evidence),
                "archive": file_entry(
                    temporary,
                    "release-evidence",
                    copied_evidence,
                ),
                "sidecar": file_entry(
                    temporary,
                    "release-evidence-sidecar",
                    copied_evidence_sidecar,
                ),
            },
            "tools": [
                file_entry(temporary, path.name, path)
                for path in copied_tools
            ],
            "deferred": [
                "hp-target-smartphone-https-revalidation",
                "hp-omen-gpu-best-model-benchmark",
            ],
            "outOfScope": ["dji-mini4-pro-integration"],
            "safety": {
                "containsOperationalDatabaseBackup": True,
                "containsReleaseEvidence": True,
                "containsEnvironmentFiles": False,
                "containsOperatorKeys": False,
                "containsCertificatePrivateKeys": False,
                "containsModelWeights": False,
                "destinationWasNew": True,
                "sourceFilesModified": False,
            },
        }
        write_text_atomic(
            temporary / MANIFEST_NAME,
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8-sig",
        )
        verify_media(temporary)
        os.replace(temporary, destination)
        return verify_media(destination)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stage and verify VisionFlow HP OMEN transfer media"
    )
    parser.add_argument("--root", default=str(default_root))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "plan",
        help="파일을 만들지 않고 이관 매체 생성 순서 출력",
    )
    stage = subparsers.add_parser(
        "stage",
        help="새 외장 매체 폴더에 검증된 이관 세트 생성",
    )
    stage.add_argument("--package")
    stage.add_argument("--release-evidence")
    stage.add_argument("--destination", required=True)
    stage.add_argument("--confirm", default="")
    verify = subparsers.add_parser(
        "verify",
        help="복사된 이관 매체를 읽기 전용으로 재검증",
    )
    verify.add_argument("--media", required=True)
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    args = build_parser(default_root).parse_args(arguments)
    root = Path(args.root).resolve()
    try:
        if args.command == "plan":
            print("VisionFlow transfer media: PLAN")
            for item in build_plan():
                print(
                    f"{item['order']:02d}. [{item['mode']}] {item['title']}"
                )
            print("No file, database, Docker, or service was changed.")
            return 0
        if args.command == "stage":
            media_root, manifest = stage_media(
                root,
                package_value=args.package,
                release_evidence_value=args.release_evidence,
                destination_value=args.destination,
                confirmation=args.confirm,
                now=datetime.now(timezone.utc),
            )
            print(f"VisionFlow transfer media: {manifest['status']}")
            print(f"Media   : {media_root}")
            print(f"Manifest: {media_root / MANIFEST_NAME}")
            print(
                "Manifest SHA-256: "
                f"{sha256_file(media_root / MANIFEST_NAME)}"
            )
            print(
                "[SENSITIVE] 실제 MySQL 백업이 포함됐습니다. "
                "암호화된 매체로 관리하세요."
            )
            return 0
        media_root, manifest = verify_media(args.media)
        print("VisionFlow transfer media: VERIFIED")
        print(f"Status  : {manifest['status']}")
        print(f"Media   : {media_root}")
        print(
            "Manifest SHA-256: "
            f"{sha256_file(media_root / MANIFEST_NAME)}"
        )
        return 0
    except (
        TransferMediaError,
        HpOmenRestoreError,
        TransferPackageError,
        FileNotFoundError,
        OSError,
    ) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
