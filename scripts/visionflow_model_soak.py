"""Run and verify the VisionFlow post-release AI model soak gate."""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

try:
    from visionflow_model_promotion import (
        ModelPromotionError,
        artifact_entry,
        is_checksum,
        is_within,
        metric,
        newest_artifact,
        parse_timestamp,
        read_json,
        resolve_inside,
        sha256_file,
    )
    from visionflow_model_release import (
        ACTIVATED_STATUS,
        ModelReleaseError,
        verify_activation_report,
        write_sidecar,
        verify_sidecar,
    )
except ModuleNotFoundError:  # pragma: no cover - package import during tests
    from scripts.visionflow_model_promotion import (
        ModelPromotionError,
        artifact_entry,
        is_checksum,
        is_within,
        metric,
        newest_artifact,
        parse_timestamp,
        read_json,
        resolve_inside,
        sha256_file,
    )
    from scripts.visionflow_model_release import (
        ACTIVATED_STATUS,
        ModelReleaseError,
        verify_activation_report,
        write_sidecar,
        verify_sidecar,
    )


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
OPERATION = "MODEL_POST_RELEASE_SOAK"
PASSED_STATUS = "MODEL_SOAK_PASSED"
BLOCKED_STATUS = "MODEL_SOAK_BLOCKED"
DEFAULT_OUTPUT = Path("artifacts/model-soak")
MEASUREMENT_DIRECTORY = DEFAULT_OUTPUT / "measurements"
ACTIVATION_PATTERN = (
    "artifacts/model-release/activation-*/"
    "visionflow-model-release-activation.json"
)
BENCHMARK_PATTERN = (
    "artifacts/model-soak/measurements/"
    "visionflow-ai-benchmark-*.json"
)
BENCHMARK_SCRIPT = Path("scripts/visionflow-ai-benchmark.ps1")
DUMMY_VIDEO_DIRECTORY = Path("03_ai-server/visionflow-ai/data/dummy")
BASE_ENVIRONMENT = Path(".env.docker")
DEFAULT_DURATION_SECONDS = 300
DEFAULT_WARMUP_SECONDS = 15
DEFAULT_INTERVAL_MILLISECONDS = 1000


class ModelSoakError(RuntimeError):
    """Raised when soak evidence is missing, stale, or inconsistent."""


class CommandResult:
    def __init__(
        self,
        exit_code: int,
        output: str = "",
        duration_ms: int = 0,
    ) -> None:
        self.exit_code = exit_code
        self.output = output
        self.duration_ms = duration_ms


Runner = Callable[[Sequence[str], Path, int], CommandResult]


def default_runner(
    command: Sequence[str],
    root: Path,
    timeout_seconds: int,
) -> CommandResult:
    started = time.monotonic()
    completed = subprocess.run(
        list(command),
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        check=False,
    )
    return CommandResult(
        completed.returncode,
        (completed.stdout or "") + (completed.stderr or ""),
        round((time.monotonic() - started) * 1000),
    )


def check(
    items: list[dict[str, Any]],
    *,
    key: str,
    title: str,
    passed: bool,
    detail: str,
) -> None:
    items.append(
        {
            "key": key,
            "title": title,
            "status": "PASS" if passed else "FAILED",
            "detail": detail,
        }
    )


def mapping_path(
    root: Path,
    value: object,
    title: str,
) -> Path:
    if not isinstance(value, Mapping) or not isinstance(
        value.get("path"),
        str,
    ):
        raise ModelSoakError(f"{title} 연결 경로가 없습니다.")
    path = resolve_inside(root, value["path"], title)
    if (
        value.get("sizeBytes") != path.stat().st_size
        or value.get("sha256") != sha256_file(path)
    ):
        raise ModelSoakError(f"{title} 동일성이 다릅니다.")
    return path


def promotion_reference(
    root: Path,
    activation: Mapping[str, Any],
) -> tuple[Path, dict[str, Any]]:
    release_path = mapping_path(
        root,
        activation.get("release"),
        "모델 릴리스 준비 보고서",
    )
    release = read_json(release_path, "모델 릴리스 준비 보고서")
    promotion_path = mapping_path(
        root,
        release.get("promotion"),
        "모델 승격 보고서",
    )
    promotion = read_json(promotion_path, "모델 승격 보고서")
    return promotion_path, promotion


