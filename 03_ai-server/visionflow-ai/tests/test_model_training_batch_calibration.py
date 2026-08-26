from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

from app.model_dataset_intake import build_dataset_intake_report
from app.model_training_batch_calibration import (
    AUTOBATCH_MEMORY_FRACTION,
    AUTOBATCH_METHOD,
    AUTOBATCH_SYMBOL,
    CALIBRATED_NEXT_ACTION,
    CALIBRATED_STATUS,
    CPU_NEXT_ACTION,
    CPU_STATUS,
    PLAN_UPDATE_NEXT_ACTION,
    PLAN_UPDATE_STATUS,
    TRAINING_BATCH_CALIBRATION_CONTRACT_ID,
    TrainingBatchCalibrationError,
    build_training_batch_calibration_report,
    write_training_batch_calibration_report,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "config/training-batch-calibration-v1.schema.json"
GPU_TEST_PATH = Path(__file__).with_name("test_model_training_gpu_preflight.py")


def _load_gpu_test_module() -> object:
    spec = importlib.util.spec_from_file_location(
        "visionflow_training_gpu_preflight_test_fixture",
        GPU_TEST_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("GPU preflight test fixture를 불러올 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gpu_test = _load_gpu_test_module()


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


class _CalibrationCuda:
    def __init__(
        self,
        *,
        device_name: str = "VisionFlow Fake GPU",
        peak_increase: bool = True,
    ) -> None:
        self.device_name = device_name
        self.allocated = 256 * 1024**2
        self.reserved = 512 * 1024**2
        self.peak_allocated = self.allocated
        self.peak_reserved = self.reserved
        self.peak_increase = peak_increase

    def is_available(self) -> bool:
        return True

    def device_count(self) -> int:
        return 1

    def get_device_properties(self, index: int) -> object:
        if index != 0:
            raise RuntimeError("invalid device")

        class Properties:
            name = self.device_name
            total_memory = 8 * 1024**3
            major = 8
            minor = 9

        return Properties()

    def mem_get_info(self, index: int) -> tuple[int, int]:
        if index != 0:
            raise RuntimeError("invalid device")
        return 6 * 1024**3, 8 * 1024**3

    def memory_allocated(self, index: int) -> int:
        if index != 0:
            raise RuntimeError("invalid device")
        return self.allocated

    def memory_reserved(self, index: int) -> int:
        if index != 0:
            raise RuntimeError("invalid device")
        return self.reserved

    def reset_peak_memory_stats(self, index: int) -> None:
        if index != 0:
            raise RuntimeError("invalid device")
        self.peak_allocated = self.allocated
        self.peak_reserved = self.reserved

    def max_memory_allocated(self, index: int) -> int:
        if index != 0:
            raise RuntimeError("invalid device")
        return self.peak_allocated

    def max_memory_reserved(self, index: int) -> int:
        if index != 0:
            raise RuntimeError("invalid device")
        return self.peak_reserved

    def synchronize(self, index: int) -> None:
        if index != 0:
            raise RuntimeError("invalid device")

    def profile_graph(self) -> None:
        if self.peak_increase:
            self.peak_allocated = 2 * 1024**3
            self.peak_reserved = 3 * 1024**3


class _CalibrationTorch:
    __version__ = "2.9.0+cu128"

    class version:
        cuda = "12.8"

    class backends:
        class cudnn:
            benchmark = False

    def __init__(
        self,
        *,
        device_name: str = "VisionFlow Fake GPU",
        peak_increase: bool = True,
    ) -> None:
        self.cuda = _CalibrationCuda(
            device_name=device_name,
            peak_increase=peak_increase,
        )


class _InnerModel:
    task = "detect"


class _CalibrationYolo:
    def __init__(self, names: dict[int, str]) -> None:
        self.task = "detect"
        self.names = names
        self.model = _InnerModel()
        self.device: str | None = None
        self.train_called = False

    def to(self, device: str) -> _CalibrationYolo:
        self.device = device
        return self

    def train(self, **_kwargs: object) -> None:
        self.train_called = True
        raise AssertionError("full training must never run in calibration")


class ModelTrainingBatchCalibrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = gpu_test.ModelTrainingGpuPreflightTest(methodName="runTest")
        self.fixture.setUp()
        self.root = self.fixture.root
        self.plan_path = self.fixture.plan_path
        self.intake_path = self.fixture.receipt_path
        self.preflight_path = (
            self.root / "output/training-gpu-preflight/training-ready.json"
        )
        self.preflight_path.parent.mkdir(parents=True)

    def tearDown(self) -> None:
        self.fixture.tearDown()

    def _prepare(self, *, stage: str = "VISDRONE_S1") -> None:
        self.fixture._write_plan(stage=stage)
        extra_image = (
            self.fixture.dataset / "images/train/train-b/frame.jpg"
        )
        extra_label = (
            self.fixture.dataset / "labels/train/train-b/frame.txt"
        )
        extra_image.parent.mkdir(parents=True, exist_ok=True)
        extra_label.parent.mkdir(parents=True, exist_ok=True)
        extra_image.write_bytes(b"second-train-image")
        extra_label.write_text(
            "".join(
                f"{index % 10} 0.5 0.5 0.01 0.01\n"
                for index in range(25)
            ),
            encoding="utf-8",
        )
        manifest = json.loads(
            self.fixture.split_manifest_path.read_text(encoding="utf-8")
        )
        if not any(
            item.get("sequenceId") == "train-b"
            for item in manifest["sequences"]
        ):
            manifest["sequences"].append(
                {
                    "sequenceId": "train-b",
                    "sourceVideoFile": "train-b.mp4",
                    "sourceVideoSha256": "d" * 64,
                    "split": "TRAIN",
                    "imageRoots": ["images/train/train-b"],
                }
            )
        self.fixture.split_manifest_path.write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )
        intake = build_dataset_intake_report(
            root=self.root,
            plan_path=self.plan_path,
            ultralytics_version="8.4.0",
            image_probe=lambda _path: (100, 100),
        )
        self.intake_path.write_text(json.dumps(intake), encoding="utf-8")
        names = (
            gpu_test.COCO_NAMES
            if stage == "VISDRONE_S1"
            else gpu_test.VISDRONE_NAMES
        )
        preflight = self.fixture._build(
            confirm_gpu_probe=True,
            torch_provider=lambda: gpu_test._FakeTorch(),
            yolo_factory=lambda _path: gpu_test._FakeYolo(names),
        )
        self.preflight_path.write_text(json.dumps(preflight), encoding="utf-8")

    def _build(self, **kwargs: object) -> dict[str, object]:
        return build_training_batch_calibration_report(
            root=self.root,
            plan_path=self.plan_path,
            intake_receipt_path=self.intake_path,
            preflight_receipt_path=self.preflight_path,
            ultralytics_version="8.4.0",
            image_probe=lambda _path: (100, 100),
            **kwargs,
        )

    def _gpu_build(
        self,
        *,
        recommended: int = 2,
        torch_module: _CalibrationTorch | None = None,
        names: dict[int, str] | None = None,
    ) -> tuple[dict[str, object], dict[str, object], _CalibrationYolo]:
        fake_torch = torch_module or _CalibrationTorch()
        model = _CalibrationYolo(names or gpu_test.COCO_NAMES)
        observed: dict[str, object] = {}

        def probe(inner: object, **kwargs: object) -> int:
            observed["inner"] = inner
            observed.update(kwargs)
            fake_torch.cuda.profile_graph()
            return recommended

        report = self._build(
            confirm_gpu_batch_calibration=True,
            torch_provider=lambda: fake_torch,
            yolo_factory=lambda _path: model,
            batch_probe=probe,
        )
        return report, observed, model

    def test_cpu_check_only_relocks_evidence_without_runtime_imports(self) -> None:
        self._prepare()
        before = set(sys.modules)
        provider_called = False

        def forbidden_provider() -> object:
            nonlocal provider_called
            provider_called = True
            raise AssertionError("GPU provider must not run")

        report = self._build(torch_provider=forbidden_provider)
        imported = set(sys.modules) - before
        self.assertFalse(provider_called)
        self.assertFalse({"torch", "ultralytics"} & imported)
        self.assertEqual(
            report["contractId"],
            TRAINING_BATCH_CALIBRATION_CONTRACT_ID,
        )
        self.assertEqual(report["status"], CPU_STATUS)
        self.assertEqual(report["nextAction"], CPU_NEXT_ACTION)
        self.assertEqual(report["dataset"]["maximumObjectsPerImage"], 25)
        self.assertIsNone(report["calibration"]["recommendedBatch"])
        self.assertFalse(report["safeguards"]["gpuAccessed"])

    def test_confirmed_gpu_calibration_uses_official_autobatch_contract(self) -> None:
        self._prepare()
        report, observed, model = self._gpu_build()
        self.assertEqual(report["status"], CALIBRATED_STATUS)
        self.assertEqual(report["nextAction"], CALIBRATED_NEXT_ACTION)
        self.assertEqual(report["calibration"]["method"], AUTOBATCH_METHOD)
        self.assertEqual(report["calibration"]["symbol"], AUTOBATCH_SYMBOL)
        self.assertEqual(observed["batch"], AUTOBATCH_MEMORY_FRACTION)
        self.assertEqual(observed["imgsz"], 1280)
        self.assertEqual(observed["max_num_obj"], 25)
        self.assertEqual(observed["dataset_size"], 2)
        self.assertIs(observed["inner"], model.model)
        self.assertEqual(model.device, "cuda:0")
        self.assertFalse(model.train_called)
        self.assertFalse(report["safeguards"]["trainingExecuted"])
        self.assertFalse(report["safeguards"]["optimizerStepExecuted"])
        self.assertFalse(report["safeguards"]["weightsPersisted"])
        self.assertTrue(report["safeguards"]["trainingGraphProfiled"])

    def test_recommended_batch_mismatch_requires_plan_update_without_mutation(self) -> None:
        self._prepare()
        before = self.plan_path.read_bytes()
        report, _observed, _model = self._gpu_build(recommended=1)
        self.assertEqual(report["status"], PLAN_UPDATE_STATUS)
        self.assertEqual(report["nextAction"], PLAN_UPDATE_NEXT_ACTION)
        self.assertFalse(
            report["calibration"]["planBatchMatchesRecommendation"]
        )
        self.assertEqual(self.plan_path.read_bytes(), before)
        self.assertFalse(report["safeguards"]["planMutated"])

    def test_cpu_only_preflight_and_tampered_preflight_are_rejected(self) -> None:
        self._prepare()
        receipt = json.loads(self.preflight_path.read_text(encoding="utf-8"))
        receipt["runtime"]["mode"] = "CPU_CHECK_ONLY"
        receipt["preflightReceiptSha256"] = _canonical_sha(
            receipt,
            "preflightReceiptSha256",
        )
        self.preflight_path.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaisesRegex(TrainingBatchCalibrationError, "GPU probe"):
            self._build()

        self._prepare()
        receipt = json.loads(self.preflight_path.read_text(encoding="utf-8"))
        receipt["runtime"]["deviceName"] = "tampered"
        self.preflight_path.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaisesRegex(TrainingBatchCalibrationError, "ReceiptSha256"):
            self._build()

    def test_runtime_mismatch_and_cudnn_benchmark_are_rejected(self) -> None:
        self._prepare()
        with self.assertRaisesRegex(TrainingBatchCalibrationError, "deviceName"):
            self._gpu_build(
                torch_module=_CalibrationTorch(device_name="Different GPU")
            )
        fake_torch = _CalibrationTorch()
        fake_torch.backends.cudnn.benchmark = True
        with self.assertRaisesRegex(TrainingBatchCalibrationError, "benchmark=false"):
            self._gpu_build(torch_module=fake_torch)

    def test_autobatch_fallback_and_invalid_recommendation_are_rejected(self) -> None:
        self._prepare()
        with self.assertRaisesRegex(TrainingBatchCalibrationError, "fallback"):
            self._gpu_build(
                torch_module=_CalibrationTorch(peak_increase=False)
            )
        with self.assertRaisesRegex(TrainingBatchCalibrationError, "안전 범위"):
            self._gpu_build(recommended=3)

    def test_parent_class_identity_mismatch_is_rejected(self) -> None:
        self._prepare(stage="VISIONFLOW_S2")
        with self.assertRaisesRegex(TrainingBatchCalibrationError, "identity"):
            self._gpu_build(names=gpu_test.COCO_NAMES)

    def test_schema_locks_statuses_method_and_no_training_boundary(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        properties = schema["properties"]
        self.assertEqual(
            properties["status"]["enum"],
            [CPU_STATUS, CALIBRATED_STATUS, PLAN_UPDATE_STATUS],
        )
        calibration = properties["calibration"]["properties"]
        self.assertEqual(calibration["method"]["const"], AUTOBATCH_METHOD)
        self.assertEqual(
            calibration["memoryFraction"]["const"],
            AUTOBATCH_MEMORY_FRACTION,
        )
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

    def test_output_is_atomic_and_paths_outside_root_are_rejected(self) -> None:
        self._prepare()
        report = self._build()
        output = "output/training-batch-calibration/s1-check.json"
        target = write_training_batch_calibration_report(
            self.root,
            output,
            report,
        )
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), report)
        with self.assertRaisesRegex(TrainingBatchCalibrationError, "덮어쓰지"):
            write_training_batch_calibration_report(self.root, output, report)
        with self.assertRaisesRegex(TrainingBatchCalibrationError, "root 밖"):
            write_training_batch_calibration_report(
                self.root,
                "../outside.json",
                report,
            )


if __name__ == "__main__":
    unittest.main()
