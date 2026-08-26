from __future__ import annotations

import json
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
AI_ROOT = REPOSITORY_ROOT / "03_ai-server/visionflow-ai"
MODULE_PATH = AI_ROOT / "app/model_dataset_intake.py"
SCHEMA_PATH = AI_ROOT / "config/dataset-intake-report-v1.schema.json"
RUNNER_PATH = REPOSITORY_ROOT / "scripts/run-visionflow-model-dataset-intake.bat"


class VisionFlowModelDatasetIntakeScriptTest(unittest.TestCase):
    def test_host_runner_invokes_cpu_only_module_without_docker(self) -> None:
        source = RUNNER_PATH.read_text(encoding="utf-8")
        self.assertIn("03_ai-server\\visionflow-ai", source)
        self.assertIn("python -B -m app.model_dataset_intake %*", source)
        self.assertNotIn("docker", source.lower())

    def test_report_schema_is_valid_json_and_locks_contract(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            schema["properties"]["contractId"]["const"],
            "visionflow.phase2b6.dataset-intake-report",
        )
        self.assertEqual(
            schema["properties"]["dataset"]["properties"]["fingerprintMode"][
                "const"
            ],
            "full",
        )

    def test_module_has_no_training_gpu_or_docker_execution(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        lowered = source.lower()
        self.assertNotIn("from ultralytics import", lowered)
        self.assertNotIn("import torch", lowered)
        self.assertNotIn(".train(", lowered)
        self.assertNotIn("torch.cuda", lowered)
        self.assertNotIn("docker ", lowered)

    def test_large_runtime_assets_remain_ignored(self) -> None:
        ai_ignore = (AI_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("datasets/*", ai_ignore)
        self.assertIn("models/*.pt", ai_ignore)
        self.assertIn("output/*", ai_ignore)


if __name__ == "__main__":
    unittest.main()
