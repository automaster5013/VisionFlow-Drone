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


class SystemTraceabilityEventOperationsCenterTest(unittest.TestCase):
    def test_current_event_operations_center_is_complete(self) -> None:
        root = SCRIPT_DIR.parent
        self.assertEqual(
            traceability.event_operations_center_ui_policy_drift(root),
            [],
        )

    def test_missing_page_mount_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_policy_sources(root)
            page = (
                root
                / "01_frontend/visionflow-web/src/app/events/page.tsx"
            )
            source = page.read_text(encoding="utf-8")
            page.write_text(
                source.replace(
                    "<EventOperationsCenter />",
                    "<div />",
                    1,
                ),
                encoding="utf-8",
            )

            drift = (
                traceability.event_operations_center_ui_policy_drift(root)
            )

        self.assertIn(
            "missing-token:events-page:<EventOperationsCenter />",
            drift,
        )

    def test_missing_source_integration_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_policy_sources(root)
            component = self.operations_center_path(root)
            source = component.read_text(encoding="utf-8")
            component.write_text(
                source.replace(
                    'fetchJson("/api/geofences/events?activeOnly=false'
                    '&limit=100", controller.signal)',
                    'fetchJson("/api/geofences?limit=100", '
                    "controller.signal)",
                    1,
                ),
                encoding="utf-8",
            )

            drift = (
                traceability.event_operations_center_ui_policy_drift(root)
            )

        self.assertIn(
            "missing-token:operations-center:"
            'fetchJson("/api/geofences/events?activeOnly=false&limit=100", '
            "controller.signal)",
            drift,
        )

    def test_missing_partial_failure_guard_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_policy_sources(root)
            component = self.operations_center_path(root)
            source = component.read_text(encoding="utf-8")
            component.write_text(
                source.replace(
                    "Promise.allSettled([",
                    "Promise.all([",
                    1,
                ),
                encoding="utf-8",
            )

            drift = (
                traceability.event_operations_center_ui_policy_drift(root)
            )

        self.assertIn(
            "missing-token:operations-center:Promise.allSettled([",
            drift,
        )

    def test_missing_auto_refresh_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_policy_sources(root)
            component = self.operations_center_path(root)
            source = component.read_text(encoding="utf-8")
            component.write_text(
                source.replace(
                    "const AUTO_REFRESH_INTERVAL_MS = 15_000",
                    "const AUTO_REFRESH_INTERVAL_MS = 60_000",
                    1,
                ),
                encoding="utf-8",
            )

            drift = (
                traceability.event_operations_center_ui_policy_drift(root)
            )

        self.assertIn(
            "missing-token:operations-center:"
            "const AUTO_REFRESH_INTERVAL_MS = 15_000",
            drift,
        )

    def test_missing_drawer_accessibility_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_policy_sources(root)
            drawer = (
                root
                / "01_frontend/visionflow-web/src/components/events"
                / "event-detail-drawer.tsx"
            )
            source = drawer.read_text(encoding="utf-8")
            drawer.write_text(
                source.replace(
                    'aria-modal="true"',
                    'aria-modal="false"',
                    1,
                ),
                encoding="utf-8",
            )

            drift = (
                traceability.event_operations_center_ui_policy_drift(root)
            )

        self.assertIn(
            'missing-token:event-drawer:aria-modal="true"',
            drift,
        )

    def test_missing_push_and_pr_trigger_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_policy_sources(root)
            workflow = root / ".github/workflows/api-audit.yml"
            source = workflow.read_text(encoding="utf-8")
            workflow.write_text(
                source.replace(
                    '      - "01_frontend/visionflow-web/src/app/events/**"\n',
                    "",
                    1,
                ),
                encoding="utf-8",
            )

            drift = (
                traceability.event_operations_center_ui_policy_drift(root)
            )

        self.assertIn(
            "trigger:event-operations:push-and-pr:"
            '"01_frontend/visionflow-web/src/app/events/**"',
            drift,
        )

    @staticmethod
    def operations_center_path(root: Path) -> Path:
        return (
            root
            / "01_frontend/visionflow-web/src/components/events"
            / "event-operations-center.tsx"
        )

    def copy_policy_sources(self, target_root: Path) -> None:
        source_root = SCRIPT_DIR.parent
        relative_paths = [
            Path(".github/workflows/api-audit.yml"),
            Path(
                "01_frontend/visionflow-web/src/app/events/page.tsx"
            ),
            Path(
                "01_frontend/visionflow-web/src/components/events"
                "/event-operations-center.tsx"
            ),
            Path(
                "01_frontend/visionflow-web/src/components/events"
                "/event-detail-drawer.tsx"
            ),
            Path(
                "01_frontend/visionflow-web/src/types/event-operations.ts"
            ),
            Path(
                "01_frontend/visionflow-web/src/app/api/ai/events/route.ts"
            ),
            Path(
                "01_frontend/visionflow-web/src/app/api/ai/alerts/route.ts"
            ),
            Path(
                "01_frontend/visionflow-web/src/app/api/geofences/events"
                "/route.ts"
            ),
            Path(
                "01_frontend/visionflow-web/src/app/api/incidents/route.ts"
            ),
            Path(
                "01_frontend/visionflow-web/src/app/api/drones/route.ts"
            ),
        ]
        for relative_path in relative_paths:
            source = source_root / relative_path
            destination = target_root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)


if __name__ == "__main__":
    unittest.main()
