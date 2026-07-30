from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from scripts.visionflow_post_closeout_changes import (
    ARCHIVE_ROOT,
    MANIFEST_NAME,
    NO_CHANGES_STATUS,
    READY_STATUS,
    PostCloseoutChangesError,
    create_changeset,
    load_verified_baseline,
    sha256_bytes,
    sha256_file,
    verify_changeset_file,
)
from scripts.visionflow_source_release import collect_source_files


NOW = datetime(2026, 7, 23, 8, 0, tzinfo=timezone.utc)


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def write_sidecar(path: Path) -> None:
    path.with_suffix(".sha256").write_text(
        f"{sha256_file(path)}  {path.name}\n",
        encoding="utf-8",
    )


class PostCloseoutChangesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        write(self.root / "compose.yaml", "services: {}\n")
        write(
            self.root / "01_frontend/visionflow-web/package.json",
            '{"name":"visionflow-web"}\n',
        )
        write(
            self.root / "02_backend/visionflow-api/gradlew.bat",
            "@echo off\n",
        )
        write(
            self.root / "02_backend/visionflow-api/build.gradle",
            "plugins {}\n",
        )
        write(
            self.root
            / "02_backend/visionflow-api/src/main/resources/db/migration/V1__base.sql",
            "CREATE TABLE drone(id BIGINT);\n",
        )
        write(
            self.root / "03_ai-server/visionflow-ai/requirements.txt",
            "fastapi==1.0\n",
        )
        write(
            self.root / "03_ai-server/visionflow-ai/app/main.py",
            "app = object()\n",
        )
        write(self.root / "scripts/existing.py", "VALUE = 1\n")
        write(self.root / "docs/existing.md", "# Existing\n")
        self.output = self.root / "artifacts/post-closeout-changes"
        self.package_dir = self.root / "artifacts/transfer-package"
        self.output.mkdir(parents=True)
        self.package_dir.mkdir(parents=True)
        self.package = (
            self.package_dir
            / "visionflow-transfer-package-20260723T070000Z.zip"
        )
        self.package.write_bytes(b"verified-transfer-package")
        self.baseline_entries, _ = collect_source_files(
            self.root,
            max_file_bytes=10 * 1024 * 1024,
            max_files=20_000,
            max_total_bytes=250 * 1024 * 1024,
        )
        self.source_manifest = {
            "schemaVersion": 1,
            "project": "visionflow",
            "operation": "PORTABLE_SOURCE_RELEASE",
            "files": self.baseline_entries,
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def baseline(self) -> dict:
        return {
            "packagePath": self.package,
            "packageManifest": {
                "packageId": "11111111-1111-4111-8111-111111111111",
                "status": "TRANSFER_PACKAGE_READY_WITH_DEFERRED",
            },
            "packageSha256": sha256_file(self.package),
            "sourceArchiveSha256": "a" * 64,
            "sourceManifestSha256": "b" * 64,
            "sourceManifest": self.source_manifest,
        }

    def make_changes(self) -> None:
        write(self.root / "scripts/existing.py", "VALUE = 2\n")
        write(self.root / "docs/new.md", "# New\n")
        (self.root / "docs/existing.md").unlink()

    def create(self):
        baseline = self.baseline()
        with mock.patch(
            "scripts.visionflow_post_closeout_changes.load_verified_baseline",
            return_value=baseline,
        ):
            return create_changeset(
                self.root,
                self.package,
                output_root=self.output,
                now=NOW,
                max_file_bytes=10 * 1024 * 1024,
                max_files=20_000,
                max_total_bytes=250 * 1024 * 1024,
            )

    def verify(self, bundle: Path):
        baseline = self.baseline()
        with mock.patch(
            "scripts.visionflow_post_closeout_changes.load_verified_baseline",
            return_value=baseline,
        ):
            return verify_changeset_file(self.root, str(bundle))

    def rewrite_bundle(
        self,
        bundle: Path,
        mutate,
        *,
        extra: tuple[str, bytes] | None = None,
    ) -> None:
        replacement = bundle.with_suffix(".replacement.zip")
        with zipfile.ZipFile(bundle, "r") as source, zipfile.ZipFile(
            replacement,
            "w",
            zipfile.ZIP_DEFLATED,
        ) as target:
            for info in source.infolist():
                value = source.read(info.filename)
                target.writestr(info.filename, mutate(info.filename, value))
            if extra:
                target.writestr(extra[0], extra[1])
        os.replace(replacement, bundle)
        write_sidecar(bundle)

    def test_create_and_verify_added_modified_deleted_changes(self) -> None:
        self.make_changes()
        bundle, sidecar, manifest = self.create()
        self.assertTrue(bundle.is_file())
        self.assertTrue(sidecar.is_file())
        self.assertEqual(READY_STATUS, manifest["status"])
        self.assertEqual(
            {
                "added": 1,
                "modified": 1,
                "deleted": 1,
            },
            {
                key: manifest["summary"][key]
                for key in ("added", "modified", "deleted")
            },
        )
        changed = {
            item["path"]: item["changeType"]
            for item in manifest["changes"]
        }
        self.assertEqual("ADDED", changed["docs/new.md"])
        self.assertEqual("MODIFIED", changed["scripts/existing.py"])
        self.assertEqual("DELETED", changed["docs/existing.md"])
        with zipfile.ZipFile(bundle) as archive:
            names = set(archive.namelist())
        self.assertIn(
            f"{ARCHIVE_ROOT}/changes/docs/new.md",
            names,
        )
        self.assertNotIn(
            f"{ARCHIVE_ROOT}/changes/docs/existing.md",
            names,
        )
        verified_path, verified = self.verify(bundle)
        self.assertEqual(bundle, verified_path)
        self.assertEqual(manifest, verified)

    def test_no_changes_creates_verifiable_marker_bundle(self) -> None:
        bundle, _, manifest = self.create()
        self.assertEqual(NO_CHANGES_STATUS, manifest["status"])
        self.assertEqual(0, manifest["summary"]["totalChanges"])
        with zipfile.ZipFile(bundle) as archive:
            self.assertEqual(
                {MANIFEST_NAME, f"{ARCHIVE_ROOT}/README.md"},
                set(archive.namelist()),
            )
        self.verify(bundle)

    def test_environment_file_is_excluded_without_value_leak(self) -> None:
        write(
            self.root / ".env",
            "VISIONFLOW_OPERATOR_KEY=OPERATOR_SHOULD_NOT_LEAK\n",
        )
        bundle, _, manifest = self.create()
        rendered = json.dumps(manifest, ensure_ascii=False)
        self.assertEqual(NO_CHANGES_STATUS, manifest["status"])
        self.assertNotIn("OPERATOR_SHOULD_NOT_LEAK", rendered)
        with zipfile.ZipFile(bundle) as archive:
            self.assertNotIn(
                "OPERATOR_SHOULD_NOT_LEAK",
                archive.read(MANIFEST_NAME).decode("utf-8"),
            )

    def test_high_confidence_secret_blocks_creation(self) -> None:
        write(
            self.root / "scripts/leak.txt",
            "token=" + "sk-" + "abcdefghijklmnopqrstuvwxyz1234567890\n",
        )
        with self.assertRaisesRegex(
            PostCloseoutChangesError,
            "고신뢰 비밀정보",
        ):
            self.create()

    def test_output_outside_artifacts_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            PostCloseoutChangesError,
            "출력 폴더",
        ):
            with mock.patch(
                "scripts.visionflow_post_closeout_changes.load_verified_baseline",
                return_value=self.baseline(),
            ):
                create_changeset(
                    self.root,
                    self.package,
                    output_root=self.root / "outside",
                    now=NOW,
                    max_file_bytes=10 * 1024 * 1024,
                    max_files=20_000,
                    max_total_bytes=250 * 1024 * 1024,
                )

    def test_outer_bundle_tamper_is_rejected(self) -> None:
        self.make_changes()
        bundle, _, _ = self.create()
        with bundle.open("ab") as stream:
            stream.write(b"changed")
        with self.assertRaisesRegex(
            PostCloseoutChangesError,
            "sidecar와 다릅니다",
        ):
            self.verify(bundle)

    def test_inner_payload_tamper_is_rejected_after_resigning(self) -> None:
        self.make_changes()
        bundle, _, _ = self.create()
        target = f"{ARCHIVE_ROOT}/changes/docs/new.md"
        self.rewrite_bundle(
            bundle,
            lambda name, value: b"changed" if name == target else value,
        )
        with self.assertRaisesRegex(
            PostCloseoutChangesError,
            "무결성이 다릅니다",
        ):
            self.verify(bundle)

    def test_path_traversal_is_rejected_after_resigning(self) -> None:
        self.make_changes()
        bundle, _, _ = self.create()
        self.rewrite_bundle(
            bundle,
            lambda _name, value: value,
            extra=(f"{ARCHIVE_ROOT}/../escape.txt", b"escape"),
        )
        with self.assertRaisesRegex(
            PostCloseoutChangesError,
            "안전하지 않은",
        ):
            self.verify(bundle)

    def test_manifest_summary_tamper_is_rejected_after_resigning(self) -> None:
        self.make_changes()
        bundle, _, _ = self.create()

        def mutate(name: str, value: bytes) -> bytes:
            if name != MANIFEST_NAME:
                return value
            manifest = json.loads(value.decode("utf-8"))
            manifest["summary"]["added"] = 99
            return json.dumps(manifest, ensure_ascii=False).encode("utf-8")

        self.rewrite_bundle(bundle, mutate)
        with self.assertRaisesRegex(
            PostCloseoutChangesError,
            "집계",
        ):
            self.verify(bundle)

    def test_changed_baseline_package_is_rejected(self) -> None:
        self.make_changes()
        bundle, _, _ = self.create()
        self.package.write_bytes(b"different-transfer-package")
        with self.assertRaisesRegex(
            PostCloseoutChangesError,
            "동일성이 다릅니다",
        ):
            self.verify(bundle)

    def test_load_verified_baseline_follows_nested_archives(self) -> None:
        source_bytes = b"safe-source-zip"
        handoff_stream = io.BytesIO()
        with zipfile.ZipFile(
            handoff_stream,
            "w",
            zipfile.ZIP_DEFLATED,
        ) as archive:
            archive.writestr("nested/source.zip", source_bytes)
        handoff_bytes = handoff_stream.getvalue()
        with zipfile.ZipFile(
            self.package,
            "w",
            zipfile.ZIP_DEFLATED,
        ) as archive:
            archive.writestr("nested/handoff.zip", handoff_bytes)
        package_manifest = {
            "status": "TRANSFER_PACKAGE_READY_WITH_DEFERRED",
            "handoff": {"archivePath": "nested/handoff.zip"},
        }
        source_result = {
            "manifest": self.source_manifest,
            "manifestSha256": "c" * 64,
            "fileCount": len(self.baseline_entries),
        }
        handoff_manifest = {
            "source": {
                "archivePath": "nested/source.zip",
                "sha256": sha256_bytes(source_bytes),
                "manifestSha256": source_result["manifestSha256"],
            }
        }
        with (
            mock.patch(
                "scripts.visionflow_post_closeout_changes.verify_transfer_package_file",
                return_value=(self.package, package_manifest),
            ),
            mock.patch(
                "scripts.visionflow_post_closeout_changes.verify_handoff_bytes",
                return_value=handoff_manifest,
            ),
            mock.patch(
                "scripts.visionflow_post_closeout_changes.verify_source_bytes",
                return_value=source_result,
            ),
        ):
            result = load_verified_baseline(self.root, self.package)
        self.assertEqual(
            source_result["manifestSha256"],
            result["sourceManifestSha256"],
        )
        self.assertEqual(
            sha256_bytes(source_bytes),
            result["sourceArchiveSha256"],
        )


if __name__ == "__main__":
    unittest.main()
