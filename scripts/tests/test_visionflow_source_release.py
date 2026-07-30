from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from scripts.visionflow_source_release import (
    SourceReleaseError,
    create_source_release,
    main,
)


class VisionFlowSourceReleaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.now = datetime.now(timezone.utc)
        self.create_project()

    def write(self, relative: str, value: bytes | str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, bytes):
            path.write_bytes(value)
        else:
            path.write_text(value, encoding="utf-8")
        return path

    def create_project(self) -> None:
        self.write("compose.yaml", "services: {}\n")
        self.write(".env.example", "DB_PASSWORD=change-me\n")
        self.write(".env.docker", "DB_PASSWORD=real-local-password\n")
        self.write("README.md", "# VisionFlow\n")

        self.write("01_frontend/visionflow-web/package.json", "{}\n")
        self.write("01_frontend/visionflow-web/package-lock.json", "{}\n")
        self.write("01_frontend/visionflow-web/src/app/page.tsx", "export default function Page() {}\n")
        self.write("01_frontend/visionflow-web/public/logo.png", b"\x89PNG\r\nfixture")
        self.write("01_frontend/visionflow-web/.env.local", "SECRET=local\n")
        self.write("01_frontend/visionflow-web/node_modules/pkg/index.js", "generated\n")
        self.write("01_frontend/visionflow-web/.next/server.js", "generated\n")

        self.write("02_backend/visionflow-api/gradlew.bat", "@echo off\r\n")
        self.write("02_backend/visionflow-api/build.gradle", "plugins {}\n")
        self.write(
            "02_backend/visionflow-api/gradle/wrapper/gradle-wrapper.jar",
            b"gradle-wrapper-fixture",
        )
        self.write(
            "02_backend/visionflow-api/src/main/java/com/visionflow/App.java",
            "class App {}\n",
        )
        self.write(
            "02_backend/visionflow-api/src/main/resources/db/migration/V1__init.sql",
            "CREATE TABLE drone(id BIGINT);\n",
        )
        self.write("02_backend/visionflow-api/build/App.class", b"compiled")

        self.write("03_ai-server/visionflow-ai/requirements.txt", "fastapi==1.0\n")
        self.write("03_ai-server/visionflow-ai/app/main.py", "def main(): pass\n")
        self.write("03_ai-server/visionflow-ai/tests/test_main.py", "def test_ok(): pass\n")
        self.write("03_ai-server/visionflow-ai/models/best.pt", b"model-weight")
        self.write("03_ai-server/visionflow-ai/data/frame.jpg", b"runtime-image")
        self.write("03_ai-server/visionflow-ai/.venv/pyvenv.cfg", "generated\n")
        self.write("scripts/run-visionflow-acceptance.bat", "@echo off\r\n")

    def build(self, **overrides):
        options = {
            "output_root": self.root / "artifacts/source-release",
            "now": self.now,
            "max_file_bytes": 10 * 1024 * 1024,
            "max_files": 20000,
            "max_total_bytes": 250 * 1024 * 1024,
        }
        options.update(overrides)
        return create_source_release(self.root, **options)

    def test_bundle_contains_rebuild_sources_and_excludes_runtime_content(self) -> None:
        bundle, sidecar, manifest = self.build()

        self.assertTrue(bundle.is_file())
        self.assertTrue(sidecar.is_file())
        with zipfile.ZipFile(bundle) as archive:
            names = set(archive.namelist())
        self.assertIn(
            "VisionFlow-Drone/02_backend/visionflow-api/src/main/resources/db/migration/V1__init.sql",
            names,
        )
        self.assertIn(
            "VisionFlow-Drone/02_backend/visionflow-api/gradle/wrapper/gradle-wrapper.jar",
            names,
        )
        self.assertIn("VisionFlow-Drone/01_frontend/visionflow-web/public/logo.png", names)
        self.assertNotIn("VisionFlow-Drone/.env.docker", names)
        self.assertNotIn("VisionFlow-Drone/03_ai-server/visionflow-ai/models/best.pt", names)
        self.assertNotIn("VisionFlow-Drone/03_ai-server/visionflow-ai/data/frame.jpg", names)
        self.assertFalse(manifest["safety"]["runtimeEnvironmentFilesIncluded"])
        self.assertFalse(manifest["safety"]["databaseDumpOrBackupIncluded"])
        reasons = {(item["path"], item["reason"]) for item in manifest["excluded"]}
        self.assertIn((".env.docker", "environment-file"), reasons)

    def test_sidecar_matches_archive(self) -> None:
        bundle, sidecar, _ = self.build()

        checksum = hashlib.sha256(bundle.read_bytes()).hexdigest()
        self.assertEqual(sidecar.read_text(encoding="utf-8"), f"{checksum}  {bundle.name}\n")

    def test_high_confidence_secret_signature_blocks_entire_archive(self) -> None:
        self.write(
            "scripts/unsafe.txt",
            "token=" + "AKIA" + "IOSFODNN7EXAMPLE" + "\n",
        )

        with self.assertRaisesRegex(SourceReleaseError, "비밀정보"):
            self.build()

    def test_missing_flyway_migration_blocks_archive(self) -> None:
        migration = (
            self.root
            / "02_backend/visionflow-api/src/main/resources/db/migration/V1__init.sql"
        )
        migration.unlink()

        with self.assertRaisesRegex(SourceReleaseError, "flyway-migration"):
            self.build()

    def test_output_outside_source_release_root_is_rejected(self) -> None:
        with self.assertRaisesRegex(SourceReleaseError, "출력 폴더"):
            self.build(output_root=self.root / "outside")

    def test_file_count_limit_is_enforced(self) -> None:
        with self.assertRaisesRegex(SourceReleaseError, "파일 수"):
            self.build(max_files=2)

    def test_total_size_limit_is_enforced(self) -> None:
        with self.assertRaisesRegex(SourceReleaseError, "총 용량"):
            self.build(max_total_bytes=10)

    def test_oversized_optional_file_is_excluded(self) -> None:
        self.write("docs/large.txt", "x" * 100)

        _, _, manifest = self.build(max_file_bytes=50)

        excluded = {item["path"]: item["reason"] for item in manifest["excluded"]}
        self.assertEqual(excluded["docs/large.txt"], "file-too-large")

    def test_source_manifest_inside_zip_matches_returned_manifest(self) -> None:
        bundle, _, manifest = self.build()

        with zipfile.ZipFile(bundle) as archive:
            archived = json.loads(
                archive.read("VisionFlow-Drone/SOURCE_MANIFEST.json").decode("utf-8")
            )
        self.assertEqual(archived, manifest)

    def test_cli_creates_archive_with_short_command_defaults(self) -> None:
        exit_code = main(["--root", str(self.root)])

        self.assertEqual(exit_code, 0)
        archives = list(
            (self.root / "artifacts/source-release").glob(
                "visionflow-source-release-*.zip"
            )
        )
        self.assertEqual(len(archives), 1)


if __name__ == "__main__":
    unittest.main()
