"""Create a secret-conscious, rebuildable VisionFlow source release archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
ARCHIVE_ROOT = "VisionFlow-Drone"
ALLOWED_TREE_ROOTS = (
    Path("01_frontend"),
    Path("02_backend"),
    Path("03_ai-server"),
    Path("scripts"),
    Path("docs"),
)
ROOT_FILE_NAMES = {
    ".dockerignore",
    ".env.example",
    ".env.sample",
    ".env.template",
    ".gitignore",
    "compose.yaml",
    "compose.yml",
    "docker-compose.yaml",
    "docker-compose.yml",
}
ROOT_FILE_PREFIXES = ("readme", "license", "changelog")
EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    ".gradle",
    ".idea",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".vscode",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "htmlcov",
    "node_modules",
    "out",
    "target",
    "tmp",
    "venv",
}
EXCLUDED_SUFFIXES = {
    ".7z",
    ".avi",
    ".bak",
    ".class",
    ".csv",
    ".db",
    ".dll",
    ".dylib",
    ".engine",
    ".exe",
    ".h5",
    ".jar",
    ".jpeg",
    ".jpg",
    ".jks",
    ".jsonl",
    ".keystore",
    ".key",
    ".log",
    ".mkv",
    ".mov",
    ".mp4",
    ".npy",
    ".npz",
    ".onnx",
    ".p12",
    ".parquet",
    ".pem",
    ".pfx",
    ".png",
    ".pt",
    ".pth",
    ".pyc",
    ".so",
    ".sqlite",
    ".sqlite3",
    ".tflite",
    ".tar",
    ".tgz",
    ".webm",
    ".zip",
}
SECRET_FILE_NAMES = {
    "credentials.json",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
    "service-account.json",
    "secrets.json",
    "secrets.yml",
    "secrets.yaml",
}
SECRET_PATTERNS = (
    ("private-key", re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("aws-access-key", re.compile(rb"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b")),
    ("openai-key", re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("google-api-key", re.compile(rb"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("slack-token", re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
)


class SourceReleaseError(RuntimeError):
    """Raised when a safe source release cannot be created."""


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


def write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def is_environment_file(name: str) -> bool:
    lowered = name.lower()
    if lowered in {".env.example", ".env.sample", ".env.template"}:
        return False
    return lowered == ".env" or lowered.startswith(".env.")


def is_runtime_data_directory(relative: Path) -> bool:
    parts = tuple(part.lower() for part in relative.parts)
    if not parts:
        return False
    if parts[-1] not in {"artifacts", "backups", "data", "logs", "runs"}:
        return False
    return "src" not in parts and "tests" not in parts and "public" not in parts


def is_gradle_wrapper_jar(relative: Path) -> bool:
    lowered = relative.as_posix().lower()
    return lowered.endswith("/gradle/wrapper/gradle-wrapper.jar")


def is_frontend_public_image(relative: Path, size_bytes: int) -> bool:
    lowered = relative.as_posix().lower()
    return (
        lowered.startswith("01_frontend/visionflow-web/public/")
        and relative.suffix.lower() in {".jpg", ".jpeg", ".png"}
        and size_bytes <= 2 * 1024 * 1024
    )


def is_flyway_migration(relative: Path) -> bool:
    lowered = relative.as_posix().lower()
    return (
        lowered.startswith(
            "02_backend/visionflow-api/src/main/resources/db/migration/"
        )
        and relative.suffix.lower() == ".sql"
    )


def exclusion_reason(relative: Path, path: Path, max_file_bytes: int) -> str | None:
    name = path.name.lower()
    if is_environment_file(path.name):
        return "environment-file"
    if name in SECRET_FILE_NAMES or name.startswith(("credentials.", "secrets.")):
        return "secret-file-name"
    if path.is_symlink():
        return "symbolic-link"
    try:
        size = path.stat().st_size
    except OSError:
        return "unreadable"
    if size > max_file_bytes:
        return "file-too-large"
    suffix = path.suffix.lower()
    if suffix == ".jar" and is_gradle_wrapper_jar(relative):
        return None
    if suffix == ".sql" and is_flyway_migration(relative):
        return None
    if suffix in {".jpg", ".jpeg", ".png"} and is_frontend_public_image(relative, size):
        return None
    if suffix in EXCLUDED_SUFFIXES or suffix == ".sql":
        return "generated-binary-data-or-secret"
    return None


def find_secret_signature(path: Path) -> str | None:
    if path.stat().st_size > 2 * 1024 * 1024:
        return None
    data = path.read_bytes()
    if b"\x00" in data[:8192]:
        return None
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(data):
            return label
    return None


def collect_source_files(
    root: Path,
    *,
    max_file_bytes: int,
    max_files: int,
    max_total_bytes: int,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    included_paths: set[Path] = set()
    excluded: list[dict[str, str]] = []

    for path in root.iterdir():
        if path.is_symlink():
            excluded.append({"path": path.name, "reason": "symbolic-link"})
            continue
        if not path.is_file():
            continue
        lowered = path.name.lower()
        if lowered in ROOT_FILE_NAMES or lowered.startswith(ROOT_FILE_PREFIXES):
            included_paths.add(path)
        elif is_environment_file(path.name):
            excluded.append({"path": path.name, "reason": "environment-file"})

    for relative_root in ALLOWED_TREE_ROOTS:
        tree_root = root / relative_root
        if not tree_root.is_dir() or tree_root.is_symlink():
            continue
        for current, directories, files in os.walk(tree_root, followlinks=False):
            current_path = Path(current)
            kept_directories = []
            for directory in directories:
                directory_path = current_path / directory
                relative = directory_path.relative_to(root)
                lowered = directory.lower()
                if directory_path.is_symlink():
                    excluded.append(
                        {"path": relative.as_posix(), "reason": "symbolic-link-directory"}
                    )
                elif lowered in EXCLUDED_DIRECTORY_NAMES or is_runtime_data_directory(relative):
                    excluded.append(
                        {"path": relative.as_posix(), "reason": "generated-or-runtime-directory"}
                    )
                else:
                    kept_directories.append(directory)
            directories[:] = kept_directories
            for filename in files:
                path = current_path / filename
                relative = path.relative_to(root)
                reason = exclusion_reason(relative, path, max_file_bytes)
                if reason:
                    excluded.append({"path": relative.as_posix(), "reason": reason})
                else:
                    included_paths.add(path)

    included = []
    total_bytes = 0
    for path in sorted(included_paths, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root)
        reason = exclusion_reason(relative, path, max_file_bytes)
        if reason:
            excluded.append({"path": relative.as_posix(), "reason": reason})
            continue
        secret = find_secret_signature(path)
        if secret:
            raise SourceReleaseError(
                f"고신뢰 비밀정보 패턴이 발견됐습니다: {relative.as_posix()} ({secret})"
            )
        size = path.stat().st_size
        total_bytes += size
        if len(included) + 1 > max_files:
            raise SourceReleaseError(f"포함 파일 수가 제한을 초과했습니다: {max_files}")
        if total_bytes > max_total_bytes:
            raise SourceReleaseError(
                f"소스 아카이브 총 용량이 제한을 초과했습니다: {max_total_bytes} bytes"
            )
        included.append(
            {
                "path": relative.as_posix(),
                "sizeBytes": size,
                "sha256": sha256_file(path),
            }
        )
    return included, sorted(excluded, key=lambda item: (item["path"], item["reason"]))


def validate_required_sources(included: list[dict[str, Any]]) -> None:
    paths = {entry["path"].lower() for entry in included}
    requirements = {
        "compose": {
            "compose.yaml",
            "compose.yml",
            "docker-compose.yaml",
            "docker-compose.yml",
        },
        "frontend-package": {"01_frontend/visionflow-web/package.json"},
        "backend-wrapper": {"02_backend/visionflow-api/gradlew.bat"},
        "backend-build": {
            "02_backend/visionflow-api/build.gradle",
            "02_backend/visionflow-api/build.gradle.kts",
        },
        "ai-dependencies": {
            "03_ai-server/visionflow-ai/requirements.txt",
            "03_ai-server/visionflow-ai/pyproject.toml",
        },
    }
    missing = [
        label for label, alternatives in requirements.items()
        if not paths.intersection(alternatives)
    ]
    if not any(path.startswith("03_ai-server/visionflow-ai/app/") for path in paths):
        missing.append("ai-app-source")
    if not any(
        path.startswith(
            "02_backend/visionflow-api/src/main/resources/db/migration/"
        )
        and path.endswith(".sql")
        for path in paths
    ):
        missing.append("flyway-migration")
    if missing:
        raise SourceReleaseError(f"재구축 필수 소스가 누락됐습니다: {sorted(missing)}")


def build_migration_readme(manifest: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# VisionFlow 안전 소스 릴리스",
            "",
            f"- 생성 시각: `{manifest['createdAt']}`",
            f"- 소스 파일: {manifest['summary']['includedFiles']}개",
            f"- 소스 용량: {manifest['summary']['includedBytes']} bytes",
            f"- 제외 항목: {manifest['summary']['excludedEntries']}개",
            "",
            "## HP OMEN 재구축 순서",
            "",
            "1. ZIP을 새 작업 폴더에 풉니다.",
            "2. `.env.example`을 참고해 새 `.env.docker`를 직접 만듭니다.",
            "3. 검증된 MySQL 백업 ZIP은 별도 보안 경로로 복사합니다.",
            "4. `best.pt`는 별도 모델 경로로 복사하고 체크섬을 기록합니다.",
            "5. `docker compose --env-file .env.docker up --build -d`를 실행합니다.",
            "6. acceptance와 release gate를 새 장비에서 다시 실행합니다.",
            "",
            "실제 `.env`, 데이터베이스, 백업, 모델 가중치, 영상은 이 ZIP에 없습니다.",
            "스마트폰 실센서와 GPU/`best.pt` 성능 검증은 새 환경에서 별도로 진행합니다.",
            "DJI Mini 4 Pro 전용 연동은 3차 프로젝트 범위입니다.",
            "",
        ]
    )


def safe_archive_name(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if name.startswith(("/", "\\")) or "\\" in name or ".." in path.parts:
        raise SourceReleaseError(f"안전하지 않은 ZIP 경로입니다: {name}")
    return path


def verify_source_archive(bundle: Path, manifest: dict[str, Any]) -> None:
    try:
        with zipfile.ZipFile(bundle, "r") as archive:
            names = [info.filename for info in archive.infolist() if not info.is_dir()]
            if len(names) != len(set(names)):
                raise SourceReleaseError("소스 ZIP에 중복된 경로가 있습니다.")
            for name in names:
                safe_archive_name(name)
            expected = {
                f"{ARCHIVE_ROOT}/{entry['path']}" for entry in manifest["files"]
            }
            expected.update(
                {
                    f"{ARCHIVE_ROOT}/SOURCE_MANIFEST.json",
                    f"{ARCHIVE_ROOT}/README-MIGRATION.md",
                }
            )
            if set(names) != expected:
                raise SourceReleaseError("소스 ZIP 파일 목록이 manifest와 다릅니다.")
            archived_manifest = json.loads(
                archive.read(f"{ARCHIVE_ROOT}/SOURCE_MANIFEST.json").decode("utf-8-sig")
            )
            if archived_manifest != manifest:
                raise SourceReleaseError("소스 ZIP 내부 manifest가 다릅니다.")
            for entry in manifest["files"]:
                archive_path = f"{ARCHIVE_ROOT}/{entry['path']}"
                data = archive.read(archive_path)
                if len(data) != entry["sizeBytes"]:
                    raise SourceReleaseError(f"ZIP 내부 파일 크기가 다릅니다: {archive_path}")
                if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                    raise SourceReleaseError(f"ZIP 내부 SHA-256이 다릅니다: {archive_path}")
    except zipfile.BadZipFile as error:
        raise SourceReleaseError("생성된 소스 ZIP이 손상되었습니다.") from error


def create_source_release(
    root: Path,
    *,
    output_root: Path,
    now: datetime,
    max_file_bytes: int,
    max_files: int,
    max_total_bytes: int,
) -> tuple[Path, Path, dict[str, Any]]:
    allowed_output = (root / "artifacts/source-release").resolve()
    resolved_output = output_root.resolve()
    if not is_within(resolved_output, allowed_output):
        raise SourceReleaseError("출력 폴더는 artifacts/source-release 내부여야 합니다.")
    included, excluded = collect_source_files(
        root,
        max_file_bytes=max_file_bytes,
        max_files=max_files,
        max_total_bytes=max_total_bytes,
    )
    validate_required_sources(included)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    resolved_output.mkdir(parents=True, exist_ok=True)
    bundle = resolved_output / f"visionflow-source-release-{timestamp}.zip"
    if bundle.exists():
        bundle = resolved_output / (
            f"visionflow-source-release-{timestamp}-{uuid.uuid4().hex[:8]}.zip"
        )
    sidecar = bundle.with_suffix(".sha256")
    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "operation": "PORTABLE_SOURCE_RELEASE",
        "createdAt": now.isoformat(),
        "archiveRoot": ARCHIVE_ROOT,
        "summary": {
            "includedFiles": len(included),
            "includedBytes": sum(entry["sizeBytes"] for entry in included),
            "excludedEntries": len(excluded),
        },
        "files": included,
        "excluded": excluded,
        "safety": {
            "runtimeEnvironmentFilesIncluded": False,
            "databaseDumpOrBackupIncluded": False,
            "modelWeightsIncluded": False,
            "runtimeMediaIncluded": False,
            "secretSignatureScan": "HIGH_CONFIDENCE",
        },
    }
    manifest_bytes = json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    readme_bytes = build_migration_readme(manifest).encode("utf-8")
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry in included:
            source = root.joinpath(*PurePosixPath(entry["path"]).parts)
            archive.write(source, f"{ARCHIVE_ROOT}/{entry['path']}")
        archive.writestr(f"{ARCHIVE_ROOT}/SOURCE_MANIFEST.json", manifest_bytes)
        archive.writestr(f"{ARCHIVE_ROOT}/README-MIGRATION.md", readme_bytes)
    verify_source_archive(bundle, manifest)
    checksum = sha256_file(bundle)
    write_text_atomic(sidecar, f"{checksum}  {bundle.name}\n")
    return bundle, sidecar, manifest


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VisionFlow portable source release")
    parser.add_argument("--root", default=str(default_root))
    parser.add_argument("--output", default="artifacts/source-release")
    parser.add_argument("--max-file-size-mb", type=int, default=10)
    parser.add_argument("--max-files", type=int, default=20000)
    parser.add_argument("--max-total-size-mb", type=int, default=250)
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    args = build_parser(default_root).parse_args(arguments)
    root = Path(args.root).resolve()
    try:
        if not root.is_dir():
            raise SourceReleaseError(f"프로젝트 루트를 찾을 수 없습니다: {root}")
        if args.max_file_size_mb <= 0 or args.max_files <= 0 or args.max_total_size_mb <= 0:
            raise SourceReleaseError("파일 크기·개수·총 용량 제한은 양수여야 합니다.")
        output = Path(args.output)
        output_root = output.resolve() if output.is_absolute() else (root / output).resolve()
        bundle, sidecar, manifest = create_source_release(
            root,
            output_root=output_root,
            now=datetime.now(timezone.utc),
            max_file_bytes=args.max_file_size_mb * 1024 * 1024,
            max_files=args.max_files,
            max_total_bytes=args.max_total_size_mb * 1024 * 1024,
        )
        print("VisionFlow portable source release: CREATED")
        print(f"Files: {manifest['summary']['includedFiles']}")
        print(f"Bundle: {bundle}")
        print(f"SHA-256: {sidecar}")
        return 0
    except (SourceReleaseError, FileNotFoundError, OSError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
