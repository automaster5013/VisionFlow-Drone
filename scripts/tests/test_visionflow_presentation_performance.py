from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts.visionflow_presentation_performance import (
    READY_STATUS,
    REVIEW_STATUS,
    PresentationPerformanceError,
    analyze_performance,
    verify_performance_report,
)
from scripts.visionflow_presentation_rehearsal import (
    READY_STATUS as REHEARSAL_READY_STATUS,
    REQUIRED_DEMO_RESULTS,
)


NOW = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)


class VisionFlowPresentationPerformanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.output = self.root / "artifacts/presentation-performance"
        self.source = self.root / (
            "artifacts/presentation-rehearsal/"
            "visionflow-presentation-rehearsal-20260724T115000Z.json"
        )
        self.source.parent.mkdir(parents=True)
        self.rehearsal = self.rehearsal_report()
        self.write_source()

    def rehearsal_report(self) -> dict:
        runs = []
        for iteration in range(1, 4):
            stages = []
            for index, name in enumerate(REQUIRED_DEMO_RESULTS):
                duration = 50 + index + iteration
                if name == "Demo AI detection":
                    duration = 500 + iteration * 10
                stages.append(
                    {
                        "name": name,
                        "status": "PASS",
                        "durationMs": duration,
                    }
                )
            runs.append(
                {
                    "iteration": iteration,
                    "status": "PASS",
                    "processExitCode": 0,
                    "elapsedSeconds": round(1 + iteration / 10, 3),
                    "acceptance": {
                        "path": (
                            "artifacts/visionflow-acceptance/"
                            f"visionflow-acceptance-{iteration}.json"
                        ),
                    },
                    "summary": {
                        "total": 20,
                        "passed": 20,
                        "failed": 0,
                    },
                    "stages": stages,
                    "issues": [],
                }
            )
        return {
            "schemaVersion": 1,
            "project": "visionflow",
            "scope": "SECOND_PROJECT_DIGITAL_TWIN",
            "operation": "PRESENTATION_STABILITY_REHEARSAL",
            "rehearsalId": "rehearsal-001",
            "generatedAt": NOW.isoformat(),
            "status": REHEARSAL_READY_STATUS,
            "policy": {
                "requestedRuns": 3,
                "maxRunSeconds": 30.0,
                "maxStepMs": 10000,
                "failFast": True,
                "requiredDemoResults": list(REQUIRED_DEMO_RESULTS),
            },
            "runs": runs,
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

    def write_source(self) -> None:
        self.source.write_text(
            json.dumps(self.rehearsal, ensure_ascii=False),
            encoding="utf-8",
        )

    def source_verifier(self, root: Path, value: str):
        self.assertEqual(self.root, root)
        self.assertEqual(
            self.source,
            (self.root / value).resolve(),
        )
        return self.source, self.rehearsal

    def analyze(self):
        with patch(
            "scripts.visionflow_presentation_performance."
            "verify_rehearsal_report",
            side_effect=self.source_verifier,
        ):
            return analyze_performance(
                self.root,
                rehearsal_value=None,
                output_root=self.output,
                warning_budget_percent=70.0,
                warning_cv_percent=60.0,
                variability_minimum_ms=250.0,
                now=NOW,
            )

    def verify(self, report: Path):
        with patch(
            "scripts.visionflow_presentation_performance."
            "verify_rehearsal_report",
            side_effect=self.source_verifier,
        ):
            return verify_performance_report(
                self.root,
                report.relative_to(self.root).as_posix(),
            )

    def set_stage_durations(self, name: str, values: list[int]) -> None:
        for run, duration in zip(
            self.rehearsal["runs"],
            values,
            strict=True,
        ):
            for stage in run["stages"]:
                if stage["name"] == name:
                    stage["durationMs"] = duration
        self.write_source()

    def test_ready_analysis_identifies_bottleneck_and_verifies(self) -> None:
        json_path, html_path, sidecar, report = self.analyze()

        self.assertEqual(READY_STATUS, report["status"])
        self.assertEqual(
            "Demo AI detection",
            report["analysis"]["bottleneck"]["name"],
        )
        self.assertEqual(0, report["analysis"]["summary"]["watchStageCount"])
        self.assertTrue(json_path.is_file())
        self.assertTrue(html_path.is_file())
        self.assertTrue(sidecar.is_file())
        verified_path, verified = self.verify(json_path)
        self.assertEqual(json_path, verified_path)
        self.assertEqual(report, verified)

    def test_stage_budget_warning_requires_review(self) -> None:
        self.rehearsal["policy"]["maxStepMs"] = 1000
        self.set_stage_durations("Demo AI detection", [800, 800, 800])

        _, _, _, report = self.analyze()

        self.assertEqual(REVIEW_STATUS, report["status"])
        self.assertEqual(
            ["Demo AI detection"],
            report["analysis"]["watchStages"],
        )
        self.assertEqual(
            80.0,
            report["analysis"]["stages"][0]["budgetUsagePercent"],
        )

    def test_slow_variable_stage_requires_review(self) -> None:
        self.set_stage_durations("Demo AI detection", [250, 250, 1000])

        _, _, _, report = self.analyze()

        self.assertEqual(REVIEW_STATUS, report["status"])
        self.assertGreater(
            report["analysis"]["stages"][0][
                "coefficientOfVariationPercent"
            ],
            60,
        )

    def test_short_jitter_does_not_create_false_variability_warning(
        self,
    ) -> None:
        self.set_stage_durations("Demo AI detection", [1, 40, 1])

        _, _, _, report = self.analyze()

        self.assertEqual(READY_STATUS, report["status"])
        self.assertEqual([], report["analysis"]["watchStages"])

    def test_source_tamper_is_rejected(self) -> None:
        json_path, _, _, _ = self.analyze()
        self.source.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(
            PresentationPerformanceError,
            "원본 발표 리허설 파일 동일성",
        ):
            self.verify(json_path)

    def test_html_tamper_is_rejected(self) -> None:
        json_path, html_path, _, _ = self.analyze()
        html_path.write_text("changed", encoding="utf-8")

        with self.assertRaisesRegex(
            PresentationPerformanceError,
            "SHA-256",
        ):
            self.verify(json_path)

    def test_output_outside_allowed_directory_is_rejected(self) -> None:
        with (
            patch(
                "scripts.visionflow_presentation_performance."
                "verify_rehearsal_report",
                side_effect=self.source_verifier,
            ),
            self.assertRaisesRegex(
                PresentationPerformanceError,
                "출력 폴더",
            ),
        ):
            analyze_performance(
                self.root,
                rehearsal_value=None,
                output_root=self.root / "outside",
                warning_budget_percent=70.0,
                warning_cv_percent=60.0,
                variability_minimum_ms=250.0,
                now=NOW,
            )

    def test_report_does_not_record_paths_keys_or_execute_deferred_work(
        self,
    ) -> None:
        json_path, html_path, _, report = self.analyze()
        value = (
            json_path.read_text(encoding="utf-8")
            + html_path.read_text(encoding="utf-8")
        )

        self.assertNotIn(str(self.root), value)
        self.assertNotIn("OPERATOR_", value)
        self.assertTrue(report["safety"]["readOnly"])
        self.assertFalse(report["safety"]["databaseMutation"])
        self.assertFalse(report["safety"]["gpuValidationExecuted"])
        self.assertFalse(
            report["safety"]["smartphoneSensorValidationExecuted"]
        )
        self.assertFalse(report["safety"]["djiIntegrationExecuted"])


if __name__ == "__main__":
    unittest.main()
