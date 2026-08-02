from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import visionflow_system_traceability_audit as traceability


class SystemTraceabilitySessionCorrelationTest(unittest.TestCase):
    def test_current_external_ingress_paths_are_guarded(self) -> None:
        root = SCRIPT_DIR.parent

        self.assertEqual(
            traceability.session_correlation_policy_drift(root),
            [],
        )

    def test_missing_ai_event_guard_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            api_root = (
                root
                / "02_backend"
                / "visionflow-api"
                / "src"
                / "main"
                / "java"
                / "com"
                / "visionflow"
                / "api"
            )
            files = {
                api_root
                / "flight"
                / "service"
                / "FlightSessionCorrelationGuard.java": """
                    findById(normalizedSessionId)
                    Objects.equals(session.getDroneId(), droneId)
                    requireOptionalOwnedSession(
                """,
                api_root
                / "flight"
                / "exception"
                / "FlightSessionDroneMismatchException.java": (
                    "FLIGHT_SESSION_DRONE_MISMATCH"
                ),
                api_root
                / "drone"
                / "service"
                / "DroneService.java": """
                    sessionCorrelationGuard.requireOptionalOwnedSession(
                    drone.updateTelemetry(
                """,
                api_root
                / "ai"
                / "service"
                / "AiInferenceEventService.java": """
                    eventRepository
                    .findBySourceIdAndSessionIdAndFrameIndex(
                """,
            }
            for path, content in files.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            drift = traceability.session_correlation_policy_drift(root)

        self.assertIn(
            "missing-token:ai-event:sessionCorrelationGuard.requireOwnedSession(",
            drift,
        )
        self.assertIn(
            "ordering:ai-event:guard-before-persistence",
            drift,
        )


if __name__ == "__main__":
    unittest.main()
