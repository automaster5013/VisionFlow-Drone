from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import visionflow_system_traceability_audit as traceability


class SystemTraceabilityGeofenceEventLifecycleTest(unittest.TestCase):
    def test_current_geofence_event_guards_are_complete(self) -> None:
        root = SCRIPT_DIR.parent
        self.assertEqual(
            traceability
            .geofence_event_lifecycle_concurrency_policy_drift(root),
            [],
        )

    def test_missing_database_unique_guard_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main = root / "02_backend" / "visionflow-api" / "src" / "main"
            files = {
                main
                / "java/com/visionflow/api/geofence/repository"
                / "DroneGeofenceRepository.java": """
                    @Lock(LockModeType.PESSIMISTIC_WRITE)
                    LockModeType.PESSIMISTIC_WRITE
                    findByIdForUpdate(
                """,
                main
                / "java/com/visionflow/api/geofence/service"
                / "GeofenceService.java": """
                    findGeofenceForUpdate(id)
                    findGeofenceForUpdate(id)
                    public void evaluate(
                    candidate.getId()
                    if (!geofence.isActive())
                    .findFirstByDroneIdAndGeofenceIdAndResolvedAtIsNullOrderByDetectedAtDesc(
                """,
                main
                / "resources/db/migration"
                / "V23__enforce_single_active_geofence_event.sql": """
                    active_drone_id BIGINT
                    active_geofence_id BIGINT
                    resolved_at IS NULL
                    uq_geofence_event_one_active_per_drone_zone
                """,
                root / "scripts/visionflow_data_integrity_audit.py": """
                    "geofence-event-multiple-active-per-drone-zone"
                    GROUP BY event.drone_id, event.geofence_id
                    HAVING COUNT(*) > 1
                """,
                root / "scripts/visionflow_data_integrity_policy.json": """
                    "key": "geofence-event-multiple-active-per-drone-zone"
                    "severity": "CRITICAL"
                """,
            }
            for path, content in files.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            drift = (
                traceability
                .geofence_event_lifecycle_concurrency_policy_drift(root)
            )

        self.assertIn(
            "missing-token:migration:UNIQUE (active_drone_id, active_geofence_id)",
            drift,
        )


if __name__ == "__main__":
    unittest.main()
