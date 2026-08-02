from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import visionflow_system_traceability_audit as traceability


class SystemTraceabilityFlightSessionLifecycleTest(unittest.TestCase):
    def test_current_lifecycle_concurrency_guards_are_complete(self) -> None:
        root = SCRIPT_DIR.parent
        self.assertEqual(
            traceability.flight_session_lifecycle_policy_drift(root),
            [],
        )

    def test_missing_database_unique_guard_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main = root / "02_backend" / "visionflow-api" / "src" / "main"
            files = {
                main
                / "java/com/visionflow/api/flight/service"
                / "FlightSessionManagementService.java": """
                    droneRepository.findByIdForUpdate(droneId)
                    .findFirstByDroneIdAndStatusOrderByStartedAtDesc(
                    new ActiveFlightSessionExistsException(droneId)
                    sessionRepository.saveAndFlush(session)
                    uq_flight_session_one_active_per_drone
                    isActiveSessionUniquenessViolation(exception)
                    findManagedSessionForUpdate(
                    findManagedSessionForUpdate(
                    findManagedSessionForUpdate(
                    findManagedSessionForUpdate(
                """,
                main
                / "java/com/visionflow/api/flight/repository"
                / "FlightSessionRepository.java": """
                    LockModeType.PESSIMISTIC_WRITE
                    findBySessionIdAndDroneIdForUpdate(
                """,
                main
                / "java/com/visionflow/api/drone/repository"
                / "DroneRepository.java": """
                    LockModeType.PESSIMISTIC_WRITE
                    findByIdForUpdate(
                """,
                main
                / "java/com/visionflow/api/flight/exception"
                / "ActiveFlightSessionExistsException.java": (
                    "ACTIVE_FLIGHT_SESSION_EXISTS"
                ),
                main
                / "resources/db/migration"
                / "V22__enforce_single_active_flight_session.sql": """
                    GENERATED ALWAYS AS
                    status = 'ACTIVE'
                """,
                root / "scripts/visionflow_data_integrity_audit.py": """
                    "flight-session-multiple-active-per-drone"
                    HAVING COUNT(*) > 1
                """,
                root / "scripts/visionflow_data_integrity_policy.json": """
                    "key": "flight-session-multiple-active-per-drone"
                    "severity": "CRITICAL"
                """,
            }
            for path, content in files.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            drift = traceability.flight_session_lifecycle_policy_drift(root)

        self.assertIn(
            "missing-token:migration:UNIQUE (active_drone_id)",
            drift,
        )


if __name__ == "__main__":
    unittest.main()
