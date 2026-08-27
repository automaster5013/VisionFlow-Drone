from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from app.model_contract import VISDRONE_CLASS_MAPPING, sha256_file
from app.model_training_plan import (
    INTERNAL_YOLO26_ARGUMENTS,
    OFFICIAL_DATASET_SPLIT_UNIT,
    PUBLIC_TRAIN_ARGUMENTS,
    TRAINING_PLAN_CONTRACT_ID,
    VIDEO_SEQUENCE_SPLIT_UNIT,
    TrainingPlanError,
    compile_training_plan,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "config/transfer-training-plan-v1.schema.json"
SPLIT_SCHEMA_PATH = PROJECT_ROOT / "config/video-split-manifest-v1.schema.json"
S1_TEMPLATE_PATH = (
    PROJECT_ROOT / "config/visdrone-s1-training.plan.template.json"
)
S2_TEMPLATE_PATH = (
    PROJECT_ROOT / "config/visdrone-s2-training.plan.template.json"
)
VISDRONE_NAMES = [str(item["sourceName"]) for item in VISDRONE_CLASS_MAPPING]


class ModelTrainingPlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repo"
        self.root.mkdir()
        (self.root / "models/manifests").mkdir(parents=True)
        (self.root / "config").mkdir()
        self.dataset = self.root / "datasets/training"
        for split, sequence in (
            ("train", "train-a"),
            ("val", "val-a"),
            ("final-heldout", "heldout-a"),
        ):
            image = self.dataset / f"images/{split}/{sequence}/frame.jpg"
            label = self.dataset / f"labels/{split}/{sequence}/frame.txt"
            image.parent.mkdir(parents=True)
            label.parent.mkdir(parents=True)
            image.write_bytes(f"{split}-image".encode())
            label.write_text("0 0.5 0.5 0.1 0.1\n", encoding="utf-8")
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

    def _write_split_manifest(self) -> None:
        self.split_manifest_path.write_text(
            json.dumps(self.split_manifest), encoding="utf-8"
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
            output = "yolo26m-visdrone-s1-best.pt"
            sources = ["VISDRONE2019_DET"]
        else:
            parent_path = self.root / "models/yolo26m-visdrone-s1-best.pt"
            parent_path.write_bytes(b"s1-parent")
            parent_manifest_path = (
                self.root
                / "models/manifests/yolo26m-visdrone-s1-best.manifest.json"
            )
            parent_manifest = {
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
            parent_manifest_path.write_text(
                json.dumps(parent_manifest), encoding="utf-8"
            )
            parent = {
                "filePath": self._relative(parent_path),
                "fileName": "yolo26m-visdrone-s1-best.pt",
                "sha256": sha256_file(parent_path),
                "manifestPath": self._relative(parent_manifest_path),
                "manifestSha256": sha256_file(parent_manifest_path),
            }
            output = "yolo26m-visdrone-s2-best.pt"
            sources = ["VISDRONE2019_DET", "VISIONFLOW_PRESENTATION"]
        plan = {
            "schemaVersion": 1,
            "contractId": TRAINING_PLAN_CONTRACT_ID,
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
                "outputFileName": output,
            },
            "data": {
                "dataYaml": self._relative(self.data_yaml),
                "datasetName": "training-fixture",
                "datasetVersion": "training-v1",
                "splitManifest": self._relative(self.split_manifest_path),
                "sourceDatasets": sources,
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

    def _rewrite_plan(self, plan: dict[str, object]) -> None:
        self.plan_path.write_text(json.dumps(plan), encoding="utf-8")

    def _compile(self, version: str = "8.4.0") -> dict[str, object]:
        return compile_training_plan(
            root=self.root,
            plan_path=self.plan_path,
            ultralytics_version=version,
        )

    def test_schema_and_templates_lock_exact_stage_contracts(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        split_schema = json.loads(SPLIT_SCHEMA_PATH.read_text(encoding="utf-8"))
        s1 = json.loads(S1_TEMPLATE_PATH.read_text(encoding="utf-8"))
        s2 = json.loads(S2_TEMPLATE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            schema["properties"]["contractId"]["const"],
            TRAINING_PLAN_CONTRACT_ID,
        )
        self.assertEqual(
            schema["properties"]["stage"]["enum"],
            ["VISDRONE_S1", "VISIONFLOW_S2"],
        )
        self.assertTrue(s1["template"])
        self.assertTrue(s2["template"])
        self.assertEqual(s1["model"]["parent"]["fileName"], "yolo26m.pt")
        self.assertEqual(
            s2["model"]["parent"]["fileName"],
            "yolo26m-visdrone-s1-best.pt",
        )
        training_properties = schema["properties"]["training"]["properties"]
        self.assertFalse(INTERNAL_YOLO26_ARGUMENTS & set(training_properties))
        self.assertEqual(
            split_schema["properties"]["splitUnit"]["enum"],
            [VIDEO_SEQUENCE_SPLIT_UNIT, OFFICIAL_DATASET_SPLIT_UNIT],
        )
        self.assertIn("sequences", split_schema["properties"])
        self.assertIn("sources", split_schema["properties"])

    def test_template_plan_is_rejected(self) -> None:
        plan = self._write_plan()
        plan["template"] = True
        self._rewrite_plan(plan)
        with self.assertRaisesRegex(TrainingPlanError, "템플릿"):
            self._compile()

    def test_s1_and_s2_stage_parent_output_and_source_composition_pass(self) -> None:
        self._write_plan("VISDRONE_S1")
        s1 = self._compile()
        self.assertEqual(s1["stage"], "VISDRONE_S1")
        self.assertEqual(
            s1["model"]["outputFileName"], "yolo26m-visdrone-s1-best.pt"
        )
        self.assertEqual(s1["data"]["sourceDatasets"], ["VISDRONE2019_DET"])

        self._write_plan("VISIONFLOW_S2")
        s2 = self._compile("8.4.129")
        self.assertEqual(s2["stage"], "VISIONFLOW_S2")
        self.assertEqual(
            s2["model"]["parent"]["fileName"],
            "yolo26m-visdrone-s1-best.pt",
        )
        self.assertIn("manifestSha256", s2["model"]["parent"])

    def test_s1_official_dataset_split_provenance_passes(self) -> None:
        self._use_official_dataset_split()
        self._write_plan("VISDRONE_S1")
        report = self._compile()
        self.assertEqual(report["data"]["splitUnit"], OFFICIAL_DATASET_SPLIT_UNIT)

    def test_official_dataset_split_rejects_video_fields_and_s2_use(self) -> None:
        self._use_official_dataset_split()
        sources = self.split_manifest["sources"]
        assert isinstance(sources, list)
        sources[0]["sourceVideoFile"] = "fabricated.mp4"
        self._write_split_manifest()
        self._write_plan("VISDRONE_S1")
        with self.assertRaisesRegex(TrainingPlanError, "키가 계약과 다릅니다"):
            self._compile()

        del sources[0]["sourceVideoFile"]
        self._write_split_manifest()
        self._write_plan("VISIONFLOW_S2")
        with self.assertRaisesRegex(TrainingPlanError, "VISDRONE_S1"):
            self._compile()

    def test_class_mapping_is_exact_and_ppe_mixing_is_rejected(self) -> None:
        self._write_plan()
        config = yaml.safe_load(self.data_yaml.read_text(encoding="utf-8"))
        config["names"][0] = "helmet"
        self.data_yaml.write_text(
            yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
        )
        with self.assertRaisesRegex(TrainingPlanError, "PPE"):
            self._compile()

    def test_train_val_image_overlap_is_rejected(self) -> None:
        self._write_plan()
        config = yaml.safe_load(self.data_yaml.read_text(encoding="utf-8"))
        config["val"] = "images/train"
        self.data_yaml.write_text(
            yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
        )
        with self.assertRaisesRegex(TrainingPlanError, "중복"):
            self._compile()

    def test_wrong_split_root_and_final_heldout_leakage_are_rejected(self) -> None:
        self._write_plan()
        sequences = self.split_manifest["sequences"]
        assert isinstance(sequences, list)
        sequences[0]["split"] = "VAL"
        self._write_split_manifest()
        with self.assertRaisesRegex(TrainingPlanError, "VIDEO_SEQUENCE"):
            self._compile()

        self.assertEqual(self.split_manifest["splitUnit"], VIDEO_SEQUENCE_SPLIT_UNIT)

        sequences[0]["split"] = "TRAIN"
        self._write_split_manifest()
        config = yaml.safe_load(self.data_yaml.read_text(encoding="utf-8"))
        config["train"] = "images/final-heldout"
        self.data_yaml.write_text(
            yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
        )
        with self.assertRaisesRegex(TrainingPlanError, "VIDEO_SEQUENCE"):
            self._compile()

    def test_missing_label_is_rejected(self) -> None:
        self._write_plan()
        label = self.dataset / "labels/train/train-a/frame.txt"
        label.unlink()
        with self.assertRaisesRegex(TrainingPlanError, "라벨"):
            self._compile()

    def test_out_of_contract_label_class_is_rejected(self) -> None:
        self._write_plan()
        label = self.dataset / "labels/train/train-a/frame.txt"
        label.write_text("10 0.5 0.5 0.1 0.1\n", encoding="utf-8")
        with self.assertRaisesRegex(TrainingPlanError, "10-class"):
            self._compile()

    def test_path_outside_root_is_rejected(self) -> None:
        plan = self._write_plan()
        outside = self.root.parent / "outside.pt"
        outside.write_bytes(b"outside")
        plan["model"]["parent"] = {
            "filePath": "../outside.pt",
            "fileName": "yolo26m.pt",
            "sha256": sha256_file(outside),
        }
        self._rewrite_plan(plan)
        with self.assertRaisesRegex(TrainingPlanError, "root 밖"):
            self._compile()

    def test_symlink_input_is_rejected(self) -> None:
        self._write_plan()
        link = self.root / "config/data-link.yaml"
        try:
            link.symlink_to(self.data_yaml)
        except OSError as error:
            self.skipTest(f"symlink를 만들 수 없습니다: {error}")
        plan = json.loads(self.plan_path.read_text(encoding="utf-8"))
        plan["data"]["dataYaml"] = self._relative(link)
        self._rewrite_plan(plan)
        with self.assertRaisesRegex(TrainingPlanError, "심볼릭 링크"):
            self._compile()

    def test_parent_weight_hash_mismatch_is_rejected(self) -> None:
        plan = self._write_plan()
        plan["model"]["parent"]["sha256"] = "f" * 64
        self._rewrite_plan(plan)
        with self.assertRaisesRegex(TrainingPlanError, "SHA-256"):
            self._compile()

    def test_s2_wrong_parent_manifest_lineage_is_rejected(self) -> None:
        plan = self._write_plan("VISIONFLOW_S2")
        parent = plan["model"]["parent"]
        manifest_path = self.root / parent["manifestPath"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["model"]["trainingStage"] = "VISIONFLOW_S2"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        parent["manifestSha256"] = sha256_file(manifest_path)
        self._rewrite_plan(plan)
        with self.assertRaisesRegex(TrainingPlanError, "VISDRONE_S1"):
            self._compile()

    def test_ultralytics_before_8_4_is_rejected(self) -> None:
        self._write_plan()
        with self.assertRaisesRegex(TrainingPlanError, "8.4.0"):
            self._compile("8.3.99")

    def test_public_arguments_are_ordered_and_internal_arguments_are_rejected(self) -> None:
        plan = self._write_plan()
        report = self._compile()
        compiled = report["compiledTraining"]
        self.assertEqual(
            compiled["argumentOrder"], ["data", *PUBLIC_TRAIN_ARGUMENTS]
        )
        self.assertEqual(list(compiled["arguments"]), compiled["argumentOrder"])
        self.assertEqual(compiled["arguments"]["optimizer"], "MuSGD")
        self.assertTrue(compiled["arguments"]["deterministic"])

        plan["training"]["o2m"] = True
        self._rewrite_plan(plan)
        with self.assertRaisesRegex(TrainingPlanError, "내부 학습 인자"):
            self._compile()

    def test_readiness_report_proves_no_training_gpu_or_runtime_imports(self) -> None:
        self._write_plan()
        before = set(sys.modules)
        report = self._compile()
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
            },
        )
        self.assertEqual(len(report["evidenceLockSha256"]), 64)


if __name__ == "__main__":
    unittest.main()
