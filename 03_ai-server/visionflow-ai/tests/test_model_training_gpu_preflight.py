from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from app.model_contract import VISDRONE_CLASS_MAPPING, sha256_file
from app.model_dataset_intake import build_dataset_intake_report
from app.model_training_gpu_preflight import (
    CPU_NEXT_ACTION,
    CPU_STATUS,
    GPU_NEXT_ACTION,
    GPU_STATUS,
    TRAINING_GPU_PREFLIGHT_CONTRACT_ID,
    TrainingGpuPreflightError,
    build_training_gpu_preflight_report,
    write_training_gpu_preflight_report,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "config/training-gpu-preflight-v1.schema.json"
VISDRONE_NAMES = {
    int(item["id"]): str(item["sourceName"])
    for item in VISDRONE_CLASS_MAPPING
}
COCO_NAMES = {
    index: name
    for index, name in enumerate(
        (
            "person", "bicycle", "car", "motorcycle", "airplane", "bus",
            "train", "truck", "boat", "traffic light", "fire hydrant",
            "stop sign", "parking meter", "bench", "bird", "cat", "dog",
            "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe",
            "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
            "skis", "snowboard", "sports ball", "kite", "baseball bat",
            "baseball glove", "skateboard", "surfboard", "tennis racket",
            "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl",
            "banana", "apple", "sandwich", "orange", "broccoli", "carrot",
            "hot dog", "pizza", "donut", "cake", "chair", "couch",
            "potted plant", "bed", "dining table", "toilet", "tv", "laptop",
            "mouse", "remote", "keyboard", "cell phone", "microwave", "oven",
            "toaster", "sink", "refrigerator", "book", "clock", "vase",
            "scissors", "teddy bear", "hair drier", "toothbrush",
        )
    )
}


def _receipt_sha(receipt: dict[str, object]) -> str:
    payload = dict(receipt)
    payload.pop("receiptSha256", None)
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


class _FakeProperties:
    name = "VisionFlow Fake GPU"
    total_memory = 8 * 1024**3
    major = 8
    minor = 9


class _FakeCuda:
    def __init__(self, *, available: bool = True, count: int = 1) -> None:
        self.available = available
        self.count = count

    def is_available(self) -> bool:
        return self.available

    def device_count(self) -> int:
        return self.count

    def get_device_properties(self, index: int) -> _FakeProperties:
        if index >= self.count:
            raise RuntimeError("invalid device")
        return _FakeProperties()

    def mem_get_info(self, index: int) -> tuple[int, int]:
        if index >= self.count:
            raise RuntimeError("invalid device")
        return 6 * 1024**3, 8 * 1024**3


class _FakeTorch:
    __version__ = "2.9.0+cu128"

    class version:
        cuda = "12.8"

    def __init__(self, *, available: bool = True, count: int = 1) -> None:
        self.cuda = _FakeCuda(available=available, count=count)


class _FakeYolo:
    def __init__(self, names: dict[int, str]) -> None:
        self.task = "detect"
        self.names = names
        self.device: str | None = None
        self.train_called = False

    def to(self, device: str) -> _FakeYolo:
        self.device = device
        return self

    def train(self, **_kwargs: object) -> None:
        self.train_called = True
        raise AssertionError("training must never run in preflight")


class ModelTrainingGpuPreflightTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repo"
        self.root.mkdir()
        (self.root / "models/manifests").mkdir(parents=True)
        (self.root / "config").mkdir()
        (self.root / "output/dataset-intake").mkdir(parents=True)
        self.dataset = self.root / "datasets/training"
        for split, sequence, content in (
            ("train", "train-a", b"train-image"),
            ("val", "val-a", b"val-image"),
            ("final-heldout", "heldout-a", b"heldout-image"),
        ):
            image = self.dataset / f"images/{split}/{sequence}/frame.jpg"
            label = self.dataset / f"labels/{split}/{sequence}/frame.txt"
            image.parent.mkdir(parents=True)
            label.parent.mkdir(parents=True)
            image.write_bytes(content)
            label.write_text(
                "".join(
                    f"{class_id} 0.5 0.5 0.01 0.01\n"
                    for class_id in range(10)
                ),
                encoding="utf-8",
            )
        self.data_yaml = self.dataset / "data.yaml"
        self.data_yaml.write_text(
            yaml.safe_dump(
                {
                    "path": ".",
                    "train": "images/train",
                    "val": "images/val",
                    "names": list(VISDRONE_NAMES.values()),
                },
                sort_keys=False,
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        self.split_manifest_path = self.dataset / "split-manifest.json"
        self.split_manifest_path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "contractId": "visionflow.phase2b4.video-split-manifest",
                    "template": False,
                    "datasetVersion": "training-v1",
                    "splitUnit": "VIDEO_SEQUENCE",
                    "adjacentFramesAcrossSplits": False,
                    "finalEvaluationExcludedFromTraining": True,
                    "sequences": [
                        {
                            "sequenceId": "train-a",
                            "sourceVideoFile": "train-a.mp4",
                            "sourceVideoSha256": "a" * 64,
                            "split": "TRAIN",
                            "imageRoots": ["images/train/train-a"],
                        },
                        {
                            "sequenceId": "val-a",
                            "sourceVideoFile": "val-a.mp4",
                            "sourceVideoSha256": "b" * 64,
                            "split": "VAL",
                            "imageRoots": ["images/val/val-a"],
                        },
                        {
                            "sequenceId": "heldout-a",
                            "sourceVideoFile": "heldout-a.mp4",
                            "sourceVideoSha256": "c" * 64,
                            "split": "FINAL_HELDOUT",
                            "imageRoots": ["images/final-heldout/heldout-a"],
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.plan_path = self.root / "config/training-plan.json"
        self.receipt_path = (
            self.root / "output/dataset-intake/training-ready.json"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _relative(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def _write_plan(
        self,
        *,
        stage: str = "VISDRONE_S1",
        device: str = "0",
    ) -> dict[str, object]:
        if stage == "VISDRONE_S1":
            parent_path = self.root / "models/yolo26m.pt"
            parent_path.write_bytes(b"coco-parent")
            parent: dict[str, object] = {
                "filePath": self._relative(parent_path),
                "fileName": "yolo26m.pt",
                "sha256": sha256_file(parent_path),
            }
            output_name = "yolo26m-visdrone-s1-best.pt"
            source_datasets = ["VISDRONE2019_DET"]
        else:
            parent_path = self.root / "models/yolo26m-visdrone-s1-best.pt"
            parent_path.write_bytes(b"s1-parent")
            manifest_path = (
                self.root
                / "models/manifests/yolo26m-visdrone-s1-best.manifest.json"
            )
            manifest_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "contractId": (
                            "visionflow.phase2b1.visdrone-weight-contract"
                        ),
                        "template": False,
                        "model": {
                            "profile": "AERIAL_SMALL_OBJECT_LIVE",
                            "role": "AERIAL_SMALL_OBJECT_DETECTION",
                            "family": "YOLO26",
                            "scale": "m",
                            "task": "detect",
                            "trainingStage": "VISDRONE_S1",
                            "weight": {
                                "fileName": "yolo26m-visdrone-s1-best.pt",
                                "sha256": sha256_file(parent_path),
                            },
                        },
                        "classes": [dict(item) for item in VISDRONE_CLASS_MAPPING],
                    }
                ),
                encoding="utf-8",
            )
            parent = {
                "filePath": self._relative(parent_path),
                "fileName": "yolo26m-visdrone-s1-best.pt",
                "sha256": sha256_file(parent_path),
                "manifestPath": self._relative(manifest_path),
                "manifestSha256": sha256_file(manifest_path),
            }
            output_name = "yolo26m-visdrone-s2-best.pt"
            source_datasets = ["VISDRONE2019_DET", "VISIONFLOW_PRESENTATION"]
        plan = {
            "schemaVersion": 1,
            "contractId": "visionflow.phase2b5.transfer-training-plan",
            "template": False,
            "planVersion": 1,
            "stage": stage,
            "model": {
                "profile": "AERIAL_SMALL_OBJECT_LIVE",
                "role": "AERIAL_SMALL_OBJECT_DETECTION",
                "family": "YOLO26",
                "scale": "m",
                "task": "detect",
                "parent": parent,
                "outputFileName": output_name,
            },
            "data": {
                "dataYaml": self._relative(self.data_yaml),
                "datasetName": "training-fixture",
                "datasetVersion": "training-v1",
                "splitManifest": self._relative(self.split_manifest_path),
                "sourceDatasets": source_datasets,
                "trainSplit": "train",
                "valSplit": "val",
                "fingerprintMode": "labels",
            },
            "training": {
                "imgsz": 1280,
                "epochs": 100,
                "batch": 2,
                "seed": 26,
                "device": device,
                "workers": 4,
                "optimizer": "MuSGD",
                "patience": 30,
                "deterministic": True,
                "amp": True,
                "close_mosaic": 10,
                "cache": False,
            },
            "inferenceEvidence": {
                "defaultHeadMode": "END_TO_END",
                "compareHeadModes": ["END_TO_END", "ONE_TO_MANY_NMS"],
                "trainingHeadSwitchAllowed": False,
            },
        }
        self.plan_path.write_text(json.dumps(plan), encoding="utf-8")
        return plan

    def _prepare(
        self,
        *,
        stage: str = "VISDRONE_S1",
        device: str = "0",
    ) -> None:
        self._write_plan(stage=stage, device=device)
        receipt = build_dataset_intake_report(
            root=self.root,
            plan_path=self.plan_path,
            ultralytics_version="8.4.0",
            image_probe=lambda _path: (100, 100),
        )
        self.receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    def _build(self, **kwargs: object) -> dict[str, object]:
        return build_training_gpu_preflight_report(
            root=self.root,
            plan_path=self.plan_path,
            intake_receipt_path=self.receipt_path,
            ultralytics_version="8.4.0",
            image_probe=lambda _path: (100, 100),
            **kwargs,
        )

    def test_cpu_check_only_relocks_s1_and_s2_without_gpu_imports(self) -> None:
        for stage in ("VISDRONE_S1", "VISIONFLOW_S2"):
            with self.subTest(stage=stage):
                self._prepare(stage=stage)
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
                self.assertEqual(report["contractId"], TRAINING_GPU_PREFLIGHT_CONTRACT_ID)
                self.assertEqual(report["status"], CPU_STATUS)
                self.assertEqual(report["nextAction"], CPU_NEXT_ACTION)
                self.assertEqual(report["training"]["batchStatus"], "PROVISIONAL")
                self.assertFalse(report["safeguards"]["gpuAccessed"])
                self.assertFalse(report["safeguards"]["modelLoaded"])

    def test_receipt_content_hash_tampering_is_rejected(self) -> None:
        self._prepare()
        receipt = json.loads(self.receipt_path.read_text(encoding="utf-8"))
        receipt["dataset"]["train"]["imageCount"] = 999
        self.receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaisesRegex(TrainingGpuPreflightError, "receiptSha256"):
            self._build()

    def test_self_consistent_but_stale_receipt_is_rejected(self) -> None:
        self._prepare()
        receipt = json.loads(self.receipt_path.read_text(encoding="utf-8"))
        receipt["dataset"]["train"]["imageCount"] = 999
        receipt["receiptSha256"] = _receipt_sha(receipt)
        self.receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaisesRegex(TrainingGpuPreflightError, "재계산"):
            self._build()

    def test_plan_change_after_intake_is_rejected(self) -> None:
        self._prepare()
        plan = json.loads(self.plan_path.read_text(encoding="utf-8"))
        plan["training"]["batch"] = 3
        self.plan_path.write_text(json.dumps(plan), encoding="utf-8")
        with self.assertRaisesRegex(TrainingGpuPreflightError, "재계산"):
            self._build()

    def test_cuda_unavailable_and_device_mismatch_are_rejected(self) -> None:
        self._prepare()
        with self.assertRaisesRegex(TrainingGpuPreflightError, "CUDA"):
            self._build(
                confirm_gpu_probe=True,
                torch_provider=lambda: _FakeTorch(available=False),
                yolo_factory=lambda _path: _FakeYolo(COCO_NAMES),
            )
        self._prepare(device="1")
        with self.assertRaisesRegex(TrainingGpuPreflightError, "범위"):
            self._build(
                confirm_gpu_probe=True,
                torch_provider=lambda: _FakeTorch(count=1),
                yolo_factory=lambda _path: _FakeYolo(COCO_NAMES),
            )

    def test_confirmed_gpu_probe_loads_parent_but_never_trains(self) -> None:
        for stage, names in (
            ("VISDRONE_S1", COCO_NAMES),
            ("VISIONFLOW_S2", VISDRONE_NAMES),
        ):
            with self.subTest(stage=stage):
                self._prepare(stage=stage)
                model = _FakeYolo(names)
                report = self._build(
                    confirm_gpu_probe=True,
                    torch_provider=lambda: _FakeTorch(),
                    yolo_factory=lambda _path, model=model: model,
                )
                self.assertEqual(report["status"], GPU_STATUS)
                self.assertEqual(report["nextAction"], GPU_NEXT_ACTION)
                self.assertEqual(report["runtime"]["deviceName"], "VisionFlow Fake GPU")
                self.assertEqual(report["runtime"]["computeCapability"], "8.9")
                self.assertEqual(report["modelProbe"]["task"], "detect")
                self.assertEqual(model.device, "cuda:0")
                self.assertFalse(model.train_called)
                self.assertTrue(report["safeguards"]["gpuAccessed"])
                self.assertFalse(report["safeguards"]["trainingExecuted"])
                self.assertFalse(report["safeguards"]["batchCalibrated"])

    def test_parent_class_identity_mismatch_is_rejected(self) -> None:
        self._prepare(stage="VISIONFLOW_S2")
        with self.assertRaisesRegex(TrainingGpuPreflightError, "10-class"):
            self._build(
                confirm_gpu_probe=True,
                torch_provider=lambda: _FakeTorch(),
                yolo_factory=lambda _path: _FakeYolo(COCO_NAMES),
            )

    def test_schema_locks_two_statuses_and_no_training_boundary(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        properties = schema["properties"]
        self.assertEqual(
            properties["status"]["enum"],
            [CPU_STATUS, GPU_STATUS],
        )
        safeguards = properties["safeguards"]["properties"]
        self.assertFalse(safeguards["trainingExecuted"]["const"])
        self.assertFalse(safeguards["batchCalibrated"]["const"])
        self.assertFalse(safeguards["dockerAccessed"]["const"])
        self.assertFalse(safeguards["dataMutated"]["const"])

    def test_output_is_atomic_and_existing_file_is_not_overwritten(self) -> None:
        self._prepare()
        report = self._build()
        output = "output/training-gpu-preflight/s1-check.json"
        target = write_training_gpu_preflight_report(self.root, output, report)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), report)
        with self.assertRaisesRegex(TrainingGpuPreflightError, "덮어쓰지"):
            write_training_gpu_preflight_report(self.root, output, report)

    def test_receipt_and_output_paths_outside_root_are_rejected(self) -> None:
        self._prepare()
        outside = Path(self.temporary.name) / "outside.json"
        outside.write_text(self.receipt_path.read_text(encoding="utf-8"), encoding="utf-8")
        with self.assertRaisesRegex(TrainingGpuPreflightError, "root 밖"):
            build_training_gpu_preflight_report(
                root=self.root,
                plan_path=self.plan_path,
                intake_receipt_path=outside,
                ultralytics_version="8.4.0",
                image_probe=lambda _path: (100, 100),
            )
        report = self._build()
        with self.assertRaisesRegex(TrainingGpuPreflightError, "root 밖"):
            write_training_gpu_preflight_report(
                self.root,
                "../outside-output.json",
                report,
            )


if __name__ == "__main__":
    unittest.main()
