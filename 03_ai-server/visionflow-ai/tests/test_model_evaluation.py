from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from app.model_evaluation import (
    build_mapping_template,
    compare_model_and_dataset_names,
    evaluate_thresholds,
    extract_confusion_matrix,
    extract_image_metrics,
    extract_per_class_metrics,
    label_path,
    load_dataset_inventory,
    load_dataset_spec,
    normalize_names,
    validate_mapping,
)


class FakeScalar:
    def __init__(self, value: float) -> None:
        self.value = value

    def item(self) -> float:
        return self.value


class FakeConfusionMatrix:
    def __init__(self) -> None:
        self.matrix = [
            [7, 1, 0, 2],
            [1, 2, 0, 1],
            [0, 0, 0, 0],
            [2, 1, 0, 0],
        ]

    def summary(self, normalize: bool, decimals: int) -> list[dict[str, object]]:
        del decimals
        value = 0.7 if normalize else 7.0
        return [{"predicted": "person", "person": FakeScalar(value)}]


class FakeMetrics:
    def __init__(self) -> None:
        self.box = SimpleNamespace(
            ap_class_index=[0, 1],
            f1=[0.75, 0.5],
            image_metrics={
                "good.jpg": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "f1": 1.0,
                    "tp": 2,
                    "fp": 0,
                    "fn": 0,
                },
                "bad.jpg": {
                    "precision": 0.25,
                    "recall": 0.5,
                    "f1": 0.333,
                    "tp": 1,
                    "fp": 3,
                    "fn": 1,
                },
            },
        )
        self.nt_per_class = [10, 4, 0]
        self.nt_per_image = [5, 3, 0]
        self.confusion_matrix = FakeConfusionMatrix()

    def class_result(self, position: int) -> tuple[float, float, float, float]:
        return [(0.8, 0.7, 0.9, 0.6), (0.5, 0.5, 0.7, 0.4)][position]


class ModelEvaluationTest(unittest.TestCase):
    def test_normalize_names_supports_list_and_integer_like_keys(self) -> None:
        self.assertEqual(normalize_names(["person", "car"]), {0: "person", 1: "car"})
        self.assertEqual(
            normalize_names({"0": "person", 1: "car"}),
            {0: "person", 1: "car"},
        )

    def test_normalize_names_rejects_gaps_and_duplicates(self) -> None:
        with self.assertRaisesRegex(ValueError, "연속"):
            normalize_names({0: "person", 2: "car"})
        with self.assertRaisesRegex(ValueError, "중복"):
            normalize_names(["person", "person"])

    def test_dataset_spec_fingerprint_changes_when_label_changes(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            image_dir = root / "images" / "val"
            label_dir = root / "labels" / "val"
            image_dir.mkdir(parents=True)
            label_dir.mkdir(parents=True)
            (image_dir / "sample.jpg").write_bytes(b"not-a-real-image")
            label = label_dir / "sample.txt"
            label.write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
            data_yaml = root / "data.yaml"
            data_yaml.write_text(
                "path: .\nval: images/val\nnames:\n  0: person\n",
                encoding="utf-8",
            )

            first = load_dataset_spec(data_yaml, "val", "labels")
            label.write_text("0 0.4 0.4 0.2 0.2\n", encoding="utf-8")
            second = load_dataset_spec(data_yaml, "val", "labels")

            self.assertEqual(first["imageCount"], 1)
            self.assertEqual(first["labelFileCount"], 1)
            self.assertNotEqual(first["fingerprintSha256"], second["fingerprintSha256"])

    def test_dataset_inventory_exposes_same_sorted_images_as_spec(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            image_dir = root / "images" / "test"
            label_dir = root / "labels" / "test"
            image_dir.mkdir(parents=True)
            label_dir.mkdir(parents=True)
            for name in ("b.jpg", "a.jpg"):
                (image_dir / name).write_bytes(b"image")
                (label_dir / Path(name).with_suffix(".txt")).write_text(
                    "0 0.5 0.5 0.2 0.2\n", encoding="utf-8"
                )
            data_yaml = root / "data.yaml"
            data_yaml.write_text(
                "path: .\ntest: images/test\nnames:\n  0: person\n",
                encoding="utf-8",
            )

            inventory, images = load_dataset_inventory(data_yaml, "test", "labels")
            legacy = load_dataset_spec(data_yaml, "test", "labels")

            self.assertEqual(inventory, legacy)
            self.assertEqual([path.name for path in images], ["a.jpg", "b.jpg"])
            self.assertEqual(label_path(images[0]), label_dir / "a.txt")

    def test_model_and_dataset_names_must_match_exactly(self) -> None:
        compare_model_and_dataset_names({0: "person"}, {0: "person"})
        with self.assertRaisesRegex(ValueError, "클래스 계약"):
            compare_model_and_dataset_names({0: "person"}, {0: "pedestrian"})

    def test_mapping_template_requires_explicit_review(self) -> None:
        template = build_mapping_template({0: "flame"}, "a" * 64, "b" * 64)
        item = template["classes"][0]
        self.assertFalse(item["enabled"])
        self.assertEqual(item["canonicalName"], "")
        self.assertEqual(item["reviewStatus"], "REQUIRED")
        errors = validate_mapping(template, {0: "flame"}, "a" * 64)
        self.assertTrue(any("APPROVED 또는 IGNORED" in error for error in errors))

    def test_mapping_validation_blocks_unapproved_enabled_class(self) -> None:
        template = build_mapping_template({0: "flame"}, "a" * 64, "b" * 64)
        item = template["classes"][0]
        item["enabled"] = True
        errors = validate_mapping(template, {0: "flame"}, "a" * 64)
        self.assertTrue(any("canonicalName" in error for error in errors))
        self.assertTrue(any("APPROVED" in error for error in errors))

        item["canonicalName"] = "fire"
        item["reviewStatus"] = "APPROVED"
        self.assertEqual(validate_mapping(template, {0: "flame"}, "a" * 64), [])

    def test_extract_metrics_includes_classes_without_ground_truth(self) -> None:
        rows = extract_per_class_metrics(
            FakeMetrics(),
            {0: "person", 1: "car", 2: "fire"},
        )
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["tp"], 7)
        self.assertEqual(rows[0]["fp"], 3)
        self.assertEqual(rows[0]["fn"], 3)
        self.assertEqual(rows[0]["countSource"], "confusion_matrix")
        self.assertEqual(rows[2]["instances"], 0)
        self.assertEqual(rows[2]["map50"], 0.0)

        images = extract_image_metrics(FakeMetrics())
        self.assertEqual(images[0]["image"], "bad.jpg")

        confusion = extract_confusion_matrix(FakeMetrics())
        self.assertEqual(confusion["raw"][0]["person"], 7.0)
        json.dumps(confusion)

    def test_quality_gate_measured_without_thresholds_and_fails_below_one(self) -> None:
        overall = {"precision": 0.8, "recall": 0.7, "map50": 0.9, "map50_95": 0.6}
        no_gate = evaluate_thresholds(
            overall,
            {"precision": None, "recall": None, "map50": None, "map50_95": None},
        )
        self.assertEqual(no_gate["status"], "MEASURED")

        failed = evaluate_thresholds(
            overall,
            {"precision": 0.9, "recall": None, "map50": None, "map50_95": None},
        )
        self.assertEqual(failed["status"], "FAILED")
        self.assertFalse(json.loads(json.dumps(failed))["checks"][0]["passed"])


if __name__ == "__main__":
    unittest.main()
