from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from scripts.visionflow_backup import (
    BackupError,
    create_backup,
    create_manifest,
    restore_backup,
    sha256_file,
    verify_archive,
    write_archive,
)


class VisionFlowBackupTest(unittest.TestCase):
    def create_staging(self, root: Path) -> Path:
        staging = root / "staging"
        database = staging / "database" / "visionflow.sql"
        snapshot = staging / "files" / "backend-data" / "ai-snapshots" / "1.jpg"
        video = staging / "files" / "ai-output" / "annotated.mp4"
        database.parent.mkdir(parents=True)
        snapshot.parent.mkdir(parents=True)
        video.parent.mkdir(parents=True)
        database.write_text("CREATE TABLE drone(id BIGINT);\n", encoding="utf-8")
        snapshot.write_bytes(b"jpeg-data")
        video.write_bytes(b"mp4-data")
        return staging

    def write_manifest(self, staging: Path) -> dict[str, object]:
        manifest = create_manifest(
            staging,
            database_name="visionflow",
            mysql_image="mysql:8.4",
            git_commit="a" * 40,
            consistent=True,
        )
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest

    def test_archive_round_trip_and_hash_verification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staging = self.create_staging(root)
            manifest = self.write_manifest(staging)
            archive = root / "backup.zip"
            write_archive(staging, archive)

            result = verify_archive(archive)

            self.assertEqual(result["status"], "VALID")
            self.assertEqual(result["databaseName"], "visionflow")
            self.assertEqual(result["fileCount"], len(manifest["files"]))
            self.assertEqual(len(sha256_file(archive)), 64)

    @mock.patch("scripts.visionflow_backup.optional_git_commit", return_value="a" * 40)
    @mock.patch("scripts.visionflow_backup.container_image", return_value="mysql:8.4")
    @mock.patch("scripts.visionflow_backup.start_services")
    @mock.patch("scripts.visionflow_backup.stop_services")
    @mock.patch(
        "scripts.visionflow_backup.running_app_services",
        return_value=["backend-api", "ai-server"],
    )
    @mock.patch("scripts.visionflow_backup.ensure_mysql_container", return_value="mysql-id")
    @mock.patch("scripts.visionflow_backup.compose_arguments", return_value=["docker"])
    def test_consistent_backup_pauses_and_resumes_only_running_services(
        self,
        compose_mock: mock.Mock,
        container_mock: mock.Mock,
        running_mock: mock.Mock,
        stop_mock: mock.Mock,
        start_mock: mock.Mock,
        image_mock: mock.Mock,
        git_mock: mock.Mock,
    ) -> None:
        del compose_mock, container_mock, running_mock, image_mock, git_mock
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "artifacts" / "backend-data").mkdir(parents=True)
            (root / "artifacts" / "backend-data" / "snapshot.jpg").write_bytes(b"jpg")
            output = root / "backups"

            def fake_dump(
                container_id: str,
                command_root: Path,
                destination: Path,
            ) -> str:
                self.assertEqual(container_id, "mysql-id")
                self.assertEqual(command_root, root)
                destination.parent.mkdir(parents=True)
                destination.write_text("CREATE TABLE drone(id BIGINT);\n", encoding="utf-8")
                return "visionflow"

            with mock.patch("scripts.visionflow_backup.dump_database", side_effect=fake_dump):
                archive = create_backup(
                    root,
                    root / ".env.docker",
                    output,
                    consistent=True,
                )

            self.assertEqual(verify_archive(archive)["status"], "VALID")
            stop_mock.assert_called_once_with(
                ["docker"],
                root,
                ["backend-api", "ai-server"],
            )
            start_mock.assert_called_once_with(
                ["docker"],
                root,
                ["backend-api", "ai-server"],
            )

    def test_changed_payload_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staging = self.create_staging(root)
            self.write_manifest(staging)
            (staging / "database" / "visionflow.sql").write_text(
                "CORRUPTED\n",
                encoding="utf-8",
            )
            archive = root / "corrupted.zip"
            write_archive(staging, archive)

            with self.assertRaisesRegex(BackupError, "크기가 다릅니다|SHA-256"):
                verify_archive(archive)

    def test_zip_slip_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "unsafe.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../outside.txt", "bad")
                archive.writestr("manifest.json", "{}")

            with self.assertRaisesRegex(BackupError, "안전하지 않은 경로"):
                verify_archive(archive_path)

    def test_unexpected_extra_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staging = self.create_staging(root)
            self.write_manifest(staging)
            archive_path = root / "extra.zip"
            write_archive(staging, archive_path)
            with zipfile.ZipFile(archive_path, "a") as archive:
                archive.writestr("files/untracked.txt", "extra")

            with self.assertRaisesRegex(BackupError, "파일 목록 불일치"):
                verify_archive(archive_path)

    def test_restore_requires_explicit_confirmation_before_any_io(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(BackupError, "--confirm RESTORE"):
                restore_backup(
                    root,
                    root / ".env.docker",
                    root / "missing.zip",
                    "",
                )


if __name__ == "__main__":
    unittest.main()
