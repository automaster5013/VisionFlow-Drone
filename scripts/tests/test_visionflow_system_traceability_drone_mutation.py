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


class SystemTraceabilityDroneMutationTest(unittest.TestCase):
    def test_current_drone_mutation_guards_are_complete(self) -> None:
        root = SCRIPT_DIR.parent
        self.assertEqual(
            traceability.drone_mutation_concurrency_policy_drift(root),
            [],
        )

    def test_missing_telemetry_lock_usage_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_policy_sources(root)
            service = (
                root
                / "02_backend/visionflow-api/src/main/java"
                / "com/visionflow/api/drone/service/DroneService.java"
            )
            source = service.read_text(encoding="utf-8")
            lock_token = "Drone drone = findDroneForUpdate(id);"
            lock_at = source.rfind(lock_token)
            self.assertGreaterEqual(lock_at, 0)
            source = (
                source[:lock_at]
                + "Drone drone = findDroneById(id);"
                + source[lock_at + len(lock_token):]
            )
            service.write_text(source, encoding="utf-8")

            drift = (
                traceability.drone_mutation_concurrency_policy_drift(root)
            )

        self.assertIn(
            "usage:service:lock-basic-status-delete-telemetry",
            drift,
        )
        self.assertIn(
            "ordering:service:updateTelemetry-lock-before-correlation-and-write",
            drift,
        )

    def copy_policy_sources(self, target_root: Path) -> None:
        source_root = SCRIPT_DIR.parent
        relative_paths = [
            Path(
                "02_backend/visionflow-api/src/main/java"
                "/com/visionflow/api/drone/repository/DroneRepository.java"
            ),
            Path(
                "02_backend/visionflow-api/src/main/java"
                "/com/visionflow/api/drone/service/DroneService.java"
            ),
            Path(
                "02_backend/visionflow-api/src/main/resources/db/migration"
                "/V2__create_drone_table.sql"
            ),
        ]
        for relative_path in relative_paths:
            source = source_root / relative_path
            target = target_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


if __name__ == "__main__":
    unittest.main()
