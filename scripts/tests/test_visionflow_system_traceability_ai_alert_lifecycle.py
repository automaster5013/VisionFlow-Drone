from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import visionflow_system_traceability_audit as traceability


class SystemTraceabilityAiAlertLifecycleTest(unittest.TestCase):
    def test_current_ai_alert_lifecycle_guards_are_complete(self) -> None:
        root = SCRIPT_DIR.parent
        self.assertEqual(
            traceability.ai_alert_lifecycle_concurrency_policy_drift(root),
            [],
        )

    def test_missing_resolve_lock_usage_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backend = (
                root
                / "02_backend/visionflow-api/src/main/java"
                / "com/visionflow/api/ai"
            )
            repository = backend / "repository/AiAlertRepository.java"
            service = backend / "service/AiAlertService.java"
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
                findAlertForUpdate(alertId)
                alert.acknowledge(
                alert.resolve(
                alertRepository.findById(alertId)
                """,
                encoding="utf-8",
            )

            drift = (
                traceability
                .ai_alert_lifecycle_concurrency_policy_drift(root)
            )

        self.assertIn(
            "usage:service:lock-acknowledge-resolve",
            drift,
        )


if __name__ == "__main__":
    unittest.main()
