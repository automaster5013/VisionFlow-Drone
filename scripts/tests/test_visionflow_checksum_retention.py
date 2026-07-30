from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from scripts.visionflow_checksum_retention import (
    ChecksumRetentionError,
    QUARANTINE_CONFIRMATION,
    RESTORE_CONFIRMATION,
    build_plan,
    quarantine,
    restore,
)


NOW = datetime(2026, 7, 24, 3, 0, tzinfo=timezone.utc)


class VisionFlowChecksumRetentionTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.output = self.root / "artifacts/checksum-quarantine"

    @staticmethod
    def checksum(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def set_age(self, path: Path, days: int) -> None:
        timestamp = (NOW - timedelta(days=days)).timestamp()
        targets = [path]
        if path.is_dir():
            targets.extend(path.rglob("*"))
        for target in targets:
            os.utime(target, (timestamp, timestamp))

    def create_run(
        self,
        name: str,
        *,
        days: int,
        references: list[str] | None = None,
    ) -> Path:
        directory = self.root / "artifacts/model-soak" / name
        directory.mkdir(parents=True)
        report = directory / "visionflow-model-soak.json"
        html = directory / "visionflow-model-soak.html"
        sidecar = directory / "visionflow-model-soak.sha256"
        report.write_text(
            json.dumps(
                {
                    "project": "visionflow",
                    "inputs": [
                        {"path": value}
                        for value in (references or [])
                    ],
                }
            ),
            encoding="utf-8",
        )
        html.write_text("<html>evidence</html>", encoding="utf-8")
        sidecar.write_text(
            (
                f"{self.checksum(report)}  {report.name}\n"
                f"{self.checksum(html)}  {html.name}\n"
            ),
            encoding="utf-8",
        )
        self.set_age(directory, days)
        return directory

    def create_signoff_reference(
        self,
        target: Path,
        *,
        days: int = 1,
    ) -> Path:
        directory = (
            self.root
            / "artifacts/model-release-signoff/signoff-latest"
        )
        directory.mkdir(parents=True)
        report = directory / "visionflow-model-release-signoff.json"
        html = directory / "visionflow-model-release-signoff.html"
        bundle = directory / "visionflow-model-release-signoff.zip"
        sidecar = directory / "visionflow-model-release-signoff.sha256"
        report.write_text(
            json.dumps(
                {
                    "inputs": [
                        {
                            "path": target.relative_to(
                                self.root
                            ).as_posix()
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        html.write_text("<html>signoff</html>", encoding="utf-8")
        bundle.write_bytes(b"bundle")
        sidecar.write_text(
            "".join(
                f"{self.checksum(path)}  {path.name}\n"
                for path in (report, html, bundle)
            ),
            encoding="utf-8",
        )
        self.set_age(directory, days)
        return directory

    def create_patch_sidecar(self, *, days: int = 20) -> tuple[Path, Path]:
        archive = self.root / "visionflow-patch.zip"
        sidecar = self.root / "visionflow-patch.sha256"
        archive.write_bytes(b"patch")
        sidecar.write_text(
            f"{self.checksum(archive)}  {archive.name}\n",
            encoding="utf-8",
        )
        self.set_age(sidecar, days)
        return archive, sidecar

    def plan(
        self,
        *,
        keep: int = 1,
        include_patch_sidecars: bool = True,
    ) -> dict:
        return build_plan(
            root=self.root,
            min_age_days=14,
            keep_per_family=keep,
            include_patch_sidecars=include_patch_sidecars,
            now=NOW,
        )

    def test_plan_keeps_latest_runs_and_selects_only_old_run(self) -> None:
        old = self.create_run("soak-old", days=30)
        for index, age in enumerate((1, 2, 3), start=1):
            self.create_run(f"soak-new-{index}", days=age)

        plan = self.plan(keep=3)

        self.assertEqual("READY", plan["status"])
        self.assertEqual(3, plan["summary"]["latestProtectedRuns"])
        self.assertEqual(
            [old.relative_to(self.root).as_posix()],
            [item["path"] for item in plan["candidates"]],
        )
        self.assertTrue(old.is_dir())

    def test_newer_report_reference_protects_old_run(self) -> None:
        old = self.create_run("soak-old", days=30)
        self.create_run("soak-new", days=1)
        self.create_signoff_reference(
            old / "visionflow-model-soak.json"
        )

        plan = self.plan(keep=1)

        self.assertEqual(0, plan["summary"]["eligibleArtifactRuns"])
        self.assertTrue(old.is_dir())

    def test_verified_old_root_patch_checksum_is_eligible(self) -> None:
        archive, sidecar = self.create_patch_sidecar()

        plan = self.plan()

        self.assertEqual(1, plan["summary"]["eligiblePatchSidecars"])
        self.assertEqual(sidecar.name, plan["candidates"][0]["path"])
        self.assertTrue(archive.is_file())
        self.assertTrue(sidecar.is_file())

    def test_old_orphan_patch_checksum_is_reversibly_eligible(self) -> None:
        _, sidecar = self.create_patch_sidecar()
        (self.root / "visionflow-patch.zip").unlink()

        plan = self.plan()

        self.assertEqual("READY", plan["status"])
        self.assertEqual(1, plan["summary"]["eligiblePatchSidecars"])
        self.assertEqual(
            "UNVERIFIED_OR_ORPHANED",
            plan["candidates"][0]["classification"],
        )
        manifest_path, _ = quarantine(
            root=self.root,
            plan=plan,
            confirmation=QUARANTINE_CONFIRMATION,
            output_root=self.output,
            now=NOW,
        )
        self.assertIsNotNone(manifest_path)
        self.assertFalse(sidecar.exists())

    def test_tampered_artifact_blocks_apply(self) -> None:
        old = self.create_run("soak-old", days=30)
        self.create_run("soak-new", days=1)
        report = old / "visionflow-model-soak.json"
        report.write_text("{}", encoding="utf-8")

        plan = self.plan(keep=1)

        self.assertEqual("REVIEW_REQUIRED", plan["status"])
        self.assertEqual(1, plan["summary"]["brokenItems"])
        with self.assertRaisesRegex(
            ChecksumRetentionError,
            "격리를 실행할 수 없습니다",
        ):
            quarantine(
                root=self.root,
                plan=plan,
                confirmation=QUARANTINE_CONFIRMATION,
                output_root=self.output,
                now=NOW,
            )
        self.assertTrue(old.is_dir())

    def test_apply_requires_explicit_confirmation(self) -> None:
        old = self.create_run("soak-old", days=30)
        self.create_run("soak-new", days=1)

        with self.assertRaisesRegex(
            ChecksumRetentionError,
            "--confirm",
        ):
            quarantine(
                root=self.root,
                plan=self.plan(keep=1),
                confirmation="",
                output_root=self.output,
                now=NOW,
            )
        self.assertTrue(old.is_dir())

    def test_quarantine_and_restore_preserve_complete_evidence_group(
        self,
    ) -> None:
        old = self.create_run("soak-old", days=30)
        self.create_run("soak-new", days=1)
        archive, sidecar = self.create_patch_sidecar()

        manifest_path, manifest = quarantine(
            root=self.root,
            plan=self.plan(keep=1),
            confirmation=QUARANTINE_CONFIRMATION,
            output_root=self.output,
            now=NOW,
        )

        self.assertIsNotNone(manifest_path)
        assert manifest_path is not None
        self.assertEqual("COMPLETED", manifest["status"])
        self.assertEqual(2, manifest["groupCount"])
        self.assertFalse(old.exists())
        self.assertFalse(sidecar.exists())
        self.assertTrue(archive.is_file())

        result = restore(
            root=self.root,
            manifest_path=manifest_path,
            confirmation=RESTORE_CONFIRMATION,
            now=NOW + timedelta(minutes=1),
        )

        self.assertTrue(result.is_file())
        self.assertTrue(old.is_dir())
        self.assertTrue(sidecar.is_file())
        self.assertTrue(
            (old / "visionflow-model-soak.sha256").is_file()
        )

    def test_extra_unchecksummed_file_marks_run_broken(self) -> None:
        old = self.create_run("soak-old", days=30)
        self.create_run("soak-new", days=1)
        (old / "untracked.txt").write_text("unexpected", encoding="utf-8")

        plan = self.plan(keep=1)

        self.assertEqual("REVIEW_REQUIRED", plan["status"])
        self.assertIn(
            "체크섬 파일 목록",
            plan["broken"][0]["detail"],
        )

    def test_partial_move_failure_rolls_back_every_source(self) -> None:
        first = self.create_run("soak-old-1", days=30)
        second = self.create_run("soak-old-2", days=20)
        self.create_run("soak-new", days=1)
        real_move = __import__("shutil").move
        forward_moves = 0

        def flaky_move(source: str, destination: str) -> str:
            nonlocal forward_moves
            destination_path = Path(destination)
            if "checksum-quarantine" in destination_path.parts:
                forward_moves += 1
                if forward_moves == 2:
                    raise OSError("simulated move failure")
            return real_move(source, destination)

        with mock.patch(
            "scripts.visionflow_checksum_retention.shutil.move",
            side_effect=flaky_move,
        ):
            with self.assertRaisesRegex(
                ChecksumRetentionError,
                "격리 실패",
            ):
                quarantine(
                    root=self.root,
                    plan=self.plan(keep=1),
                    confirmation=QUARANTINE_CONFIRMATION,
                    output_root=self.output,
                    now=NOW,
                )

        self.assertTrue(first.is_dir())
        self.assertTrue(second.is_dir())

    def test_unsafe_restore_manifest_path_is_rejected(self) -> None:
        self.create_run("soak-old", days=30)
        self.create_run("soak-new", days=1)
        manifest_path, _ = quarantine(
            root=self.root,
            plan=self.plan(keep=1),
            confirmation=QUARANTINE_CONFIRMATION,
            output_root=self.output,
            now=NOW,
        )
        assert manifest_path is not None
        manifest = json.loads(
            manifest_path.read_text(encoding="utf-8-sig")
        )
        manifest["groups"][0]["originalPath"] = "../outside"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        with self.assertRaisesRegex(
            ChecksumRetentionError,
            "안전하지 않은",
        ):
            restore(
                root=self.root,
                manifest_path=manifest_path,
                confirmation=RESTORE_CONFIRMATION,
                now=NOW,
            )

    def test_empty_project_has_no_candidates_and_no_side_effects(
        self,
    ) -> None:
        before = list(self.root.rglob("*"))

        plan = self.plan()

        self.assertEqual("READY", plan["status"])
        self.assertEqual(0, plan["summary"]["eligibleItems"])
        self.assertEqual(before, list(self.root.rglob("*")))


if __name__ == "__main__":
    unittest.main()
