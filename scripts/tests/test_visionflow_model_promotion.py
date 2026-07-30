from __future__ import annotations

import json
import unittest
from datetime import timedelta
from pathlib import Path

from scripts.tests import test_visionflow_hp_omen_restore as hp_test
from scripts.compare_visionflow_ai_benchmarks import build_comparison
from scripts.visionflow_hp_omen_restore import sha256_file
from scripts.visionflow_model_promotion import (
    BLOCKED_STATUS,
    READY_STATUS,
    REVIEW_STATUS,
    ModelPromotionError,
    build_plan,
    build_report,
    verify_report,
    write_report,
)

NOW = hp_test.NOW


def write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    return path


def benchmark_summary(
    *,
    model_name: str,
    model_sha256: str,
    average_inference_ms: float,
    p95_inference_ms: float,
    processing_fps: float,
    dropped_frames: int = 0,
) -> dict[str, object]:
    return {
        "benchmarkValid": True,
        "benchmarkId": model_name,
        "runLabel": model_name,
        "hardwareLabel": "HP-OMEN-RTX-5060",
        "inputAssetName": "fixed-demo-video.mp4",
        "inputAssetSha256": "f" * 64,
        "modelProfile": model_name.removesuffix(".pt"),
        "modelName": model_name,
        "modelSha256": model_sha256,
        "modelClassCount": 8,
        "deviceEffective": "cuda:0",
        "cudaDeviceName": "NVIDIA GeForce RTX 5060 Laptop GPU",
        "sourceType": "FILE",
        "durationSeconds": 60,
        "imageSize": 640,
        "confidence": 0.35,
        "iou": 0.70,
        "averageInputFps": 10.0,
        "averageProcessingFps": processing_fps,
        "averageInferenceMs": average_inference_ms,
        "maximumObservedP95InferenceMs": p95_inference_ms,
        "droppedFrameDelta": dropped_frames,
    }


