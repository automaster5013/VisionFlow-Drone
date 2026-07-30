from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


def load_summary(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as summary_file:
        value = json.load(summary_file)

    if not isinstance(value, dict):
        raise ValueError(f"벤치마크 JSON 최상위 값은 객체여야 합니다: {path}")

    return value


def number(summary: dict[str, Any], key: str) -> float:
    value = summary.get(key)

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"벤치마크 필드가 숫자가 아닙니다: {key}")

    return float(value)


def optional_text(summary: dict[str, Any], key: str) -> str:
    value = summary.get(key)
    return str(value) if value is not None else ""


def percent_change(baseline: float, candidate: float) -> float | None:
    if baseline == 0:
        return None

    return round((candidate - baseline) / baseline * 100.0, 2)


def reduction_percent(baseline: float, candidate: float) -> float | None:
    change = percent_change(baseline, candidate)
    return -change if change is not None else None


def processing_ratio(summary: dict[str, Any]) -> float | None:
    input_fps = number(summary, "averageInputFps")
    processing_fps = number(summary, "averageProcessingFps")
    return round(processing_fps / input_fps, 4) if input_fps > 0 else None


def fairness_checks(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []

    if baseline.get("benchmarkValid") is False:
        failures.append("BASELINE_INVALID")

    if candidate.get("benchmarkValid") is False:
        failures.append("CANDIDATE_INVALID")

    exact_match_fields = (
        ("hardwareLabel", "HARDWARE_MISMATCH"),
        ("inputAssetSha256", "INPUT_ASSET_MISMATCH"),
        ("sourceType", "SOURCE_TYPE_MISMATCH"),
        ("deviceEffective", "DEVICE_MISMATCH"),
        ("imageSize", "IMAGE_SIZE_MISMATCH"),
        ("confidence", "CONFIDENCE_MISMATCH"),
        ("iou", "IOU_MISMATCH"),
    )

    for field, reason in exact_match_fields:
        baseline_value = baseline.get(field)
        candidate_value = candidate.get(field)

        if (
            baseline_value is not None
            and candidate_value is not None
            and baseline_value != candidate_value
        ):
            failures.append(reason)

    baseline_duration = number(baseline, "durationSeconds")
    candidate_duration = number(candidate, "durationSeconds")

    if abs(baseline_duration - candidate_duration) > 1.0:
        failures.append("DURATION_MISMATCH")

    baseline_input_fps = number(baseline, "averageInputFps")
    candidate_input_fps = number(candidate, "averageInputFps")
    input_reference = max(baseline_input_fps, candidate_input_fps)

    if input_reference > 0:
        input_gap_ratio = abs(baseline_input_fps - candidate_input_fps) / input_reference

        if input_gap_ratio > 0.10:
            failures.append("INPUT_RATE_MISMATCH")

    if min(baseline_input_fps, candidate_input_fps) < 2.0:
        warnings.append("LOW_LOAD_INPUT_UNDER_2_FPS")

    if not baseline.get("modelSha256") or not candidate.get("modelSha256"):
        warnings.append("MODEL_SHA256_MISSING")

    if not baseline.get("inputAssetSha256") or not candidate.get("inputAssetSha256"):
        warnings.append("INPUT_ASSET_SHA256_MISSING")

    warnings.append("ACCURACY_NOT_MEASURED")
    return failures, warnings


def metric_comparison(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, dict[str, float | None]]:
    average_latency_baseline = number(baseline, "averageInferenceMs")
    average_latency_candidate = number(candidate, "averageInferenceMs")
    p95_baseline = number(baseline, "maximumObservedP95InferenceMs")
    p95_candidate = number(candidate, "maximumObservedP95InferenceMs")
    processing_baseline = number(baseline, "averageProcessingFps")
    processing_candidate = number(candidate, "averageProcessingFps")
    input_baseline = number(baseline, "averageInputFps")
    input_candidate = number(candidate, "averageInputFps")
    drop_baseline = number(baseline, "droppedFrameDelta")
    drop_candidate = number(candidate, "droppedFrameDelta")

    return {
        "averageInferenceMs": {
            "baseline": average_latency_baseline,
            "candidate": average_latency_candidate,
            "delta": round(average_latency_candidate - average_latency_baseline, 2),
            "candidateReductionPct": reduction_percent(
                average_latency_baseline,
                average_latency_candidate,
            ),
        },
        "maximumObservedP95InferenceMs": {
            "baseline": p95_baseline,
            "candidate": p95_candidate,
            "delta": round(p95_candidate - p95_baseline, 2),
            "candidateReductionPct": reduction_percent(p95_baseline, p95_candidate),
        },
        "averageProcessingFps": {
            "baseline": processing_baseline,
            "candidate": processing_candidate,
            "delta": round(processing_candidate - processing_baseline, 2),
            "candidateGainPct": percent_change(processing_baseline, processing_candidate),
        },
        "averageInputFps": {
            "baseline": input_baseline,
            "candidate": input_candidate,
            "delta": round(input_candidate - input_baseline, 2),
            "candidateChangePct": percent_change(input_baseline, input_candidate),
        },
        "inputToProcessingRatio": {
            "baseline": processing_ratio(baseline),
            "candidate": processing_ratio(candidate),
            "delta": _optional_delta(
                processing_ratio(baseline),
                processing_ratio(candidate),
            ),
        },
        "droppedFrameDelta": {
            "baseline": drop_baseline,
            "candidate": drop_candidate,
            "delta": round(drop_candidate - drop_baseline, 2),
        },
    }


def _optional_delta(baseline: float | None, candidate: float | None) -> float | None:
    if baseline is None or candidate is None:
        return None

    return round(candidate - baseline, 4)


def verdict(
    valid: bool,
    metrics: dict[str, dict[str, float | None]],
) -> str:
    if not valid:
        return "INVALID_COMPARISON"

    latency_reduction = metrics["averageInferenceMs"]["candidateReductionPct"]
    processing_gain = metrics["averageProcessingFps"]["candidateGainPct"]
    drop_delta = metrics["droppedFrameDelta"]["delta"]

    if latency_reduction is None or processing_gain is None or drop_delta is None:
        return "INSUFFICIENT_DATA"

    if latency_reduction >= 5.0 and processing_gain >= -5.0 and drop_delta <= 0:
        return "CANDIDATE_FASTER"

    if latency_reduction <= -5.0 and processing_gain <= 5.0 and drop_delta >= 0:
        return "BASELINE_FASTER"

    if abs(latency_reduction) < 5.0 and abs(processing_gain) < 5.0 and drop_delta == 0:
        return "PERFORMANCE_COMPARABLE"

    return "TRADE_OFF"


def identity(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "benchmarkId": optional_text(summary, "benchmarkId"),
        "runLabel": optional_text(summary, "runLabel"),
        "hardwareLabel": optional_text(summary, "hardwareLabel"),
        "inputAssetName": optional_text(summary, "inputAssetName"),
        "inputAssetSha256": optional_text(summary, "inputAssetSha256"),
        "modelProfile": optional_text(summary, "modelProfile"),
        "modelName": optional_text(summary, "modelName"),
        "modelSha256": optional_text(summary, "modelSha256"),
        "modelClassCount": summary.get("modelClassCount"),
        "deviceEffective": optional_text(summary, "deviceEffective")
        or optional_text(summary, "device"),
        "cudaDeviceName": optional_text(summary, "cudaDeviceName"),
        "imageSize": summary.get("imageSize"),
        "confidence": summary.get("confidence"),
        "iou": summary.get("iou"),
        "sourceType": optional_text(summary, "sourceType"),
        "durationSeconds": summary.get("durationSeconds"),
    }


def build_comparison(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    failures, warnings = fairness_checks(baseline, candidate)
    metrics = metric_comparison(baseline, candidate)
    comparison_valid = not failures

    return {
        "comparisonVersion": 1,
        "generatedAt": datetime.now().astimezone().isoformat(),
        "comparisonValid": comparison_valid,
        "fairnessFailures": failures,
        "warnings": warnings,
        "verdict": verdict(comparison_valid, metrics),
        "baseline": identity(baseline),
        "candidate": identity(candidate),
        "metrics": metrics,
        "scope": (
            "YOLO 실행 성능만 비교합니다. 탐지 정확도, 정밀도, 재현율 및 "
            "mAP 비교는 포함하지 않습니다."
        ),
    }


def safe_label(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    return normalized or "comparison"


def write_outputs(
    comparison: dict[str, Any],
    output_directory: Path,
    label: str,
) -> tuple[Path, Path, Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    stem = f"visionflow-ai-comparison-{timestamp}-{safe_label(label)}"
    json_path = output_directory / f"{stem}.json"
    csv_path = output_directory / f"{stem}.csv"
    markdown_path = output_directory / f"{stem}.md"

    with json_path.open("w", encoding="utf-8") as output_file:
        json.dump(comparison, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")

    flat_row = _flat_csv_row(comparison)

    with csv_path.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=list(flat_row))
        writer.writeheader()
        writer.writerow(flat_row)

    markdown_path.write_text(_markdown_report(comparison), encoding="utf-8")
    return json_path, csv_path, markdown_path


def _flat_csv_row(comparison: dict[str, Any]) -> dict[str, Any]:
    baseline = comparison["baseline"]
    candidate = comparison["candidate"]
    metrics = comparison["metrics"]

    return {
        "GeneratedAt": comparison["generatedAt"],
        "ComparisonValid": comparison["comparisonValid"],
        "Verdict": comparison["verdict"],
        "FairnessFailures": ",".join(comparison["fairnessFailures"]),
        "Warnings": ",".join(comparison["warnings"]),
        "BaselineProfile": baseline["modelProfile"],
        "BaselineModel": baseline["modelName"],
        "BaselineSha256": baseline["modelSha256"],
        "CandidateProfile": candidate["modelProfile"],
        "CandidateModel": candidate["modelName"],
        "CandidateSha256": candidate["modelSha256"],
        "Hardware": candidate["hardwareLabel"],
        "Device": candidate["deviceEffective"],
        "AverageInferenceBaselineMs": metrics["averageInferenceMs"]["baseline"],
        "AverageInferenceCandidateMs": metrics["averageInferenceMs"]["candidate"],
        "AverageInferenceReductionPct": metrics["averageInferenceMs"][
            "candidateReductionPct"
        ],
        "P95BaselineMs": metrics["maximumObservedP95InferenceMs"]["baseline"],
        "P95CandidateMs": metrics["maximumObservedP95InferenceMs"]["candidate"],
        "P95ReductionPct": metrics["maximumObservedP95InferenceMs"][
            "candidateReductionPct"
        ],
        "ProcessingBaselineFps": metrics["averageProcessingFps"]["baseline"],
        "ProcessingCandidateFps": metrics["averageProcessingFps"]["candidate"],
        "ProcessingGainPct": metrics["averageProcessingFps"]["candidateGainPct"],
        "DroppedFramesBaseline": metrics["droppedFrameDelta"]["baseline"],
        "DroppedFramesCandidate": metrics["droppedFrameDelta"]["candidate"],
    }


def _format_value(value: Any) -> str:
    if value is None:
        return "-"

    if isinstance(value, float):
        return f"{value:.2f}"

    return str(value)


def _markdown_report(comparison: dict[str, Any]) -> str:
    baseline = comparison["baseline"]
    candidate = comparison["candidate"]
    metrics = comparison["metrics"]
    rows = [
        (
            "평균 추론 지연(ms)",
            metrics["averageInferenceMs"]["baseline"],
            metrics["averageInferenceMs"]["candidate"],
            metrics["averageInferenceMs"]["candidateReductionPct"],
        ),
        (
            "관측 P95 최대(ms)",
            metrics["maximumObservedP95InferenceMs"]["baseline"],
            metrics["maximumObservedP95InferenceMs"]["candidate"],
            metrics["maximumObservedP95InferenceMs"]["candidateReductionPct"],
        ),
        (
            "평균 처리 FPS",
            metrics["averageProcessingFps"]["baseline"],
            metrics["averageProcessingFps"]["candidate"],
            metrics["averageProcessingFps"]["candidateGainPct"],
        ),
        (
            "드롭 프레임",
            metrics["droppedFrameDelta"]["baseline"],
            metrics["droppedFrameDelta"]["candidate"],
            None,
        ),
    ]
    table_rows = "\n".join(
        f"| {name} | {_format_value(base)} | {_format_value(cand)} | "
        f"{_format_value(change)} |"
        for name, base, cand, change in rows
    )
    failures = ", ".join(comparison["fairnessFailures"]) or "없음"
    warnings = ", ".join(comparison["warnings"]) or "없음"

    return f"""# VisionFlow AI 모델 A/B 성능 비교

- 비교 유효성: `{comparison['comparisonValid']}`
- 판정: `{comparison['verdict']}`
- 공정성 실패: `{failures}`
- 주의사항: `{warnings}`

## 실행 조건

| 구분 | 기준 모델 | 후보 모델 |
|---|---|---|
| 프로필 | {baseline['modelProfile']} | {candidate['modelProfile']} |
| 모델 | {baseline['modelName']} | {candidate['modelName']} |
| SHA-256 | {baseline['modelSha256']} | {candidate['modelSha256']} |
| 하드웨어 | {baseline['hardwareLabel']} | {candidate['hardwareLabel']} |
| 장치 | {baseline['deviceEffective']} | {candidate['deviceEffective']} |
| 입력 파일 | {baseline['inputAssetName']} | {candidate['inputAssetName']} |
| 입력 SHA-256 | {baseline['inputAssetSha256']} | {candidate['inputAssetSha256']} |
| 입력 크기 | {baseline['imageSize']} | {candidate['imageSize']} |

## 성능 결과

후보 변화율은 지연 시간에서는 감소율, 처리 FPS에서는 증가율입니다.

| 지표 | 기준 | 후보 | 후보 변화율(%) |
|---|---:|---:|---:|
{table_rows}

## 범위

{comparison['scope']}
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "VisionFlow AI 벤치마크 JSON 두 개를 "
            "공정성 검증 후 비교합니다."
        )
    )
    parser.add_argument("baseline", type=Path, help="기준 모델 벤치마크 JSON")
    parser.add_argument("candidate", type=Path, help="후보 모델 벤치마크 JSON")
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("artifacts/ai-benchmark-comparison"),
    )
    parser.add_argument("--label", default="model-ab")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    comparison = build_comparison(
        load_summary(args.baseline),
        load_summary(args.candidate),
    )
    json_path, csv_path, markdown_path = write_outputs(
        comparison,
        args.output_directory,
        args.label,
    )
    print(f"Comparison valid: {comparison['comparisonValid']}")
    print(f"Verdict        : {comparison['verdict']}")
    print(f"JSON report    : {json_path.resolve()}")
    print(f"CSV report     : {csv_path.resolve()}")
    print(f"Markdown report: {markdown_path.resolve()}")
    return 0 if comparison["comparisonValid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
