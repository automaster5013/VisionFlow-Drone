from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import visionflow_system_traceability_audit as traceability


class SystemTraceabilityDemoScenarioLifecycleTest(unittest.TestCase):
    def test_current_demo_scenario_guards_are_complete(self) -> None:
        root = SCRIPT_DIR.parent
        self.assertEqual(
            traceability
            .demo_scenario_lifecycle_concurrency_policy_drift(root),
            [],
        )

    def test_missing_escalate_lock_usage_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backend = (
                root
                / "02_backend/visionflow-api/src/main/java"
                / "com/visionflow/api/demo"
            )
            repository = (
                backend / "repository/DemoScenarioRepository.java"
            )
            service = backend / "service/DemoScenarioService.java"
            repository.parent.mkdir(parents=True, exist_ok=True)
            service.parent.mkdir(parents=True, exist_ok=True)
            repository.write_text(
                """
                @Lock(LockModeType.PESSIMISTIC_WRITE)
                LockModeType.PESSIMISTIC_WRITE
                findByIdForUpdate(
                """,
                encoding="utf-8",
            )
            service.write_text(
                """
                public DemoScenarioResponse find(String scenarioId) {
                    findScenario(scenarioId)
                }
                @Transactional
                public DemoScenarioResponse detect(String scenarioId) {
                    findScenarioForUpdate(scenarioId)
                    inferenceEventService.create(
                }
                @Transactional
                public DemoScenarioResponse escalate(String scenarioId) {
                    findScenario(scenarioId)
                    lockIncidentForDemoEscalation(incidentId)
                }
                @Transactional
                public DemoScenarioResponse resolve(String scenarioId) {
                    findScenarioForUpdate(scenarioId)
                    alertService.resolve(
                }
                @Transactional
                public DemoScenarioResponse complete(String scenarioId) {
                    findScenarioForUpdate(scenarioId)
                    flightSessionService.complete(
                }
                scenarioRepository.findById(normalized)
                """,
                encoding="utf-8",
            )

            drift = (
                traceability
                .demo_scenario_lifecycle_concurrency_policy_drift(root)
            )

        self.assertIn(
            "usage:service:lock-detect-escalate-resolve-complete",
            drift,
        )
        self.assertIn(
            "ordering:service:escalate-lock-before-mutation",
            drift,
        )


if __name__ == "__main__":
    unittest.main()
