"""VisionFlow logical backup, integrity verification, and guarded restore tool."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
APP_SERVICES = ("backend-api", "ai-server", "frontend-web")
ARTIFACT_DIRECTORIES = {
    "backend-data": Path("artifacts/backend-data"),
    "ai-output": Path("artifacts/ai-output"),
}
MEDIA_EXTENSIONS = {
    ".avi",
    ".gif",
    ".jpeg",
    ".jpg",
    ".mjpeg",
    ".mov",
    ".mp4",
    ".png",
    ".webm",
}


class BackupError(RuntimeError):
    """Raised for an expected backup or restore failure."""


def sha256_stream(stream: Any) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return sha256_stream(stream)


def run_command(
    arguments: list[str],
    *,
    cwd: Path,
    capture: bool = False,
) -> str:
    result = subprocess.run(
        arguments,
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        command = " ".join(arguments[:4])
        raise BackupError(
            f"명령 실행 실패(exit {result.returncode}): {command}\n{detail}"
        )
    return (result.stdout or "").strip()


def compose_arguments(root: Path, environment_file: Path) -> list[str]:
    compose_file = root / "compose.yaml"
    if not compose_file.is_file():
        raise BackupError(f"Compose 파일을 찾을 수 없습니다: {compose_file}")
    if not environment_file.is_file():
        raise BackupError(f"환경 파일을 찾을 수 없습니다: {environment_file}")
    return [
        "docker",
        "compose",
        "--env-file",
        str(environment_file),
        "-f",
        str(compose_file),
    ]


def ensure_mysql_container(compose: list[str], root: Path) -> str:
    container_id = run_command(
        [*compose, "ps", "-q", "mysql"],
        cwd=root,
        capture=True,
    )
    if not container_id:
        print("[START] MySQL service")
        run_command([*compose, "up", "-d", "--wait", "mysql"], cwd=root)
        container_id = run_command(
            [*compose, "ps", "-q", "mysql"],
            cwd=root,
            capture=True,
        )
    if not container_id:
        raise BackupError("MySQL 컨테이너 ID를 확인할 수 없습니다.")
    return container_id.splitlines()[0].strip()


def running_app_services(compose: list[str], root: Path) -> list[str]:
    output = run_command(
        [*compose, "ps", "--status", "running", "--services"],
        cwd=root,
        capture=True,
    )
    running = set(output.splitlines())
    return [service for service in APP_SERVICES if service in running]


def stop_services(compose: list[str], root: Path, services: list[str]) -> None:
    if services:
        run_command([*compose, "stop", *services], cwd=root)


def start_services(compose: list[str], root: Path, services: list[str]) -> None:
    if services:
        run_command([*compose, "up", "-d", "--wait", *services], cwd=root)


def container_database_name(container_id: str, root: Path) -> str:
    database_name = run_command(
        [
            "docker",
            "exec",
            container_id,
            "sh",
            "-c",
            'printf "%s" "$MYSQL_DATABASE"',
        ],
        cwd=root,
        capture=True,
    )
    if not re.fullmatch(r"[A-Za-z0-9_]+", database_name):
        raise BackupError(f"안전하지 않은 MySQL 데이터베이스 이름: {database_name!r}")
    return database_name


def dump_database(container_id: str, root: Path, destination: Path) -> str:
    database_name = container_database_name(container_id, root)
    container_dump = f"/tmp/visionflow-backup-{uuid.uuid4().hex}.sql"
    dump_script = (
        'set -eu; MYSQL_PWD="$MYSQL_PASSWORD" mysqldump '
        '--user="$MYSQL_USER" --single-transaction --quick '
        '--routines --events --triggers --hex-blob --no-tablespaces '
        '--set-gtid-purged=OFF --default-character-set=utf8mb4 '
        f'"$MYSQL_DATABASE" > "{container_dump}"'
    )
    try:
        run_command(
            ["docker", "exec", container_id, "sh", "-c", dump_script],
            cwd=root,
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        run_command(
            ["docker", "cp", f"{container_id}:{container_dump}", str(destination)],
            cwd=root,
        )
    finally:
        subprocess.run(
            ["docker", "exec", container_id, "rm", "-f", container_dump],
            cwd=root,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    if not destination.is_file() or destination.stat().st_size == 0:
        raise BackupError("MySQL 논리 덤프가 비어 있습니다.")
    return database_name


def copy_artifact_directory(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        return
    if not source.is_dir():
        raise BackupError(f"영속 데이터 경로가 디렉터리가 아닙니다: {source}")
    for item in source.rglob("*"):
        if item.is_symlink():
            raise BackupError(f"백업 범위에 심볼릭 링크가 있습니다: {item}")
    shutil.copytree(source, destination, dirs_exist_ok=True)


def list_payload_files(staging: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in staging.rglob("*")
            if path.is_file() and path.name != "manifest.json"
        ),
        key=lambda path: path.relative_to(staging).as_posix(),
    )


def optional_git_commit(root: Path) -> str | None:
    try:
        return run_command(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture=True,
        )
    except (BackupError, FileNotFoundError):
        return None


def container_image(container_id: str, root: Path) -> str | None:
    try:
        return run_command(
            ["docker", "inspect", "--format={{.Config.Image}}", container_id],
            cwd=root,
            capture=True,
        )
    except BackupError:
        return None


def create_manifest(
    staging: Path,
    *,
    database_name: str,
    mysql_image: str | None,
    git_commit: str | None,
    consistent: bool,
) -> dict[str, Any]:
    files = []
    for path in list_payload_files(staging):
        files.append(
            {
                "path": path.relative_to(staging).as_posix(),
                "sizeBytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "database": {
            "name": database_name,
            "dumpPath": "database/visionflow.sql",
            "mysqlImage": mysql_image,
            "logicalDump": True,
        },
        "artifacts": sorted(ARTIFACT_DIRECTORIES),
        "consistency": {
            "database": "single-transaction",
            "applicationServicesPaused": consistent,
        },
        "gitCommit": git_commit,
        "files": files,
    }


def write_archive(staging: Path, destination: Path) -> None:
    temporary_archive = destination.with_suffix(destination.suffix + ".partial")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(temporary_archive, "w", allowZip64=True) as archive:
            all_files = [staging / "manifest.json", *list_payload_files(staging)]
            for path in all_files:
                relative = path.relative_to(staging).as_posix()
                compression = (
                    zipfile.ZIP_STORED
                    if path.suffix.lower() in MEDIA_EXTENSIONS
                    else zipfile.ZIP_DEFLATED
                )
                archive.write(path, relative, compress_type=compression)
        os.replace(temporary_archive, destination)
    finally:
        if temporary_archive.exists():
            temporary_archive.unlink()


def resolve_under_root(root: Path, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def create_backup(
    root: Path,
    environment_file: Path,
    output_directory: Path,
    *,
    consistent: bool,
) -> Path:
    compose = compose_arguments(root, environment_file)
    previously_running = running_app_services(compose, root)
    if consistent:
        print(f"[PAUSE] Application services: {', '.join(previously_running) or 'none'}")
        stop_services(compose, root, previously_running)

    try:
        container_id = ensure_mysql_container(compose, root)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_directory.mkdir(parents=True, exist_ok=True)
        destination = output_directory / f"visionflow-backup-{timestamp}.zip"
        if destination.exists():
            destination = output_directory / (
                f"visionflow-backup-{timestamp}-{uuid.uuid4().hex[:8]}.zip"
            )

        with tempfile.TemporaryDirectory(
            prefix=".visionflow-backup-",
            dir=output_directory,
        ) as temporary:
            staging = Path(temporary)
            print("[BACKUP] MySQL logical dump")
            database_name = dump_database(
                container_id,
                root,
                staging / "database/visionflow.sql",
            )
            print("[BACKUP] Persistent artifacts")
            for name, relative_source in ARTIFACT_DIRECTORIES.items():
                copy_artifact_directory(
                    root / relative_source,
                    staging / "files" / name,
                )
            manifest = create_manifest(
                staging,
                database_name=database_name,
                mysql_image=container_image(container_id, root),
                git_commit=optional_git_commit(root),
                consistent=consistent,
            )
            (staging / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print("[BACKUP] ZIP package and SHA-256 manifest")
            write_archive(staging, destination)
        verify_archive(destination)
        return destination
    finally:
        if consistent:
            print("[RESUME] Previously running application services")
            start_services(compose, root, previously_running)


def safe_archive_names(archive: zipfile.ZipFile) -> list[str]:
    names = [info.filename for info in archive.infolist() if not info.is_dir()]
    if len(names) != len(set(names)):
        raise BackupError("ZIP 안에 중복된 파일 경로가 있습니다.")
    for name in names:
        path = PurePosixPath(name)
        if name.startswith(("/", "\\")) or "\\" in name or ".." in path.parts:
            raise BackupError(f"ZIP 안에 안전하지 않은 경로가 있습니다: {name}")
    return names


def verify_archive(backup_file: Path) -> dict[str, Any]:
    if not backup_file.is_file():
        raise BackupError(f"백업 ZIP을 찾을 수 없습니다: {backup_file}")
    try:
        with zipfile.ZipFile(backup_file, "r") as archive:
            names = safe_archive_names(archive)
            if "manifest.json" not in names:
                raise BackupError("백업 ZIP에 manifest.json이 없습니다.")
            manifest = json.loads(archive.read("manifest.json").decode("utf-8-sig"))
            if manifest.get("schemaVersion") != SCHEMA_VERSION:
                raise BackupError("지원하지 않는 백업 스키마 버전입니다.")
            if manifest.get("project") != PROJECT_NAME:
                raise BackupError("VisionFlow 백업 파일이 아닙니다.")
            database = manifest.get("database")
            if not isinstance(database, dict):
                raise BackupError("manifest.json의 database가 올바르지 않습니다.")
            database_name = database.get("name")
            if not isinstance(database_name, str) or not re.fullmatch(
                r"[A-Za-z0-9_]+",
                database_name,
            ):
                raise BackupError("manifest.json의 DB 이름이 올바르지 않습니다.")
            if database.get("dumpPath") != "database/visionflow.sql":
                raise BackupError("manifest.json의 DB 덤프 경로가 올바르지 않습니다.")
            entries = manifest.get("files")
            if not isinstance(entries, list):
                raise BackupError("manifest.json의 files가 올바르지 않습니다.")

            expected: dict[str, dict[str, Any]] = {}
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                    raise BackupError("manifest.json에 잘못된 파일 항목이 있습니다.")
                path = entry["path"]
                if path in expected:
                    raise BackupError(f"manifest.json에 중복된 경로가 있습니다: {path}")
                size = entry.get("sizeBytes")
                checksum = entry.get("sha256")
                if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                    raise BackupError(
                        f"manifest 파일 크기가 올바르지 않습니다: {path}"
                    )
                if not isinstance(checksum, str) or not re.fullmatch(
                    r"[0-9a-fA-F]{64}",
                    checksum,
                ):
                    raise BackupError(f"manifest SHA-256이 올바르지 않습니다: {path}")
                expected[path] = entry

            actual = set(names) - {"manifest.json"}
            if actual != set(expected):
                missing = sorted(set(expected) - actual)
                extra = sorted(actual - set(expected))
                raise BackupError(
                    f"백업 파일 목록 불일치. missing={missing}, extra={extra}"
                )
            if "database/visionflow.sql" not in expected:
                raise BackupError("MySQL 논리 덤프가 manifest에 없습니다.")

            total_size = 0
            for path, entry in expected.items():
                info = archive.getinfo(path)
                expected_size = int(entry.get("sizeBytes", -1))
                if info.file_size != expected_size:
                    raise BackupError(f"파일 크기가 다릅니다: {path}")
                with archive.open(path, "r") as stream:
                    actual_hash = sha256_stream(stream)
                if actual_hash.lower() != str(entry.get("sha256", "")).lower():
                    raise BackupError(f"SHA-256이 다릅니다: {path}")
                total_size += info.file_size
            return {
                "status": "VALID",
                "backupFile": str(backup_file),
                "createdAt": manifest.get("createdAt"),
                "databaseName": database_name,
                "fileCount": len(expected),
                "payloadBytes": total_size,
                "manifest": manifest,
            }
    except zipfile.BadZipFile as error:
        raise BackupError(
            f"손상되었거나 올바르지 않은 ZIP입니다: {backup_file}"
        ) from error


def extract_verified_archive(backup_file: Path, destination: Path) -> dict[str, Any]:
    verification = verify_archive(backup_file)
    manifest = verification["manifest"]
    with zipfile.ZipFile(backup_file, "r") as archive:
        for entry in manifest["files"]:
            relative = PurePosixPath(entry["path"])
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry["path"], "r") as source, target.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
    return manifest


def restore_database(container_id: str, root: Path, sql_file: Path) -> None:
    database_name = container_database_name(container_id, root)
    container_restore = f"/tmp/visionflow-restore-{uuid.uuid4().hex}.sql"
    reset_script = (
        'set -eu; MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql --user=root '
        f'-e "DROP DATABASE IF EXISTS {database_name}; '
        f'CREATE DATABASE {database_name} CHARACTER SET utf8mb4 '
        'COLLATE utf8mb4_unicode_ci;"'
    )
    import_script = (
        'set -eu; MYSQL_PWD="$MYSQL_PASSWORD" mysql --user="$MYSQL_USER" '
        f'"$MYSQL_DATABASE" < "{container_restore}"'
    )
    try:
        run_command(
            ["docker", "cp", str(sql_file), f"{container_id}:{container_restore}"],
            cwd=root,
        )
        run_command(
            ["docker", "exec", container_id, "sh", "-c", reset_script],
            cwd=root,
        )
        run_command(
            ["docker", "exec", container_id, "sh", "-c", import_script],
            cwd=root,
        )
    finally:
        subprocess.run(
            ["docker", "exec", container_id, "rm", "-f", container_restore],
            cwd=root,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def restore_artifacts(root: Path, extracted: Path, displaced: Path) -> None:
    for name, relative_target in ARTIFACT_DIRECTORIES.items():
        target = root / relative_target
        source = extracted / "files" / name
        if target.exists():
            displaced_target = displaced / name
            displaced_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(displaced_target))
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            target.mkdir(parents=True, exist_ok=True)


def restore_backup(
    root: Path,
    environment_file: Path,
    backup_file: Path,
    confirmation: str,
) -> tuple[Path, Path]:
    if confirmation != "RESTORE":
        raise BackupError(
            "복구는 기존 DB와 영속 데이터를 교체합니다. "
            "--confirm RESTORE가 필요합니다."
        )
    verification = verify_archive(backup_file)
    compose = compose_arguments(root, environment_file)
    previously_running = running_app_services(compose, root)
    stop_services(compose, root, previously_running)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safety_directory = root / "backups" / "pre-restore"
    displaced = root / "backups" / "displaced" / timestamp
    restore_succeeded = False

    try:
        container_id = ensure_mysql_container(compose, root)
        current_database = container_database_name(container_id, root)
        backup_database = verification["databaseName"]
        if current_database != backup_database:
            raise BackupError(
                f"DB 이름 불일치: current={current_database}, backup={backup_database}"
            )

        print("[SAFETY] Current state backup before restore")
        safety_backup = create_backup(
            root,
            environment_file,
            safety_directory,
            consistent=True,
        )
        with tempfile.TemporaryDirectory(
            prefix=".visionflow-restore-",
            dir=root / "backups",
        ) as temporary:
            extracted = Path(temporary)
            extract_verified_archive(backup_file, extracted)
            print("[RESTORE] MySQL database")
            restore_database(
                container_id,
                root,
                extracted / "database/visionflow.sql",
            )
            print("[RESTORE] Persistent artifacts")
            restore_artifacts(root, extracted, displaced)
        restore_succeeded = True
        return safety_backup, displaced
    finally:
        if restore_succeeded:
            print("[RESUME] Previously running application services")
            start_services(compose, root, previously_running)
        else:
            print(
                "[SAFE] Restore did not complete; application services remain stopped.",
                file=sys.stderr,
            )


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VisionFlow backup and recovery")
    parser.add_argument("--root", default=str(default_root))
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup = subparsers.add_parser("backup", help="MySQL과 영속 증적 백업")
    backup.add_argument("--environment-file", default=".env.docker")
    backup.add_argument("--output-directory", default="backups")
    backup.add_argument("--consistent", action="store_true")

    verify = subparsers.add_parser("verify", help="백업 ZIP 무결성 검증")
    verify.add_argument("--backup", required=True)

    restore = subparsers.add_parser("restore", help="검증된 백업 복구")
    restore.add_argument("--environment-file", default=".env.docker")
    restore.add_argument("--backup", required=True)
    restore.add_argument("--confirm", default="")
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    args = build_parser(default_root).parse_args(arguments)
    root = Path(args.root).resolve()
    try:
        if args.command == "backup":
            environment_file = resolve_under_root(root, args.environment_file)
            output_directory = resolve_under_root(root, args.output_directory)
            destination = create_backup(
                root,
                environment_file,
                output_directory,
                consistent=args.consistent,
            )
            print("\n[PASS] VisionFlow backup completed")
            print(f"Backup: {destination}")
            print(f"SHA256: {sha256_file(destination)}")
        elif args.command == "verify":
            backup_file = resolve_under_root(root, args.backup)
            result = verify_archive(backup_file)
            print("[PASS] VisionFlow backup integrity verified")
            print(json.dumps({k: v for k, v in result.items() if k != "manifest"}, indent=2))
        elif args.command == "restore":
            environment_file = resolve_under_root(root, args.environment_file)
            backup_file = resolve_under_root(root, args.backup)
            safety_backup, displaced = restore_backup(
                root,
                environment_file,
                backup_file,
                args.confirm,
            )
            print("\n[PASS] VisionFlow restore completed")
            print(f"Pre-restore safety backup: {safety_backup}")
            print(f"Displaced artifacts: {displaced}")
        return 0
    except (BackupError, FileNotFoundError, OSError, json.JSONDecodeError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
