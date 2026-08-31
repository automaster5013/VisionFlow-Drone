from __future__ import annotations

import json
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
AI_ROOT = REPOSITORY_ROOT / "03_ai-server/visionflow-ai"
RUNNER_PATH = REPOSITORY_ROOT / "scripts/run-visionflow-labeled-small-object-evaluation.bat"


class VisionFlowLabeledSmallObjectEvaluationScriptTest(unittest.TestCase):
    def test_host_runner_invokes_module_and_forwards_arguments_without_docker(self) -> None:
        source = RUNNER_PATH.read_text(encoding="utf-8")
        self.assertIn("03_ai-server\\visionflow-ai", source)
        self.assertIn("python -B -m app.labeled_small_object_evaluation %*", source)
        self.assertNotIn("docker", source.lower())

    def test_contract_files_exist_and_are_valid_json(self) -> None:
        paths = (
            AI_ROOT / "config/labeled-small-object-evaluation-v1.schema.json",
            AI_ROOT / "config/video-split-manifest-v1.schema.json",
            AI_ROOT / "datasets/final-heldout.split-manifest.template.json",
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertTrue(path.is_file())
                self.assertIsInstance(json.loads(path.read_text(encoding="utf-8")), dict)

    def test_evaluator_has_no_import_time_gpu_dependencies(self) -> None:
        source = (
            AI_ROOT / "app/labeled_small_object_evaluation.py"
        ).read_text(encoding="utf-8")
        prefix = source.split("def run_isolated_model", maxsplit=1)[0]
        self.assertNotIn("from ultralytics import", prefix)
        self.assertNotIn("import torch", prefix)


    def test_evaluator_supports_s1_receipt_official_split_and_explicit_gpu_gate(self) -> None:
        source = (
            AI_ROOT / "app/labeled_small_object_evaluation.py"
        ).read_text(encoding="utf-8")
        self.assertIn("--candidate-training-receipt", source)
        self.assertIn("--candidate-manifest", source)
        self.assertIn("--check-only", source)
        self.assertIn("--confirm-gpu-evaluation", source)
        self.assertIn("OFFICIAL_DATASET_SPLIT", source)
        self.assertIn("S1_TRAINING_EXECUTION_RECEIPT", source)
        self.assertIn("READY_FOR_EXPLICIT_GPU_LABELED_EVALUATION", source)


if __name__ == "__main__":
    unittest.main()