class ModelPromotionTest(unittest.TestCase):
    def setUp(self) -> None:
        hp_fixture = hp_test.HpOmenRestoreTest(methodName="runTest")
        hp_fixture.setUp()
        self.addCleanup(hp_fixture.doCleanups)
        self.hp = hp_fixture
        self.hp.prepare()
        self.hp.make_activation_ready()
        self.activation_path, activation, exit_code = self.hp.activate(
            hp_test.FakeActivationRunner(self.hp.destination)
        )
        self.assertEqual(0, exit_code)
        self.root = self.hp.destination
        self.model_path = (
            self.root / "03_ai-server/visionflow-ai/models/best.pt"
        )
        self.model_sha256 = sha256_file(self.model_path)
        self.baseline_model_path = self.model_path.with_name("yolo26n.pt")
        self.baseline_model_path.write_bytes(b"baseline-yolo26n-model")
        self.baseline_model_sha256 = sha256_file(self.baseline_model_path)
        self.now = NOW + timedelta(hours=1)
        self.assertEqual(self.model_sha256, activation["model"]["sha256"])
        self.comparison_path = self.write_comparison()
        self.accuracy_path = self.write_accuracy()

    def write_comparison(
        self,
        *,
        baseline_latency: float = 20.0,
        candidate_latency: float = 15.0,
        baseline_processing: float = 10.0,
        candidate_processing: float = 10.2,
        candidate_dropped: int = 0,
    ) -> Path:
        baseline = benchmark_summary(
            model_name="yolo26n.pt",
            model_sha256=self.baseline_model_sha256,
            average_inference_ms=baseline_latency,
            p95_inference_ms=baseline_latency + 5.0,
            processing_fps=baseline_processing,
        )
        candidate = benchmark_summary(
            model_name="best.pt",
            model_sha256=self.model_sha256,
            average_inference_ms=candidate_latency,
            p95_inference_ms=candidate_latency + 4.0,
            processing_fps=candidate_processing,
            dropped_frames=candidate_dropped,
        )
        comparison = build_comparison(baseline, candidate)
        comparison["generatedAt"] = (
            NOW + timedelta(minutes=10)
        ).isoformat()
        return write_json(
            self.root
            / "artifacts/ai-benchmark-comparison/"
            "visionflow-ai-comparison-20260724-011000.json",
            comparison,
        )

    def write_accuracy(
        self,
        *,
        gate_status: str = "PASSED",
        mapping_status: str = "VALID",
        missing_labels: int = 0,
    ) -> Path:
        overall = {
            "precision": 0.90,
            "recall": 0.85,
            "map50": 0.92,
            "map75": 0.80,
            "map50_95": 0.72,
        }
        minimums = {
            "precision": 0.80,
            "recall": 0.80,
            "map50": 0.85,
            "map50_95": 0.65,
        }
        checks = [
            {
                "metric": key,
                "minimum": minimum,
                "actual": overall[key],
                "passed": overall[key] >= minimum,
            }
            for key, minimum in minimums.items()
        ]
        report = {
            "schemaVersion": 1,
            "generatedAt": (
                NOW + timedelta(minutes=20)
            ).isoformat(),
            "model": {
                "fileName": "best.pt",
                "sizeBytes": self.model_path.stat().st_size,
                "sha256": self.model_sha256,
            },
            "dataset": {
                "imageCount": 100,
                "labelFileCount": 100 - missing_labels,
                "missingLabelFileCount": missing_labels,
                "fingerprintSha256": "d" * 64,
            },
            "evaluation": {
                "device": "0",
                "runtime": {
                    "cudaAvailable": True,
                    "cudaDeviceName": (
                        "NVIDIA GeForce RTX 5060 Laptop GPU"
                    ),
                },
            },
            "qualityGate": {
                "status": gate_status,
                "checks": checks if gate_status == "PASSED" else [],
            },
            "classMapping": {
                "status": mapping_status,
                "providedPath": (
                    "03_ai-server/visionflow-ai/config/"
                    "best-model-classes.json"
                ),
                "errors": [] if mapping_status == "VALID" else ["review"],
            },
            "metrics": {"overall": overall},
        }
        return write_json(
            self.root
            / "artifacts/model-evaluation/best-20260724/"
            "evaluation-report.json",
            report,
        )

    def build(self) -> dict[str, object]:
        return build_report(
            root=self.root,
            activation_path=self.activation_path,
            comparison_path=self.comparison_path,
            accuracy_path=self.accuracy_path,
            model_path=self.model_path,
            now=self.now,
            activation_max_age_hours=24,
            comparison_max_age_hours=24,
            accuracy_max_age_hours=168,
        )

    def test_ready_report_writes_and_independently_verifies(self) -> None:
        report = self.build()
        self.assertEqual(READY_STATUS, report["status"])
        self.assertEqual(0, report["summary"]["failed"])
        report_path, _, _ = write_report(
            output_directory=self.root / "artifacts/model-promotion",
            report=report,
        )

        verified_path, verified = verify_report(
            root=self.root,
            report_path=report_path,
        )

        self.assertEqual(report_path, verified_path)
        self.assertEqual(report, verified)

    def test_measured_accuracy_without_thresholds_is_blocked(self) -> None:
        self.accuracy_path = self.write_accuracy(gate_status="MEASURED")

        report = self.build()

        self.assertEqual(BLOCKED_STATUS, report["status"])
        self.assertEqual(
            "FAILED",
            next(
                item["status"]
                for item in report["checks"]
                if item["key"] == "accuracy-quality-gate"
            ),
        )

    def test_performance_tradeoff_requires_human_review(self) -> None:
        self.comparison_path = self.write_comparison(
            candidate_latency=15.0,
            candidate_processing=8.0,
            candidate_dropped=0,
        )

        report = self.build()

        self.assertEqual(REVIEW_STATUS, report["status"])
        self.assertEqual("TRADE_OFF", report["performance"]["verdict"])

    def test_candidate_model_hash_mismatch_is_blocked(self) -> None:
        comparison = json.loads(
            self.comparison_path.read_text(encoding="utf-8-sig")
        )
        comparison["candidate"]["modelSha256"] = "b" * 64
        write_json(self.comparison_path, comparison)

        report = self.build()

        self.assertEqual(BLOCKED_STATUS, report["status"])

    def test_missing_dataset_label_is_blocked(self) -> None:
        self.accuracy_path = self.write_accuracy(missing_labels=1)

        report = self.build()

        self.assertEqual(BLOCKED_STATUS, report["status"])

    def test_report_sidecar_tamper_is_rejected(self) -> None:
        report_path, _, _ = write_report(
            output_directory=self.root / "artifacts/model-promotion",
            report=self.build(),
        )
        report_path.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(ModelPromotionError, "SHA-256"):
            verify_report(root=self.root, report_path=report_path)

    def test_changed_model_is_rejected_during_verify(self) -> None:
        report_path, _, _ = write_report(
            output_directory=self.root / "artifacts/model-promotion",
            report=self.build(),
        )
        self.model_path.write_bytes(b"changed-best-model")

        with self.assertRaisesRegex(
            ModelPromotionError,
            "다릅니다|동일성",
        ):
            verify_report(root=self.root, report_path=report_path)

    def test_plan_is_read_only_and_complete(self) -> None:
        plan = build_plan()

        self.assertEqual(5, len(plan))
        self.assertIn("SHA-256", plan[3])


if __name__ == "__main__":
    unittest.main()
