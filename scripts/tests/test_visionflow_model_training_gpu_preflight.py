from __future__ import annotations

import json
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
AI_ROOT = REPOSITORY_ROOT / "03_ai-server/visionflow-ai"
MODULE_PATH = AI_ROOT / "app/model_training_gpu_preflight.py"
SCHEMA_PATH = AI_ROOT / "config/training-gpu-preflight-v1.schema.json"
RUNNER_PATH = (
    REPOSITORY_ROOT / "scripts/run-visionflow-model-training-gpu-preflight.bat"
)


class VisionFlowModelTrainingGpuPreflightScriptTest(unittest.TestCase):
    def test_host_runner_invokes_preflight_module_without_docker(self) -> None:
        source = RUNNER_PATH.read_text(encoding="utf-8")
        self.assertIn("03_ai-server\\visionflow-ai", source)
        self.assertIn("python -B -m app.model_training_gpu_preflight %*", source)
        self.assertNotIn("docker", source.lower())

    def test_schema_locks_statuses_batch_boundary_and_safeguards(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        properties = schema["properties"]
        self.assertEqual(
            properties["contractId"]["const"],
            "visionflow.phase2b6.training-gpu-preflight",
        )
        self.assertEqual(
            properties["status"]["enum"],
            ["READY_FOR_GPU_PROBE", "READY_FOR_BATCH_CALIBRATION"],
        )
        self.assertEqual(
            properties["training"]["properties"]["batchStatus"]["const"],
            "PROVISIONAL",
        )
        safeguards = properties["safeguards"]["properties"]
        self.assertFalse(safeguards["trainingExecuted"]["const"])
        self.assertFalse(safeguards["batchCalibrated"]["const"])
        self.assertFalse(safeguards["dockerAccessed"]["const"])
        self.assertFalse(safeguards["dataMutated"]["const"])

    def test_gpu_imports_are_lazy_and_training_is_never_called(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        lowered = source.lower()
        self.assertNotIn("import torch", lowered)
        self.assertNotIn("from ultralytics import", lowered)
        self.assertNotIn(".train(", lowered)
        self.assertNotIn("subprocess", lowered)
        self.assertNotIn("docker ", lowered)
        self.assertIn('importlib.import_module("torch")', source)
        self.assertIn('importlib.import_module("ultralytics")', source)
        self.assertIn("confirm_gpu_probe", source)

    def test_existing_runtime_preflight_and_ignore_policy_remain_separate(self) -> None:
        runtime_preflight = AI_ROOT / "app/gpu_preflight.py"
        self.assertTrue(runtime_preflight.is_file())
        ai_ignore = (AI_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("datasets/*", ai_ignore)
        self.assertIn("models/*.pt", ai_ignore)
        self.assertIn("output/*", ai_ignore)


if __name__ == "__main__":
    unittest.main()
