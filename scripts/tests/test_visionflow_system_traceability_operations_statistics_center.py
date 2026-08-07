from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import visionflow_system_traceability_audit as traceability


class SystemTraceabilityOperationsStatisticsCenterTest(unittest.TestCase):
    def test_current_operations_statistics_center_is_complete(self) -> None:
        root = SCRIPT_DIR.parent
        self.assertEqual(
            traceability.operations_statistics_center_ui_policy_drift(root),
            [],
        )

    def test_missing_page_mount_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_policy_sources(root)
            page = root / "01_frontend/visionflow-web/src/app/statistics/page.tsx"
            page.write_text(
                page.read_text(encoding="utf-8").replace(
                    "<OperationsStatisticsCenter />", "<div />", 1
                ),
                encoding="utf-8",
            )
            drift = traceability.operations_statistics_center_ui_policy_drift(root)

        self.assertIn(
            "missing-token:statistics-page:<OperationsStatisticsCenter />",
            drift,
        )

    def test_missing_partial_failure_isolation_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_policy_sources(root)
            component = self.center_path(root)
            component.write_text(
                component.read_text(encoding="utf-8").replace(
                    "Promise.allSettled([", "Promise.all([", 1
                ),
                encoding="utf-8",
            )
            drift = traceability.operations_statistics_center_ui_policy_drift(root)

        self.assertIn(
            "missing-token:statistics-center:Promise.allSettled([",
            drift,
        )

    def test_missing_response_parser_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_policy_sources(root)
            component = self.center_path(root)
            component.write_text(
                component.read_text(encoding="utf-8").replace(
                    "parseOperationsStatisticsAiMetrics(aiResult.value)",
                    "aiResult.value",
                    1,
                ),
                encoding="utf-8",
            )
            drift = traceability.operations_statistics_center_ui_policy_drift(root)

        self.assertIn(
            "missing-token:statistics-center:"
            "parseOperationsStatisticsAiMetrics(aiResult.value)",
            drift,
        )

    def test_missing_auto_refresh_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_policy_sources(root)
            component = self.center_path(root)
            component.write_text(
                component.read_text(encoding="utf-8").replace(
                    "const AUTO_REFRESH_INTERVAL_MS = 30_000",
                    "const AUTO_REFRESH_INTERVAL_MS = 60_000",
                    1,
                ),
                encoding="utf-8",
            )
            drift = traceability.operations_statistics_center_ui_policy_drift(root)

        self.assertIn(
            "missing-token:statistics-center:"
            "const AUTO_REFRESH_INTERVAL_MS = 30_000",
            drift,
        )

    def test_mutation_method_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_policy_sources(root)
            component = self.center_path(root)
            component.write_text(
                component.read_text(encoding="utf-8").replace(
                    'method: "GET"', 'method: "POST"', 1
                ),
                encoding="utf-8",
            )
            drift = traceability.operations_statistics_center_ui_policy_drift(root)

        self.assertIn(
            "usage:operations-statistics:center-read-only-no-mutation",
            drift,
        )

    def test_missing_push_and_pr_trigger_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_policy_sources(root)
            workflow = root / ".github/workflows/api-audit.yml"
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace(
                    '      - "01_frontend/visionflow-web/src/app/statistics/**"\n',
                    "",
                    1,
                ),
                encoding="utf-8",
            )
            drift = traceability.operations_statistics_center_ui_policy_drift(root)

        self.assertIn(
            "trigger:operations-statistics:push-and-pr:"
            '"01_frontend/visionflow-web/src/app/statistics/**"',
            drift,
        )

    def test_zero_work_order_resolution_uses_no_sample_marker(self) -> None:
        component = self.center_path(SCRIPT_DIR.parent).read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "maintenance && maintenance.totalWorkOrders > 0",
            component,
        )
        self.assertIn(
            '? formatPercent(maintenance.resolutionRatePercent)\n'
            '                : "—"',
            component,
        )

    @staticmethod
    def center_path(root: Path) -> Path:
        return (
            root
            / "01_frontend/visionflow-web/src/components/statistics"
            / "operations-statistics-center.tsx"
        )

    def copy_policy_sources(self, target_root: Path) -> None:
        source_root = SCRIPT_DIR.parent
        relative_paths = [
            Path(".github/workflows/api-audit.yml"),
            Path("01_frontend/visionflow-web/src/app/statistics/page.tsx"),
            Path(
                "01_frontend/visionflow-web/src/components/statistics"
                "/operations-statistics-center.tsx"
            ),
            Path(
                "01_frontend/visionflow-web/src/types/operations-statistics.ts"
            ),
            Path(
                "01_frontend/visionflow-web/src/app/api/dashboard/operations/route.ts"
            ),
            Path(
                "01_frontend/visionflow-web/src/app/api/flight-quality"
                "/fleet-reliability/route.ts"
            ),
            Path(
                "01_frontend/visionflow-web/src/app/api/maintenance/metrics/route.ts"
            ),
            Path(
                "01_frontend/visionflow-web/src/app/api/ai/metrics/status/route.ts"
            ),
        ]
        for relative_path in relative_paths:
            source = source_root / relative_path
            destination = target_root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)


if __name__ == "__main__":
    unittest.main()
