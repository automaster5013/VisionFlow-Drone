from __future__ import annotations

import unittest
from datetime import timedelta

from scripts.tests import test_visionflow_model_promotion as promotion_test
from scripts.visionflow_model_promotion import write_report
from scripts.visionflow_model_release import (
    ACTIVATED_STATUS,
    ACTIVATION_CONFIRMATION,
    FAILED_STATUS,
    PREPARED_STATUS,
    ROLLED_BACK_STATUS,
    CommandResult,
    ModelReleaseError,
    build_plan,
    build_release_report,
    execute_activation,
    verify_activation_report,
    verify_release_report,
    write_release,
)


NOW = promotion_test.NOW + timedelta(hours=2)


class FakeReleaseRunner:
    def __init__(self, *, fail_key: str | None = None) -> None:
        self.fail_key = fail_key
        self.calls: list[str] = []

    def __call__(self, command, _root, _timeout_seconds) -> CommandResult:
        joined = " ".join(str(item) for item in command)
        if command[0] == "cmd.exe":
            key = "acceptance"
        elif command[-2:] == ["config", "-q"]:
            key = "compose-config"
        elif "visionflow-model-rollback.env" in joined:
            key = "automatic-rollback"
        else:
            key = "promoted-start"
        self.calls.append(key)
        return CommandResult(
            9 if key == self.fail_key else 0,
            f"{key} {'failed' if key == self.fail_key else 'passed'}\n",
            10,
        )


