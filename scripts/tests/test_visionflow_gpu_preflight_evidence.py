from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.visionflow_gpu_preflight_evidence import (
    GpuPreflightEvidenceError,
    extract_json_object,
    sha256_file,
    verify_evidence,
    write_evidence,
)


class VisionFlowGpuPreflightEvidenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.model = (
            self.root
            / "03_ai-server"
            / "visionflow-ai"
            / "models"
            / "best.pt"
        )
        self.model.parent.mkdir(parents=True)
        self.model.write_bytes(b"visionflow-test-model")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def container_output(self) -> str:
        model_hash = sha256_file(self.model)
        value = {
            "success": True,
            "status": "GPU_MODEL_READY",
            "message": "ready",
            "model": {
                "profile": "best-gpu",
                "localFile": True,
                "sizeBytes": self.model.stat().st_size,
                "sha256": model_hash,
                "classCount": 3,
                "confidence": 0.35,
                "iou": 0.7,
                "imageSize": 640,
                "deviceRequested": "0",
                "deviceEffective": "cuda:0",
                "requireCuda": True,
                "torchVersion": "2.12.1+cu130",
                "torchCudaVersion": "13.0",
                "cudnnVersion": 91000,
                "cudaAvailable": True,
                "cudaDeviceCount": 1,
                "cudaDeviceIndex": 0,
                "cudaDeviceName": "NVIDIA GeForce RTX 5060 Laptop GPU",
                "cudaCapability": [12, 0],
                "cudaTotalMemoryBytes": 8589934592,
            },
        }
        return f"compose warning\n{json.dumps(value, ensure_ascii=False)}\n"

    def build(self) -> tuple[Path, Path, Path, dict[str, object]]:
        return write_evidence(
            root=self.root,
            model_path=self.model,
            expected_sha256=sha256_file(self.model),
            gpu_info="RTX 5060 Laptop GPU, 590.00, 8192 MiB\n",
            docker_info="29.6.1\n",
            container_output=self.container_output(),
            output_directory=self.root / "artifacts" / "gpu-readiness",
            now=datetime(2026, 7, 25, 1, 2, 3, tzinfo=timezone.utc),
        )

    def test_mixed_compose_output_extracts_container_json(self) -> None:
        result = extract_json_object(self.container_output())
        self.assertTrue(result["success"])
        self.assertEqual("GPU_MODEL_READY", result["status"])

    def test_build_and_independent_verify(self) -> None:
        json_path, html_path, sidecar, report = self.build()

        self.assertEqual("GPU_MODEL_READY", report["status"])
        self.assertEqual("best.pt", report["model"]["fileName"])
        self.assertNotIn(str(self.root), json_path.read_text(encoding="utf-8-sig"))
        self.assertTrue(html_path.is_file())
        self.assertTrue(sidecar.is_file())

        verified_path, verified = verify_evidence(
            root=self.root,
            report_path=json_path,
        )
        self.assertEqual(json_path, verified_path)
        self.assertEqual("GPU_MODEL_READY", verified["status"])

    def test_host_container_hash_mismatch_is_rejected(self) -> None:
        output = json.loads(self.container_output().splitlines()[-1])
        output["model"]["sha256"] = "b" * 64

        with self.assertRaisesRegex(
            GpuPreflightEvidenceError,
            "SHA-256이 다릅니다",
        ):
            write_evidence(
                root=self.root,
                model_path=self.model,
                expected_sha256=sha256_file(self.model),
                gpu_info="RTX 5060\n",
                docker_info="29.6.1\n",
                container_output=json.dumps(output),
                output_directory=self.root / "artifacts",
            )

    def test_tampered_report_fails_verification(self) -> None:
        json_path, _, _, _ = self.build()
        json_path.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(
            GpuPreflightEvidenceError,
            "SHA-256이 다릅니다",
        ):
            verify_evidence(root=self.root, report_path=json_path)

    def test_changed_model_fails_independent_verification(self) -> None:
        json_path, _, _, _ = self.build()
        self.model.write_bytes(b"changed-model")

        with self.assertRaisesRegex(
            GpuPreflightEvidenceError,
            "현재 모델 파일",
        ):
            verify_evidence(root=self.root, report_path=json_path)

    def test_output_outside_project_is_rejected(self) -> None:
        outside = self.root.parent / "outside-gpu-evidence"

        with self.assertRaisesRegex(
            GpuPreflightEvidenceError,
            "프로젝트 밖",
        ):
            write_evidence(
                root=self.root,
                model_path=self.model,
                expected_sha256=sha256_file(self.model),
                gpu_info="RTX 5060\n",
                docker_info="29.6.1\n",
                container_output=self.container_output(),
                output_directory=outside,
            )


if __name__ == "__main__":
    unittest.main()
