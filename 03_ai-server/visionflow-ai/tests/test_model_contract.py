from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from app.model_contract import (
    COCO_VISDRONE_CANONICAL_CLASSES,
    CONTRACT_ID,
    FINAL_HELDOUT_SPLIT,
    LABELED_EVALUATION_POLICY_ID,
    LABELED_EVALUATION_SPLIT_UNITS,
    LABELED_METRIC_PROVENANCE,
    SHOWDOWN_MATCH_IOU_THRESHOLD,
    SHOWDOWN_METRIC_PROVENANCE,
    SHOWDOWN_RECOVERED_LABEL,
    SMALL_OBJECT_DEFINITION,
    SMALL_OBJECT_MAX_AREA_PX,
    VISDRONE_CLASS_MAPPING,
    ModelContractError,
    sha256_file,
    validate_profile_registry,
    validate_weight_manifest,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / "config/model-profiles-v1.json"
S1_TEMPLATE_PATH = (
    PROJECT_ROOT
    / "models/manifests/yolo26m-visdrone-s1-best.manifest.template.json"
)
S2_TEMPLATE_PATH = (
    PROJECT_ROOT
    / "models/manifests/yolo26m-visdrone-s2-best.manifest.template.json"
)


def load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def materialize_manifest(template_path: Path, weight_path: Path) -> dict[str, object]:
    manifest = load_json(template_path)
    manifest["template"] = False
    model = manifest["model"]
    assert isinstance(model, dict)
    model["activationEligible"] = True
    weight = model["weight"]
    assert isinstance(weight, dict)
    weight["sizeBytes"] = weight_path.stat().st_size
    weight["sha256"] = sha256_file(weight_path)
    lineage = model["lineage"]
    assert isinstance(lineage, dict)
    lineage["parentSha256"] = "b" * 64
    data = manifest["data"]
    assert isinstance(data, dict)
    data["datasetVersion"] = "2026-08-26"
    data["datasetFingerprintSha256"] = "c" * 64
    split = data["splitPolicy"]
    assert isinstance(split, dict)
    split["splitManifestSha256"] = "d" * 64
    training = manifest["training"]
    assert isinstance(training, dict)
    training.update({"imageSize": 1280, "epochs": 100, "batch": 8, "seed": 26})
    runtime = manifest["runtime"]
    assert isinstance(runtime, dict)
    runtime.update(
        {
            "python": "3.11.9",
            "ultralytics": "8.3.999",
            "torch": "2.12.1",
            "cuda": "13.0",
        }
    )
    evaluation = manifest["evaluation"]
    assert isinstance(evaluation, dict)
    evaluation.update(
        {
            "status": "MEASURED",
            "precision": 0.61,
            "recall": 0.62,
            "map50": 0.63,
            "map50_95": 0.42,
        }
    )
    small = evaluation["smallObject"]
    assert isinstance(small, dict)
    small.update({"recall": 0.6, "missRate": 0.4})
    per_class = evaluation["perClass"]
    assert isinstance(per_class, list)
    for row in per_class:
        assert isinstance(row, dict)
        row.update({"precision": 0.5, "recall": 0.5, "map50": 0.5, "map50_95": 0.3})
    return manifest


def model_status(manifest: dict[str, object], weight_path: Path) -> dict[str, object]:
    classes = manifest["classes"]
    assert isinstance(classes, list)
    return {
        "resolvedPath": str(weight_path),
        "sizeBytes": weight_path.stat().st_size,
        "sha256": sha256_file(weight_path),
        "task": "detect",
        "classCount": len(classes),
        "classes": [
            {"id": row["id"], "name": row["sourceName"]}
            for row in classes
            if isinstance(row, dict)
        ],
    }


class ModelProfileRegistryTest(unittest.TestCase):
    def test_three_profiles_and_exact_visdrone_mapping_pass(self) -> None:
        registry = validate_profile_registry(load_json(REGISTRY_PATH))
        self.assertEqual(registry["contractId"], CONTRACT_ID)
        mappings = registry["classMappings"]
        self.assertIsInstance(mappings, dict)
        assert isinstance(mappings, dict)
        self.assertEqual(
            mappings["VISDRONE2019_DET"],
            [dict(item) for item in VISDRONE_CLASS_MAPPING],
        )

    def test_mapping_drift_is_rejected(self) -> None:
        registry = load_json(REGISTRY_PATH)
        mappings = registry["classMappings"]
        assert isinstance(mappings, dict)
        visdrone = mappings["VISDRONE2019_DET"]
        assert isinstance(visdrone, list)
        first = visdrone[0]
        assert isinstance(first, dict)
        first["canonicalName"] = "pedestrian"
        with self.assertRaisesRegex(ModelContractError, "표준 매핑"):
            validate_profile_registry(registry)

    def test_deterministic_compare_policy_is_exact(self) -> None:
        registry = validate_profile_registry(load_json(REGISTRY_PATH))
        profiles = registry["profiles"]
        assert isinstance(profiles, dict)
        compare = profiles["DETERMINISTIC_COMPARE"]
        assert isinstance(compare, dict)

        self.assertEqual(
            compare["matchIouThreshold"],
            SHOWDOWN_MATCH_IOU_THRESHOLD,
        )
        self.assertEqual(compare["smallObjectDefinition"], SMALL_OBJECT_DEFINITION)
        self.assertEqual(compare["smallObjectMaxAreaPx"], SMALL_OBJECT_MAX_AREA_PX)
        self.assertEqual(compare["metricProvenance"], SHOWDOWN_METRIC_PROVENANCE)
        self.assertEqual(compare["recoveredLabel"], SHOWDOWN_RECOVERED_LABEL)

    def test_deterministic_compare_policy_drift_is_rejected(self) -> None:
        for field, replacement in (
            ("matchIouThreshold", 0.6),
            ("metricProvenance", "RECALL"),
            ("recoveredLabel", "RECOVERED"),
        ):
            with self.subTest(field=field):
                registry = load_json(REGISTRY_PATH)
                profiles = registry["profiles"]
                assert isinstance(profiles, dict)
                compare = profiles["DETERMINISTIC_COMPARE"]
                assert isinstance(compare, dict)
                compare[field] = replacement
                with self.assertRaisesRegex(ModelContractError, field):
                    validate_profile_registry(registry)

    def test_labeled_small_object_evaluation_contract_is_exact(self) -> None:
        registry = validate_profile_registry(load_json(REGISTRY_PATH))
        contracts = registry["evaluationContracts"]
        assert isinstance(contracts, dict)
        labeled = contracts[LABELED_EVALUATION_POLICY_ID]
        assert isinstance(labeled, dict)
        self.assertEqual(labeled["datasetSplit"], FINAL_HELDOUT_SPLIT)
        self.assertEqual(
            labeled["splitUnits"], list(LABELED_EVALUATION_SPLIT_UNITS)
        )
        self.assertEqual(labeled["metricProvenance"], LABELED_METRIC_PROVENANCE)
        self.assertTrue(labeled["runtimeProxyExcluded"])
        self.assertEqual(
            labeled["baselineCanonicalClasses"],
            list(COCO_VISDRONE_CANONICAL_CLASSES),
        )

    def test_labeled_evaluation_contract_drift_is_rejected(self) -> None:
        for field, replacement in (
            ("datasetSplit", "VAL"),
            ("splitUnits", ["VIDEO_SEQUENCE"]),
            ("metricProvenance", SHOWDOWN_METRIC_PROVENANCE),
            ("runtimeProxyExcluded", False),
            ("baselineCanonicalClasses", ["person", "van"]),
        ):
            with self.subTest(field=field):
                registry = load_json(REGISTRY_PATH)
                contracts = registry["evaluationContracts"]
                assert isinstance(contracts, dict)
                labeled = contracts[LABELED_EVALUATION_POLICY_ID]
                assert isinstance(labeled, dict)
                labeled[field] = replacement
                with self.assertRaisesRegex(ModelContractError, field):
                    validate_profile_registry(registry)


class WeightManifestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.s1_weight = self.root / "yolo26m-visdrone-s1-best.pt"
        self.s1_weight.write_bytes(b"visionflow-s1-weight")
        self.registry = load_json(REGISTRY_PATH)
        self.manifest = materialize_manifest(S1_TEMPLATE_PATH, self.s1_weight)

    def test_s1_activation_contract_passes(self) -> None:
        result = validate_weight_manifest(
            self.manifest,
            self.registry,
            weight_path=self.s1_weight,
            model_status=model_status(self.manifest, self.s1_weight),
            activation=True,
        )
        self.assertEqual(result["trainingStage"], "VISDRONE_S1")
        self.assertEqual(result["classCount"], 10)

    def test_template_is_rejected(self) -> None:
        template = load_json(S2_TEMPLATE_PATH)
        with self.assertRaisesRegex(ModelContractError, "템플릿"):
            validate_weight_manifest(template, self.registry)

    def test_s2_is_contract_only_and_cannot_activate(self) -> None:
        s2_weight = self.root / "yolo26m-visdrone-s2-best.pt"
        s2_weight.write_bytes(b"visionflow-s2-weight")
        manifest = materialize_manifest(S2_TEMPLATE_PATH, s2_weight)
        validate_weight_manifest(manifest, self.registry, weight_path=s2_weight)
        with self.assertRaisesRegex(ModelContractError, "LIVE 활성화"):
            validate_weight_manifest(
                manifest,
                self.registry,
                weight_path=s2_weight,
                activation=True,
            )

    def test_ppe_role_cannot_replace_visdrone_role(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        model = manifest["model"]
        assert isinstance(model, dict)
        model["role"] = "PPE_DETECTION"
        with self.assertRaisesRegex(ModelContractError, "PPE 가중치"):
            validate_weight_manifest(manifest, self.registry)

    def test_wrong_s1_lineage_is_rejected(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        model = manifest["model"]
        assert isinstance(model, dict)
        lineage = model["lineage"]
        assert isinstance(lineage, dict)
        lineage["parentFileName"] = "yolo26m-visdrone-s1-best.pt"
        with self.assertRaisesRegex(ModelContractError, "lineage"):
            validate_weight_manifest(manifest, self.registry)

    def test_weight_hash_mismatch_is_rejected(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        model = manifest["model"]
        assert isinstance(model, dict)
        weight = model["weight"]
        assert isinstance(weight, dict)
        weight["sha256"] = "e" * 64
        with self.assertRaisesRegex(ModelContractError, "SHA-256"):
            validate_weight_manifest(manifest, self.registry, weight_path=self.s1_weight)

    def test_model_class_mismatch_is_rejected(self) -> None:
        status = model_status(self.manifest, self.s1_weight)
        classes = status["classes"]
        assert isinstance(classes, list)
        first = classes[0]
        assert isinstance(first, dict)
        first["name"] = "person"
        with self.assertRaisesRegex(ModelContractError, "클래스"):
            validate_weight_manifest(
                self.manifest,
                self.registry,
                model_status=status,
            )

    def test_official_dataset_split_is_accepted(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        data = manifest["data"]
        assert isinstance(data, dict)
        split = data["splitPolicy"]
        assert isinstance(split, dict)
        split["unit"] = "OFFICIAL_DATASET_SPLIT"
        result = validate_weight_manifest(
            manifest,
            self.registry,
            weight_path=self.s1_weight,
            activation=True,
        )
        self.assertEqual(result["trainingStage"], "VISDRONE_S1")

    def test_adjacent_frame_split_is_rejected(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        data = manifest["data"]
        assert isinstance(data, dict)
        split = data["splitPolicy"]
        assert isinstance(split, dict)
        split["adjacentFramesAcrossSplits"] = True
        with self.assertRaisesRegex(ModelContractError, "인접 프레임"):
            validate_weight_manifest(manifest, self.registry)


if __name__ == "__main__":
    unittest.main()
