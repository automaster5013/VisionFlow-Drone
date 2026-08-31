from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.model_contract import ModelContractError, sha256_file
from app.model_preflight import run_preflight
from tests.test_model_contract import (
    REGISTRY_PATH,
    S1_TEMPLATE_PATH,
    S2_TEMPLATE_PATH,
    materialize_manifest,
    model_status,
)


class ModelPreflightTest(unittest.TestCase):
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
        weight_path.write_bytes(b"deterministic-test-weight")
        manifest = materialize_manifest(template_path, weight_path)
        manifest_path = self.root / "models/manifests" / f"{weight_path.stem}.manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return manifest_path, weight_path, manifest

    def test_s1_activation_preflight_passes_without_gpu_inference(self) -> None:
        manifest_path, weight_path, manifest = self._materialize(
            S1_TEMPLATE_PATH,
            "yolo26m-visdrone-s1-best.pt",
        )
        result = run_preflight(
            root=self.root,
            manifest_path=manifest_path,
            weight_path=weight_path,
            activation=True,
            status_loader=lambda path: model_status(manifest, path),
        )
        self.assertTrue(result["success"])
        contract = result["contract"]
        self.assertIsInstance(contract, dict)
        assert isinstance(contract, dict)
        self.assertEqual(contract["profile"], "AERIAL_SMALL_OBJECT_LIVE")
        self.assertEqual(contract["trainingStage"], "VISDRONE_S1")

    def test_relative_paths_are_resolved_from_explicit_root(self) -> None:
        manifest_path, weight_path, manifest = self._materialize(
            S2_TEMPLATE_PATH,
            "yolo26m-visdrone-s2-best.pt",
        )
        result = run_preflight(
            root=self.root,
            manifest_path=manifest_path.relative_to(self.root),
            weight_path=weight_path.relative_to(self.root),
            profiles_path=Path("config/model-profiles-v1.json"),
            status_loader=lambda path: model_status(manifest, path),
        )
        self.assertTrue(result["success"])

    def test_s2_activation_preflight_is_rejected(self) -> None:
        manifest_path, weight_path, manifest = self._materialize(
            S2_TEMPLATE_PATH,
            "yolo26m-visdrone-s2-best.pt",
        )
        with self.assertRaisesRegex(ModelContractError, "LIVE 활성화"):
            run_preflight(
                root=self.root,
                manifest_path=manifest_path,
                weight_path=weight_path,
                activation=True,
                status_loader=lambda path: model_status(manifest, path),
            )

    def test_path_outside_project_root_is_rejected(self) -> None:
        manifest_path, weight_path, manifest = self._materialize(
            S2_TEMPLATE_PATH,
            "yolo26m-visdrone-s2-best.pt",
        )
        outside = self.root.parent / "outside-weight.pt"
        outside.write_bytes(b"outside")
        self.addCleanup(outside.unlink)
        with self.assertRaisesRegex(ModelContractError, "루트 안"):
            run_preflight(
                root=self.root,
                manifest_path=manifest_path,
                weight_path=outside,
                status_loader=lambda path: model_status(manifest, weight_path),
            )

    def test_status_hash_mismatch_is_rejected(self) -> None:
        manifest_path, weight_path, manifest = self._materialize(
            S2_TEMPLATE_PATH,
            "yolo26m-visdrone-s2-best.pt",
        )
        status = model_status(manifest, weight_path)
        status["sha256"] = "f" * 64
        self.assertNotEqual(status["sha256"], sha256_file(weight_path))
        with self.assertRaisesRegex(ModelContractError, "크기 또는 SHA-256"):
            run_preflight(
                root=self.root,
                manifest_path=manifest_path,
                weight_path=weight_path,
                status_loader=lambda path: status,
            )


if __name__ == "__main__":
    unittest.main()