def benchmark_numbers(benchmark: Mapping[str, Any]) -> dict[str, float]:
    integer_fields = (
        "durationSeconds",
        "intervalMilliseconds",
        "sampleCount",
        "processedFrameDelta",
        "acceptedFrameDelta",
        "droppedFrameDelta",
    )
    for key in integer_fields:
        value = benchmark.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ModelSoakError(
                f"소크 벤치마크 {key} 값은 정수여야 합니다."
            )
    values = {
        key: metric(benchmark.get(key), f"소크 벤치마크 {key}")
        for key in (
            "durationSeconds",
            "intervalMilliseconds",
            "sampleCount",
            "processedFrameDelta",
            "acceptedFrameDelta",
            "droppedFrameDelta",
            "averageInputFps",
            "averageProcessingFps",
            "averageInferenceMs",
            "maximumObservedP95InferenceMs",
        )
    }
    non_negative = (
        "sampleCount",
        "processedFrameDelta",
        "acceptedFrameDelta",
        "droppedFrameDelta",
        "averageInputFps",
        "averageProcessingFps",
        "averageInferenceMs",
        "maximumObservedP95InferenceMs",
    )
    if (
        values["durationSeconds"] <= 0
        or values["intervalMilliseconds"] <= 0
        or any(values[key] < 0 for key in non_negative)
    ):
        raise ModelSoakError("소크 벤치마크 숫자 범위가 올바르지 않습니다.")
    return values


def reference_numbers(promotion: Mapping[str, Any]) -> dict[str, float]:
    performance = promotion.get("performance")
    metrics = (
        performance.get("metrics")
        if isinstance(performance, Mapping)
        else None
    )
    if not isinstance(metrics, Mapping):
        raise ModelSoakError("승격 성능 기준이 없습니다.")
    values: dict[str, float] = {}
    for source_key, result_key in (
        ("averageInferenceMs", "averageInferenceMs"),
        (
            "maximumObservedP95InferenceMs",
            "maximumObservedP95InferenceMs",
        ),
    ):
        source = metrics.get(source_key)
        if not isinstance(source, Mapping):
            raise ModelSoakError(f"승격 성능 기준이 없습니다: {source_key}")
        value = metric(source.get("candidate"), f"{source_key}.candidate")
        if value <= 0:
            raise ModelSoakError(f"승격 성능 기준이 0 이하입니다: {source_key}")
        values[result_key] = value
    return values


def age_hours(now: datetime, generated_at: object, title: str) -> float:
    timestamp = parse_timestamp(generated_at, title)
    age = now.astimezone(timezone.utc) - timestamp
    if age < -timedelta(minutes=5):
        raise ModelSoakError(f"{title} 생성 시각이 미래입니다.")
    return max(0.0, age.total_seconds() / 3600.0)


def drop_rate(values: Mapping[str, float]) -> float:
    denominator = max(
        values["processedFrameDelta"] + values["droppedFrameDelta"],
        values["acceptedFrameDelta"] + values["droppedFrameDelta"],
    )
    if denominator <= 0:
        return 100.0 if values["droppedFrameDelta"] > 0 else 0.0
    return values["droppedFrameDelta"] / denominator * 100.0


