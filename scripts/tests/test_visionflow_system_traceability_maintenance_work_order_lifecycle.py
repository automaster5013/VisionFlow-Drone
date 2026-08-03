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


class SystemTraceabilityMaintenanceWorkOrderLifecycleTest(
    unittest.TestCase
):
    def test_current_maintenance_work_order_guards_are_complete(
        self,
    ) -> None:
        root = SCRIPT_DIR.parent
        self.assertEqual(
            traceability
            .maintenance_work_order_lifecycle_concurrency_policy_drift(
                root
            ),
            [],
        )

    def test_missing_sla_work_order_reload_lock_is_detected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_policy_sources(root)
            service = (
                root
                / "02_backend/visionflow-api/src/main/java"
                / "com/visionflow/api/maintenance/service"
                / "MaintenanceSlaIncidentEscalationService.java"
            )
            source = service.read_text(encoding="utf-8")
            source = source.replace(
                "findByIdForUpdate(workOrderId)",
                "findById(workOrderId)",
                1,
            )
            service.write_text(source, encoding="utf-8")

            drift = (
                traceability
                .maintenance_work_order_lifecycle_concurrency_policy_drift(
                    root
                )
            )

        self.assertIn(
            "missing-token:sla-service:"
            "findByIdForUpdate(workOrderId)",
            drift,
        )
        self.assertIn(
            "ordering:sla-service:"
            "incident-before-work-order-lock-before-reevaluation",
            drift,
        )

    def copy_policy_sources(self, target_root: Path) -> None:
        source_root = SCRIPT_DIR.parent
        relative_paths = [
            Path(
                "02_backend/visionflow-api/src/main/java"
                "/com/visionflow/api/maintenance/repository"
                "/MaintenanceWorkOrderRepository.java"
            ),
            Path(
                "02_backend/visionflow-api/src/main/java"
                "/com/visionflow/api/incident/repository"
                "/IncidentRepository.java"
            ),
            Path(
                "02_backend/visionflow-api/src/main/java"
                "/com/visionflow/api/maintenance/service"
                "/MaintenanceWorkOrderService.java"
            ),
            Path(
                "02_backend/visionflow-api/src/main/java"
                "/com/visionflow/api/maintenance/service"
                "/MaintenanceSlaIncidentEscalationService.java"
            ),
            Path(
                "02_backend/visionflow-api/src/main/resources"
                "/db/migration"
                "/V19__create_maintenance_work_order.sql"
            ),
        ]
        for relative_path in relative_paths:
            source = source_root / relative_path
            target = target_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


if __name__ == "__main__":
    unittest.main()
