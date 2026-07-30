from __future__ import annotations

import unittest
from datetime import timedelta

from scripts.tests import test_visionflow_hp_omen_restore as hp_test
from scripts.visionflow_hp_omen_transfer_day import (
    CONFIRMATION_STATUS,
    MANUAL_STATUS,
    READY_STATUS,
    RECOVERY_STATUS,
    TransferDayError,
    bootstrap_day,
    build_plan,
    latest_checkpoint,
    resume_day,
    verify_checkpoint,
)


NOW = hp_test.NOW + timedelta(hours=6)


class HpOmenTransferDayTest(unittest.TestCase):
    def setUp(self) -> None:
        fixture = hp_test.HpOmenRestoreTest(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.workspace = fixture.destination
        self.environment = fixture.environment

    def bootstrap(self):
        return bootstrap_day(
            package=str(self.fixture.package),
            workspace=str(self.workspace),
            confirmation=hp_test.PREPARE_CONFIRMATION,
            now=NOW,
        )

    def resume(
        self,
        *,
        confirmation: str = "",
        runner=None,
        environment=None,
        now=NOW + timedelta(minutes=1),
    ):
        return resume_day(
            workspace=self.workspace,
            confirmation=confirmation,
            run_benchmark=False,
            timeout_seconds=300,
            environment=(
                self.environment
                if environment is None
                else environment
            ),
            now=now,
            runner=runner or hp_test.FakeActivationRunner(
                self.workspace
            ),
            platform_name="nt",
        )

    def test_bootstrap_prepares_workspace_and_seals_checkpoint(
        self,
    ) -> None:
        path, report = self.bootstrap()

        self.assertEqual(MANUAL_STATUS, report["status"])
        self.assertEqual(1, report["transitionNumber"])
        self.assertIsNone(report["previousCheckpoint"])
        self.assertTrue(path.is_file())
        verified_path, verified = verify_checkpoint(
            self.workspace,
            path,
            environment={},
            platform_name="nt",
        )
        self.assertEqual(path, verified_path)
        self.assertEqual(report, verified)

    def test_bootstrap_adopts_verified_workspace_after_checkpoint_gap(
        self,
    ) -> None:
        prepare_path, _ = self.fixture.prepare()
        self.assertTrue(prepare_path.is_file())
        self.assertFalse((self.workspace / "artifacts/hp-omen-transfer-day").exists())

        path, report = self.bootstrap()

        self.assertEqual(MANUAL_STATUS, report["status"])
        self.assertEqual(1, report["transitionNumber"])
        self.assertTrue(path.is_file())

    def test_blocked_preflight_remains_manual_without_runner(
        self,
    ) -> None:
        self.bootstrap()
        runner = hp_test.FakeActivationRunner(self.workspace)

        _, report, exit_code = self.resume(
            runner=runner,
            environment={},
        )

        self.assertEqual(0, exit_code)
        self.assertEqual(MANUAL_STATUS, report["status"])
        self.assertIsNotNone(report["preflightReport"])
        self.assertEqual([], runner.calls)

    def test_preflight_then_confirmation_activates_once(self) -> None:
        self.bootstrap()
        self.fixture.make_activation_ready()
        runner = hp_test.FakeActivationRunner(self.workspace)

        confirmation_path, confirmation, preflight_code = self.resume(
            runner=runner,
        )

        self.assertEqual(0, preflight_code)
        self.assertEqual(CONFIRMATION_STATUS, confirmation["status"])
        self.assertEqual([], runner.calls)

        same_path, waiting, waiting_code = self.resume(
            runner=runner,
            now=NOW + timedelta(minutes=2),
        )
        self.assertEqual(0, waiting_code)
        self.assertEqual(confirmation_path, same_path)
        self.assertEqual(CONFIRMATION_STATUS, waiting["status"])
        self.assertEqual([], runner.calls)

        ready_path, ready, activation_code = self.resume(
            confirmation=hp_test.ACTIVATE_CONFIRMATION,
            runner=runner,
            now=NOW + timedelta(minutes=3),
        )

        self.assertEqual(0, activation_code)
        self.assertEqual(READY_STATUS, ready["status"])
        self.assertEqual(
            [
                "restore",
                "gpu-stack",
                "target-profile",
                "machine-comparison",
                "acceptance",
            ],
            runner.calls,
        )
        verified_path, verified = verify_checkpoint(
            self.workspace,
            ready_path,
            environment={},
            platform_name="nt",
        )
        self.assertEqual(ready_path, verified_path)
        self.assertEqual(ready, verified)

    def test_failed_activation_records_recovery_required(self) -> None:
        self.bootstrap()
        self.fixture.make_activation_ready()
        self.resume()
        runner = hp_test.FakeActivationRunner(
            self.workspace,
            fail_key="gpu-stack",
        )

        recovery_path, recovery, exit_code = self.resume(
            confirmation=hp_test.ACTIVATE_CONFIRMATION,
            runner=runner,
            now=NOW + timedelta(minutes=2),
        )

        self.assertEqual(1, exit_code)
        self.assertEqual(RECOVERY_STATUS, recovery["status"])
        self.assertIsNotNone(recovery["activationReport"])
        blocked_runner = hp_test.FakeActivationRunner(self.workspace)
        same_path, same, resume_code = self.resume(
            runner=blocked_runner,
            now=NOW + timedelta(minutes=3),
        )
        self.assertEqual(1, resume_code)
        self.assertEqual(recovery_path, same_path)
        self.assertEqual(recovery, same)
        self.assertEqual([], blocked_runner.calls)

    def test_tampered_latest_checkpoint_blocks_resume(self) -> None:
        path, _ = self.bootstrap()
        path.with_suffix(".html").write_text(
            "tampered",
            encoding="utf-8",
        )
        runner = hp_test.FakeActivationRunner(self.workspace)

        with self.assertRaisesRegex(TransferDayError, "SHA-256"):
            self.resume(runner=runner)

        self.assertEqual([], runner.calls)

    def test_checkpoint_never_records_role_key_values(self) -> None:
        self.bootstrap()
        self.fixture.make_activation_ready()
        path, _, _ = self.resume()
        serialized = path.read_text(encoding="utf-8-sig")

        for secret in self.environment.values():
            self.assertNotIn(secret, serialized)

    def test_plan_is_read_only_and_has_seven_steps(self) -> None:
        plan = build_plan()

        self.assertEqual(7, len(plan))
        self.assertEqual("CONFIRM_PREPARE", plan[0]["mode"])
        self.assertEqual("RESUME", plan[5]["mode"])
        self.assertEqual("DEFERRED", plan[6]["mode"])


if __name__ == "__main__":
    unittest.main()
