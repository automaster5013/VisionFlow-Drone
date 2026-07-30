from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.visionflow_evidence_catalog import (
    CLEANUP_RECOMMENDED,
    HEALTHY,
    REVIEW_REQUIRED,
    EvidenceCatalogError,
    build_catalog,
    main,
    write_catalog,
)


NOW = datetime(2026, 7, 24, 5, 0, tzinfo=timezone.utc)


class VisionFlowEvidenceCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.output = self.root / "artifacts/evidence-catalog"

    @staticmethod
    def checksum(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def create_sidecar(
        self,
        parent: Path,
        *,
        target_name: str = "report.json",
        sidecar_name: str = "report.sha256",
        content: bytes = b'{"status":"PASS"}',
        star: bool = False,
    ) -> tuple[Path, Path]:
        parent.mkdir(parents=True, exist_ok=True)
        target = parent / target_name
        sidecar = parent / sidecar_name
        target.write_bytes(content)
        marker = "*" if star else ""
        sidecar.write_text(
            f"{self.checksum(target)}  {marker}{target.name}\n",
            encoding="utf-8",
        )
        return target, sidecar

    def build(self) -> dict:
        return build_catalog(root=self.root, now=NOW)

    def test_verified_artifact_sidecar_is_healthy(self) -> None:
        self.create_sidecar(self.root / "artifacts/release")

        report = self.build()

        self.assertEqual(HEALTHY, report["status"])
        self.assertEqual(1, report["summary"]["verifiedSidecars"])
        self.assertEqual(
            "VERIFIED",
            report["sidecars"][0]["targets"][0]["status"],
        )

    def test_hash_mismatch_in_artifacts_requires_review(self) -> None:
        target, _ = self.create_sidecar(
            self.root / "artifacts/release"
        )
        target.write_bytes(b"changed")

        report = self.build()

        self.assertEqual(REVIEW_REQUIRED, report["status"])
        self.assertEqual(1, report["summary"]["errorSidecars"])
        self.assertEqual("HASH_MISMATCH", report["sidecars"][0]["status"])

    def test_missing_artifact_target_requires_review(self) -> None:
        target, _ = self.create_sidecar(
            self.root / "artifacts/release"
        )
        target.unlink()

        report = self.build()

        self.assertEqual(REVIEW_REQUIRED, report["status"])
        self.assertEqual("MISSING_TARGET", report["sidecars"][0]["status"])

    def test_invalid_artifact_sidecar_requires_review(self) -> None:
        _, sidecar = self.create_sidecar(
            self.root / "artifacts/release"
        )
        sidecar.write_text("not-a-checksum\n", encoding="utf-8")

        report = self.build()

        self.assertEqual(REVIEW_REQUIRED, report["status"])
        self.assertEqual("INVALID_FORMAT", report["sidecars"][0]["status"])

    def test_root_orphan_is_cleanup_warning_not_integrity_error(
        self,
    ) -> None:
        target, sidecar = self.create_sidecar(
            self.root,
            target_name="patch.zip",
            sidecar_name="patch.sha256",
        )
        target.unlink()

        report = self.build()

        self.assertEqual(CLEANUP_RECOMMENDED, report["status"])
        self.assertEqual("WARNING", report["sidecars"][0]["severity"])
        self.assertEqual(0, report["summary"]["errorSidecars"])
        self.assertTrue(sidecar.is_file())

    def test_old_verified_root_checksum_is_cleanup_candidate(self) -> None:
        _, sidecar = self.create_sidecar(
            self.root,
            target_name="patch.zip",
            sidecar_name="patch.sha256",
        )
        timestamp = (NOW - timedelta(days=20)).timestamp()
        os.utime(sidecar, (timestamp, timestamp))

        report = self.build()

        self.assertEqual(CLEANUP_RECOMMENDED, report["status"])
        self.assertEqual(1, report["summary"]["cleanupCandidates"])

    def test_missing_model_run_sidecar_requires_review(self) -> None:
        run = self.root / "artifacts/model-soak/soak-broken"
        run.mkdir(parents=True)
        (run / "visionflow-model-soak.json").write_text(
            "{}",
            encoding="utf-8",
        )

        report = self.build()

        self.assertEqual(REVIEW_REQUIRED, report["status"])
        self.assertEqual(1, report["summary"]["invalidArtifactRuns"])

    def test_binary_marker_and_space_in_filename_are_supported(self) -> None:
        self.create_sidecar(
            self.root / "artifacts/release",
            target_name="report bundle.zip",
            star=True,
        )

        report = self.build()

        self.assertEqual(HEALTHY, report["status"])
        self.assertEqual(
            "report bundle.zip",
            report["sidecars"][0]["targets"][0]["path"],
        )

    def test_unsafe_sidecar_target_is_rejected(self) -> None:
        parent = self.root / "artifacts/release"
        parent.mkdir(parents=True)
        sidecar = parent / "report.sha256"
        sidecar.write_text(
            f"{'a' * 64}  ../outside.json\n",
            encoding="utf-8",
        )

        report = self.build()

        self.assertEqual(REVIEW_REQUIRED, report["status"])
        self.assertEqual("INVALID_FORMAT", report["sidecars"][0]["status"])

    def test_catalog_overwrites_two_fixed_files_without_new_sidecar(
        self,
    ) -> None:
        self.create_sidecar(self.root / "artifacts/release")
        first = self.build()
        paths = write_catalog(
            root=self.root,
            output=self.output,
            report=first,
        )
        second = self.build()
        write_catalog(
            root=self.root,
            output=self.output,
            report=second,
        )

        self.assertTrue(all(path.is_file() for path in paths))
        self.assertEqual(
            {
                "visionflow-evidence-catalog.json",
                "visionflow-evidence-catalog.html",
            },
            {path.name for path in self.output.iterdir()},
        )
        self.assertFalse(list(self.output.glob("*.sha256")))

    def test_check_only_does_not_create_catalog_files(self) -> None:
        self.create_sidecar(self.root / "artifacts/release")

        result = main(
            [
                "--root",
                str(self.root),
                "--check-only",
            ]
        )

        self.assertEqual(0, result)
        self.assertFalse(self.output.exists())

    def test_output_outside_catalog_directory_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            EvidenceCatalogError,
            "artifacts/evidence-catalog",
        ):
            write_catalog(
                root=self.root,
                output=self.root / "outside",
                report=self.build(),
            )


if __name__ == "__main__":
    unittest.main()
