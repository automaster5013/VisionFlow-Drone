from __future__ import annotations

import json
import unittest
from datetime import timedelta
from pathlib import Path

from scripts.tests import test_visionflow_model_release as release_test
from scripts.visionflow_model_release import (
    ACTIVATION_CONFIRMATION,
    execute_activation,
)
from scripts.visionflow_model_soak import (
    BLOCKED_STATUS,
    PASSED_STATUS,
    CommandResult,
    ModelSoakError,
    build_plan,
    build_report,
    default_policy,
    run_benchmark,
    verify_report,
    write_report,
)
from scripts.visionflow_model_promotion import sha256_file


NOW = release_test.NOW + timedelta(hours=1)


def write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    return path


class ModelSoakTest(unittest.TestCase):
    def setUp(self) -> None:
        fixture = release_test.ModelReleaseTest(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.root = fixture.root
        (
            self.activation_path,
            self.activation,
            exit_code,
        ) = execute_activation(
            root=self.root,
            release_report_path=fixture.release_path,
            confirmation=ACTIVATION_CONFIRMATION,
            timeout_seconds=300,
            now=release_test.NOW,
            runner=release_test.FakeReleaseRunner(),
            platform_name="nt",
        )
        self.assertEqual(0, exit_code)
        self.input_file = (
            self.root / "03_ai-server/visionflow-ai/data/dummy/soak.mp4"
        )
        self.input_file.parent.mkdir(parents=True, exist_ok=True)
        self.input_file.write_bytes(b"fixed-soak-video")
        (self.root / ".env.docker").write_text(
            "\n".join(
                (
                    "MYSQL_PASSWORD=fixture",
                    "AI_SOURCE_TYPE=DUMMY_VIDEO",
                    "AI_DUMMY_VIDEO_PATH=/app/data/dummy/soak.mp4",
                    "",
                )
            ),
            encoding="utf-8",
        )
        (self.root / "scripts/visionflow-ai-benchmark.ps1").write_text(
            "Write-Host fixture\n",
            encoding="utf-8",
        )
        self.benchmark_path = self.write_benchmark()

    def benchmark_value(self) -> dict[str, object]:
        started_at = NOW - timedelta(minutes=10)
        return {
            "benchmarkVersion": 2,
            "benchmarkId": "best-post-release-soak",
            "runLabel": "best-post-release-soak",
            "generatedAt": (
                started_at + timedelta(seconds=300)
            ).isoformat(),
            "startedAt": started_at.isoformat(),
            "durationSeconds": 300,
            "warmupSeconds": 15,
            "intervalMilliseconds": 1000,
            "sampleCount": 280,
            "hardwareLabel": "HP-OMEN-RTX-5060",
            "inputAssetName": self.input_file.name,
            "inputAssetSha256": sha256_file(self.input_file),
            "inputAssetSizeBytes": self.input_file.stat().st_size,
            "modelProfile": "best-gpu",
            "modelName": "best.pt",
            "modelSha256": self.activation["activeModel"]["sha256"],
            "modelSizeBytes": self.fixture.fixture.model_path.stat().st_size,
            "modelClassCount": 8,
            "device": "cuda:0",
            "deviceEffective": "cuda:0",
            "cudaAvailable": True,
            "cudaDeviceName": "NVIDIA GeForce RTX 5060 Laptop GPU",
            "sourceType": "DUMMY_VIDEO",
            "benchmarkValid": True,
            "finalHealthStatus": "HEALTHY",
            "observedHealthStatuses": ["HEALTHY"],
            "processedFrameDelta": 2940,
            "acceptedFrameDelta": 3000,
            "droppedFrameDelta": 10,
            "averageInputFps": 10.0,
            "averageProcessingFps": 9.8,
            "averageInferenceMs": 17.0,
            "maximumObservedP95InferenceMs": 22.0,
        }

    def write_benchmark(
        self,
        value: dict[str, object] | None = None,
        *,
        name: str = "visionflow-ai-benchmark-soak.json",
    ) -> Path:
        return write_json(
            self.root / "artifacts/model-soak/measurements" / name,
            value or self.benchmark_value(),
        )

    def build(self) -> dict[str, object]:
        return build_report(
            root=self.root,
            activation_path=self.activation_path,
            benchmark_path=self.benchmark_path,
            now=NOW,
            **default_policy(),
        )

    def test_passing_soak_writes_and_independently_verifies(self) -> None:
        report = self.build()
        self.assertEqual(PASSED_STATUS, report["status"])
        self.assertEqual(0, report["summary"]["failed"])
        report_path, _, _ = write_report(
            output_directory=self.root / "artifacts/model-soak",
            report=report,
        )

        verified_path, verified = verify_report(
            root=self.root,
            report_path=report_path,
        )

        self.assertEqual(report_path, verified_path)
        self.assertEqual(report, verified)

    def test_average_latency_regression_is_blocked(self) -> None:
        benchmark = self.benchmark_value()
        benchmark["averageInferenceMs"] = 19.0
        self.benchmark_path = self.write_benchmark(benchmark)

        report = self.build()

        self.assertEqual(BLOCKED_STATUS, report["status"])
        self.assertEqual(
            "FAILED",
            next(
                item["status"]
                for item in report["checks"]
                if item["key"] == "average-latency"
            ),
        )

    def test_model_hash_mismatch_is_blocked(self) -> None:
        benchmark = self.benchmark_value()
        benchmark["modelSha256"] = "a" * 64
        self.benchmark_path = self.write_benchmark(benchmark)

        report = self.build()

        self.assertEqual(BLOCKED_STATUS, report["status"])

    def test_missing_input_identity_is_blocked(self) -> None:
        benchmark = self.benchmark_value()
        benchmark["inputAssetSha256"] = ""
        benchmark["inputAssetName"] = ""
        self.benchmark_path = self.write_benchmark(benchmark)

        report = self.build()

        self.assertEqual(BLOCKED_STATUS, report["status"])

    def test_short_measurement_timeline_is_blocked(self) -> None:
        benchmark = self.benchmark_value()
        benchmark["generatedAt"] = (
            NOW - timedelta(minutes=9, seconds=50)
        ).isoformat()
        self.benchmark_path = self.write_benchmark(benchmark)

        report = self.build()

        self.assertEqual(BLOCKED_STATUS, report["status"])

    def test_changed_benchmark_invalidates_saved_report(self) -> None:
        report_path, _, _ = write_report(
            output_directory=self.root / "artifacts/model-soak",
            report=self.build(),
        )
        benchmark = self.benchmark_value()
        benchmark["droppedFrameDelta"] = 99
        self.write_benchmark(benchmark)

        with self.assertRaisesRegex(ModelSoakError, "동일성"):
            verify_report(root=self.root, report_path=report_path)

    def test_report_tamper_is_rejected_by_sidecar(self) -> None:
        report_path, _, _ = write_report(
            output_directory=self.root / "artifacts/model-soak",
            report=self.build(),
        )
        report_path.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "SHA-256"):
            verify_report(root=self.root, report_path=report_path)

    def test_run_benchmark_accepts_exactly_one_new_measurement(self) -> None:
        benchmark = self.benchmark_value()

        def runner(command, _root, _timeout_seconds):
            output_index = command.index("-OutputDirectory") + 1
            output_directory = Path(command[output_index])
            write_json(
                output_directory / "visionflow-ai-benchmark-new.json",
                benchmark,
            )
            return CommandResult(0, "benchmark passed\n", 300000)

        created = run_benchmark(
            root=self.root,
            activation_path=self.activation_path,
            input_file=self.input_file,
            duration_seconds=300,
            warmup_seconds=15,
            interval_milliseconds=1000,
            runner=runner,
            platform_name="nt",
        )

        self.assertEqual(
            "visionflow-ai-benchmark-new.json",
            created.name,
        )

    def test_run_refuses_mismatched_dummy_source_before_runner(self) -> None:
        (self.root / ".env.docker").write_text(
            "AI_SOURCE_TYPE=SMARTPHONE_LIVE\n",
            encoding="utf-8",
        )
        calls: list[object] = []

        def runner(*args):
            calls.append(args)
            return CommandResult(0)

        with self.assertRaisesRegex(ModelSoakError, "AI_SOURCE_TYPE"):
            run_benchmark(
                root=self.root,
                activation_path=self.activation_path,
                input_file=self.input_file,
                duration_seconds=300,
                warmup_seconds=15,
                interval_milliseconds=1000,
                runner=runner,
                platform_name="nt",
            )

        self.assertEqual([], calls)

    def test_plan_is_read_only_and_covers_health(self) -> None:
        plan = build_plan()

        self.assertEqual(6, len(plan))
        self.assertIn("HEALTHY", plan[4])


if __name__ == "__main__":
    unittest.main()
