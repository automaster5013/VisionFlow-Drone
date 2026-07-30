from __future__ import annotations

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
from scripts.visionflow_hp_omen_restore import HpOmenRestoreError
from scripts.visionflow_migration_handoff import create_handoff
from scripts.visionflow_transfer_media import (
    BOOTSTRAP_FILES,
    TransferMediaError,
)
from scripts.visionflow_transfer_package import (
    CONFIRMATION as PACKAGE_CONFIRMATION,
    create_transfer_package,
)
from scripts.visionflow_transfer_rehearsal import (
    CONFIRMATION,
    FAILED_STATUS,
    READY_STATUS,
    STEP_DEFINITIONS,
    TransferRehearsalError,
    build_plan,
    execute_rehearsal,
    main,
    verify_report,
)


NOW = datetime(2026, 7, 24, 5, 0, tzinfo=timezone.utc)


class TransferRehearsalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "VisionFlow-Drone"
        self.temporary_parent = self.base / "system-temp"
        self.temporary_parent.mkdir()
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
            / "backups/visionflow-backup-20260724T040000Z.zip"
        )
        create_backup(backup)
        source = (
            self.root
            / "artifacts/source-release/"
            "visionflow-source-release-20260724T040100Z.zip"
        )
        source_sha, manifest_sha = create_source(source)
        evidence = (
            self.root
            / "artifacts/release-evidence/"
            "visionflow-release-evidence-20260724T040200Z.zip"
        )
        create_evidence(evidence, backup)
        baseline = (
            self.root
            / "artifacts/machine-readiness/"
            "visionflow-machine-baseline-20260724T040300Z.json"
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
            "visionflow-transfer-readiness-20260724T040400Z.json"
        )
        create_readiness(
            readiness,
            handoff,
            generated_at=NOW - timedelta(hours=1),
        )
        self.package, _, _ = create_transfer_package(
            self.root,
            readiness_value=str(readiness),
            handoff_value=str(handoff),
            backup_value=str(backup),
            output_root=self.root / "artifacts/transfer-package",
            max_readiness_age_hours=24,
            confirmation=PACKAGE_CONFIRMATION,
            now=NOW,
        )

    def execute(self, **overrides):
        arguments = {
            "package_value": None,
            "confirmation": CONFIRMATION,
            "now": NOW,
            "temporary_parent": self.temporary_parent,
        }
        arguments.update(overrides)
        return execute_rehearsal(self.root, **arguments)

    def test_plan_is_read_only_and_has_six_steps(self) -> None:
        plan = build_plan()
        self.assertEqual(6, len(plan))
        self.assertEqual("READ_ONLY", plan[0]["mode"])
        self.assertEqual("CLEANUP", plan[-1]["mode"])
        self.assertFalse(
            (self.root / "artifacts/transfer-rehearsal").exists()
        )

    def test_execute_requires_exact_confirmation_before_output(self) -> None:
        with self.assertRaisesRegex(TransferRehearsalError, "confirm"):
            self.execute(confirmation="")
        self.assertFalse(
            (self.root / "artifacts/transfer-rehearsal").exists()
        )

    def test_temporary_parent_must_be_outside_project(self) -> None:
        inside = self.root / "temporary"
        inside.mkdir()
        with self.assertRaisesRegex(TransferRehearsalError, "프로젝트 밖"):
            self.execute(temporary_parent=inside)

    def test_execute_and_independent_verify_succeed(self) -> None:
        report_path, report, exit_code = self.execute()
        self.assertEqual(0, exit_code)
        self.assertEqual(READY_STATUS, report["status"])
        self.assertTrue(report["safety"]["temporaryWorkspaceRemoved"])
        self.assertEqual([], list(self.temporary_parent.iterdir()))
        verified_path, verified = verify_report(
            self.root,
            report_path.relative_to(self.root).as_posix(),
        )
        self.assertEqual(report_path, verified_path)
        self.assertEqual(report, verified)

    def test_success_report_has_exact_passed_step_order(self) -> None:
        _, report, _ = self.execute()
        self.assertEqual(
            [key for key, _ in STEP_DEFINITIONS],
            [item["key"] for item in report["steps"]],
        )
        self.assertTrue(
            all(item["status"] == "PASS" for item in report["steps"])
        )
        self.assertEqual(
            "PASS",
            report["preparedSourceIdentity"]["status"],
        )

    def test_stage_failure_is_reported_and_temporary_data_removed(self) -> None:
        def failed_stage(*_args, **_kwargs):
            raise TransferMediaError("synthetic media failure")

        report_path, report, exit_code = self.execute(
            stage_function=failed_stage
        )
        self.assertEqual(1, exit_code)
        self.assertEqual(FAILED_STATUS, report["status"])
        self.assertEqual("FAILED", report["steps"][1]["status"])
        self.assertEqual("PASS", report["steps"][-1]["status"])
        self.assertEqual([], list(self.temporary_parent.iterdir()))
        with self.assertRaisesRegex(
            TransferRehearsalError,
            "성공한",
        ):
            verify_report(
                self.root,
                report_path.relative_to(self.root).as_posix(),
            )

    def test_prepare_failure_is_reported_and_temporary_data_removed(self) -> None:
        def failed_prepare(*_args, **_kwargs):
            raise HpOmenRestoreError("synthetic prepare failure")

        _, report, exit_code = self.execute(
            prepare_function=failed_prepare
        )
        self.assertEqual(1, exit_code)
        self.assertEqual("FAILED", report["steps"][3]["status"])
        self.assertEqual("SKIPPED", report["steps"][4]["status"])
        self.assertEqual("PASS", report["steps"][5]["status"])
        self.assertEqual([], list(self.temporary_parent.iterdir()))

    def test_changed_report_html_is_rejected(self) -> None:
        report_path, _, _ = self.execute()
        report_path.with_suffix(".html").write_text(
            "<html>changed</html>",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            TransferRehearsalError,
            "SHA-256",
        ):
            verify_report(
                self.root,
                report_path.relative_to(self.root).as_posix(),
            )

    def test_changed_original_package_invalidates_report(self) -> None:
        report_path, _, _ = self.execute()
        self.package.write_bytes(self.package.read_bytes() + b"changed")
        with self.assertRaisesRegex(
            TransferRehearsalError,
            "패키지",
        ):
            verify_report(
                self.root,
                report_path.relative_to(self.root).as_posix(),
            )

    def test_report_outside_artifact_root_is_rejected(self) -> None:
        outside = self.root / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(
            TransferRehearsalError,
            "허용 영역",
        ):
            verify_report(self.root, "outside.json")

    def test_cli_plan_and_verify(self) -> None:
        self.assertEqual(0, main(["--root", str(self.root), "plan"]))
        report_path, _, _ = self.execute()
        self.assertEqual(
            0,
            main(
                [
                    "--root",
                    str(self.root),
                    "verify",
                    "--report",
                    report_path.relative_to(self.root).as_posix(),
                ]
            ),
        )


if __name__ == "__main__":
    unittest.main()