class ModelReleaseTest(unittest.TestCase):
    def setUp(self) -> None:
        fixture = promotion_test.ModelPromotionTest(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.root = fixture.root
        self.hp_activation_path = fixture.activation_path
        promotion = fixture.build()
        self.promotion_path, _, _ = write_report(
            output_directory=self.root / "artifacts/model-promotion",
            report=promotion,
        )
        (
            release,
            activation_env,
            rollback_env,
        ) = build_release_report(
            root=self.root,
            promotion_path=self.promotion_path,
            now=NOW,
        )
        self.release_path, _, _ = write_release(
            output_directory=self.root / "artifacts/model-release",
            report=release,
            activation_env=activation_env,
            rollback_env=rollback_env,
        )

    def create_release(self, now):
        release, activation_env, rollback_env = build_release_report(
            root=self.root,
            promotion_path=self.promotion_path,
            now=now,
        )
        return write_release(
            output_directory=self.root / "artifacts/model-release",
            report=release,
            activation_env=activation_env,
            rollback_env=rollback_env,
        )[0]

    def test_prepare_uses_best_and_verified_baseline_without_secrets(
        self,
    ) -> None:
        path, report = verify_release_report(
            root=self.root,
            report_path=self.release_path,
        )

        self.assertEqual(self.release_path, path)
        self.assertEqual(PREPARED_STATUS, report["status"])
        self.assertEqual(
            "hp-runtime-activation",
            report["hpRuntimeActivation"]["key"],
        )
        self.assertEqual("best.pt", report["activeModel"]["fileName"])
        self.assertEqual(
            "yolo26n.pt",
            report["rollbackModel"]["fileName"],
        )
        activation_env = (
            self.release_path.parent / "visionflow-model-release.env"
        ).read_text(encoding="utf-8")
        rollback_env = (
            self.release_path.parent / "visionflow-model-rollback.env"
        ).read_text(encoding="utf-8")
        self.assertIn("AI_MODEL_PATH=best.pt", activation_env)
        self.assertIn("AI_MODEL_PATH=yolo26n.pt", rollback_env)
        self.assertNotIn("PASSWORD", activation_env + rollback_env)

    def test_prepare_requires_verified_hp_runtime_activation(self) -> None:
        self.hp_activation_path.unlink()

        with self.assertRaisesRegex(
            ModelReleaseError,
            "HP OMEN 기본 런타임 활성화",
        ):
            build_release_report(
                root=self.root,
                promotion_path=self.promotion_path,
                now=NOW + timedelta(minutes=1),
            )

    def test_non_ready_promotion_is_rejected(self) -> None:
        self.fixture.comparison_path = self.fixture.write_comparison(
            candidate_latency=15.0,
            candidate_processing=8.0,
        )
        promotion = self.fixture.build()
        promotion_path, _, _ = write_report(
            output_directory=self.root / "artifacts/model-promotion",
            report=promotion,
        )

        with self.assertRaisesRegex(
            ModelReleaseError,
            "MODEL_PROMOTION_READY",
        ):
            build_release_report(
                root=self.root,
                promotion_path=promotion_path,
                now=NOW,
            )

    def test_changed_rollback_model_invalidates_release(self) -> None:
        self.fixture.baseline_model_path.write_bytes(b"changed-baseline")

        with self.assertRaisesRegex(ModelReleaseError, "롤백 모델"):
            verify_release_report(
                root=self.root,
                report_path=self.release_path,
            )

    def test_activation_requires_confirmation_before_runner(self) -> None:
        runner = FakeReleaseRunner()

        with self.assertRaisesRegex(
            ModelReleaseError,
            ACTIVATION_CONFIRMATION,
        ):
            execute_activation(
                root=self.root,
                release_report_path=self.release_path,
                confirmation="",
                timeout_seconds=300,
                now=NOW,
                runner=runner,
                platform_name="nt",
            )

        self.assertEqual([], runner.calls)

    def test_successful_activation_runs_fixed_order_and_verifies(self) -> None:
        runner = FakeReleaseRunner()

        report_path, report, exit_code = execute_activation(
            root=self.root,
            release_report_path=self.release_path,
            confirmation=ACTIVATION_CONFIRMATION,
            timeout_seconds=300,
            now=NOW,
            runner=runner,
            platform_name="nt",
        )

        self.assertEqual(0, exit_code)
        self.assertEqual(ACTIVATED_STATUS, report["status"])
        self.assertEqual(
            ["compose-config", "promoted-start", "acceptance"],
            runner.calls,
        )
        verified_path, verified = verify_activation_report(
            root=self.root,
            report_path=report_path,
        )
        self.assertEqual(report_path, verified_path)
        self.assertEqual(report, verified)

    def test_same_prepared_release_cannot_run_twice(self) -> None:
        first_runner = FakeReleaseRunner()
        _, _, first_code = execute_activation(
            root=self.root,
            release_report_path=self.release_path,
            confirmation=ACTIVATION_CONFIRMATION,
            timeout_seconds=300,
            now=NOW,
            runner=first_runner,
            platform_name="nt",
        )
        self.assertEqual(0, first_code)
        duplicate_runner = FakeReleaseRunner()

        with self.assertRaisesRegex(
            ModelReleaseError,
            "이미 실행되었습니다",
        ):
            execute_activation(
                root=self.root,
                release_report_path=self.release_path,
                confirmation=ACTIVATION_CONFIRMATION,
                timeout_seconds=300,
                now=NOW + timedelta(minutes=1),
                runner=duplicate_runner,
                platform_name="nt",
            )

        self.assertEqual([], duplicate_runner.calls)

    def test_start_failure_automatically_rolls_back(self) -> None:
        runner = FakeReleaseRunner(fail_key="promoted-start")

        report_path, report, exit_code = execute_activation(
            root=self.root,
            release_report_path=self.release_path,
            confirmation=ACTIVATION_CONFIRMATION,
            timeout_seconds=300,
            now=NOW,
            runner=runner,
            platform_name="nt",
        )

        self.assertEqual(1, exit_code)
        self.assertEqual(ROLLED_BACK_STATUS, report["status"])
        self.assertEqual(
            [
                "compose-config",
                "promoted-start",
                "automatic-rollback",
            ],
            runner.calls,
        )
        verify_activation_report(root=self.root, report_path=report_path)

    def test_rolled_back_release_requires_new_prepare_before_retry(
        self,
    ) -> None:
        _, rolled_back, first_code = execute_activation(
            root=self.root,
            release_report_path=self.release_path,
            confirmation=ACTIVATION_CONFIRMATION,
            timeout_seconds=300,
            now=NOW,
            runner=FakeReleaseRunner(fail_key="promoted-start"),
            platform_name="nt",
        )
        self.assertEqual(1, first_code)
        self.assertEqual(ROLLED_BACK_STATUS, rolled_back["status"])
        retry_runner = FakeReleaseRunner()
        with self.assertRaisesRegex(
            ModelReleaseError,
            "이미 실행되었습니다",
        ):
            execute_activation(
                root=self.root,
                release_report_path=self.release_path,
                confirmation=ACTIVATION_CONFIRMATION,
                timeout_seconds=300,
                now=NOW + timedelta(minutes=1),
                runner=retry_runner,
                platform_name="nt",
            )
        self.assertEqual([], retry_runner.calls)

        new_release = self.create_release(NOW + timedelta(minutes=2))
        _, retried, retry_code = execute_activation(
            root=self.root,
            release_report_path=new_release,
            confirmation=ACTIVATION_CONFIRMATION,
            timeout_seconds=300,
            now=NOW + timedelta(minutes=3),
            runner=retry_runner,
            platform_name="nt",
        )

        self.assertEqual(0, retry_code)
        self.assertEqual(
            "NEW_RELEASE_AFTER_ROLLED_BACK",
            retried["activationGuard"]["status"],
        )

    def test_acceptance_exception_still_rolls_back(self) -> None:
        class ExceptionRunner(FakeReleaseRunner):
            def __call__(self, command, root, timeout_seconds):
                if command[0] == "cmd.exe":
                    self.calls.append("acceptance")
                    raise TimeoutError("acceptance timeout")
                return super().__call__(command, root, timeout_seconds)

        runner = ExceptionRunner()
        report_path, report, exit_code = execute_activation(
            root=self.root,
            release_report_path=self.release_path,
            confirmation=ACTIVATION_CONFIRMATION,
            timeout_seconds=300,
            now=NOW,
            runner=runner,
            platform_name="nt",
        )

        self.assertEqual(1, exit_code)
        self.assertEqual(ROLLED_BACK_STATUS, report["status"])
        self.assertEqual("automatic-rollback", runner.calls[-1])
        verify_activation_report(root=self.root, report_path=report_path)

    def test_rollback_failure_is_critical_activation_failure(self) -> None:
        class FailingRollbackRunner(FakeReleaseRunner):
            def __call__(self, command, root, timeout_seconds):
                joined = " ".join(str(item) for item in command)
                if (
                    "visionflow-model-rollback.env" in joined
                    or command[0] == "cmd.exe"
                ):
                    key = (
                        "automatic-rollback"
                        if "rollback.env" in joined
                        else "acceptance"
                    )
                    self.calls.append(key)
                    return CommandResult(9, f"{key} failed\n", 10)
                return super().__call__(command, root, timeout_seconds)

        runner = FailingRollbackRunner()
        report_path, report, exit_code = execute_activation(
            root=self.root,
            release_report_path=self.release_path,
            confirmation=ACTIVATION_CONFIRMATION,
            timeout_seconds=300,
            now=NOW,
            runner=runner,
            platform_name="nt",
        )

        self.assertEqual(1, exit_code)
        self.assertEqual(FAILED_STATUS, report["status"])
        self.assertTrue(report["safety"]["rollbackAttempted"])
        self.assertFalse(report["safety"]["rollbackSucceeded"])
        verify_activation_report(root=self.root, report_path=report_path)

    def test_rollback_failure_blocks_new_release_attempt(self) -> None:
        class CriticalRunner(FakeReleaseRunner):
            def __call__(self, command, root, timeout_seconds):
                joined = " ".join(str(item) for item in command)
                if command[0] == "cmd.exe":
                    self.calls.append("acceptance")
                    return CommandResult(9, "acceptance failed\n", 10)
                if "visionflow-model-rollback.env" in joined:
                    self.calls.append("automatic-rollback")
                    return CommandResult(9, "rollback failed\n", 10)
                return super().__call__(command, root, timeout_seconds)

        _, failed, first_code = execute_activation(
            root=self.root,
            release_report_path=self.release_path,
            confirmation=ACTIVATION_CONFIRMATION,
            timeout_seconds=300,
            now=NOW,
            runner=CriticalRunner(),
            platform_name="nt",
        )
        self.assertEqual(1, first_code)
        self.assertEqual(FAILED_STATUS, failed["status"])
        new_release = self.create_release(NOW + timedelta(minutes=1))
        blocked_runner = FakeReleaseRunner()

        with self.assertRaisesRegex(
            ModelReleaseError,
            "자동 롤백이 실패",
        ):
            execute_activation(
                root=self.root,
                release_report_path=new_release,
                confirmation=ACTIVATION_CONFIRMATION,
                timeout_seconds=300,
                now=NOW + timedelta(minutes=2),
                runner=blocked_runner,
                platform_name="nt",
            )

        self.assertEqual([], blocked_runner.calls)

    def test_tampered_latest_activation_blocks_new_release(self) -> None:
        first_path, _, first_code = execute_activation(
            root=self.root,
            release_report_path=self.release_path,
            confirmation=ACTIVATION_CONFIRMATION,
            timeout_seconds=300,
            now=NOW,
            runner=FakeReleaseRunner(),
            platform_name="nt",
        )
        self.assertEqual(0, first_code)
        first_path.with_suffix(".html").write_text(
            "tampered",
            encoding="utf-8",
        )
        new_release = self.create_release(NOW + timedelta(minutes=1))
        blocked_runner = FakeReleaseRunner()

        with self.assertRaisesRegex(
            ModelReleaseError,
            "최신 모델 릴리스 실행 이력",
        ):
            execute_activation(
                root=self.root,
                release_report_path=new_release,
                confirmation=ACTIVATION_CONFIRMATION,
                timeout_seconds=300,
                now=NOW + timedelta(minutes=2),
                runner=blocked_runner,
                platform_name="nt",
            )

        self.assertEqual([], blocked_runner.calls)

    def test_plan_is_read_only_and_includes_automatic_rollback(self) -> None:
        plan = build_plan()

        self.assertEqual(7, len(plan))
        self.assertIn("HP OMEN", plan[0])
        self.assertIn("자동 롤백", plan[5])


if __name__ == "__main__":
    unittest.main()
