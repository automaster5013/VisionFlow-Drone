from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from app.model_contract import VISDRONE_CLASS_MAPPING, sha256_file
from app.model_dataset_intake import (
    DATASET_INTAKE_CONTRACT_ID,
    DatasetIntakeError,
    build_dataset_intake_report,
    write_dataset_intake_report,
)
from app.model_training_plan import OFFICIAL_DATASET_SPLIT_UNIT

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "config/dataset-intake-report-v1.schema.json"
VISDRONE_NAMES = [str(item["sourceName"]) for item in VISDRONE_CLASS_MAPPING]


class ModelDatasetIntakeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repo"
        self.root.mkdir()
        (self.root / "models/manifests").mkdir(parents=True)
        (self.root / "config").mkdir()
        self.dataset = self.root / "datasets/training"
        self.train_image = self._write_image("train", "train-a", b"train-image")
        self.val_image = self._write_image("val", "val-a", b"val-image")
        (self.dataset / "images/final-heldout/heldout-a").mkdir(parents=True)
        self._write_label(self.train_image, self._all_class_labels())
        self._write_label(self.val_image, self._all_class_labels())
        self.data_yaml = self.dataset / "data.yaml"
        self.data_yaml.write_text(
            yaml.safe_dump(
                {
                    "path": ".",
                    "train": "images/train",
                    "val": "images/val",
                    "names": VISDRONE_NAMES,
                },
                sort_keys=False,
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        self.split_manifest_path = self.dataset / "split-manifest.json"
        self.split_manifest = {
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
        self._write_split_manifest()
        self.plan_path = self.root / "config/training-plan.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _relative(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def _write_image(self, split: str, sequence: str, content: bytes) -> Path:
        image = self.dataset / f"images/{split}/{sequence}/frame.jpg"
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(content)
        return image

    def _write_label(self, image: Path, content: str) -> Path:
        relative = image.relative_to(self.dataset)
        parts = list(relative.parts)
        parts[parts.index("images")] = "labels"
        label = self.dataset.joinpath(*parts).with_suffix(".txt")
        label.parent.mkdir(parents=True, exist_ok=True)
        label.write_text(content, encoding="utf-8")
        return label

    def _all_class_labels(self) -> str:
        return "".join(
            f"{class_id} 0.5 0.5 0.01 0.01\n" for class_id in range(10)
        )

    def _write_split_manifest(self) -> None:
        self.split_manifest_path.write_text(
            json.dumps(self.split_manifest),
            encoding="utf-8",
        )

    def _use_official_dataset_split(self) -> None:
        sequences = self.split_manifest.pop("sequences")
        assert isinstance(sequences, list)
        self.split_manifest["splitUnit"] = OFFICIAL_DATASET_SPLIT_UNIT
        self.split_manifest["sources"] = [
            {
                "sourceId": str(sequence["sequenceId"]),
                "sourceArtifactFile": f"{sequence['sequenceId']}.zip",
                "sourceArtifactSha256": str(sequence["sourceVideoSha256"]),
                "split": str(sequence["split"]),
                "imageRoots": list(sequence["imageRoots"]),
            }
            for sequence in sequences
        ]
        self._write_split_manifest()

    def _write_plan(self, stage: str = "VISDRONE_S1") -> dict[str, object]:
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
            dataset_name = "VisDrone2019-DET"
        else:
            parent_path = self.root / "models/yolo26m-visdrone-s1-best.pt"
            parent_path.write_bytes(b"s1-parent")
            manifest_path = (
                self.root
                / "models/manifests/yolo26m-visdrone-s1-best.manifest.json"
            )
            manifest = {
                "schemaVersion": 1,
                "contractId": "visionflow.phase2b1.visdrone-weight-contract",
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
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            parent = {
                "filePath": self._relative(parent_path),
                "fileName": "yolo26m-visdrone-s1-best.pt",
                "sha256": sha256_file(parent_path),
                "manifestPath": self._relative(manifest_path),
                "manifestSha256": sha256_file(manifest_path),
            }
            output_name = "yolo26m-visdrone-s2-best.pt"
            source_datasets = ["VISDRONE2019_DET", "VISIONFLOW_PRESENTATION"]
            dataset_name = "VisionFlow-VisDrone-S2"
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
                "datasetName": dataset_name,
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
                "device": "0",
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

    def _build(self, *, stage: str = "VISDRONE_S1") -> dict[str, object]:
        self._write_plan(stage)
        return build_dataset_intake_report(
            root=self.root,
            plan_path=self.plan_path,
            ultralytics_version="8.4.0",
            image_probe=lambda _path: (100, 100),
        )

    def test_s1_and_s2_full_content_intake_reports_pass(self) -> None:
        for stage in ("VISDRONE_S1", "VISIONFLOW_S2"):
            with self.subTest(stage=stage):
                report = self._build(stage=stage)
                self.assertEqual(report["contractId"], DATASET_INTAKE_CONTRACT_ID)
                self.assertEqual(report["status"], "READY")
                self.assertEqual(report["stage"], stage)
                self.assertEqual(report["dataset"]["fingerprintMode"], "full")
                self.assertEqual(report["dataset"]["classCount"], 10)
                self.assertEqual(report["dataset"]["train"]["objectCount"], 10)
                self.assertEqual(
                    report["dataset"]["train"]["maximumObjectsPerImage"],
                    10,
                )
                self.assertEqual(report["dataset"]["val"]["smallObjectCount"], 10)
                self.assertEqual(len(report["receiptSha256"]), 64)

    def test_official_dataset_split_is_preserved_in_intake_receipt(self) -> None:
        self._use_official_dataset_split()
        report = self._build()
        self.assertEqual(
            report["dataset"]["splitUnit"],
            OFFICIAL_DATASET_SPLIT_UNIT,
        )

    def test_schema_locks_ready_full_fingerprint_and_safeguards(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        properties = schema["properties"]
        self.assertEqual(
            properties["contractId"]["const"],
            DATASET_INTAKE_CONTRACT_ID,
        )
        self.assertEqual(properties["status"]["const"], "READY")
        dataset_properties = properties["dataset"]["properties"]
        self.assertEqual(
            dataset_properties["splitUnit"]["enum"],
            ["VIDEO_SEQUENCE", "OFFICIAL_DATASET_SPLIT"],
        )
        self.assertEqual(dataset_properties["fingerprintMode"]["const"], "full")
        self.assertEqual(dataset_properties["classCount"]["const"], 10)
        class_items = schema["$defs"]["splitEvidence"]["properties"]["classes"]
        self.assertEqual(
            schema["$defs"]["splitEvidence"]["properties"][
                "maximumObjectsPerImage"
            ]["minimum"],
            1,
        )
        self.assertEqual(len(class_items["prefixItems"]), 10)
        self.assertFalse(class_items["items"])
        safeguards = properties["safeguards"]["properties"]
        self.assertFalse(safeguards["trainingExecuted"]["const"])
        self.assertFalse(safeguards["gpuAccessed"]["const"])
        self.assertFalse(safeguards["dockerAccessed"]["const"])

    def test_different_paths_with_same_content_across_splits_are_rejected(self) -> None:
        self.val_image.write_bytes(self.train_image.read_bytes())
        self._write_plan()
        with self.assertRaisesRegex(DatasetIntakeError, "동일 이미지 콘텐츠"):
            build_dataset_intake_report(
                root=self.root,
                plan_path=self.plan_path,
                ultralytics_version="8.4.0",
                image_probe=lambda _path: (100, 100),
            )

    def test_image_decode_failure_is_rejected(self) -> None:
        self._write_plan()

        def reject(_path: Path) -> tuple[int, int]:
            raise ValueError("corrupt")

        with self.assertRaisesRegex(DatasetIntakeError, "디코딩"):
            build_dataset_intake_report(
                root=self.root,
                plan_path=self.plan_path,
                ultralytics_version="8.4.0",
                image_probe=reject,
            )

    def test_class_without_objects_is_rejected_per_split(self) -> None:
        self._write_label(
            self.val_image,
            "".join(
                f"{class_id} 0.5 0.5 0.01 0.01\n" for class_id in range(9)
            ),
        )
        self._write_plan()
        with self.assertRaisesRegex(DatasetIntakeError, "motor"):
            build_dataset_intake_report(
                root=self.root,
                plan_path=self.plan_path,
                ultralytics_version="8.4.0",
                image_probe=lambda _path: (100, 100),
            )

    def test_orphan_label_in_managed_split_is_rejected(self) -> None:
        orphan = self.dataset / "labels/train/train-a/orphan.txt"
        orphan.write_text("0 0.5 0.5 0.1 0.1\n", encoding="utf-8")
        self._write_plan()
        with self.assertRaisesRegex(DatasetIntakeError, "orphan"):
            build_dataset_intake_report(
                root=self.root,
                plan_path=self.plan_path,
                ultralytics_version="8.4.0",
                image_probe=lambda _path: (100, 100),
            )

    def test_empty_negative_image_is_measured(self) -> None:
        negative = self._write_image("train", "train-a", b"negative-image")
        negative = negative.with_name("negative.jpg")
        negative.write_bytes(b"negative-image")
        self._write_label(negative, "")
        report = self._build()
        train = report["dataset"]["train"]
        self.assertEqual(train["imageCount"], 2)
        self.assertEqual(train["emptyLabelImageCount"], 1)
        self.assertEqual(train["emptyLabelImageRate"], 0.5)
        self.assertEqual(train["maximumObjectsPerImage"], 10)

    def test_maximum_objects_per_image_is_measured_for_autobatch(self) -> None:
        crowded = self.train_image.with_name("crowded.jpg")
        crowded.write_bytes(b"crowded-image")
        self._write_label(crowded, self._all_class_labels() * 3)
        report = self._build()
        train = report["dataset"]["train"]
        self.assertEqual(train["imageCount"], 2)
        self.assertEqual(train["objectCount"], 40)
        self.assertEqual(train["maximumObjectsPerImage"], 30)

    def test_full_fingerprint_changes_when_image_bytes_change(self) -> None:
        first = self._build()
        self.train_image.write_bytes(b"train-image-updated")
        second = build_dataset_intake_report(
            root=self.root,
            plan_path=self.plan_path,
            ultralytics_version="8.4.0",
            image_probe=lambda _path: (100, 100),
        )
        self.assertNotEqual(
            first["dataset"]["combinedFingerprintSha256"],
            second["dataset"]["combinedFingerprintSha256"],
        )

    def test_output_is_atomic_and_existing_file_is_not_overwritten(self) -> None:
        report = self._build()
        output = "output/dataset-intake/s1-ready.json"
        target = write_dataset_intake_report(self.root, output, report)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), report)
        with self.assertRaisesRegex(DatasetIntakeError, "덮어쓰지"):
            write_dataset_intake_report(self.root, output, report)

    def test_output_outside_root_is_rejected(self) -> None:
        report = self._build()
        with self.assertRaisesRegex(DatasetIntakeError, "root 밖"):
            write_dataset_intake_report(self.root, "../outside.json", report)

    def test_report_proves_no_training_gpu_or_runtime_imports(self) -> None:
        self._write_plan()
        before = set(sys.modules)
        report = build_dataset_intake_report(
            root=self.root,
            plan_path=self.plan_path,
            ultralytics_version="8.4.0",
            image_probe=lambda _path: (100, 100),
        )
        imported = set(sys.modules) - before
        self.assertFalse({"torch", "ultralytics"} & imported)
        self.assertEqual(
            report["safeguards"],
            {
                "trainingExecuted": False,
                "gpuAccessed": False,
                "dockerAccessed": False,
                "torchImported": False,
                "ultralyticsImported": False,
                "imageDecodeCpuOnly": True,
            },
        )


if __name__ == "__main__":
    unittest.main()
