from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compare_visionflow_ai_benchmarks import build_comparison


def _summary(
    *,
    profile: str,
    model_sha256: str,
    average_inference_ms: float,
    p95_inference_ms: float,
    processing_fps: float,
    input_fps: float = 10.0,
) -> dict[str, object]:
    return {
        "benchmarkValid": True,
        "benchmarkId": profile,
        "hardwareLabel": "HP-OMEN",
        "inputAssetName": "benchmark.mp4",
        "inputAssetSha256": "f" * 64,
        "modelProfile": profile,
        "modelName": f"{profile}.pt",
        "modelSha256": model_sha256,
        "deviceEffective": "cuda:0",
        "cudaDeviceName": "NVIDIA GeForce RTX 5060 Laptop GPU",
        "sourceType": "SMARTPHONE_LIVE",
        "durationSeconds": 60,
        "imageSize": 640,
        "confidence": 0.35,
        "iou": 0.70,
        "averageInputFps": input_fps,
        "averageProcessingFps": processing_fps,
        "averageInferenceMs": average_inference_ms,
        "maximumObservedP95InferenceMs": p95_inference_ms,
        "droppedFrameDelta": 0,
    }


class BenchmarkComparisonTest(unittest.TestCase):
    def test_candidate_faster_when_conditions_match(self) -> None:
        baseline = _summary(
            profile="yolo26n-gpu",
            model_sha256="a" * 64,
            average_inference_ms=20.0,
            p95_inference_ms=25.0,
            processing_fps=10.0,
        )
        candidate = _summary(
            profile="best-gpu",
            model_sha256="b" * 64,
            average_inference_ms=15.0,
            p95_inference_ms=19.0,
            processing_fps=10.2,
        )

        comparison = build_comparison(baseline, candidate)

        self.assertTrue(comparison["comparisonValid"])
        self.assertEqual(comparison["verdict"], "CANDIDATE_FASTER")
        self.assertEqual(comparison["fairnessFailures"], [])

    def test_input_rate_mismatch_invalidates_comparison(self) -> None:
        baseline = _summary(
            profile="yolo26n-gpu",
            model_sha256="a" * 64,
            average_inference_ms=20.0,
            p95_inference_ms=25.0,
            processing_fps=10.0,
            input_fps=10.0,
        )
        candidate = _summary(
            profile="best-gpu",
            model_sha256="b" * 64,
            average_inference_ms=15.0,
            p95_inference_ms=19.0,
            processing_fps=5.0,
            input_fps=5.0,
        )

        comparison = build_comparison(baseline, candidate)

        self.assertFalse(comparison["comparisonValid"])
        self.assertEqual(comparison["verdict"], "INVALID_COMPARISON")
        self.assertIn("INPUT_RATE_MISMATCH", comparison["fairnessFailures"])


if __name__ == "__main__":
    unittest.main()
