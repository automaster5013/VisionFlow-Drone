from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from app.labeled_small_object_evaluation import (
    GroundTruth,
    Prediction,
    compare_records,
    deterministic_match,
    extract_predictions,
    parse_yolo_label_file,
    run_isolated_model,
    summarize_latencies,
    validate_video_split_manifest,
)
from app.model_contract import (
    COCO_VISDRONE_CANONICAL_CLASSES,
    LABELED_EVALUATION_CONTRACT_ID,
    LABELED_METRIC_PROVENANCE,
    SMALL_OBJECT_DEFINITION,
    VISDRONE_CLASS_MAPPING,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPLIT_SCHEMA_PATH = PROJECT_ROOT / "config/video-split-manifest-v1.schema.json"
REPORT_SCHEMA_PATH = (
    PROJECT_ROOT / "config/labeled-small-object-evaluation-v1.schema.json"
)
SPLIT_TEMPLATE_PATH = (
    PROJECT_ROOT / "datasets/final-heldout.split-manifest.template.json"
)
VISDRONE_NAMES = {
    int(item["id"]): str(item["sourceName"]) for item in VISDRONE_CLASS_MAPPING
}


def truth(
    index: int,
    bbox: tuple[float, float, float, float],
    *,
    canonical: str = "person",
    small: bool = True,
) -> GroundTruth:
    return GroundTruth(
        image="sample.jpg",
        index=index,
        source_class_id=0,
        source_name="pedestrian",
        canonical_name=canonical,
        bbox=bbox,
        area_px=(bbox[2] - bbox[0]) * (bbox[3] - bbox[1]),
        small=small,
    )


def prediction(
    bbox: tuple[float, float, float, float],
    *,
    canonical: str = "person",
    confidence: float = 0.9,
) -> Prediction:
    return Prediction(
        source_class_id=0,
        source_name="pedestrian",
        canonical_name=canonical,
        bbox=bbox,
        confidence=confidence,
    )


def split_manifest() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "contractId": "visionflow.phase2b4.video-split-manifest",
        "template": False,
        "datasetVersion": "heldout-v1",
        "splitUnit": "VIDEO_SEQUENCE",
        "adjacentFramesAcrossSplits": False,
        "finalEvaluationExcludedFromTraining": True,
        "sequences": [
            {
                "sequenceId": "heldout-a",
                "sourceVideoFile": "heldout-a.mp4",
                "sourceVideoSha256": "a" * 64,
                "split": "FINAL_HELDOUT",
                "imageRoots": ["images/final-heldout/heldout-a"],
            }
        ],
    }


