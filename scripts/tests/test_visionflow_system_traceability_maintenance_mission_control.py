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


class SystemTraceabilityMaintenanceMissionControlTest(
    unittest.TestCase
):
    def test_current_maintenance_mission_control_is_complete(
        self,
    ) -> None:
        root = SCRIPT_DIR.parent
        self.assertEqual(
            traceability.maintenance_mission_control_ui_policy_drift(
                root
            ),
            [],
        )

    def test_missing_board_mount_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_policy_sources(root)
            board = (
                root
                / "01_frontend/visionflow-web/src/components"
                / "maintenance/maintenance-work-order-board.tsx"
            )
            source = board.read_text(encoding="utf-8")
            source = source.replace(
                "<MaintenanceMissionControl "
                "refreshKey={metricsRevision} />",
                "",
                1,
            )
            board.write_text(source, encoding="utf-8")

            drift = (
                traceability
                .maintenance_mission_control_ui_policy_drift(root)
            )

        self.assertIn(
            "missing-token:work-order-board:"
            "<MaintenanceMissionControl "
            "refreshKey={metricsRevision} />",
            drift,
        )
        self.assertIn(
            "ordering:work-order-board:"
            "mission-control-before-detail-panels",
            drift,
        )

    def test_missing_auto_refresh_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_policy_sources(root)
            component = (
                root
                / "01_frontend/visionflow-web/src/components"
                / "maintenance/maintenance-mission-control.tsx"
            )
            source = component.read_text(encoding="utf-8")
            source = source.replace(
                "window.setInterval(",
                "window.setTimeout(",
                1,
            )
            component.write_text(source, encoding="utf-8")

            drift = (
                traceability
                .maintenance_mission_control_ui_policy_drift(root)
            )

        self.assertIn(
            "missing-token:mission-control:window.setInterval(",
            drift,
        )

    def test_missing_fleet_clearance_integration_is_detected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_policy_sources(root)
            component = (
                root
                / "01_frontend/visionflow-web/src/components"
                / "maintenance/maintenance-mission-control.tsx"
            )
            source = component.read_text(encoding="utf-8")
            source = source.replace(
                'fetch("/api/maintenance/flight-clearance"',
                'fetch("/api/maintenance/sla/incidents"',
                1,
            )
            component.write_text(source, encoding="utf-8")

            drift = (
                traceability
                .maintenance_mission_control_ui_policy_drift(root)
            )

        self.assertIn(
            "missing-token:mission-control:"
            'fetch("/api/maintenance/flight-clearance"',
            drift,
        )
        self.assertIn(
            "ordering:mission-control:tracking-and-fleet-fetch-"
            "before-parse-before-summary-before-render",
            drift,
        )

    def test_missing_readiness_drilldown_is_detected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_policy_sources(root)
            component = (
                root
                / "01_frontend/visionflow-web/src/components"
                / "maintenance/maintenance-mission-control.tsx"
            )
            source = component.read_text(encoding="utf-8")
            source = source.replace(
                'id="maintenance-readiness-detail"',
                'id="maintenance-readiness-summary"',
                1,
            )
            component.write_text(source, encoding="utf-8")

            drift = (
                traceability
                .maintenance_mission_control_ui_policy_drift(root)
            )

        self.assertIn(
            "missing-token:mission-control:"
            'id="maintenance-readiness-detail"',
            drift,
        )
        self.assertIn(
            "ordering:mission-control:readiness-filter-before-"
            "detail-before-drone-link",
            drift,
        )
    def copy_policy_sources(self, target_root: Path) -> None:
        source_root = SCRIPT_DIR.parent
        relative_paths = [
            Path(
                "01_frontend/visionflow-web/src/components/maintenance"
                "/maintenance-mission-control.tsx"
            ),
            Path(
                "01_frontend/visionflow-web/src/components/maintenance"
                "/maintenance-work-order-board.tsx"
            ),
            Path(
                "01_frontend/visionflow-web/src/types"
                "/maintenance-sla-incident-tracking.ts"
            ),
            Path(
                "01_frontend/visionflow-web/src/types"
                "/maintenance-flight-clearance.ts"
            ),
            Path(
                "01_frontend/visionflow-web/src/app/api/maintenance"
                "/sla/incidents/route.ts"
            ),
            Path(
                "01_frontend/visionflow-web/src/app/api/maintenance"
                "/flight-clearance/route.ts"
            ),
            Path(
                "01_frontend/visionflow-web/src/lib/server"
                "/maintenance-work-order-proxy.ts"
            ),
        ]
        for relative_path in relative_paths:
            source = source_root / relative_path
            target = target_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


if __name__ == "__main__":
    unittest.main()
