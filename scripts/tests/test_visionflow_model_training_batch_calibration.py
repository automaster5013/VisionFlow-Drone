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
            "VISIONFLOW_BOUNDED_ULTRALYTICS_PROFILE_OPS",
        )
        self.assertEqual(
            calibration["symbol"]["const"],
            "ultralytics.utils.torch_utils.profile_ops",
        )
        self.assertEqual(calibration["memoryFraction"]["const"], 0.6)
        runtime = properties["runtime"]
        self.assertEqual(
            runtime["properties"]["candidatePolicy"]["const"],
            "POWERS_OF_TWO_UP_TO_PLANNED_BATCH",
        )
        for field in (
            "candidateBatchSizes",
            "candidateProfiles",
            "profileMemoryTargetGb",
        ):
            self.assertIn(field, runtime["required"])
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
            '"ultralytics.utils.torch_utils"',
            source,
        )
        self.assertIn("confirm_gpu_batch_calibration", source)
        self.assertIn("_bounded_candidate_batches", source)
        self.assertIn("max_num_obj=maximum_objects_per_image", source)
        self.assertIn("profileMemoryTargetGb", source)
        self.assertNotIn("check_train_batch_size", source)
        self.assertNotIn("dataset_size=train_image_count", source)

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
