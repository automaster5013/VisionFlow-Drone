from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import unittest
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from app.model_training_execution import (
    READY_NEXT_ACTION,
    READY_STATUS,
    S1_TRAINING_EXECUTION_CONTRACT_ID,
    TRAINED_NEXT_ACTION,
    TRAINED_STATUS,
    S1TrainingExecutionError,
    build_s1_training_execution_report,
    write_s1_training_execution_report,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "config/training-execution-v1.schema.json"
CALIBRATION_TEST_PATH = Path(__file__).with_name(
    "test_model_training_batch_calibration.py"
)


def _load_calibration_test_module() -> object:
    spec = importlib.util.spec_from_file_location(
        "visionflow_training_batch_calibration_test_fixture",
        CALIBRATION_TEST_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("batch calibration test fixture를 불러올 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


calibration_test = _load_calibration_test_module()


def _canonical_sha(value: dict[str, object], receipt_field: str) -> str:
    payload = dict(value)
    payload.pop(receipt_field, None)
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


class _TrainedModel:
    task = "detect"
    names = calibration_test.gpu_test.VISDRONE_NAMES


class _TrainingModel:
    task = "detect"
    names = calibration_test.gpu_test.COCO_NAMES

    def __init__(
        self,
        *,
        failure: Exception | None = None,
        mutate: Callable[[], None] | None = None,
    ) -> None:
        self.failure = failure
        self.mutate = mutate
        self.train_calls: list[dict[str, object]] = []

    def train(self, **kwargs: object) -> object:
        self.train_calls.append(dict(kwargs))
        run_dir = Path(str(kwargs["project"])) / str(kwargs["name"])
        weights = run_dir / "weights"
        weights.mkdir(parents=True)
        (weights / "best.pt").write_bytes(b"trained-best-weight")
        (weights / "last.pt").write_bytes(b"trained-last-weight")
        if self.mutate is not None:
            self.mutate()
        if self.failure is not None:
            raise self.failure
        return SimpleNamespace(save_dir=run_dir)


class ModelTrainingExecutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = calibration_test.ModelTrainingBatchCalibrationTest(
            methodName="runTest"
        )
        self.fixture.setUp()
        self.fixture._prepare(stage="VISDRONE_S1")
        calibration, _observed, _model = self.fixture._gpu_build(recommended=2)
        self.root = self.fixture.root
        self.plan_path = self.fixture.plan_path
        self.intake_path = self.fixture.intake_path
        self.preflight_path = self.fixture.preflight_path
        self.calibration_path = (
            self.root / "output/training-batch-calibration/s1-gpu.json"
        )
        self.calibration_path.parent.mkdir(parents=True)
        self.calibration_path.write_text(
            json.dumps(calibration),
            encoding="utf-8",
        )
        self.run_name = "visdrone-s1-test"

    def tearDown(self) -> None:
        self.fixture.tearDown()

    def _build(self, **kwargs: object) -> dict[str, object]:
        return build_s1_training_execution_report(
            root=self.root,
            plan_path=self.plan_path,
            intake_receipt_path=self.intake_path,
            preflight_receipt_path=self.preflight_path,
            calibration_receipt_path=self.calibration_path,
            run_name=self.run_name,
            ultralytics_version="8.4.0",
            image_probe=lambda _path: (100, 100),
            **kwargs,
        )

    def _runtime_build(
        self,
        *,
        model: _TrainingModel | None = None,
        torch_module: object | None = None,
    ) -> tuple[dict[str, object], _TrainingModel]:
        training_model = model or _TrainingModel()

        def factory(path: str) -> object:
            if Path(path).name == "yolo26m.pt":
                return training_model
            return _TrainedModel()

        moments = iter(
            (
                datetime(2026, 8, 27, 1, 0, tzinfo=UTC),
                datetime(2026, 8, 27, 2, 0, tzinfo=UTC),
            )
        )
        report = self._build(
            confirm_s1_training=True,
            torch_provider=lambda: torch_module
            or calibration_test._CalibrationTorch(),
            yolo_factory=factory,
            clock=lambda: next(moments),
        )
        return report, training_model

    def test_check_only_relocks_all_evidence_without_runtime_imports(self) -> None:
        before = set(sys.modules)
        provider_called = False

        def forbidden_provider() -> object:
            nonlocal provider_called
            provider_called = True
            raise AssertionError("runtime provider must not run")

        report = self._build(torch_provider=forbidden_provider)
        imported = set(sys.modules) - before
        self.assertFalse(provider_called)
        self.assertFalse({"torch", "ultralytics"} & imported)
        self.assertEqual(report["contractId"], S1_TRAINING_EXECUTION_CONTRACT_ID)
        self.assertEqual(report["status"], READY_STATUS)
        self.assertEqual(report["nextAction"], READY_NEXT_ACTION)
        self.assertFalse(report["approval"]["explicitS1TrainingConfirmed"])
        self.assertFalse(report["safeguards"]["trainingExecuted"])
        self.assertIsNone(report["artifacts"]["canonicalWeight"])

    def test_explicit_training_calls_yolo_once_and_promotes_named_weight(self) -> None:
        report, model = self._runtime_build()
        self.assertEqual(report["status"], TRAINED_STATUS)
        self.assertEqual(report["nextAction"], TRAINED_NEXT_ACTION)
        self.assertEqual(len(model.train_calls), 1)
        arguments = model.train_calls[0]
        self.assertEqual(arguments["batch"], 2)
        self.assertEqual(arguments["imgsz"], 1280)
        self.assertEqual(arguments["optimizer"], "MuSGD")
        self.assertTrue(arguments["deterministic"])
        self.assertFalse(arguments["exist_ok"])
        self.assertFalse(arguments["resume"])
        self.assertEqual(arguments["name"], self.run_name)
        canonical = self.root / "models/yolo26m-visdrone-s1-best.pt"
        self.assertTrue(canonical.is_file())
        self.assertEqual(
            report["artifacts"]["canonicalWeight"]["sha256"],
            report["artifacts"]["bestCheckpoint"]["sha256"],
        )
        self.assertTrue(report["safeguards"]["trainingExecuted"])
        self.assertFalse(report["safeguards"]["manifestMaterialized"])
        self.assertFalse(report["safeguards"]["evaluationMeasured"])
        self.assertFalse(report["safeguards"]["activationEligible"])

    def test_stale_or_nonapproved_calibration_is_rejected(self) -> None:
        receipt = json.loads(self.calibration_path.read_text(encoding="utf-8"))
        receipt["status"] = "PLAN_BATCH_UPDATE_REQUIRED"
        receipt["nextAction"] = "UPDATE_PLAN_BATCH_AND_RERUN_PHASE2B6A_6B_6C"
        receipt["calibration"]["planBatchMatchesRecommendation"] = False
        receipt["calibrationReceiptSha256"] = _canonical_sha(
            receipt,
            "calibrationReceiptSha256",
        )
        self.calibration_path.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaisesRegex(S1TrainingExecutionError, "승인 대기"):
            self._build()

    def test_s2_and_unsafe_run_names_are_rejected(self) -> None:
        receipt = json.loads(self.calibration_path.read_text(encoding="utf-8"))
        receipt["stage"] = "VISIONFLOW_S2"
        receipt["calibrationReceiptSha256"] = _canonical_sha(
            receipt,
            "calibrationReceiptSha256",
        )
        self.calibration_path.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaisesRegex(S1TrainingExecutionError, "VISDRONE_S1"):
            self._build()
        with self.assertRaisesRegex(S1TrainingExecutionError, "runName"):
            build_s1_training_execution_report(
                root=self.root,
                plan_path=self.plan_path,
                intake_receipt_path=self.intake_path,
                preflight_receipt_path=self.preflight_path,
                calibration_receipt_path=self.calibration_path,
                run_name="../escape",
                ultralytics_version="8.4.0",
                image_probe=lambda _path: (100, 100),
            )

    def test_runtime_mismatch_and_training_failure_do_not_promote_weight(self) -> None:
        with self.assertRaisesRegex(S1TrainingExecutionError, "deviceName"):
            self._runtime_build(
                torch_module=calibration_test._CalibrationTorch(
                    device_name="Different GPU"
                )
            )
        failing_model = _TrainingModel(failure=RuntimeError("synthetic failure"))
        with self.assertRaisesRegex(S1TrainingExecutionError, r"train\(\)이 실패"):
            self._runtime_build(model=failing_model)
        self.assertFalse(
            (self.root / "models/yolo26m-visdrone-s1-best.pt").exists()
        )

    def test_input_mutation_during_training_blocks_promotion(self) -> None:
        original = self.plan_path.read_text(encoding="utf-8")

        def mutate() -> None:
            changed = json.loads(original)
            changed["planVersion"] = 2
            self.plan_path.write_text(json.dumps(changed), encoding="utf-8")

        with self.assertRaises(ValueError):
            self._runtime_build(model=_TrainingModel(mutate=mutate))
        self.assertFalse(
            (self.root / "models/yolo26m-visdrone-s1-best.pt").exists()
        )

    def test_existing_run_weight_and_receipt_are_never_overwritten(self) -> None:
        run_dir = self.root / "output/training-runs" / self.run_name
        run_dir.mkdir(parents=True)
        with self.assertRaisesRegex(S1TrainingExecutionError, "덮어쓰지"):
            self._build()
        run_dir.rmdir()
        canonical = self.root / "models/yolo26m-visdrone-s1-best.pt"
        canonical.write_bytes(b"existing")
        with self.assertRaisesRegex(S1TrainingExecutionError, "덮어쓰지"):
            self._build()

        report_path = self.root / "output/training-execution/s1.json"
        report = {"status": READY_STATUS}
        written = write_s1_training_execution_report(
            self.root,
            "output/training-execution/s1.json",
            report,
        )
        self.assertEqual(json.loads(written.read_text(encoding="utf-8")), report)
        with self.assertRaisesRegex(S1TrainingExecutionError, "덮어쓰지"):
            write_s1_training_execution_report(
                self.root,
                "output/training-execution/s1.json",
                report,
            )
        self.assertEqual(written, report_path)

    def test_schema_locks_s1_only_explicit_boundary_and_no_manifest(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        properties = schema["properties"]
        self.assertEqual(
            properties["contractId"]["const"],
            S1_TRAINING_EXECUTION_CONTRACT_ID,
        )
        self.assertEqual(properties["stage"]["const"], "VISDRONE_S1")
        self.assertEqual(
            properties["model"]["$ref"],
            "#/$defs/model",
        )
        safeguards = schema["$defs"]["safeguards"]["properties"]
        self.assertFalse(safeguards["manifestMaterialized"]["const"])
        self.assertFalse(safeguards["activationEligible"]["const"])
        self.assertFalse(safeguards["evaluationMeasured"]["const"])
        approval = properties["approval"]["properties"]
        self.assertFalse(approval["resumeAllowed"]["const"])
        self.assertFalse(approval["overwriteAllowed"]["const"])


if __name__ == "__main__":
    unittest.main()
