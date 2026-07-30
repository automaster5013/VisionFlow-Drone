from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.tests.test_visionflow_transfer_package import (
    create_backup,
    create_baseline,
    create_evidence,
    create_readiness,
    create_source,
)
from scripts.visionflow_migration_handoff import create_handoff
from scripts.visionflow_transfer_media import (
    BOOTSTRAP_FILES,
    CONFIRMATION,
    MANIFEST_NAME,
    READY_STATUS,
    TransferMediaError,
    build_plan,
    main,
    resolve_package,
    stage_media,
    verify_media,
)
from scripts.visionflow_transfer_package import (
    CONFIRMATION as PACKAGE_CONFIRMATION,
    create_transfer_package,
)


NOW = datetime(2026, 7, 24, 3, 0, tzinfo=timezone.utc)


class TransferMediaTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "VisionFlow-Drone"
        self.media_parent = self.base / "external-media"
        self.media_parent.mkdir()
        for relative in (
            "artifacts/source-release",
            "artifacts/release-evidence",
            "artifacts/machine-readiness",
            "artifacts/migration-handoff",
            "artifacts/transfer-readiness",
            "artifacts/transfer-package",
            "backups",
            "scripts",
        ):
            (self.root / relative).mkdir(parents=True)
        for name in BOOTSTRAP_FILES:
            (self.root / "scripts" / name).write_text(
                f"bootstrap fixture: {name}\n",
                encoding="utf-8",
            )

        backup = (
            self.root
            / "backups/visionflow-backup-20260724T020000Z.zip"
        )
        create_backup(backup)
        source = (
            self.root
            / "artifacts/source-release/"
            "visionflow-source-release-20260724T020100Z.zip"
        )
        source_sha, manifest_sha = create_source(source)
        evidence = (
            self.root
            / "artifacts/release-evidence/"
            "visionflow-release-evidence-20260724T020200Z.zip"
        )
        create_evidence(evidence, backup)
        self.evidence = evidence
        baseline = (
            self.root
            / "artifacts/machine-readiness/"
            "visionflow-machine-baseline-20260724T020300Z.json"
        )
        create_baseline(baseline, source_sha, manifest_sha)
        handoff, _, _ = create_handoff(
            self.root,
            output_root=self.root / "artifacts/migration-handoff",
            now=NOW - timedelta(hours=2),
        )
        readiness = (
            self.root
            / "artifacts/transfer-readiness/"
            "visionflow-transfer-readiness-20260724T020400Z.json"
        )
        create_readiness(
            readiness,
            handoff,
            generated_at=NOW - timedelta(hours=1),
        )
        self.package, self.package_sidecar, _ = create_transfer_package(
            self.root,
            readiness_value=str(readiness),
            handoff_value=str(handoff),
            backup_value=str(backup),
            output_root=self.root / "artifacts/transfer-package",
            max_readiness_age_hours=24,
            confirmation=PACKAGE_CONFIRMATION,
            now=NOW,
        )
        self.destination = self.media_parent / "VisionFlow-Transfer-Media"

    def stage(self):
        return stage_media(
            self.root,
            package_value=None,
            release_evidence_value=None,
            destination_value=str(self.destination),
            confirmation=CONFIRMATION,
            now=NOW,
        )

    def test_plan_is_read_only_and_has_five_steps(self) -> None:
        plan = build_plan()
        self.assertEqual(5, len(plan))
        self.assertEqual("READ_ONLY", plan[0]["mode"])
        self.assertEqual("MANUAL", plan[-1]["mode"])
        self.assertFalse(self.destination.exists())

    def test_stage_requires_exact_confirmation(self) -> None:
        with self.assertRaisesRegex(TransferMediaError, "confirm"):
            stage_media(
                self.root,
                package_value=None,
                release_evidence_value=None,
                destination_value=str(self.destination),
                confirmation="",
                now=NOW,
            )
        self.assertFalse(self.destination.exists())

    def test_stage_rejects_existing_destination(self) -> None:
        self.destination.mkdir()
        with self.assertRaisesRegex(TransferMediaError, "이미 존재"):
            self.stage()

    def test_stage_rejects_destination_inside_project(self) -> None:
        destination = self.root / "transfer-copy"
        with self.assertRaisesRegex(TransferMediaError, "프로젝트 폴더 밖"):
            stage_media(
                self.root,
                package_value=None,
                release_evidence_value=None,
                destination_value=str(destination),
                confirmation=CONFIRMATION,
                now=NOW,
            )

    def test_stage_fails_when_bootstrap_tool_is_missing(self) -> None:
        (self.root / "scripts" / BOOTSTRAP_FILES[-1]).unlink()
        with self.assertRaisesRegex(TransferMediaError, "필수 도구"):
            self.stage()
        self.assertFalse(self.destination.exists())

    def test_latest_invalid_package_does_not_fallback(self) -> None:
        invalid = (
            self.root
            / "artifacts/transfer-package/"
            "visionflow-transfer-package-99999999T999999Z.zip"
        )
        invalid.write_bytes(b"not a zip")
        newer = self.package.stat().st_mtime + 10
        os.utime(invalid, (newer, newer))
        with self.assertRaises(TransferMediaError):
            resolve_package(self.root, None)

    def test_stage_and_verify_media(self) -> None:
        media_root, manifest = self.stage()
        self.assertEqual(self.destination, media_root)
        self.assertEqual(READY_STATUS, manifest["status"])
        verified_root, verified = verify_media(media_root)
        self.assertEqual(media_root, verified_root)
        self.assertEqual(manifest, verified)
        self.assertTrue(
            verified["safety"]["containsOperationalDatabaseBackup"]
        )
        self.assertTrue(verified["safety"]["containsReleaseEvidence"])
        self.assertFalse(verified["safety"]["containsModelWeights"])

    def test_stage_contains_only_expected_files(self) -> None:
        media_root, _ = self.stage()
        files = {
            path.relative_to(media_root).as_posix()
            for path in media_root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(6 + len(BOOTSTRAP_FILES), len(files))
        self.assertEqual(
            2,
            len([path for path in files if path.endswith(".sha256")]),
        )
        self.assertFalse(
            any(
                Path(path).name.lower().startswith(".env")
                or Path(path).suffix.lower()
                in {".pt", ".onnx", ".engine", ".pem", ".key"}
                for path in files
            )
        )

    def test_verify_rejects_changed_package(self) -> None:
        media_root, manifest = self.stage()
        package = media_root / manifest["package"]["archive"]["path"]
        package.write_bytes(package.read_bytes() + b"changed")
        with self.assertRaisesRegex(TransferMediaError, "SHA-256"):
            verify_media(media_root)

    def test_verify_rejects_changed_bootstrap_tool(self) -> None:
        media_root, _ = self.stage()
        tool = (
            media_root
            / "tools/scripts"
            / "visionflow_hp_omen_restore.py"
        )
        tool.write_text("changed\n", encoding="utf-8")
        with self.assertRaisesRegex(TransferMediaError, "SHA-256"):
            verify_media(media_root)

    def test_verify_rejects_changed_release_evidence(self) -> None:
        media_root, manifest = self.stage()
        evidence = (
            media_root
            / manifest["releaseEvidence"]["archive"]["path"]
        )
        evidence.write_bytes(evidence.read_bytes() + b"changed")

        with self.assertRaisesRegex(TransferMediaError, "SHA-256"):
            verify_media(media_root)

    def test_verify_rejects_unexpected_file(self) -> None:
        media_root, _ = self.stage()
        (media_root / ".env.docker").write_text(
            "SECRET=value\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(TransferMediaError, "파일 구성이"):
            verify_media(media_root)

    def test_verify_rejects_manifest_path_traversal(self) -> None:
        media_root, _ = self.stage()
        manifest_path = media_root / MANIFEST_NAME
        manifest = json.loads(
            manifest_path.read_text(encoding="utf-8-sig")
        )
        manifest["package"]["archive"]["path"] = "../outside.zip"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8-sig",
        )
        with self.assertRaisesRegex(TransferMediaError, "경로"):
            verify_media(media_root)

    def test_verify_rejects_missing_package_sidecar(self) -> None:
        media_root, manifest = self.stage()
        sidecar = media_root / manifest["package"]["sidecar"]["path"]
        sidecar.unlink()
        with self.assertRaisesRegex(TransferMediaError, "SHA-256"):
            verify_media(media_root)

    def test_cli_plan_and_verify(self) -> None:
        self.assertEqual(
            0,
            main(["--root", str(self.root), "plan"]),
        )
        media_root, _ = self.stage()
        self.assertEqual(
            0,
            main(
                [
                    "--root",
                    str(self.root),
                    "verify",
                    "--media",
                    str(media_root),
                ]
            ),
        )


if __name__ == "__main__":
    unittest.main()
