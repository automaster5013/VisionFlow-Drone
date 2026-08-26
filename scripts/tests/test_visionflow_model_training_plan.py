from __future__ import annotations

import json
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
AI_ROOT = REPOSITORY_ROOT / "03_ai-server/visionflow-ai"
RUNNER_PATH = REPOSITORY_ROOT / "scripts/run-visionflow-model-training-plan.bat"


class VisionFlowModelTrainingPlanScriptTest(unittest.TestCase):
    def test_host_runner_invokes_module_and_forwards_arguments_without_docker(self) -> None:
        source = RUNNER_PATH.read_text(encoding="utf-8")
        self.assertIn("03_ai-server\\visionflow-ai", source)
        self.assertIn("python -B -m app.model_training_plan %*", source)
        self.assertNotIn("docker", source.lower())

    def test_contract_schema_and_both_templates_are_valid_json(self) -> None:
        paths = (
            AI_ROOT / "config/transfer-training-plan-v1.schema.json",
            AI_ROOT / "config/visdrone-s1-training.plan.template.json",
            AI_ROOT / "config/visdrone-s2-training.plan.template.json",
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertTrue(path.is_file())
                self.assertIsInstance(
                    json.loads(path.read_text(encoding="utf-8")), dict
                )

    def test_planner_has_no_training_gpu_or_docker_execution(self) -> None:
        source = (AI_ROOT / "app/model_training_plan.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("from ultralytics import", source)
        self.assertNotIn("import torch", source)
        self.assertNotIn(".train(", source)
        self.assertNotIn("docker ", source.lower())


if __name__ == "__main__":
    unittest.main()
