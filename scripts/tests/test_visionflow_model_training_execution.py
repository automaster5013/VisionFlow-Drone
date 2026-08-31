from __future__ import annotations

import json
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
AI_ROOT = REPOSITORY_ROOT / "03_ai-server/visionflow-ai"
MODULE_PATH = AI_ROOT / "app/model_training_execution.py"
SCHEMA_PATH = AI_ROOT / "config/training-execution-v1.schema.json"
RUNNER_PATH = REPOSITORY_ROOT / "scripts/run-visionflow-model-training-execution.bat"


class VisionFlowModelTrainingExecutionScriptTest(unittest.TestCase):
    def test_host_runner_invokes_s1_execution_module_without_docker(self) -> None:
        source = RUNNER_PATH.read_text(encoding="utf-8")
        self.assertIn("03_ai-server\\visionflow-ai", source)
        self.assertIn("python -B -m app.model_training_execution %*", source)
        self.assertNotIn("docker", source.lower())

    def test_source_has_lazy_runtime_and_explicit_training_boundary(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        lowered = source.lower()
        self.assertNotIn("import torch", lowered)
        self.assertNotIn("from ultralytics import", lowered)
        self.assertNotIn("subprocess", lowered)
        self.assertNotIn("docker ", lowered)
        self.assertIn('importlib.import_module("torch")', source)
        self.assertIn('importlib.import_module("ultralytics")', source)
        self.assertIn("confirm_s1_training", source)
        self.assertIn('"exist_ok": False', source)
        self.assertIn('"resume": False', source)
        self.assertEqual(source.count("train(**controlled_arguments)"), 1)
        self.assertIn(
            "with _working_directory(dataset_working_directory):",
            source,
        )
        self.assertIn("training data.yaml", source)

    def test_schema_locks_s1_statuses_artifact_name_and_evaluation_boundary(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        properties = schema["properties"]
        self.assertEqual(properties["stage"]["const"], "VISDRONE_S1")
        self.assertEqual(
            properties["status"]["enum"],
            [
                "READY_FOR_EXPLICIT_S1_TRAINING",
                "TRAINED_AWAITING_EVALUATION",
            ],
        )
        model = schema["$defs"]["model"]["properties"]
        self.assertEqual(model["parentFileName"]["const"], "yolo26m.pt")
        self.assertEqual(
            model["outputFileName"]["const"],
            "yolo26m-visdrone-s1-best.pt",
        )
        safeguards = schema["$defs"]["safeguards"]["properties"]
        self.assertFalse(safeguards["manifestMaterialized"]["const"])
        self.assertFalse(safeguards["evaluationMeasured"]["const"])
        self.assertFalse(safeguards["activationEligible"]["const"])

    def test_ignore_policy_keeps_datasets_weights_and_runs_out_of_git(self) -> None:
        ignore = (AI_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("datasets/*", ignore)
        self.assertIn("models/*.pt", ignore)
        self.assertIn("output/*", ignore)


if __name__ == "__main__":
    unittest.main()
