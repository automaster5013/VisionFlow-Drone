from __future__ import annotations

import json
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
AI_ROOT = REPOSITORY_ROOT / "03_ai-server/visionflow-ai"
MODULE_PATH = AI_ROOT / "app/model_training_batch_calibration.py"
INTAKE_MODULE_PATH = AI_ROOT / "app/model_dataset_intake.py"
SCHEMA_PATH = AI_ROOT / "config/training-batch-calibration-v1.schema.json"
INTAKE_SCHEMA_PATH = AI_ROOT / "config/dataset-intake-report-v1.schema.json"
RUNNER_PATH = (
    REPOSITORY_ROOT
    / "scripts/run-visionflow-model-training-batch-calibration.bat"
)


class VisionFlowModelTrainingBatchCalibrationScriptTest(unittest.TestCase):
    def test_host_runner_invokes_calibration_module_without_docker(self) -> None:
        source = RUNNER_PATH.read_text(encoding="utf-8")
        self.assertIn("03_ai-server\\visionflow-ai", source)
        self.assertIn(
            "python -B -m app.model_training_batch_calibration %*",
            source,
        )
        self.assertNotIn("docker", source.lower())

    def test_schema_locks_method_fraction_statuses_and_safeguards(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        properties = schema["properties"]
        self.assertEqual(
            properties["contractId"]["const"],
            "visionflow.phase2b6.training-batch-calibration",
        )
        self.assertEqual(
            properties["status"]["enum"],
            [
                "READY_FOR_EXPLICIT_GPU_BATCH_CALIBRATION",
                "READY_FOR_TRAINING_APPROVAL",
                "PLAN_BATCH_UPDATE_REQUIRED",
            ],
        )
        calibration = properties["calibration"]["properties"]
        self.assertEqual(
            calibration["method"]["const"],
            "ULTRALYTICS_CHECK_TRAIN_BATCH_SIZE",
        )
        self.assertEqual(calibration["memoryFraction"]["const"], 0.6)
        safeguards = properties["safeguards"]["properties"]
        for field in (
            "trainingExecuted",
            "yoloTrainCalled",
            "optimizerStepExecuted",
            "weightsPersisted",
            "planMutated",
            "dataMutated",
            "dockerAccessed",
        ):
            self.assertFalse(safeguards[field]["const"])

    def test_gpu_imports_are_lazy_and_full_training_is_never_called(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        lowered = source.lower()
        self.assertNotIn("import torch", lowered)
        self.assertNotIn("from ultralytics import", lowered)
        self.assertNotIn(".train(", lowered)
        self.assertNotIn("subprocess", lowered)
        self.assertNotIn("docker ", lowered)
        self.assertIn('importlib.import_module("torch")', source)
        self.assertIn(
            'importlib.import_module("ultralytics.utils.autobatch")',
            source,
        )
        self.assertIn("confirm_gpu_batch_calibration", source)
        self.assertIn("max_num_obj=maximum_objects_per_image", source)
        self.assertIn("dataset_size=train_image_count", source)

    def test_intake_locks_dense_scene_autobatch_evidence(self) -> None:
        module_source = INTAKE_MODULE_PATH.read_text(encoding="utf-8")
        intake_schema = json.loads(
            INTAKE_SCHEMA_PATH.read_text(encoding="utf-8")
        )
        self.assertIn("maximumObjectsPerImage", module_source)
        split_evidence = intake_schema["$defs"]["splitEvidence"]
        self.assertIn("maximumObjectsPerImage", split_evidence["required"])
        self.assertEqual(
            split_evidence["properties"]["maximumObjectsPerImage"]["minimum"],
            1,
        )

    def test_existing_preflight_and_ignore_policy_remain_separate(self) -> None:
        preflight = AI_ROOT / "app/model_training_gpu_preflight.py"
        self.assertTrue(preflight.is_file())
        ai_ignore = (AI_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("datasets/*", ai_ignore)
        self.assertIn("models/*.pt", ai_ignore)
        self.assertIn("output/*", ai_ignore)


if __name__ == "__main__":
    unittest.main()
