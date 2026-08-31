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


class SystemTraceabilityAiSnapshotConcurrencyTest(unittest.TestCase):
    def test_current_ai_snapshot_guards_are_complete(self) -> None:
        root = SCRIPT_DIR.parent
        self.assertEqual(
            traceability.ai_snapshot_concurrency_policy_drift(root),
            [],
        )

    def test_missing_attachment_lock_usage_is_detected(self) -> None:
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
                "AiInferenceEvent event = findEventForUpdate(eventId);",
                "AiInferenceEvent event = findEvent(eventId);",
                1,
            )
            service.write_text(source, encoding="utf-8")

            drift = traceability.ai_snapshot_concurrency_policy_drift(
                root
            )

        self.assertIn(
            "usage:service:attachSnapshot-uses-event-lock",
            drift,
        )
        self.assertIn(
            "ordering:service:attachSnapshot-lock-before-storage-and-write",
            drift,
        )

    def test_missing_deletion_lock_usage_is_detected(self) -> None:
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
            delete_at = source.index(
                "public SnapshotDeletionResult deleteSnapshot("
            )
            prefix = source[:delete_at]
            suffix = source[delete_at:].replace(
                "AiInferenceEvent event = findEventForUpdate(eventId);",
                "AiInferenceEvent event = findEvent(eventId);",
                1,
            )
            service.write_text(prefix + suffix, encoding="utf-8")

            drift = traceability.ai_snapshot_concurrency_policy_drift(
                root
            )

        self.assertIn(
            "usage:service:deleteSnapshot-uses-event-lock",
            drift,
        )
        self.assertIn(
            "ordering:service:"
            "deleteSnapshot-lock-before-storage-delete-and-write",
            drift,
        )

    def copy_policy_sources(self, target_root: Path) -> None:
        source_root = SCRIPT_DIR.parent
        relative_paths = [
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
        ]
        for relative_path in relative_paths:
            source = source_root / relative_path
            target = target_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


if __name__ == "__main__":
    unittest.main()
