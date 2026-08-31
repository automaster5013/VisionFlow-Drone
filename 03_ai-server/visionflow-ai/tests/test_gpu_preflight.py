from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.gpu_preflight import validate_contract_status, validate_model_status
from tests.test_model_contract import (
    REGISTRY_PATH,
    S1_TEMPLATE_PATH,
    materialize_manifest,
    model_status,
)


def valid_status() -> dict[str, object]:
    return {
        "localFile": True,
        "cudaAvailable": True,
        "requireCuda": True,
        "deviceEffective": "cuda:0",
        "sha256": "a" * 64,
    }


class GpuPreflightStatusTest(unittest.TestCase):
    def test_valid_cuda_model_status_passes(self) -> None:
        validate_model_status(
            valid_status(),
            expected_sha256="A" * 64,
        )

    def test_cpu_fallback_is_rejected(self) -> None:
        status = valid_status()
        status["deviceEffective"] = "cpu"

        with self.assertRaisesRegex(RuntimeError, "CUDA가 아닙니다"):
            validate_model_status(
                status,
                expected_sha256="a" * 64,
            )

    def test_host_container_hash_mismatch_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "SHA-256이 다릅니다"):
            validate_model_status(
                valid_status(),
                expected_sha256="b" * 64,
            )

    def test_invalid_container_hash_is_rejected(self) -> None:
        status = valid_status()
        status["sha256"] = "not-a-sha256"

        with self.assertRaisesRegex(RuntimeError, "올바르지 않습니다"):
            validate_model_status(
                status,
                expected_sha256="",
            )


class GpuPreflightContractTest(unittest.TestCase):
    def test_aerial_profile_requires_manifest(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "매니페스트가 필요"):
            validate_contract_status(
                valid_status(),
                model_profile="AERIAL_SMALL_OBJECT_LIVE",
                manifest_path="",
            )

    def test_legacy_profile_remains_compatible_without_manifest(self) -> None:
        result = validate_contract_status(
            valid_status(),
            model_profile="best-gpu",
            manifest_path="",
        )
        self.assertIsNone(result)

    def test_s1_manifest_and_loaded_status_pass_activation_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            weight_path = root / "yolo26m-visdrone-s1-best.pt"
            weight_path.write_bytes(b"gpu-contract-test-weight")
            manifest = materialize_manifest(S1_TEMPLATE_PATH, weight_path)
            manifest_path = root / "yolo26m-visdrone-s1-best.manifest.json"
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False),
                encoding="utf-8",
            )
            contract = validate_contract_status(
                model_status(manifest, weight_path),
                model_profile="AERIAL_SMALL_OBJECT_LIVE",
                manifest_path=str(manifest_path),
                profiles_path=str(REGISTRY_PATH),
            )
            assert contract is not None
            self.assertEqual(contract["trainingStage"], "VISDRONE_S1")


if __name__ == "__main__":
    unittest.main()
