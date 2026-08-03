from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import visionflow_system_traceability_audit as traceability


class SystemTraceabilityIncidentLifecycleTest(unittest.TestCase):
    def test_current_incident_lifecycle_guards_are_complete(self) -> None:
        root = SCRIPT_DIR.parent
        self.assertEqual(
            traceability.incident_lifecycle_concurrency_policy_drift(root),
            [],
        )

    def test_missing_operator_lock_usage_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backend = (
                root
                / "02_backend/visionflow-api/src/main/java"
                / "com/visionflow/api"
            )
            files = {
                backend
                / "incident/repository/IncidentRepository.java": """
                    @Lock(LockModeType.PESSIMISTIC_WRITE)
                    @Lock(LockModeType.PESSIMISTIC_WRITE)
                    @Lock(LockModeType.PESSIMISTIC_WRITE)
                    LockModeType.PESSIMISTIC_WRITE
                    findByIdForUpdate(
                    findBySourceTypeAndSourceIdForUpdate(
                    findOverdueForEscalationForUpdate(
                """,
                backend / "incident/service/IncidentService.java": """
                    findIncidentForUpdate(incidentId)
                    findIncidentForUpdate(incidentId)
                    findIncidentForUpdate(incidentId)
                    findBySourceTypeAndSourceIdForUpdate(
                    findBySourceTypeAndSourceIdForUpdate(
                    findBySourceTypeAndSourceIdForUpdate(
                """,
                backend
                / "incident/service/IncidentSlaEscalationService.java": """
                    findOverdueForEscalationForUpdate(
                    findByIdForUpdate(incidentId)
                """,
                backend
                / "flight/quality/service"
                / "FlightQualityIncidentAutomationService.java": """
                    droneRepository.findByIdForUpdate(
                    findBySourceTypeAndSourceIdForUpdate(
                """,
                backend
                / "maintenance/service"
                / "FlightGateIncidentAutomationService.java": """
                    droneRepository.findByIdForUpdate(
                    findBySourceTypeAndSourceIdForUpdate(
                    findBySourceTypeAndSourceIdForUpdate(
                """,
                backend
                / "maintenance/service"
                / "MaintenanceSlaIncidentEscalationService.java": """
                    findByIdForUpdate(incidentId.get())
                    existsByIncidentIdAndActionTypeAndActor(
                """,
                backend / "demo/service/DemoScenarioService.java": """
                    lockIncidentForDemoEscalation(incidentId)
                    jdbcTemplate.update(
                    SELECT id FROM incident WHERE id = ? FOR UPDATE
                    UPDATE incident
                """,
            }
            for path, content in files.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            drift = (
                traceability.incident_lifecycle_concurrency_policy_drift(
                    root
                )
            )

        self.assertIn(
            "usage:operator:lock-assign-priority-status-note",
            drift,
        )


if __name__ == "__main__":
    unittest.main()
