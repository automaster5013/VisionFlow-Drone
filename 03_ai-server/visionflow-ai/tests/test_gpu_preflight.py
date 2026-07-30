from __future__ import annotations

import unittest

from app.gpu_preflight import validate_model_status


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


if __name__ == "__main__":
    unittest.main()