def build_report(
    *,
    root: Path,
    activation_path: Path,
    benchmark_path: Path,
    now: datetime,
    min_duration_seconds: float,
    min_input_fps: float,
    min_processing_ratio: float,
    max_drop_rate_pct: float,
    max_average_regression_pct: float,
    max_p95_regression_pct: float,
    min_sample_coverage_pct: float,
    activation_max_age_hours: float,
    benchmark_max_age_hours: float,
    metrics_reset_by_runner: bool = False,
    soak_id: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    try:
        activation_path, activation = verify_activation_report(
            root=root,
            report_path=activation_path,
        )
    except (ModelReleaseError, OSError) as error:
        raise ModelSoakError(str(error)) from error
    benchmark_path = resolve_inside(root, benchmark_path, "소크 벤치마크")
    benchmark = read_json(benchmark_path, "소크 벤치마크")
    promotion_path, promotion = promotion_reference(root, activation)
    values = benchmark_numbers(benchmark)
    reference = reference_numbers(promotion)
    checks: list[dict[str, Any]] = []

    activation_ready = activation.get("status") == ACTIVATED_STATUS
    check(
        checks,
        key="release-activation",
        title="승격 모델 활성화",
        passed=activation_ready,
        detail=str(activation.get("status")),
    )

    activation_age = age_hours(
        now,
        activation.get("generatedAt"),
        "모델 릴리스 실행",
    )
    check(
        checks,
        key="activation-freshness",
        title="활성화 최신성",
        passed=activation_age <= activation_max_age_hours,
        detail=(
            f"{activation_age:.2f}시간 / "
            f"{activation_max_age_hours:.2f}시간"
        ),
    )
    benchmark_age = age_hours(
        now,
        benchmark.get("generatedAt"),
        "소크 벤치마크",
    )
    check(
        checks,
        key="benchmark-freshness",
        title="소크 증적 최신성",
        passed=benchmark_age <= benchmark_max_age_hours,
        detail=(
            f"{benchmark_age:.2f}시간 / "
            f"{benchmark_max_age_hours:.2f}시간"
        ),
    )
    activation_time = parse_timestamp(
        activation.get("generatedAt"),
        "모델 릴리스 실행",
    )
    benchmark_started = parse_timestamp(
        benchmark.get("startedAt"),
        "소크 벤치마크 시작",
    )
    benchmark_generated = parse_timestamp(
        benchmark.get("generatedAt"),
        "소크 벤치마크",
    )
    measured_seconds = (
        benchmark_generated - benchmark_started
    ).total_seconds()
    after_activation = (
        benchmark_started >= activation_time
        and measured_seconds >= values["durationSeconds"] - 5.0
        and measured_seconds <= values["durationSeconds"] + 120.0
    )
    check(
        checks,
        key="measurement-order",
        title="활성화 이후 측정",
        passed=after_activation,
        detail=(
            "승격 모델 활성화 이후 측정"
            if after_activation
            else "소크 측정 순서 또는 측정 시간 범위가 올바르지 않습니다."
        ),
    )

    active_model = activation.get("activeModel")
    active_sha = (
        active_model.get("sha256")
        if isinstance(active_model, Mapping)
        else None
    )
    model_ok = (
        isinstance(active_model, Mapping)
        and benchmark.get("modelName") == active_model.get("fileName")
        and benchmark.get("modelSha256") == active_sha
        and is_checksum(active_sha)
    )
    check(
        checks,
        key="model-identity",
        title="실행 모델 동일성",
        passed=model_ok,
        detail=(
            "활성화 best.pt SHA-256 일치"
            if model_ok
            else "소크 실행 모델과 활성화 모델이 다릅니다."
        ),
    )

    cuda_ok = (
        benchmark.get("cudaAvailable") is True
        and str(benchmark.get("deviceEffective", "")).startswith("cuda:")
        and str(benchmark.get("device", "")).lower() != "cpu"
    )
    check(
        checks,
        key="cuda-runtime",
        title="CUDA 실행",
        passed=cuda_ok,
        detail=str(benchmark.get("deviceEffective")),
    )

    benchmark_valid = (
        benchmark.get("benchmarkVersion") == 2
        and benchmark.get("benchmarkValid") is True
    )
    check(
        checks,
        key="benchmark-valid",
        title="벤치마크 유효성",
        passed=benchmark_valid,
        detail=(
            "benchmarkVersion=2 / valid=true"
            if benchmark_valid
            else "지원하는 유효 벤치마크가 아닙니다."
        ),
    )

    duration_ok = values["durationSeconds"] >= min_duration_seconds
    check(
        checks,
        key="duration",
        title="소크 측정 시간",
        passed=duration_ok,
        detail=(
            f"{values['durationSeconds']:.0f}초 / "
            f"최소 {min_duration_seconds:.0f}초"
        ),
    )
    expected_samples = (
        values["durationSeconds"]
        * 1000.0
        / values["intervalMilliseconds"]
    )
    sample_coverage = (
        values["sampleCount"] / expected_samples * 100.0
        if expected_samples > 0
        else 0.0
    )
    sample_ok = sample_coverage >= min_sample_coverage_pct
    check(
        checks,
        key="sample-coverage",
        title="메트릭 표본 커버리지",
        passed=sample_ok,
        detail=(
            f"{sample_coverage:.2f}% / "
            f"최소 {min_sample_coverage_pct:.2f}%"
        ),
    )

    input_ok = (
        values["processedFrameDelta"] > 0
        and values["averageInputFps"] >= min_input_fps
    )
    check(
        checks,
        key="input-load",
        title="실제 프레임 부하",
        passed=input_ok,
        detail=(
            f"processed={values['processedFrameDelta']:.0f}, "
            f"input={values['averageInputFps']:.2f} FPS"
        ),
    )
    processing_ratio = (
        values["averageProcessingFps"] / values["averageInputFps"]
        if values["averageInputFps"] > 0
        else 0.0
    )
    processing_ok = processing_ratio >= min_processing_ratio
    check(
        checks,
        key="processing-ratio",
        title="입력 대비 처리량",
        passed=processing_ok,
        detail=(
            f"{processing_ratio:.4f} / 최소 {min_processing_ratio:.4f}"
        ),
    )

    observed_drop_rate = drop_rate(values)
    drop_ok = observed_drop_rate <= max_drop_rate_pct
    check(
        checks,
        key="drop-rate",
        title="프레임 드롭률",
        passed=drop_ok,
        detail=(
            f"{observed_drop_rate:.4f}% / "
            f"최대 {max_drop_rate_pct:.4f}%"
        ),
    )

    average_limit = (
        reference["averageInferenceMs"]
        * (1.0 + max_average_regression_pct / 100.0)
    )
    average_ok = values["averageInferenceMs"] <= average_limit
    check(
        checks,
        key="average-latency",
        title="평균 추론 지연 회귀",
        passed=average_ok,
        detail=(
            f"{values['averageInferenceMs']:.2f}ms / "
            f"한계 {average_limit:.2f}ms"
        ),
    )
    p95_limit = (
        reference["maximumObservedP95InferenceMs"]
        * (1.0 + max_p95_regression_pct / 100.0)
    )
    p95_ok = values["maximumObservedP95InferenceMs"] <= p95_limit
    check(
        checks,
        key="p95-latency",
        title="P95 추론 지연 회귀",
        passed=p95_ok,
        detail=(
            f"{values['maximumObservedP95InferenceMs']:.2f}ms / "
            f"한계 {p95_limit:.2f}ms"
        ),
    )

    health_values = benchmark.get("observedHealthStatuses")
    observed_health = (
        [str(item) for item in health_values]
        if isinstance(health_values, list)
        else []
    )
    health_ok = (
        benchmark.get("finalHealthStatus") == "HEALTHY"
        and "CRITICAL" not in observed_health
    )
    check(
        checks,
        key="runtime-health",
        title="AI 런타임 상태",
        passed=health_ok,
        detail=(
            f"final={benchmark.get('finalHealthStatus')}; "
            f"observed={observed_health}"
        ),
    )

    input_sha = benchmark.get("inputAssetSha256")
    reproducible_input = (
        isinstance(benchmark.get("inputAssetName"), str)
        and bool(benchmark.get("inputAssetName"))
        and is_checksum(input_sha)
        and isinstance(benchmark.get("inputAssetSizeBytes"), int)
        and benchmark.get("inputAssetSizeBytes", 0) > 0
        and benchmark.get("sourceType") == "DUMMY_VIDEO"
    )
    check(
        checks,
        key="input-identity",
        title="고정 입력 영상 동일성",
        passed=reproducible_input,
        detail=(
            str(benchmark.get("inputAssetName"))
            if reproducible_input
            else "DUMMY_VIDEO 입력의 이름·크기·SHA-256이 없습니다."
        ),
    )

    failed = sum(item["status"] == "FAILED" for item in checks)
    passed = len(checks) - failed
    status = BLOCKED_STATUS if failed else PASSED_STATUS
    return {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "operation": OPERATION,
        "soakId": soak_id or str(uuid.uuid4()),
        "generatedAt": now.astimezone(timezone.utc).isoformat(),
        "status": status,
        "inputs": [
            artifact_entry(root, "model-release-activation", activation_path),
            artifact_entry(root, "model-promotion", promotion_path),
            artifact_entry(root, "soak-benchmark", benchmark_path),
        ],
        "model": {
            "fileName": (
                active_model.get("fileName")
                if isinstance(active_model, Mapping)
                else None
            ),
            "sha256": active_sha,
            "deviceEffective": benchmark.get("deviceEffective"),
        },
        "measurement": {
            "durationSeconds": values["durationSeconds"],
            "sampleCount": values["sampleCount"],
            "sampleCoveragePct": round(sample_coverage, 4),
            "processedFrameDelta": values["processedFrameDelta"],
            "averageInputFps": values["averageInputFps"],
            "averageProcessingFps": values["averageProcessingFps"],
            "processingRatio": round(processing_ratio, 4),
            "droppedFrameDelta": values["droppedFrameDelta"],
            "dropRatePct": round(observed_drop_rate, 4),
            "averageInferenceMs": values["averageInferenceMs"],
            "maximumObservedP95InferenceMs": values[
                "maximumObservedP95InferenceMs"
            ],
            "finalHealthStatus": benchmark.get("finalHealthStatus"),
        },
        "reference": {
            "averageInferenceMs": reference["averageInferenceMs"],
            "maximumObservedP95InferenceMs": reference[
                "maximumObservedP95InferenceMs"
            ],
            "averageLimitMs": round(average_limit, 4),
            "p95LimitMs": round(p95_limit, 4),
        },
        "checks": checks,
        "summary": {
            "total": len(checks),
            "passed": passed,
            "failed": failed,
            "blocking": failed,
        },
        "policy": {
            "minDurationSeconds": min_duration_seconds,
            "minInputFps": min_input_fps,
            "minProcessingRatio": min_processing_ratio,
            "maxDropRatePct": max_drop_rate_pct,
            "maxAverageRegressionPct": max_average_regression_pct,
            "maxP95RegressionPct": max_p95_regression_pct,
            "minSampleCoveragePct": min_sample_coverage_pct,
            "activationMaxAgeHours": activation_max_age_hours,
            "benchmarkMaxAgeHours": benchmark_max_age_hours,
            "fixedInputIdentityRequired": True,
            "cudaRequired": True,
        },
        "safety": {
            "readOnlyEvaluation": True,
            "metricsResetByRunner": metrics_reset_by_runner,
            "databaseMutation": False,
            "dockerMutation": False,
            "modelWeightsModified": False,
            "inputVideoIncluded": False,
            "environmentValuesRecorded": False,
            "operatorKeysRecorded": False,
            "absolutePathsRecorded": False,
        },
    }


def render_html(report: Mapping[str, Any]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['title']))}</td>"
        f"<td>{html.escape(str(item['status']))}</td>"
        f"<td>{html.escape(str(item['detail']))}</td>"
        "</tr>"
        for item in report["checks"]
    )
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VisionFlow 모델 소크 게이트</title><style>
body{{margin:0;background:#eef3f8;color:#0f172a;font-family:Arial,'Noto Sans KR',sans-serif}}
main{{max-width:1050px;margin:32px auto;padding:0 20px}}
section{{background:#fff;border:1px solid #dbe4ee;border-radius:16px;padding:24px;margin:16px 0}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid #e2e8f0;text-align:left}}
</style></head><body><main><section>
<h1>VisionFlow 배포 후 모델 소크 게이트</h1>
<p>{html.escape(str(report['status']))}</p>
<p>{html.escape(str(report['generatedAt']))}</p></section>
<section><h2>검증 항목</h2><table>
<tr><th>항목</th><th>상태</th><th>내용</th></tr>{rows}
</table></section></main></body></html>"""


def write_report(
    *,
    output_directory: Path,
    report: dict[str, Any],
) -> tuple[Path, Path, Path]:
    timestamp = parse_timestamp(
        report["generatedAt"],
        "모델 소크",
    ).strftime("%Y%m%dT%H%M%SZ")
    run_directory = output_directory / f"soak-{timestamp}"
    if run_directory.exists():
        run_directory = output_directory / (
            f"soak-{timestamp}-{uuid.uuid4().hex[:8]}"
        )
    run_directory.mkdir(parents=True, exist_ok=False)
    report_path = run_directory / "visionflow-model-soak.json"
    html_path = run_directory / "visionflow-model-soak.html"
    sidecar_path = run_directory / "visionflow-model-soak.sha256"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    html_path.write_text(render_html(report), encoding="utf-8")
    write_sidecar(sidecar_path, [report_path, html_path])
    return report_path, html_path, sidecar_path


def input_by_key(report: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    inputs = report.get("inputs")
    if not isinstance(inputs, list):
        raise ModelSoakError("모델 소크 입력 목록이 없습니다.")
    matches = [
        item
        for item in inputs
        if isinstance(item, Mapping)
        and item.get("key") == key
    ]
    if len(matches) != 1:
        raise ModelSoakError(f"모델 소크 입력이 정확히 하나가 아닙니다: {key}")
    return matches[0]


def verify_report(
    *,
    root: Path,
    report_path: Path,
) -> tuple[Path, dict[str, Any]]:
    root = root.resolve()
    report_path = resolve_inside(root, report_path, "모델 소크 보고서")
    html_path = report_path.with_suffix(".html")
    sidecar_path = report_path.with_suffix(".sha256")
    verify_sidecar(sidecar_path, [report_path, html_path])
    report = read_json(report_path, "모델 소크 보고서")
    if (
        report.get("schemaVersion") != SCHEMA_VERSION
        or report.get("project") != PROJECT_NAME
        or report.get("operation") != OPERATION
        or report.get("status") not in {PASSED_STATUS, BLOCKED_STATUS}
    ):
        raise ModelSoakError("VisionFlow 모델 소크 보고서가 아닙니다.")
    try:
        uuid.UUID(str(report.get("soakId")))
    except (ValueError, AttributeError) as error:
        raise ModelSoakError("모델 소크 ID가 올바르지 않습니다.") from error
    resolved: dict[str, Path] = {}
    for key in (
        "model-release-activation",
        "model-promotion",
        "soak-benchmark",
    ):
        item = input_by_key(report, key)
        resolved[key] = mapping_path(root, item, key)
    policy = report.get("policy")
    safety = report.get("safety")
    if not isinstance(policy, Mapping) or not isinstance(safety, Mapping):
        raise ModelSoakError("모델 소크 정책이 없습니다.")
    metrics_reset_by_runner = safety.get("metricsResetByRunner")
    if not isinstance(metrics_reset_by_runner, bool):
        raise ModelSoakError("메트릭 초기화 실행 여부가 올바르지 않습니다.")
    rebuilt = build_report(
        root=root,
        activation_path=resolved["model-release-activation"],
        benchmark_path=resolved["soak-benchmark"],
        now=parse_timestamp(report.get("generatedAt"), "모델 소크"),
        min_duration_seconds=metric(
            policy.get("minDurationSeconds"),
            "최소 측정 시간",
        ),
        min_input_fps=metric(policy.get("minInputFps"), "최소 입력 FPS"),
        min_processing_ratio=metric(
            policy.get("minProcessingRatio"),
            "최소 처리 비율",
        ),
        max_drop_rate_pct=metric(
            policy.get("maxDropRatePct"),
            "최대 드롭률",
        ),
        max_average_regression_pct=metric(
            policy.get("maxAverageRegressionPct"),
            "평균 지연 회귀 허용치",
        ),
        max_p95_regression_pct=metric(
            policy.get("maxP95RegressionPct"),
            "P95 지연 회귀 허용치",
        ),
        min_sample_coverage_pct=metric(
            policy.get("minSampleCoveragePct"),
            "최소 표본 커버리지",
        ),
        activation_max_age_hours=metric(
            policy.get("activationMaxAgeHours"),
            "활성화 최신성",
        ),
        benchmark_max_age_hours=metric(
            policy.get("benchmarkMaxAgeHours"),
            "벤치마크 최신성",
        ),
        metrics_reset_by_runner=metrics_reset_by_runner,
        soak_id=str(report.get("soakId")),
    )
    if rebuilt != report:
        raise ModelSoakError(
            "현재 활성화·승격·벤치마크로 재계산한 소크 판정이 다릅니다."
        )
    if resolved["model-promotion"] != mapping_path(
        root,
        input_by_key(rebuilt, "model-promotion"),
        "model-promotion",
    ):
        raise ModelSoakError("모델 승격 증적 연결이 다릅니다.")
    if html_path.read_text(encoding="utf-8-sig") != render_html(report):
        raise ModelSoakError("모델 소크 JSON과 HTML이 다릅니다.")
    return report_path, report


def default_policy() -> dict[str, float]:
    return {
        "min_duration_seconds": 300.0,
        "min_input_fps": 2.0,
        "min_processing_ratio": 0.90,
        "max_drop_rate_pct": 1.0,
        "max_average_regression_pct": 20.0,
        "max_p95_regression_pct": 25.0,
        "min_sample_coverage_pct": 80.0,
        "activation_max_age_hours": 24.0,
        "benchmark_max_age_hours": 2.0,
    }


def build_plan() -> list[str]:
    return [
        "MODEL_RELEASE_ACTIVATED와 현재 best.pt 동일성 재검증",
        "고정 입력 영상 SHA-256을 기록한 5분 GPU 벤치마크",
        "입력 부하·표본 커버리지·처리량·드롭률 확인",
        "승격 당시 평균·P95 지연 대비 성능 회귀 확인",
        "AI 런타임 HEALTHY와 CUDA 실행 확인",
        "MODEL_SOAK_PASSED 또는 MODEL_SOAK_BLOCKED 증적 생성",
    ]


def dotenv_value(path: Path, key: str) -> str | None:
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == key:
            return value.strip().strip("\"'")
    return None


def verify_dummy_source_configuration(root: Path, input_file: Path) -> None:
    environment = resolve_inside(root, BASE_ENVIRONMENT, "Docker 환경파일")
    dummy_root = (root / DUMMY_VIDEO_DIRECTORY).resolve()
    if not is_within(input_file, dummy_root):
        raise ModelSoakError(
            "고정 입력 영상은 AI data/dummy 폴더 안에 있어야 합니다."
        )
    relative = input_file.relative_to(dummy_root).as_posix()
    expected_container_path = f"/app/data/dummy/{relative}"
    if (
        dotenv_value(environment, "AI_SOURCE_TYPE") != "DUMMY_VIDEO"
        or dotenv_value(environment, "AI_DUMMY_VIDEO_PATH")
        != expected_container_path
    ):
        raise ModelSoakError(
            ".env.docker의 AI_SOURCE_TYPE과 AI_DUMMY_VIDEO_PATH가 "
            "고정 입력 영상과 일치하지 않습니다."
        )


def run_benchmark(
    *,
    root: Path,
    activation_path: Path,
    input_file: Path,
    duration_seconds: int,
    warmup_seconds: int,
    interval_milliseconds: int,
    runner: Runner,
    platform_name: str,
) -> Path:
    if platform_name != "nt":
        raise ModelSoakError("모델 소크 측정은 Windows HP OMEN 전용입니다.")
    _, activation = verify_activation_report(
        root=root,
        report_path=activation_path,
    )
    if activation.get("status") != ACTIVATED_STATUS:
        raise ModelSoakError(
            "MODEL_RELEASE_ACTIVATED 이후에만 소크 측정을 실행할 수 있습니다."
        )
    script = resolve_inside(root, BENCHMARK_SCRIPT, "AI 벤치마크 스크립트")
    input_file = resolve_inside(root, input_file, "고정 입력 영상")
    verify_dummy_source_configuration(root, input_file)
    measurement_directory = (root / MEASUREMENT_DIRECTORY).resolve()
    if not is_within(measurement_directory, root):
        raise ModelSoakError("소크 측정 출력 경로가 프로젝트 밖에 있습니다.")
    measurement_directory.mkdir(parents=True, exist_ok=True)
    before = {
        path.resolve()
        for path in measurement_directory.glob(
            "visionflow-ai-benchmark-*.json"
        )
        if path.is_file() and not path.is_symlink()
    }
    command = [
        "powershell.exe",
        "-NoLogo",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-DurationSeconds",
        str(duration_seconds),
        "-WarmupSeconds",
        str(warmup_seconds),
        "-IntervalMilliseconds",
        str(interval_milliseconds),
        "-OutputDirectory",
        str(measurement_directory),
        "-RunLabel",
        "best-post-release-soak",
        "-InputFilePath",
        str(input_file),
    ]
    try:
        result = runner(
            command,
            root,
            duration_seconds + warmup_seconds + 120,
        )
    except Exception as error:
        raise ModelSoakError(
            f"소크 벤치마크 실행 중 오류가 발생했습니다: {error}"
        ) from error
    if result.output:
        print(result.output.rstrip())
    if result.exit_code != 0:
        raise ModelSoakError(
            f"소크 벤치마크 실행 실패: exit={result.exit_code}"
        )
    after = {
        path.resolve()
        for path in measurement_directory.glob(
            "visionflow-ai-benchmark-*.json"
        )
        if path.is_file() and not path.is_symlink()
    }
    created = sorted(after - before, key=lambda path: path.as_posix())
    if len(created) != 1:
        raise ModelSoakError(
            "소크 벤치마크 JSON이 정확히 하나 생성되지 않았습니다."
        )
    benchmark = read_json(created[0], "소크 벤치마크")
    if (
        benchmark.get("inputAssetSha256") != sha256_file(input_file)
        or benchmark.get("inputAssetSizeBytes") != input_file.stat().st_size
    ):
        raise ModelSoakError("소크 입력 영상 동일성이 다릅니다.")
    return created[0]


def add_policy_arguments(value: argparse.ArgumentParser) -> None:
    policy = default_policy()
    value.add_argument(
        "--min-duration-seconds",
        type=float,
        default=policy["min_duration_seconds"],
    )
    value.add_argument(
        "--min-input-fps",
        type=float,
        default=policy["min_input_fps"],
    )
    value.add_argument(
        "--min-processing-ratio",
        type=float,
        default=policy["min_processing_ratio"],
    )
    value.add_argument(
        "--max-drop-rate-pct",
        type=float,
        default=policy["max_drop_rate_pct"],
    )
    value.add_argument(
        "--max-average-regression-pct",
        type=float,
        default=policy["max_average_regression_pct"],
    )
    value.add_argument(
        "--max-p95-regression-pct",
        type=float,
        default=policy["max_p95_regression_pct"],
    )
    value.add_argument(
        "--min-sample-coverage-pct",
        type=float,
        default=policy["min_sample_coverage_pct"],
    )
    value.add_argument(
        "--activation-max-age-hours",
        type=float,
        default=policy["activation_max_age_hours"],
    )
    value.add_argument(
        "--benchmark-max-age-hours",
        type=float,
        default=policy["benchmark_max_age_hours"],
    )


def parser(default_root: Path) -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="VisionFlow post-release model soak gate"
    )
    value.add_argument("--root", default=str(default_root))
    subparsers = value.add_subparsers(dest="command", required=True)
    subparsers.add_parser("plan")
    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("--activation")
    evaluate.add_argument("--benchmark")
    evaluate.add_argument("--output", default=DEFAULT_OUTPUT.as_posix())
    add_policy_arguments(evaluate)
    run = subparsers.add_parser("run")
    run.add_argument("--activation")
    run.add_argument("--input-file", required=True)
    run.add_argument(
        "--duration-seconds",
        type=int,
        default=DEFAULT_DURATION_SECONDS,
    )
    run.add_argument(
        "--warmup-seconds",
        type=int,
        default=DEFAULT_WARMUP_SECONDS,
    )
    run.add_argument(
        "--interval-milliseconds",
        type=int,
        default=DEFAULT_INTERVAL_MILLISECONDS,
    )
    run.add_argument("--output", default=DEFAULT_OUTPUT.as_posix())
    add_policy_arguments(run)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--report", required=True)
    return value


def output_path(root: Path, value: str) -> Path:
    output = resolve_inside(
        root,
        value,
        "모델 소크 출력",
        require_file=False,
    )
    if not is_within(output, (root / DEFAULT_OUTPUT).resolve()):
        raise ModelSoakError(
            "모델 소크 출력은 artifacts/model-soak 안에 있어야 합니다."
        )
    return output


def main(argv: Sequence[str] | None = None) -> int:
    root_default = Path(__file__).resolve().parent.parent
    arguments = parser(root_default).parse_args(argv)
    root = Path(arguments.root).resolve()
    try:
        if arguments.command == "plan":
            print("VisionFlow model soak: PLAN")
            for index, item in enumerate(build_plan(), start=1):
                print(f"{index:02d}. {item}")
            print("No metrics, model, database, Docker, or service was changed.")
            return 0
        if arguments.command == "verify":
            path, report = verify_report(
                root=root,
                report_path=Path(arguments.report),
            )
            print("VisionFlow model soak: VERIFIED")
            print(f"Status: {report['status']}")
            print(f"Report: {path}")
            return 0

        output = output_path(root, arguments.output)
        activation = (
            resolve_inside(root, arguments.activation, "모델 릴리스 실행")
            if arguments.activation
            else newest_artifact(root, ACTIVATION_PATTERN, "모델 릴리스 실행")
        )
        if arguments.command == "run":
            if (
                arguments.duration_seconds < 5
                or arguments.warmup_seconds < 0
                or arguments.interval_milliseconds < 100
            ):
                raise ModelSoakError("소크 측정 시간·간격 값이 올바르지 않습니다.")
            benchmark = run_benchmark(
                root=root,
                activation_path=activation,
                input_file=Path(arguments.input_file),
                duration_seconds=arguments.duration_seconds,
                warmup_seconds=arguments.warmup_seconds,
                interval_milliseconds=arguments.interval_milliseconds,
                runner=default_runner,
                platform_name=os.name,
            )
        else:
            benchmark = (
                resolve_inside(root, arguments.benchmark, "소크 벤치마크")
                if arguments.benchmark
                else newest_artifact(root, BENCHMARK_PATTERN, "소크 벤치마크")
            )

        policy_values = {
            "min_duration_seconds": arguments.min_duration_seconds,
            "min_input_fps": arguments.min_input_fps,
            "min_processing_ratio": arguments.min_processing_ratio,
            "max_drop_rate_pct": arguments.max_drop_rate_pct,
            "max_average_regression_pct": (
                arguments.max_average_regression_pct
            ),
            "max_p95_regression_pct": arguments.max_p95_regression_pct,
            "min_sample_coverage_pct": arguments.min_sample_coverage_pct,
            "activation_max_age_hours": arguments.activation_max_age_hours,
            "benchmark_max_age_hours": arguments.benchmark_max_age_hours,
        }
        if any(value <= 0 for value in policy_values.values()):
            raise ModelSoakError("모델 소크 정책 값은 모두 양수여야 합니다.")
        report = build_report(
            root=root,
            activation_path=activation,
            benchmark_path=benchmark,
            now=datetime.now(timezone.utc),
            metrics_reset_by_runner=arguments.command == "run",
            **policy_values,
        )
        report_path, html_path, sidecar_path = write_report(
            output_directory=output,
            report=report,
        )
        verify_report(root=root, report_path=report_path)
        print(f"VisionFlow model soak: {report['status']}")
        print(f"JSON report: {report_path}")
        print(f"HTML report: {html_path}")
        print(f"SHA-256   : {sidecar_path}")
        return 0 if report["status"] == PASSED_STATUS else 1
    except (
        ModelSoakError,
        ModelReleaseError,
        ModelPromotionError,
        OSError,
        subprocess.SubprocessError,
    ) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
