from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from visionflow_retention_drill import DrillError, run_recovery_drill


class VisionFlowRetentionRecoveryDrillTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.now = datetime.now(timezone.utc)
        self.audit = self.root / "audit.json"
        self.backup = self.root / "backup.zip"
        self.acceptance = self.root / "scripts/run-visionflow-acceptance.bat"
        self.acceptance.parent.mkdir(parents=True)
        self.acceptance.write_text("@echo off\r\nexit /b 0\r\n", encoding="utf-8")
        self.output = self.root / "artifacts/retention-drill"

    def plan(self, eligible_count: int = 1) -> tuple[Path, dict[str, object]]:
        path = self.root / "artifacts/retention-quarantine/plan.json"
        return path, {
            "status": "DRY_RUN_COMPLETE" if eligible_count else "NO_CHANGES",
            "eligibleCount": eligible_count,
            "eligibleBytes": 10 if eligible_count else 0,
        }

    def manifest(self) -> tuple[Path, dict[str, object]]:
        path = self.root / "artifacts/retention-quarantine/run/quarantine-manifest.json"
        return path, {
            "status": "COMPLETED",
            "fileCount": 1,
            "totalBytes": 10,
            "files": [],
        }

    def invoke(self, *, execute: bool, confirmation: str, runner=mock.DEFAULT):
        kwargs = {
            "execute": execute,
            "confirmation": confirmation,
            "output_root": self.output,
            "timeout_seconds": 300,
            "max_audit_age_hours": 24.0,
            "max_backup_age_days": 7.0,
            "now": self.now,
        }
        if runner is not mock.DEFAULT:
            kwargs["runner"] = runner
        return run_recovery_drill(
            self.root,
            self.audit,
            self.backup,
            **kwargs,
        )

    @mock.patch("visionflow_retention_drill.quarantine_candidates")
    def test_plan_mode_never_moves_files(self, quarantine: mock.Mock) -> None:
        quarantine.return_value = self.plan()

        _, report, exit_code = self.invoke(execute=False, confirmation="")

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "PLAN_COMPLETE")
        self.assertEqual(quarantine.call_count, 1)
        self.assertFalse(quarantine.call_args.kwargs["apply"])

    @mock.patch("visionflow_retention_drill.quarantine_candidates")
    def test_no_candidates_finishes_without_execute(self, quarantine: mock.Mock) -> None:
        quarantine.return_value = self.plan(eligible_count=0)

        _, report, exit_code = self.invoke(
            execute=True,
            confirmation="RUN_RESTORE_DRILL",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "NO_CANDIDATES")
        self.assertEqual(quarantine.call_count, 1)

    def test_execute_requires_explicit_confirmation(self) -> None:
        with self.assertRaisesRegex(DrillError, "RUN_RESTORE_DRILL"):
            self.invoke(execute=True, confirmation="")

    @mock.patch("visionflow_retention_drill.verify_restored_files", return_value=[])
    @mock.patch("visionflow_retention_drill.restore_quarantine")
    @mock.patch("visionflow_retention_drill.quarantine_candidates")
    def test_successful_acceptance_is_always_restored(
        self,
        quarantine: mock.Mock,
        restore: mock.Mock,
        verify: mock.Mock,
    ) -> None:
        quarantine.side_effect = [self.plan(), self.manifest()]
        restore.return_value = self.root / "restore-result.json"

        def passed_runner(root: Path, log: Path, timeout: int) -> dict[str, object]:
            return {"status": "PASSED", "exitCode": 0, "timedOut": False}

        _, report, exit_code = self.invoke(
            execute=True,
            confirmation="RUN_RESTORE_DRILL",
            runner=passed_runner,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "PASSED")
        restore.assert_called_once()
        verify.assert_called_once()

    @mock.patch("visionflow_retention_drill.verify_restored_files", return_value=[])
    @mock.patch("visionflow_retention_drill.restore_quarantine")
    @mock.patch("visionflow_retention_drill.quarantine_candidates")
    def test_failed_acceptance_still_restores(
        self,
        quarantine: mock.Mock,
        restore: mock.Mock,
        verify: mock.Mock,
    ) -> None:
        quarantine.side_effect = [self.plan(), self.manifest()]
        restore.return_value = self.root / "restore-result.json"

        def failed_runner(root: Path, log: Path, timeout: int) -> dict[str, object]:
            return {"status": "FAILED", "exitCode": 1, "timedOut": False}

        _, report, exit_code = self.invoke(
            execute=True,
            confirmation="RUN_RESTORE_DRILL",
            runner=failed_runner,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], "ACCEPTANCE_FAILED_RESTORED")
        restore.assert_called_once()
        verify.assert_called_once()

    @mock.patch("visionflow_retention_drill.restore_quarantine")
    @mock.patch("visionflow_retention_drill.quarantine_candidates")
    def test_runner_exception_still_restores(
        self,
        quarantine: mock.Mock,
        restore: mock.Mock,
    ) -> None:
        quarantine.side_effect = [self.plan(), self.manifest()]
        restore.return_value = self.root / "restore-result.json"

        def error_runner(root: Path, log: Path, timeout: int) -> dict[str, object]:
            raise RuntimeError("simulated acceptance error")

        _, report, exit_code = self.invoke(
            execute=True,
            confirmation="RUN_RESTORE_DRILL",
            runner=error_runner,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], "ACCEPTANCE_FAILED_RESTORED")
        restore.assert_called_once()

    @mock.patch("visionflow_retention_drill.verify_restored_files", return_value=[])
    @mock.patch("visionflow_retention_drill.restore_quarantine")
    @mock.patch("visionflow_retention_drill.quarantine_candidates")
    def test_keyboard_interrupt_still_restores_and_returns_130(
        self,
        quarantine: mock.Mock,
        restore: mock.Mock,
        verify: mock.Mock,
    ) -> None:
        quarantine.side_effect = [self.plan(), self.manifest()]
        restore.return_value = self.root / "restore-result.json"

        def interrupted_runner(root: Path, log: Path, timeout: int) -> dict[str, object]:
            raise KeyboardInterrupt

        _, report, exit_code = self.invoke(
            execute=True,
            confirmation="RUN_RESTORE_DRILL",
            runner=interrupted_runner,
        )

        self.assertEqual(exit_code, 130)
        self.assertEqual(report["status"], "INTERRUPTED_RESTORED")
        restore.assert_called_once()
        verify.assert_called_once()

    @mock.patch("visionflow_retention_drill.restore_quarantine")
    @mock.patch("visionflow_retention_drill.quarantine_candidates")
    def test_restore_failure_has_distinct_critical_status(
        self,
        quarantine: mock.Mock,
        restore: mock.Mock,
    ) -> None:
        quarantine.side_effect = [self.plan(), self.manifest()]
        restore.side_effect = RuntimeError("simulated restore failure")

        def passed_runner(root: Path, log: Path, timeout: int) -> dict[str, object]:
            return {"status": "PASSED", "exitCode": 0, "timedOut": False}

        _, report, exit_code = self.invoke(
            execute=True,
            confirmation="RUN_RESTORE_DRILL",
            runner=passed_runner,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(report["status"], "RESTORE_FAILED")

    @mock.patch("visionflow_retention_drill.quarantine_candidates")
    def test_quarantine_failure_is_reported(self, quarantine: mock.Mock) -> None:
        quarantine.side_effect = [self.plan(), RuntimeError("simulated quarantine failure")]

        _, report, exit_code = self.invoke(
            execute=True,
            confirmation="RUN_RESTORE_DRILL",
            runner=lambda *_: {"status": "PASSED"},
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], "QUARANTINE_FAILED")


if __name__ == "__main__":
    unittest.main()