class LabeledSmallObjectEvaluationTest(unittest.TestCase):
    def test_yolo_label_area_uses_original_resolution(self) -> None:
        with TemporaryDirectory() as directory:
            label = Path(directory) / "sample.txt"
            label.write_text("0 0.5 0.5 0.03 0.03\n", encoding="utf-8")
            parsed = parse_yolo_label_file(
                label,
                image="sample.jpg",
                width=1000,
                height=1000,
                names=VISDRONE_NAMES,
            )
        self.assertEqual(len(parsed), 1)
        self.assertAlmostEqual(parsed[0].area_px, 900.0)
        self.assertTrue(parsed[0].small)
        self.assertEqual(parsed[0].canonical_name, "person")

    def test_yolo_label_rejects_malformed_or_out_of_bounds_box(self) -> None:
        with TemporaryDirectory() as directory:
            label = Path(directory) / "sample.txt"
            label.write_text("0 0.98 0.5 0.10 0.10\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "경계"):
                parse_yolo_label_file(
                    label,
                    image="sample.jpg",
                    width=100,
                    height=100,
                    names=VISDRONE_NAMES,
                )

    def test_deterministic_matching_is_class_aware_and_one_to_one(self) -> None:
        truths = [truth(0, (0, 0, 10, 10)), truth(1, (0, 0, 10, 10))]
        predictions = [
            prediction((0, 0, 10, 10)),
            prediction((0, 0, 10, 10), canonical="car"),
        ]
        result = deterministic_match(truths, predictions)
        self.assertEqual(result.pairs, ((0, 0, 1.0),))
        self.assertEqual(result.unmatched_ground_truth, (1,))
        self.assertEqual(result.unmatched_predictions, (1,))

    def test_candidate_recovered_small_object_uses_ground_truth_matches(self) -> None:
        truths = {"sample.jpg": [truth(0, (0, 0, 10, 10))]}
        metrics, rows = compare_records(
            truths,
            {"sample.jpg": []},
            {"sample.jpg": [prediction((0, 0, 10, 10))]},
        )
        self.assertEqual(metrics["baseline"]["smallFn"], 1)
        self.assertEqual(metrics["candidate"]["smallTp"], 1)
        self.assertEqual(metrics["comparison"]["recoveredSmallObjectCount"], 1)
        self.assertTrue(rows[0]["candidateRecovered"])

    def test_ground_truth_is_required_for_recall_claim(self) -> None:
        with self.assertRaisesRegex(ValueError, "Recall"):
            compare_records({"sample.jpg": []}, {"sample.jpg": []}, {"sample.jpg": []})

        large_truth = truth(0, (0, 0, 40, 40), small=False)
        with self.assertRaisesRegex(ValueError, "small-object Recall"):
            compare_records(
                {"sample.jpg": [large_truth]},
                {"sample.jpg": []},
                {"sample.jpg": []},
            )

    def test_split_manifest_covers_each_image_exactly_once(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "images/final-heldout/heldout-a/frame.jpg"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"image")
            manifest_path = root / "split.json"
            manifest_path.write_text(json.dumps(split_manifest()), encoding="utf-8")
            result = validate_video_split_manifest(
                split_manifest(),
                manifest_path=manifest_path,
                dataset_base=root,
                images=[image],
            )
        self.assertEqual(result["splitUnit"], "VIDEO_SEQUENCE")
        self.assertEqual(len(result["manifestSha256"]), 64)

    def test_split_manifest_rejects_template_and_uncovered_image(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "images/other/frame.jpg"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"image")
            manifest_path = root / "split.json"
            manifest_path.write_text("{}", encoding="utf-8")
            template = split_manifest()
            template["template"] = True
            with self.assertRaisesRegex(ValueError, "템플릿"):
                validate_video_split_manifest(
                    template,
                    manifest_path=manifest_path,
                    dataset_base=root,
                    images=[image],
                )
            with self.assertRaisesRegex(ValueError, "정확히 하나"):
                validate_video_split_manifest(
                    split_manifest(),
                    manifest_path=manifest_path,
                    dataset_base=root,
                    images=[image],
                )

    def test_split_manifest_rejects_duplicate_source_video_hash(self) -> None:
        manifest = split_manifest()
        sequences = manifest["sequences"]
        assert isinstance(sequences, list)
        duplicate = copy.deepcopy(sequences[0])
        assert isinstance(duplicate, dict)
        duplicate["sequenceId"] = "heldout-b"
        duplicate["imageRoots"] = ["images/final-heldout/heldout-b"]
        sequences.append(duplicate)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "split.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "고유"):
                validate_video_split_manifest(
                    manifest,
                    manifest_path=manifest_path,
                    dataset_base=root,
                    images=[],
                )

    def test_latency_summary_has_interpolated_percentiles_and_vram_scope(self) -> None:
        summary = summarize_latencies(
            [10.0, 20.0, 30.0, 40.0], peak_allocated=100, peak_reserved=200
        )
        self.assertEqual(summary["measurementScope"], "SEQUENTIAL_ISOLATED_MODEL_RUN")
        self.assertEqual(summary["p50LatencyMs"], 25.0)
        self.assertAlmostEqual(summary["p95LatencyMs"], 38.5)
        self.assertEqual(summary["peakVramAllocatedBytes"], 100)
        self.assertIsNone(summary["offlineDropRate"])

    def test_prediction_adapter_excludes_unsupported_coco_classes(self) -> None:
        boxes = SimpleNamespace(
            xyxy=[[0, 0, 10, 10], [0, 0, 5, 5]],
            cls=[0, 2],
            conf=[0.9, 0.8],
        )
        predictions, ignored = extract_predictions(
            SimpleNamespace(boxes=boxes),
            names={0: "person", 2: "bird"},
            canonical_resolver=lambda _class_id, name: (
                name if name in COCO_VISDRONE_CANONICAL_CLASSES else None
            ),
        )
        self.assertEqual(len(predictions), 1)
        self.assertEqual(predictions[0].canonical_name, "person")
        self.assertEqual(ignored, 1)

    def test_isolated_execution_adapter_runs_with_fake_cuda_and_yolo(self) -> None:
        class FakeCuda:
            @staticmethod
            def is_available() -> bool:
                return True

            @staticmethod
            def device_count() -> int:
                return 1

            @staticmethod
            def synchronize(_device: int) -> None:
                return None

            @staticmethod
            def reset_peak_memory_stats(_device: int) -> None:
                return None

            @staticmethod
            def max_memory_allocated(_device: int) -> int:
                return 123

            @staticmethod
            def max_memory_reserved(_device: int) -> int:
                return 456

            @staticmethod
            def empty_cache() -> None:
                return None

        class FakeYolo:
            names = {0: "person"}
            task = "detect"

            def __init__(self, _path: str) -> None:
                pass

            def predict(self, **_kwargs):
                return [
                    SimpleNamespace(
                        boxes=SimpleNamespace(
                            xyxy=[[0, 0, 10, 10]], cls=[0], conf=[0.9]
                        )
                    )
                ]

        with TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "yolo26m.pt"
            model.write_bytes(b"model")
            image = root / "sample.jpg"
            image.write_bytes(b"image")
            fake_modules = {
                "torch": SimpleNamespace(cuda=FakeCuda()),
                "ultralytics": SimpleNamespace(YOLO=FakeYolo),
            }
            with patch.dict(sys.modules, fake_modules):
                predictions, performance, status = run_isolated_model(
                    model_path=model,
                    profile="GENERAL_LIVE",
                    images=[image],
                    device="0",
                    image_size=1280,
                    confidence=0.25,
                    nms_iou=0.7,
                    warmup=1,
                    canonical_resolver=lambda _class_id, name: name,
                )

        self.assertEqual(len(predictions[str(image.resolve())]), 1)
        self.assertEqual(performance["peakVramAllocatedBytes"], 123)
        self.assertEqual(performance["peakVramReservedBytes"], 456)
        self.assertEqual(status["profile"], "GENERAL_LIVE")

    def test_schemas_lock_ground_truth_provenance_and_small_object_definition(self) -> None:
        report_schema = json.loads(REPORT_SCHEMA_PATH.read_text(encoding="utf-8"))
        split_schema = json.loads(SPLIT_SCHEMA_PATH.read_text(encoding="utf-8"))
        template = json.loads(SPLIT_TEMPLATE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            report_schema["properties"]["contractId"]["const"],
            LABELED_EVALUATION_CONTRACT_ID,
        )
        self.assertEqual(
            report_schema["properties"]["metricProvenance"]["const"],
            LABELED_METRIC_PROVENANCE,
        )
        self.assertEqual(
            report_schema["properties"]["policy"]["properties"]
            ["smallObjectDefinition"]["const"],
            SMALL_OBJECT_DEFINITION,
        )
        self.assertEqual(
            split_schema["properties"]["splitUnit"]["const"], "VIDEO_SEQUENCE"
        )
        self.assertTrue(template["template"])


if __name__ == "__main__":
    unittest.main()
