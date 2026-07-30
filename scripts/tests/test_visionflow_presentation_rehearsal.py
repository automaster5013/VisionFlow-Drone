from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts.visionflow_presentation_gate import (
    READY_STATUS as PRESENTATION_GATE_READY_STATUS,
)
from scripts.visionflow_presentation_rehearsal import (
    BLOCKED_STATUS,
    READY_STATUS,
    REQUIRED_DEMO_RESULTS,
    PresentationRehearsalError,
    run_rehearsal,
    verify_rehearsal_report,
)


NOW = datetime(2026, 7, 24, 9, 0, tzinfo=timezone.utc)


class VisionFlowPresentationRehearsalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.output = self.root / "artifacts/presentation-rehearsal"
        self.gate_path = self.write_json(
            "artifacts/presentation-gate/"
            "visionflow-presentation-gate-20260724T085000Z.json",
            {"status": PRESENTATION_GATE_READY_STATUS},
        )
        self.gate_report = {
            "status": PRESENTATION_GATE_READY_STATUS,
            "deferred": [
                {
                    "key": "smartphone-real-sensor-https",
                    "status": "DEFERRED",
                    "scope": "SECOND_PROJECT_FOLLOW_UP",
                    "reason": "later",
                },
                {
                    "key": "dji-mini4-pro-integration",
                    "status": "OUT_OF_SCOPE",
                    "scope": "THIRD_PROJECT",
                    "reason": "phase 3",
                },
            ],
        }
        self.fail_iteration: int | None = None
        self.slow_stage_iteration: int | None = None

    def write_json(self, relative: str, value: dict) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def acceptance_report(self, iteration: int) -> dict:
        failed = iteration == self.fail_iteration
        results = []
        for index, name in enumerate(REQUIRED_DEMO_RESULTS):
            duration = 500 + index
            if (
                iteration == self.slow_stage_iteration
                and name == "Demo AI detection"
            ):
                duration = 10001
            results.append(
                {
                    "Name": name,
                    "Passed": not failed,
                    "DurationMs": duration,
                }
            )
        return {
            "generatedAt": NOW.isoformat(),
            "configuration": {
                "runDemo": True,
                "skipAi": False,
            },
            "summary": {
                "total": len(results),
                "passed": 0 if failed else len(results),
                "failed": len(results) if failed else 0,
            },
            "scenario": None if failed else {"stage": "COMPLETED"},
            "results": results,
        }

    def runner(self, iteration: int) -> int:
        self.write_json(
            "artifacts/visionflow-acceptance/"
            f"visionflow-acceptance-20260724-09000{iteration}.json",
            self.acceptance_report(iteration),
        )
        return 1 if iteration == self.fail_iteration else 0

    def gate_verifier(self, root: Path, value: str):
        self.assertEqual(self.root, root)
        self.assertEqual(
            self.gate_path,
            (self.root / value).resolve(),
        )
        return self.gate_path, self.gate_report

    def run_rehearsal_test(
        self,
        *,
        runs: int = 3,
        fail_fast: bool = True,
    ):
        monotonic_values = []
        for iteration in range(runs):
            monotonic_values.extend([float(iteration), float(iteration + 1)])
        with (
            patch(
                "scripts.visionflow_presentation_rehearsal."
                "verify_gate_report",
                side_effect=self.gate_verifier,
            ),
            patch(
                "scripts.visionflow_presentation_rehearsal.time.monotonic",
                side_effect=monotonic_values,
            ),
        ):
            return run_rehearsal(
                self.root,
                gate_value=None,
                runner=self.runner,
                runs=runs,
                max_run_seconds=30,
                max_step_ms=10000,
                fail_fast=fail_fast,
                output_root=self.output,
                now=NOW,
            )

    def verify(self, report: Path):
        with patch(
            "scripts.visionflow_presentation_rehearsal."
            "verify_gate_report",
            side_effect=self.gate_verifier,
        ):
            return verify_rehearsal_report(
                self.root,
                report.relative_to(self.root).as_posix(),
            )

    def test_three_consecutive_runs_create_ready_verified_evidence(self) -> None:
        json_path, html_path, sidecar, report, exit_code = (
            self.run_rehearsal_test()
        )

        self.assertEqual(0, exit_code)
        self.assertEqual(READY_STATUS, report["status"])
        self.assertEqual(3, report["summary"]["passedRuns"])
        self.assertEqual(100.0, report["metrics"]["successRatePercent"])
        self.assertEqual(1.0, report["metrics"]["averageRunSeconds"])
        self.assertTrue(json_path.is_file())
        self.assertTrue(html_path.is_file())
        self.assertTrue(sidecar.is_file())
        verified_path, verified = self.verify(json_path)
        self.assertEqual(json_path, verified_path)
        self.assertEqual(report, verified)

    def test_second_failure_stops_early_and_blocks(self) -> None:
        self.fail_iteration = 2

        _, _, _, report, exit_code = self.run_rehearsal_test()

        self.assertEqual(1, exit_code)
        self.assertEqual(BLOCKED_STATUS, report["status"])
        self.assertEqual(2, report["summary"]["attemptedRuns"])
        self.assertEqual(1, report["summary"]["passedRuns"])
        self.assertEqual("FAILED", report["runs"][1]["status"])

    def test_slow_required_stage_blocks_rehearsal(self) -> None:
        self.slow_stage_iteration = 1

        _, _, _, report, exit_code = self.run_rehearsal_test()

        self.assertEqual(1, exit_code)
        self.assertEqual("FAILED", report["runs"][0]["status"])
        self.assertIn("단계 시간 초과", report["runs"][0]["issues"][0])

    def test_report_does_not_record_absolute_path_or_keys(self) -> None:
        json_path, html_path, _, report, _ = self.run_rehearsal_test()
        value = (
            json_path.read_text(encoding="utf-8-sig")
            + html_path.read_text(encoding="utf-8")
        )

        self.assertNotIn(str(self.root), value)
        self.assertNotIn("OPERATOR_", value)
        self.assertFalse(report["safety"]["operatorKeysRecorded"])
        self.assertFalse(report["safety"]["smartphoneSensorValidationExecuted"])
        self.assertFalse(report["safety"]["djiIntegrationExecuted"])

    def test_acceptance_tamper_is_rejected(self) -> None:
        json_path, _, _, report, _ = self.run_rehearsal_test()
        acceptance = self.root / report["runs"][0]["acceptance"]["path"]
        acceptance.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(
            PresentationRehearsalError,
            "증적 파일 동일성이 다릅니다",
        ):
            self.verify(json_path)

    def test_html_tamper_is_rejected_by_sidecar(self) -> None:
        json_path, html_path, _, _, _ = self.run_rehearsal_test()
        html_path.write_text("changed", encoding="utf-8")

        with self.assertRaisesRegex(
            PresentationRehearsalError,
            "SHA-256",
        ):
            self.verify(json_path)

    def test_missing_acceptance_report_creates_verifiable_blocked_evidence(
        self,
    ) -> None:
        def no_report_runner(_: int) -> int:
            return 1

        with (
            patch(
                "scripts.visionflow_presentation_rehearsal."
                "verify_gate_report",
                side_effect=self.gate_verifier,
            ),
            patch(
                "scripts.visionflow_presentation_rehearsal.time.monotonic",
                side_effect=[0.0, 1.0, 1.0],
            ),
        ):
            json_path, _, _, report, exit_code = run_rehearsal(
                self.root,
                gate_value=None,
                runner=no_report_runner,
                runs=3,
                max_run_seconds=30,
                max_step_ms=10000,
                fail_fast=True,
                output_root=self.output,
                now=NOW,
            )

        self.assertEqual(1, exit_code)
        self.assertEqual(BLOCKED_STATUS, report["status"])
        self.assertIsNone(report["runs"][0]["acceptance"])
        verified_path, verified = self.verify(json_path)
        self.assertEqual(json_path, verified_path)
        self.assertEqual(report, verified)

    def test_output_outside_allowed_directory_is_rejected(self) -> None:
        with (
            patch(
                "scripts.visionflow_presentation_rehearsal."
                "verify_gate_report",
                side_effect=self.gate_verifier,
            ),
            patch(
                "scripts.visionflow_presentation_rehearsal.time.monotonic",
                side_effect=[0.0, 1.0],
            ),
            self.assertRaisesRegex(
                PresentationRehearsalError,
                "출력 폴더",
            ),
        ):
            run_rehearsal(
                self.root,
                gate_value=None,
                runner=self.runner,
                runs=1,
                max_run_seconds=30,
                max_step_ms=10000,
                fail_fast=True,
                output_root=self.root / "outside",
                now=NOW,
            )


if __name__ == "__main__":
    unittest.main()
