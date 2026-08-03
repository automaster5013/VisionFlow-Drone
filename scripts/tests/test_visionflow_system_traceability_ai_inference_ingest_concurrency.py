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


class SystemTraceabilityAiInferenceIngestConcurrencyTest(
    unittest.TestCase
):
    def test_current_ai_ingest_guards_are_complete(self) -> None:
        root = SCRIPT_DIR.parent
        self.assertEqual(
            traceability.ai_inference_ingest_concurrency_policy_drift(
                root
            ),
            [],
        )

    def test_missing_session_lock_usage_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_policy_sources(root)
            service = (
                root
                / "02_backend/visionflow-api/src/main/java"
                / "com/visionflow/api/ai/service"
                / "AiInferenceEventService.java"
            )
            source = service.read_text(encoding="utf-8")
            source = source.replace(
                "requireOwnedSessionForUpdate(",
                "requireOwnedSession(",
                1,
            )
            service.write_text(source, encoding="utf-8")

            drift = (
                traceability
                .ai_inference_ingest_concurrency_policy_drift(root)
            )

        self.assertIn(
            "missing-token:event-service:"
            "sessionCorrelationGuard.requireOwnedSessionForUpdate(",
            drift,
        )
        self.assertIn(
            "ordering:event-service:"
            "session-lock-before-idempotency-and-insert",
            drift,
        )

    def copy_policy_sources(self, target_root: Path) -> None:
        source_root = SCRIPT_DIR.parent
        relative_paths = [
            Path(
                "02_backend/visionflow-api/src/main/java"
                "/com/visionflow/api/flight/repository"
                "/FlightSessionRepository.java"
            ),
            Path(
                "02_backend/visionflow-api/src/main/java"
                "/com/visionflow/api/flight/service"
                "/FlightSessionCorrelationGuard.java"
            ),
            Path(
                "02_backend/visionflow-api/src/main/java"
                "/com/visionflow/api/ai/repository"
                "/AiInferenceEventRepository.java"
            ),
            Path(
                "02_backend/visionflow-api/src/main/java"
                "/com/visionflow/api/ai/service"
                "/AiInferenceEventService.java"
            ),
            Path(
                "02_backend/visionflow-api/src/main/resources"
                "/db/migration"
                "/V5__create_ai_inference_event_tables.sql"
            ),
        ]
        for relative_path in relative_paths:
            source = source_root / relative_path
            target = target_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


if __name__ == "__main__":
    unittest.main()
