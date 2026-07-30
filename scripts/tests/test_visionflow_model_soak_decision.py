from __future__ import annotations

import unittest
from datetime import timedelta

from scripts.tests import test_visionflow_model_soak as soak_test
from scripts.visionflow_model_soak import BLOCKED_STATUS, write_report
from scripts.visionflow_model_soak_decision import (
    FAILED_STATUS,
    ROLLBACK_CONFIRMATION,
    ROLLED_BACK_STATUS,
    STABILIZED_STATUS,
    ModelSoakDecisionError,
    build_plan,
    execute_decision,
    verify_decision_report,
)
from scripts.visionflow_model_release import CommandResult


NOW = soak_test.NOW + timedelta(hours=1)


class FakeDecisionRunner:
    def __init__(
        self,
        *,
        fail_key: str | None = None,
        raise_key: str | None = None,
    ) -> None:
        self.fail_key = fail_key
        self.raise_key = raise_key
        self.calls: list[str] = []

    def __call__(self, command, _root, _timeout_seconds) -> CommandResult:
        if command[0] == "cmd.exe":
            key = "rollback-acceptance"
        elif command[-2:] == ["config", "-q"]:
            key = "rollback-compose-config"
        else:
            key = "rollback-start"
        self.calls.append(key)
        if key == self.raise_key:
            raise TimeoutError(f"{key} timeout")
        return CommandResult(
            9 if key == self.fail_key else 0,
            f"{key} {'failed' if key == self.fail_key else 'passed'}\n",
            10,
        )


class ModelSoakDecisionTest(unittest.TestCase):
    def setUp(self) -> None:
        fixture = soak_test.ModelSoakTest(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.root = fixture.root
        self.output = self.root / "artifacts/model-soak-decision"
        self.passed_soak_path, _, _ = write_report(
            output_directory=self.root / "artifacts/model-soak",
            report=fixture.build(),
        )

    def blocked_soak(self):
        benchmark = self.fixture.benchmark_value()
        benchmark["averageInferenceMs"] = 99.0
        self.fixture.benchmark_path = self.fixture.write_benchmark(
            benchmark,
            name="visionflow-ai-benchmark-blocked.json",
        )
        report = self.fixture.build()
        self.assertEqual(BLOCKED_STATUS, report["status"])
        return write_report(
            output_directory=self.root / "artifacts/model-soak",
            report=report,
        )[0]

    def execute(self, soak_path, runner, confirmation=""):
        return execute_decision(
            root=self.root,
            soak_path=soak_path,
            confirmation=confirmation,
            timeout_seconds=300,
            now=NOW,
            output_directory=self.output,
            runner=runner,
            platform_name="nt",
        )

    def test_passed_soak_is_stabilized_without_runner(self) -> None:
        runner = FakeDecisionRunner()

        report_path, report, exit_code = self.execute(
            self.passed_soak_path,
            runner,
        )

        self.assertEqual(0, exit_code)
        self.assertEqual(STABILIZED_STATUS, report["status"])
        self.assertEqual([], runner.calls)
        self.assertFalse(report["safety"]["rollbackRequired"])
        verified_path, verified = verify_decision_report(
            root=self.root,
            report_path=report_path,
        )
        self.assertEqual(report_path, verified_path)
        self.assertEqual(report, verified)

    def test_blocked_soak_requires_confirmation_before_runner(self) -> None:
        runner = FakeDecisionRunner()
        blocked_path = self.blocked_soak()

        with self.assertRaisesRegex(
            ModelSoakDecisionError,
            ROLLBACK_CONFIRMATION,
        ):
            self.execute(blocked_path, runner)

        self.assertEqual([], runner.calls)
        self.assertFalse(self.output.exists())

    def test_blocked_soak_rolls_back_in_fixed_order(self) -> None:
        runner = FakeDecisionRunner()

        report_path, report, exit_code = self.execute(
            self.blocked_soak(),
            runner,
            ROLLBACK_CONFIRMATION,
        )

        self.assertEqual(1, exit_code)
        self.assertEqual(ROLLED_BACK_STATUS, report["status"])
        self.assertEqual(
            [
                "rollback-compose-config",
                "rollback-start",
                "rollback-acceptance",
            ],
            runner.calls,
        )
        self.assertTrue(report["safety"]["rollbackSucceeded"])
        verify_decision_report(root=self.root, report_path=report_path)

    def test_compose_failure_stops_before_stack_mutation(self) -> None:
        runner = FakeDecisionRunner(fail_key="rollback-compose-config")

        report_path, report, exit_code = self.execute(
            self.blocked_soak(),
            runner,
            ROLLBACK_CONFIRMATION,
        )

        self.assertEqual(1, exit_code)
        self.assertEqual(FAILED_STATUS, report["status"])
        self.assertEqual(["rollback-compose-config"], runner.calls)
        self.assertFalse(report["safety"]["rollbackAttempted"])
        verify_decision_report(root=self.root, report_path=report_path)

    def test_start_failure_stops_before_acceptance(self) -> None:
        runner = FakeDecisionRunner(fail_key="rollback-start")

        report_path, report, exit_code = self.execute(
            self.blocked_soak(),
            runner,
            ROLLBACK_CONFIRMATION,
        )

        self.assertEqual(1, exit_code)
        self.assertEqual(FAILED_STATUS, report["status"])
        self.assertEqual(
            ["rollback-compose-config", "rollback-start"],
            runner.calls,
        )
        verify_decision_report(root=self.root, report_path=report_path)

    def test_acceptance_exception_is_recorded_as_failure(self) -> None:
        runner = FakeDecisionRunner(raise_key="rollback-acceptance")

        report_path, report, exit_code = self.execute(
            self.blocked_soak(),
            runner,
            ROLLBACK_CONFIRMATION,
        )

        self.assertEqual(1, exit_code)
        self.assertEqual(FAILED_STATUS, report["status"])
        self.assertEqual("rollback-acceptance", runner.calls[-1])
        verify_decision_report(root=self.root, report_path=report_path)

    def test_changed_soak_invalidates_decision_report(self) -> None:
        report_path, _, _ = self.execute(
            self.passed_soak_path,
            FakeDecisionRunner(),
        )
        self.passed_soak_path.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "동일성"):
            verify_decision_report(
                root=self.root,
                report_path=report_path,
            )

    def test_tampered_decision_is_rejected_by_sidecar(self) -> None:
        report_path, _, _ = self.execute(
            self.passed_soak_path,
            FakeDecisionRunner(),
        )
        report_path.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "SHA-256"):
            verify_decision_report(
                root=self.root,
                report_path=report_path,
            )

    def test_non_windows_blocked_decision_is_rejected(self) -> None:
        runner = FakeDecisionRunner()

        with self.assertRaisesRegex(
            ModelSoakDecisionError,
            "Windows HP OMEN",
        ):
            execute_decision(
                root=self.root,
                soak_path=self.blocked_soak(),
                confirmation=ROLLBACK_CONFIRMATION,
                timeout_seconds=300,
                now=NOW,
                output_directory=self.output,
                runner=runner,
                platform_name="posix",
            )

        self.assertEqual([], runner.calls)

    def test_plan_is_read_only_and_covers_both_outcomes(self) -> None:
        plan = build_plan()

        self.assertEqual(6, len(plan))
        self.assertIn(STABILIZED_STATUS, plan[1])
        self.assertIn("yolo26n.pt", plan[3])


if __name__ == "__main__":
    unittest.main()
