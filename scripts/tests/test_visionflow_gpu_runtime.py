from __future__ import annotations

import unittest
from pathlib import Path


class VisionFlowGpuRuntimeContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[2]

    def read(self, relative: str) -> str:
        return (self.root / relative).read_text(encoding="utf-8")

    def test_gpu_compose_requires_cuda_and_model_hash(self) -> None:
        compose = self.read("compose.gpu.yaml")
        self.assertIn('AI_REQUIRE_CUDA: "true"', compose)
        self.assertIn('AI_REQUIRE_LOCAL_MODEL: "true"', compose)
        self.assertIn("AI_EXPECTED_MODEL_SHA256", compose)
        self.assertIn("capabilities: [gpu]", compose)

    def test_dockerfile_uses_cuda_wheel_build_arguments(self) -> None:
        dockerfile = self.read(
            "03_ai-server/visionflow-ai/Dockerfile"
        )
        self.assertIn("ARG TORCH_VERSION=", dockerfile)
        self.assertIn("ARG TORCHVISION_VERSION=", dockerfile)
        self.assertIn("ARG TORCH_INDEX_URL=", dockerfile)
        self.assertIn('"torch==${TORCH_VERSION}"', dockerfile)

    def test_detector_performs_real_cuda_allocation_and_model_move(
        self,
    ) -> None:
        detector = self.read(
            "03_ai-server/visionflow-ai/app/inference/"
            "yolo_detector.py"
        )
        self.assertIn("torch.ones(", detector)
        self.assertIn("self._model.to(effective_device)", detector)
        self.assertIn("torch.cuda.synchronize(device_index)", detector)

    def test_host_hash_is_forwarded_to_container_preflight(self) -> None:
        preflight = self.read(
            "scripts/visionflow-gpu-preflight.ps1"
        )
        hash_position = preflight.index(
            "$env:AI_EXPECTED_MODEL_SHA256"
        )
        run_position = preflight.index('"app.gpu_preflight"')
        self.assertLess(hash_position, run_position)
        self.assertIn("Get-FileHash", preflight)

    def test_successful_preflight_creates_verifiable_evidence(self) -> None:
        preflight = self.read(
            "scripts/visionflow-gpu-preflight.ps1"
        )
        evidence = self.read(
            "scripts/visionflow_gpu_preflight_evidence.py"
        )
        self.assertIn("visionflow_gpu_preflight_evidence.py", preflight)
        self.assertIn('"--expected-sha256"', preflight)
        self.assertIn('"--container-output"', preflight)
        self.assertIn("GPU_MODEL_PREFLIGHT", evidence)
        self.assertIn("GPU_MODEL_READY", evidence)
        verify_batch = self.read(
            "scripts/run-visionflow-gpu-preflight-verify.bat"
        )
        self.assertIn("visionflow_gpu_preflight_evidence.py", verify_batch)
        self.assertIn(" verify ", verify_batch)

    def test_local_ai_tests_are_an_explicit_package(self) -> None:
        marker = (
            self.root
            / "03_ai-server"
            / "visionflow-ai"
            / "tests"
            / "__init__.py"
        )
        self.assertTrue(marker.is_file())
        self.assertIn("third-party", marker.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
