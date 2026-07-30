from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts.visionflow_presentation_performance import (
    READY_STATUS as PERFORMANCE_READY_STATUS,
)
from scripts.visionflow_presentation_quick_check import (
    BLOCKED_STATUS,
    ENDPOINTS,
    READY_STATUS,
    PresentationQuickCheckError,
    run_quick_check,
    verify_quick_check_report,
)


NOW = datetime(2026, 7, 24, 13, 0, tzinfo=timezone.utc)


class VisionFlowPresentationQuickCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.output = self.root / "artifacts/presentation-quick-check"
        self.source = self.root / (
            "artifacts/presentation-performance/"
            "visionflow-presentation-performance-20260724T125000Z.json"
        )
        self.source.parent.mkdir(parents=True)
        self.performance = {
            "status": PERFORMANCE_READY_STATUS,
            "analysisId": "analysis-001",
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
        self.source.write_text(
            json.dumps(self.performance, ensure_ascii=False),
            encoding="utf-8",
        )
        self.failed: set[str] = set()

    def source_verifier(self, root: Path, value: str):
        self.assertEqual(self.root, root)
        self.assertEqual(
            self.source,
            (self.root / value).resolve(),
        )
        return self.source, self.performance

    def probe(self, endpoint, _: float):
        failed = endpoint["key"] in self.failed
        return {
            "key": endpoint["key"],
            "title": endpoint["title"],
            "base": endpoint["base"],
            "path": endpoint["path"],
            "status": "FAILED" if failed else "PASS",
            "statusCode": 503 if failed else 200,
            "durationMs": 10,
            "errorCode": "HTTP_503" if failed else None,
        }

    def run_check(self):
        with patch(
            "scripts.visionflow_presentation_quick_check."
            "verify_performance_report",
            side_effect=self.source_verifier,
        ):
            return run_quick_check(
                self.root,
                performance_value=None,
                output_root=self.output,
                probe=self.probe,
                timeout_seconds=5.0,
                frontend_url="http://localhost:3000",
                backend_url="http://localhost:8080",
                ai_url="http://localhost:8000",
                now=NOW,
            )

    def verify(self, report: Path):
        with patch(
            "scripts.visionflow_presentation_quick_check."
            "verify_performance_report",
            side_effect=self.source_verifier,
        ):
            return verify_quick_check_report(
                self.root,
                report.relative_to(self.root).as_posix(),
            )

    def test_all_paths_ready_and_report_independently_verifies(self) -> None:
        json_path, html_path, sidecar, report, exit_code = self.run_check()

        self.assertEqual(0, exit_code)
        self.assertEqual(READY_STATUS, report["status"])
        self.assertEqual(len(ENDPOINTS), report["summary"]["passed"])
        self.assertEqual(
            "PRESENTATION_PATHS_HEALTHY",
            report["diagnosis"]["code"],
        )
        self.assertTrue(json_path.is_file())
        self.assertTrue(html_path.is_file())
        self.assertTrue(sidecar.is_file())
        verified_path, verified = self.verify(json_path)
        self.assertEqual(json_path, verified_path)
        self.assertEqual(report, verified)

    def test_backend_failure_is_classified(self) -> None:
        self.failed = {"backend-health", "backend-drones"}

        _, _, _, report, exit_code = self.run_check()

        self.assertEqual(1, exit_code)
        self.assertEqual(BLOCKED_STATUS, report["status"])
        self.assertEqual(
            "BACKEND_OR_DATABASE_UNAVAILABLE",
            report["diagnosis"]["code"],
        )

    def test_ai_failure_is_classified(self) -> None:
        self.failed = {"ai-ingest", "ai-stream"}

        _, _, _, report, _ = self.run_check()

        self.assertEqual(
            "AI_SERVER_UNAVAILABLE",
            report["diagnosis"]["code"],
        )

    def test_ai_proxy_failure_is_distinguished_from_ai_server(self) -> None:
        self.failed = {
            "frontend-ai-ingest-proxy",
            "frontend-ai-stream-proxy",
        }

        _, _, _, report, _ = self.run_check()

        self.assertEqual(
            "FRONTEND_AI_PROXY_FAILURE",
            report["diagnosis"]["code"],
        )

    def test_multiple_service_failures_are_classified(self) -> None:
        self.failed = {"backend-health", "ai-ingest"}

        _, _, _, report, _ = self.run_check()

        self.assertEqual(
            "MULTIPLE_SERVICE_FAILURES",
            report["diagnosis"]["code"],
        )

    def test_source_tamper_is_rejected(self) -> None:
        json_path, _, _, _, _ = self.run_check()
        self.source.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(
            PresentationQuickCheckError,
            "원본 발표 성능 파일 동일성",
        ):
            self.verify(json_path)

    def test_html_tamper_is_rejected(self) -> None:
        json_path, html_path, _, _, _ = self.run_check()
        html_path.write_text("changed", encoding="utf-8")

        with self.assertRaisesRegex(
            PresentationQuickCheckError,
            "SHA-256",
        ):
            self.verify(json_path)

    def test_output_outside_allowed_directory_is_rejected(self) -> None:
        with (
            patch(
                "scripts.visionflow_presentation_quick_check."
                "verify_performance_report",
                side_effect=self.source_verifier,
            ),
            self.assertRaisesRegex(
                PresentationQuickCheckError,
                "출력 폴더",
            ),
        ):
            run_quick_check(
                self.root,
                performance_value=None,
                output_root=self.root / "outside",
                probe=self.probe,
                timeout_seconds=5.0,
                frontend_url="http://localhost:3000",
                backend_url="http://localhost:8080",
                ai_url="http://localhost:8000",
                now=NOW,
            )

    def test_report_omits_bodies_secrets_and_deferred_execution(self) -> None:
        json_path, html_path, _, report, _ = self.run_check()
        value = (
            json_path.read_text(encoding="utf-8")
            + html_path.read_text(encoding="utf-8")
        )

        self.assertNotIn(str(self.root), value)
        self.assertNotIn("OPERATOR_", value)
        self.assertTrue(report["safety"]["readOnly"])
        self.assertFalse(report["safety"]["responseBodiesRecorded"])
        self.assertFalse(report["safety"]["automaticRestart"])
        self.assertFalse(report["safety"]["gpuValidationExecuted"])
        self.assertFalse(
            report["safety"]["smartphoneSensorValidationExecuted"]
        )
        self.assertFalse(report["safety"]["djiIntegrationExecuted"])


if __name__ == "__main__":
    unittest.main()
