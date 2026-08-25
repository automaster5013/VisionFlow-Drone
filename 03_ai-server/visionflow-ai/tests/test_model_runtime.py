from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.model_contract import ModelContractError, TrackKind
from app.model_runtime import create_runtime_model_selection
from tests.test_model_contract import (
    REGISTRY_PATH,
    S1_TEMPLATE_PATH,
    S2_TEMPLATE_PATH,
    materialize_manifest,
    model_status,
)


class RuntimeModelSelectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        (self.root / "config").mkdir()
        (self.root / "models/manifests").mkdir(parents=True)
        self.profiles = self.root / "config/model-profiles-v1.json"
        self.profiles.write_bytes(REGISTRY_PATH.read_bytes())

    def _materialize(
        self,
        template_path: Path,
        weight_name: str,
    ) -> tuple[Path, Path, dict[str, object]]:
        weight_path = self.root / "models" / weight_name
        weight_path.write_bytes(b"phase2b2-runtime-test-weight")
        manifest = materialize_manifest(template_path, weight_path)
        manifest_path = (
            self.root
            / "models/manifests"
            / f"{weight_path.stem}.manifest.json"
        )
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return manifest_path, weight_path, manifest

    def test_legacy_profile_remains_compatible_without_registry_read(self) -> None:
        selection = create_runtime_model_selection(
            model_profile="best-gpu",
            model_path="/app/models/best.pt",
            profiles_path=str(self.root / "missing-registry.json"),
        )
        contract = selection.validate_loaded_status(
            {"profile": "best-gpu", "classCount": 80}
        )
        person = selection.resolve_class(0, "person")

        self.assertEqual(selection.mode, "LEGACY_COMPAT")
        self.assertEqual(contract["validation"], "LEGACY_COMPAT")
        self.assertEqual(person.canonical_name, "person")
        self.assertIs(person.track_kind, TrackKind.HUMAN)

    def test_general_live_requires_exact_weight_file(self) -> None:
        selection = create_runtime_model_selection(
            model_profile="GENERAL_LIVE",
            model_path="models/yolo26m.pt",
            profiles_path=str(self.profiles),
        )
        contract = selection.validate_loaded_status(
            {"profile": "GENERAL_LIVE", "classCount": 80}
        )

        self.assertEqual(contract["trainingStage"], "COCO_BASE")
        self.assertEqual(contract["validation"], "PROFILE_REGISTRY")
        with self.assertRaisesRegex(ModelContractError, "yolo26m.pt"):
            create_runtime_model_selection(
                model_profile="GENERAL_LIVE",
                model_path="models/best.pt",
                profiles_path=str(self.profiles),
            )

    def test_aerial_live_requires_manifest(self) -> None:
        with self.assertRaisesRegex(ModelContractError, "매니페스트"):
            create_runtime_model_selection(
                model_profile="AERIAL_SMALL_OBJECT_LIVE",
                model_path="models/yolo26m-visdrone-s2-best.pt",
                profiles_path=str(self.profiles),
            )

    def test_s2_activation_and_exact_visdrone_mapping_pass(self) -> None:
        manifest_path, weight_path, manifest = self._materialize(
            S2_TEMPLATE_PATH,
            "yolo26m-visdrone-s2-best.pt",
        )
        selection = create_runtime_model_selection(
            model_profile="AERIAL_SMALL_OBJECT_LIVE",
            model_path=str(weight_path),
            manifest_path=str(manifest_path),
            profiles_path=str(self.profiles),
        )
        status = model_status(manifest, weight_path)
        status["profile"] = "AERIAL_SMALL_OBJECT_LIVE"
        contract = selection.validate_loaded_status(status)

        pedestrian = selection.resolve_class(0, "pedestrian")
        people = selection.resolve_class(1, "people")
        motor = selection.resolve_class(9, "motor")
        enriched = selection.enrich_status(status, contract)

        self.assertEqual(contract["trainingStage"], "VISIONFLOW_S2")
        self.assertEqual(contract["validation"], "WEIGHT_MANIFEST")
        self.assertEqual(pedestrian.canonical_name, "person")
        self.assertEqual(people.canonical_name, "person")
        self.assertIs(pedestrian.track_kind, TrackKind.HUMAN)
        self.assertIs(people.track_kind, TrackKind.HUMAN)
        self.assertEqual(motor.canonical_name, "motorcycle")
        self.assertIs(motor.track_kind, TrackKind.CYCLE)
        runtime_contract = enriched["runtimeContract"]
        self.assertIsInstance(runtime_contract, dict)
        assert isinstance(runtime_contract, dict)
        self.assertTrue(runtime_contract["manifestValidated"])
        self.assertEqual(runtime_contract["classMappingId"], "VISDRONE2019_DET")

    def test_runtime_class_name_drift_is_rejected(self) -> None:
        manifest_path, weight_path, _ = self._materialize(
            S2_TEMPLATE_PATH,
            "yolo26m-visdrone-s2-best.pt",
        )
        selection = create_runtime_model_selection(
            model_profile="AERIAL_SMALL_OBJECT_LIVE",
            model_path=str(weight_path),
            manifest_path=str(manifest_path),
            profiles_path=str(self.profiles),
        )
        with self.assertRaisesRegex(ModelContractError, "클래스 이름"):
            selection.resolve_class(0, "person")

    def test_s1_cannot_be_selected_for_live_runtime(self) -> None:
        manifest_path, weight_path, _ = self._materialize(
            S1_TEMPLATE_PATH,
            "yolo26m-visdrone-s1-best.pt",
        )
        with self.assertRaisesRegex(ModelContractError, "s2-best"):
            create_runtime_model_selection(
                model_profile="AERIAL_SMALL_OBJECT_LIVE",
                model_path=str(weight_path),
                manifest_path=str(manifest_path),
                profiles_path=str(self.profiles),
            )

    def test_compare_profile_is_rejected_by_single_model_runtime(self) -> None:
        with self.assertRaisesRegex(ModelContractError, "단일 LIVE"):
            create_runtime_model_selection(
                model_profile="DETERMINISTIC_COMPARE",
                model_path="models/yolo26m.pt",
                profiles_path=str(self.profiles),
            )

    def test_loaded_status_profile_mismatch_is_rejected(self) -> None:
        selection = create_runtime_model_selection(
            model_profile="GENERAL_LIVE",
            model_path="models/yolo26m.pt",
            profiles_path=str(self.profiles),
        )
        with self.assertRaisesRegex(ModelContractError, "profile"):
            selection.validate_loaded_status(
                {"profile": "best-gpu", "classCount": 80}
            )


if __name__ == "__main__":
    unittest.main()
