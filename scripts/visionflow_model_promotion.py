"""Build and verify the VisionFlow best.pt model-promotion gate."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from compare_visionflow_ai_benchmarks import (
        verdict as calculate_performance_verdict,
    )
    from visionflow_hp_omen_restore import (
        ACTIVATED_STATUS,
        HpOmenRestoreError,
        verify_activation_report,
    )
except ModuleNotFoundError:  # pragma: no cover - package import during tests
    from scripts.compare_visionflow_ai_benchmarks import (
        verdict as calculate_performance_verdict,
    )
    from scripts.visionflow_hp_omen_restore import (
        ACTIVATED_STATUS,
        HpOmenRestoreError,
        verify_activation_report,
    )


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
OPERATION = "MODEL_PROMOTION_GATE"
READY_STATUS = "MODEL_PROMOTION_READY"
REVIEW_STATUS = "MODEL_PROMOTION_REVIEW_REQUIRED"
BLOCKED_STATUS = "MODEL_PROMOTION_BLOCKED"
DEFAULT_MODEL = Path("03_ai-server/visionflow-ai/models/best.pt")
DEFAULT_OUTPUT = Path("artifacts/model-promotion")
READY_PERFORMANCE_VERDICTS = {
    "CANDIDATE_FASTER",
    "PERFORMANCE_COMPARABLE",
}
REVIEW_PERFORMANCE_VERDICTS = {
    "TRADE_OFF",
    "BASELINE_FASTER",
    "INSUFFICIENT_DATA",
}


class ModelPromotionError(RuntimeError):
    """Raised when model-promotion inputs or evidence are unsafe."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_checksum(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_inside(
    root: Path,
    value: str | Path,
    title: str,
    *,
    require_file: bool = True,
) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if not is_within(resolved, root.resolve()):
        raise ModelPromotionError(
            f"{title} 경로가 프로젝트 밖에 있습니다: {candidate}"
        )
    if require_file and (
        not resolved.is_file()
        or resolved.is_symlink()
    ):
        raise ModelPromotionError(
            f"{title} 일반 파일을 찾을 수 없습니다: {candidate}"
        )
    return resolved


def relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as error:
        raise ModelPromotionError(
            f"경로가 프로젝트 밖에 있습니다: {path}"
        ) from error


def read_json(path: Path, title: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ModelPromotionError(
            f"{title} JSON을 읽을 수 없습니다."
        ) from error
    if not isinstance(value, dict):
        raise ModelPromotionError(f"{title} 최상위 값은 객체여야 합니다.")
    return value


def newest_artifact(root: Path, pattern: str, title: str) -> Path:
    candidates = [
        path.resolve()
        for path in root.glob(pattern)
        if path.is_file() and not path.is_symlink()
    ]
    if not candidates:
        raise ModelPromotionError(f"{title} 산출물을 찾을 수 없습니다.")
    return max(
        candidates,
        key=lambda path: (path.stat().st_mtime_ns, path.as_posix()),
    )


def resolve_input(
    root: Path,
    value: str | None,
    pattern: str,
    title: str,
) -> Path:
    if value:
        return resolve_inside(root, value, title)
    return newest_artifact(root, pattern, title)


def artifact_entry(root: Path, key: str, path: Path) -> dict[str, Any]:
    return {
        "key": key,
        "path": relative_path(root, path),
        "sizeBytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def parse_timestamp(value: object, title: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ModelPromotionError(f"{title} 생성 시각이 없습니다.")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ModelPromotionError(
            f"{title} 생성 시각 형식이 올바르지 않습니다."
        ) from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def age_check(
    generated_at: object,
    *,
    title: str,
    now: datetime,
    max_age_hours: float,
) -> tuple[bool, str]:
    timestamp = parse_timestamp(generated_at, title)
    age = now.astimezone(timezone.utc) - timestamp
    if age < -timedelta(minutes=5):
        return False, f"{title} 생성 시각이 미래입니다."
    age_hours = max(0.0, age.total_seconds() / 3600.0)
    return (
        age_hours <= max_age_hours,
        f"{title} 경과 시간 {age_hours:.2f}시간 / 제한 {max_age_hours:.2f}시간",
    )


def metric(value: object, title: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ModelPromotionError(f"{title} 값이 유효한 숫자가 아닙니다.")
    return float(value)


def check(
    items: list[dict[str, Any]],
    *,
    key: str,
    title: str,
    status: str,
    detail: str,
) -> None:
    items.append(
        {
            "key": key,
            "title": title,
            "status": status,
            "detail": detail,
        }
    )


def validate_accuracy_metrics(
    accuracy: Mapping[str, Any],
) -> dict[str, float]:
    metrics = accuracy.get("metrics")
    overall = metrics.get("overall") if isinstance(metrics, Mapping) else None
    if not isinstance(overall, Mapping):
        raise ModelPromotionError("정확도 평가 전체 지표가 없습니다.")
    values = {
        key: metric(overall.get(key), f"정확도 {key}")
        for key in ("precision", "recall", "map50", "map75", "map50_95")
    }
    if any(value < 0.0 or value > 1.0 for value in values.values()):
        raise ModelPromotionError("정확도 지표는 0~1 사이여야 합니다.")
    return values


def validate_performance_metrics(
    comparison: Mapping[str, Any],
) -> dict[str, Any]:
    metrics = comparison.get("metrics")
    if not isinstance(metrics, Mapping):
        raise ModelPromotionError("A/B 비교 성능 지표가 없습니다.")
    requirements = {
        "averageInferenceMs": True,
        "maximumObservedP95InferenceMs": True,
        "averageProcessingFps": True,
        "averageInputFps": True,
        "inputToProcessingRatio": True,
        "droppedFrameDelta": False,
    }
    normalized: dict[str, Any] = dict(metrics)
    values_by_key: dict[str, tuple[float, float]] = {}
    for key, strictly_positive in requirements.items():
        values = metrics.get(key)
        if not isinstance(values, Mapping):
            raise ModelPromotionError(f"A/B 비교 지표가 없습니다: {key}")
        parsed: list[float] = []
        for side in ("baseline", "candidate"):
            number = metric(values.get(side), f"{key}.{side}")
            if number < 0 or (strictly_positive and number <= 0):
                raise ModelPromotionError(
                    f"{key}.{side} 값이 허용 범위를 벗어났습니다."
                )
            parsed.append(number)
        values_by_key[key] = (parsed[0], parsed[1])

    for key, (baseline_value, candidate_value) in values_by_key.items():
        expected_delta = round(
            candidate_value - baseline_value,
            4 if key == "inputToProcessingRatio" else 2,
        )
        recorded_delta = metric(metrics[key].get("delta"), f"{key}.delta")
        tolerance = 0.0001 if key == "inputToProcessingRatio" else 0.01
        if not math.isclose(
            recorded_delta,
            expected_delta,
            abs_tol=tolerance,
        ):
            raise ModelPromotionError(
                "A/B 비교 파생 지표가 baseline·candidate 값과 다릅니다."
            )

    percentage_fields = (
        (
            "averageInferenceMs",
            "candidateReductionPct",
            "reduction",
        ),
        (
            "maximumObservedP95InferenceMs",
            "candidateReductionPct",
            "reduction",
        ),
        (
            "averageProcessingFps",
            "candidateGainPct",
            "change",
        ),
        (
            "averageInputFps",
            "candidateChangePct",
            "change",
        ),
    )
    for key, field, calculation in percentage_fields:
        baseline_value, candidate_value = values_by_key[key]
        change = (
            (candidate_value - baseline_value)
            / baseline_value
            * 100.0
        )
        expected = round(-change if calculation == "reduction" else change, 2)
        recorded = metric(metrics[key].get(field), f"{key}.{field}")
        if not math.isclose(recorded, expected, abs_tol=0.01):
            raise ModelPromotionError(
                "A/B 비교 백분율 지표가 baseline·candidate 값과 다릅니다."
            )
    expected_verdict = calculate_performance_verdict(
        bool(comparison.get("comparisonValid")),
        normalized,
    )
    if comparison.get("verdict") != expected_verdict:
        raise ModelPromotionError(
            "A/B 비교 판정과 성능 지표를 재계산한 결과가 다릅니다."
        )
    return normalized


def validate_comparison_fairness(
    comparison: Mapping[str, Any],
    metrics: Mapping[str, Any],
) -> None:
    if (
        comparison.get("comparisonVersion") != 1
        or comparison.get("comparisonValid") is not True
        or comparison.get("fairnessFailures") != []
    ):
        raise ModelPromotionError(
            "A/B 비교가 유효하지 않거나 공정성 실패가 존재합니다."
        )
    baseline = comparison.get("baseline")
    candidate = comparison.get("candidate")
    if not isinstance(baseline, Mapping) or not isinstance(candidate, Mapping):
        raise ModelPromotionError("A/B 기준·후보 모델 식별자가 없습니다.")
    exact_fields = (
        "hardwareLabel",
        "inputAssetSha256",
        "deviceEffective",
        "imageSize",
        "confidence",
        "iou",
        "sourceType",
    )
    for field in exact_fields:
        baseline_value = baseline.get(field)
        candidate_value = candidate.get(field)
        if baseline_value in (None, "") or baseline_value != candidate_value:
            raise ModelPromotionError(
                f"A/B 비교 조건이 동일하지 않습니다: {field}"
            )
    if not is_checksum(baseline.get("inputAssetSha256")):
        raise ModelPromotionError("A/B 입력 영상 SHA-256이 올바르지 않습니다.")
    for side, identity in (("baseline", baseline), ("candidate", candidate)):
        if not is_checksum(identity.get("modelSha256")):
            raise ModelPromotionError(
                f"A/B {side} 모델 SHA-256이 올바르지 않습니다."
            )
        if not str(identity.get("deviceEffective", "")).startswith("cuda:"):
            raise ModelPromotionError(
                f"A/B {side}가 CUDA에서 실행되지 않았습니다."
            )
    baseline_duration = metric(
        baseline.get("durationSeconds"),
        "baseline.durationSeconds",
    )
    candidate_duration = metric(
        candidate.get("durationSeconds"),
        "candidate.durationSeconds",
    )
    if (
        baseline_duration <= 0
        or candidate_duration <= 0
        or abs(baseline_duration - candidate_duration) > 1.0
    ):
        raise ModelPromotionError("A/B 측정 시간이 동일하지 않습니다.")
    input_values = metrics["averageInputFps"]
    baseline_input = metric(input_values.get("baseline"), "baseline input FPS")
    candidate_input = metric(
        input_values.get("candidate"),
        "candidate input FPS",
    )
    input_reference = max(baseline_input, candidate_input)
    if (
        input_reference <= 0
        or abs(baseline_input - candidate_input) / input_reference > 0.10
    ):
        raise ModelPromotionError("A/B 입력 프레임 속도가 동일하지 않습니다.")


def validate_quality_gate(
    accuracy: Mapping[str, Any],
    overall: Mapping[str, float],
) -> bool:
    quality_gate = accuracy.get("qualityGate")
    checks = (
        quality_gate.get("checks")
        if isinstance(quality_gate, Mapping)
        else None
    )
    if (
        not isinstance(quality_gate, Mapping)
        or quality_gate.get("status") != "PASSED"
        or not isinstance(checks, list)
    ):
        return False
    expected_metrics = {"precision", "recall", "map50", "map50_95"}
    by_metric: dict[str, Mapping[str, Any]] = {}
    for item in checks:
        if not isinstance(item, Mapping):
            return False
        metric_name = item.get("metric")
        if not isinstance(metric_name, str) or metric_name in by_metric:
            return False
        by_metric[metric_name] = item
    if set(by_metric) != expected_metrics:
        return False
    for metric_name, item in by_metric.items():
        try:
            minimum = metric(item.get("minimum"), f"{metric_name} 최소값")
            actual = metric(item.get("actual"), f"{metric_name} 실제값")
        except ModelPromotionError:
            return False
        if (
            minimum < 0.0
            or minimum > 1.0
            or not math.isclose(
                actual,
                overall[metric_name],
                abs_tol=1e-12,
            )
            or item.get("passed") is not (actual >= minimum)
        ):
            return False
    return True


def build_report(
    *,
    root: Path,
    activation_path: Path,
    comparison_path: Path,
    accuracy_path: Path,
    model_path: Path,
    now: datetime,
    activation_max_age_hours: float,
    comparison_max_age_hours: float,
    accuracy_max_age_hours: float,
    promotion_id: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    activation_path = resolve_inside(root, activation_path, "HP 활성화 보고서")
    comparison_path = resolve_inside(root, comparison_path, "A/B 성능 비교")
    accuracy_path = resolve_inside(root, accuracy_path, "정확도 평가")
    model_path = resolve_inside(root, model_path, "승격 후보 모델")

    activation = read_json(activation_path, "HP 활성화 보고서")
    comparison = read_json(comparison_path, "A/B 성능 비교")
    accuracy = read_json(accuracy_path, "정확도 평가")
    model_sha256 = sha256_file(model_path)
    checks: list[dict[str, Any]] = []

    try:
        _, verified_activation = verify_activation_report(
            root,
            relative_path(root, activation_path),
        )
        activation_ok = verified_activation.get("status") == ACTIVATED_STATUS
        activation_detail = str(verified_activation.get("status"))
    except (HpOmenRestoreError, OSError) as error:
        activation_ok = False
        activation_detail = str(error)
    check(
        checks,
        key="hp-activation",
        title="HP OMEN 활성화",
        status="PASS" if activation_ok else "FAILED",
        detail=activation_detail,
    )

    for key, title, source, limit in (
        (
            "activation-freshness",
            "HP 활성화 최신성",
            activation.get("generatedAt"),
            activation_max_age_hours,
        ),
        (
            "comparison-freshness",
            "A/B 성능 비교 최신성",
            comparison.get("generatedAt"),
            comparison_max_age_hours,
        ),
        (
            "accuracy-freshness",
            "정확도 평가 최신성",
            accuracy.get("generatedAt"),
            accuracy_max_age_hours,
        ),
    ):
        try:
            passed, detail = age_check(
                source,
                title=title,
                now=now,
                max_age_hours=limit,
            )
        except ModelPromotionError as error:
            passed, detail = False, str(error)
        check(
            checks,
            key=key,
            title=title,
            status="PASS" if passed else "FAILED",
            detail=detail,
        )

    activation_model = activation.get("model")
    activation_sha = (
        str(activation_model.get("sha256", "")).lower()
        if isinstance(activation_model, Mapping)
        else ""
    )
    activation_identity_ok = (
        is_checksum(activation_sha)
        and activation_sha == model_sha256
    )
    check(
        checks,
        key="activation-model-identity",
        title="활성화·현재 모델 동일성",
        status="PASS" if activation_identity_ok else "FAILED",
        detail=(
            "best.pt SHA-256 일치"
            if activation_identity_ok
            else "활성화 보고서와 현재 best.pt SHA-256 불일치"
        ),
    )

    candidate = comparison.get("candidate")
    try:
        comparison_metrics = validate_performance_metrics(comparison)
        validate_comparison_fairness(comparison, comparison_metrics)
        comparison_metrics_valid = True
    except ModelPromotionError as error:
        comparison_metrics = {}
        comparison_metrics_valid = False
        comparison_metrics_error = str(error)
    comparison_valid = (
        isinstance(candidate, Mapping) and comparison_metrics_valid
    )
    check(
        checks,
        key="performance-fairness",
        title="A/B 비교 공정성",
        status="PASS" if comparison_valid else "FAILED",
        detail=(
            "동일 하드웨어·입력·설정 비교"
            if comparison_valid
            else (
                comparison_metrics_error
                if not comparison_metrics_valid
                else "A/B 비교가 유효하지 않거나 공정성 실패가 존재"
            )
        ),
    )

    candidate_sha = (
        str(candidate.get("modelSha256", "")).lower()
        if isinstance(candidate, Mapping)
        else ""
    )
    candidate_device = (
        str(candidate.get("deviceEffective", ""))
        if isinstance(candidate, Mapping)
        else ""
    )
    performance_identity_ok = (
        candidate_sha == model_sha256
        and candidate.get("modelName") == model_path.name
        and candidate_device.startswith("cuda:")
    )
    check(
        checks,
        key="performance-model-identity",
        title="성능 후보 모델·CUDA 동일성",
        status="PASS" if performance_identity_ok else "FAILED",
        detail=(
            f"{candidate_device} / best.pt SHA-256 일치"
            if performance_identity_ok
            else "성능 후보가 현재 best.pt 또는 CUDA 실행과 일치하지 않음"
        ),
    )

    performance_verdict = str(comparison.get("verdict", ""))
    warnings = comparison.get("warnings")
    warnings = warnings if isinstance(warnings, list) else []
    significant_warnings = [
        str(item)
        for item in warnings
        if item != "ACCURACY_NOT_MEASURED"
    ]
    if (
        performance_verdict in READY_PERFORMANCE_VERDICTS
        and not significant_warnings
    ):
        performance_status = "PASS"
    elif (
        performance_verdict in REVIEW_PERFORMANCE_VERDICTS
        or significant_warnings
    ):
        performance_status = "REVIEW"
    else:
        performance_status = "FAILED"
    check(
        checks,
        key="performance-verdict",
        title="실시간 처리 성능 판정",
        status=performance_status,
        detail=(
            f"{performance_verdict}; warnings={significant_warnings}"
        ),
    )

    accuracy_model = accuracy.get("model")
    accuracy_sha = (
        str(accuracy_model.get("sha256", "")).lower()
        if isinstance(accuracy_model, Mapping)
        else ""
    )
    accuracy_identity_ok = accuracy_sha == model_sha256
    check(
        checks,
        key="accuracy-model-identity",
        title="정확도 후보 모델 동일성",
        status="PASS" if accuracy_identity_ok else "FAILED",
        detail=(
            "정확도 평가 best.pt SHA-256 일치"
            if accuracy_identity_ok
            else "정확도 평가 모델과 현재 best.pt SHA-256 불일치"
        ),
    )

    try:
        overall = validate_accuracy_metrics(accuracy)
        metrics_ok = True
        metrics_detail = (
            f"P={overall['precision']:.4f}, R={overall['recall']:.4f}, "
            f"mAP50={overall['map50']:.4f}, "
            f"mAP50-95={overall['map50_95']:.4f}"
        )
    except ModelPromotionError as error:
        overall = {}
        metrics_ok = False
        metrics_detail = str(error)
    quality_gate = accuracy.get("qualityGate")
    quality_ok = metrics_ok and validate_quality_gate(accuracy, overall)
    check(
        checks,
        key="accuracy-quality-gate",
        title="명시적 정확도 기준",
        status="PASS" if quality_ok else "FAILED",
        detail=(
            "Precision·Recall·mAP 기준 통과"
            if quality_ok
            else "기준 미설정(MEASURED) 또는 정확도 기준 실패"
        ),
    )

    mapping = accuracy.get("classMapping")
    mapping_ok = (
        isinstance(mapping, Mapping)
        and mapping.get("status") == "VALID"
        and mapping.get("errors") == []
        and bool(mapping.get("providedPath"))
    )
    check(
        checks,
        key="class-mapping",
        title="관제 클래스 매핑 승인",
        status="PASS" if mapping_ok else "FAILED",
        detail=(
            "승인된 클래스 매핑 VALID"
            if mapping_ok
            else "승인된 클래스 매핑이 없거나 유효하지 않음"
        ),
    )

    dataset = accuracy.get("dataset")
    dataset_ok = (
        isinstance(dataset, Mapping)
        and isinstance(dataset.get("imageCount"), int)
        and dataset.get("imageCount", 0) > 0
        and dataset.get("labelFileCount") == dataset.get("imageCount")
        and dataset.get("missingLabelFileCount") == 0
        and is_checksum(dataset.get("fingerprintSha256"))
    )
    check(
        checks,
        key="dataset-integrity",
        title="검증 데이터셋 완전성",
        status="PASS" if dataset_ok else "FAILED",
        detail=(
            f"{dataset.get('imageCount')}장 / 누락 라벨 0"
            if dataset_ok
            else "평가 이미지·라벨·데이터셋 지문이 불완전"
        ),
    )

    evaluation = accuracy.get("evaluation")
    runtime = (
        evaluation.get("runtime")
        if isinstance(evaluation, Mapping)
        else None
    )
    accuracy_cuda_ok = (
        isinstance(evaluation, Mapping)
        and str(evaluation.get("device", "")).lower() != "cpu"
        and isinstance(runtime, Mapping)
        and runtime.get("cudaAvailable") is True
    )
    check(
        checks,
        key="accuracy-cuda",
        title="정확도 평가 CUDA 실행",
        status="PASS" if accuracy_cuda_ok else "FAILED",
        detail=(
            f"device={evaluation.get('device')}"
            if accuracy_cuda_ok
            else "정확도 평가가 CUDA 장치에서 실행되지 않음"
        ),
    )

    check(
        checks,
        key="accuracy-metrics",
        title="정확도 지표 유효성",
        status="PASS" if metrics_ok else "FAILED",
        detail=metrics_detail,
    )

    failed = sum(item["status"] == "FAILED" for item in checks)
    review = sum(item["status"] == "REVIEW" for item in checks)
    passed = sum(item["status"] == "PASS" for item in checks)
    status = (
        BLOCKED_STATUS
        if failed
        else (REVIEW_STATUS if review else READY_STATUS)
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "operation": OPERATION,
        "promotionId": promotion_id or str(uuid.uuid4()),
        "generatedAt": now.astimezone(timezone.utc).isoformat(),
        "status": status,
        "model": {
            "fileName": model_path.name,
            "sizeBytes": model_path.stat().st_size,
            "sha256": model_sha256,
        },
        "inputs": [
            artifact_entry(root, "hp-activation", activation_path),
            artifact_entry(root, "performance-comparison", comparison_path),
            artifact_entry(root, "accuracy-evaluation", accuracy_path),
        ],
        "performance": {
            "verdict": performance_verdict,
            "warnings": [str(item) for item in warnings],
            "metrics": comparison_metrics,
        },
        "accuracy": {
            "qualityGateStatus": (
                quality_gate.get("status")
                if isinstance(quality_gate, Mapping)
                else None
            ),
            "mappingStatus": (
                mapping.get("status")
                if isinstance(mapping, Mapping)
                else None
            ),
            "datasetFingerprintSha256": (
                dataset.get("fingerprintSha256")
                if isinstance(dataset, Mapping)
                else None
            ),
            "imageCount": (
                dataset.get("imageCount")
                if isinstance(dataset, Mapping)
                else None
            ),
            "overall": overall,
        },
        "checks": checks,
        "summary": {
            "total": len(checks),
            "passed": passed,
            "review": review,
            "failed": failed,
            "blocking": failed,
        },
        "policy": {
            "activationMaxAgeHours": activation_max_age_hours,
            "comparisonMaxAgeHours": comparison_max_age_hours,
            "accuracyMaxAgeHours": accuracy_max_age_hours,
            "readyPerformanceVerdicts": sorted(
                READY_PERFORMANCE_VERDICTS
            ),
            "approvedClassMappingRequired": True,
            "explicitAccuracyThresholdsRequired": True,
            "completeLabelsRequired": True,
            "cudaRequired": True,
        },
        "safety": {
            "readOnlyEvaluation": True,
            "modelWeightsIncluded": False,
            "modelAbsolutePathRecorded": False,
            "datasetAbsolutePathRecorded": False,
            "operatorKeysRecorded": False,
            "environmentValuesRecorded": False,
            "databaseMutation": False,
            "dockerMutation": False,
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
    model = report["model"]
    accuracy = report["accuracy"]
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VisionFlow 모델 승격 게이트</title><style>
body{{margin:0;background:#eef3f8;color:#0f172a;font-family:Arial,'Noto Sans KR',sans-serif}}
main{{max-width:1050px;margin:32px auto;padding:0 20px}}
section{{background:#fff;border:1px solid #dbe4ee;border-radius:16px;padding:24px;margin:16px 0}}
table{{width:100%;border-collapse:collapse}}
th,td{{padding:10px;border-bottom:1px solid #e2e8f0;text-align:left}}
.ready{{color:#047857;font-weight:800}}.review{{color:#b45309;font-weight:800}}
.blocked{{color:#b91c1c;font-weight:800}}code{{word-break:break-all}}
</style></head><body><main>
<section><h1>VisionFlow best.pt 모델 승격 게이트</h1>
<p class="{'ready' if report['status'] == READY_STATUS else ('review' if report['status'] == REVIEW_STATUS else 'blocked')}">
{html.escape(str(report['status']))}</p>
<p>{html.escape(str(report['generatedAt']))}</p></section>
<section><h2>모델</h2><p>{html.escape(str(model['fileName']))}</p>
<p><code>{html.escape(str(model['sha256']))}</code></p></section>
<section><h2>성능·정확도</h2>
<p>성능 판정: {html.escape(str(report['performance']['verdict']))}</p>
<p>정확도 기준: {html.escape(str(accuracy['qualityGateStatus']))}</p>
<p>클래스 매핑: {html.escape(str(accuracy['mappingStatus']))}</p></section>
<section><h2>검증 항목</h2><table>
<tr><th>항목</th><th>상태</th><th>내용</th></tr>{rows}</table></section>
<section><h2>안전</h2>
<p>읽기 전용 판정이며 모델·데이터셋 내용, 환경값, 운영자 키를 포함하지 않습니다.</p>
</section></main></body></html>"""


def write_report(
    *,
    output_directory: Path,
    report: dict[str, Any],
) -> tuple[Path, Path, Path]:
    timestamp = parse_timestamp(
        report["generatedAt"],
        "모델 승격 보고서",
    ).strftime("%Y%m%dT%H%M%SZ")
    run_directory = output_directory / f"promotion-{timestamp}"
    if run_directory.exists():
        run_directory = output_directory / (
            f"promotion-{timestamp}-{uuid.uuid4().hex[:8]}"
        )
    run_directory.mkdir(parents=True, exist_ok=False)
    json_path = run_directory / "visionflow-model-promotion.json"
    html_path = run_directory / "visionflow-model-promotion.html"
    sidecar_path = run_directory / "visionflow-model-promotion.sha256"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    html_path.write_text(render_html(report), encoding="utf-8")
    sidecar_path.write_text(
        (
            f"{sha256_file(json_path)}  {json_path.name}\n"
            f"{sha256_file(html_path)}  {html_path.name}\n"
        ),
        encoding="utf-8",
    )
    return json_path, html_path, sidecar_path


def verify_sidecar(sidecar: Path, paths: Sequence[Path]) -> None:
    if not sidecar.is_file() or sidecar.is_symlink():
        raise ModelPromotionError("모델 승격 SHA-256 sidecar가 없습니다.")
    recorded: dict[str, str] = {}
    for line in sidecar.read_text(encoding="utf-8-sig").splitlines():
        parts = line.strip().split()
        if len(parts) != 2 or not is_checksum(parts[0]):
            raise ModelPromotionError("모델 승격 SHA-256 형식이 잘못되었습니다.")
        recorded[parts[1]] = parts[0].lower()
    if set(recorded) != {path.name for path in paths}:
        raise ModelPromotionError("모델 승격 SHA-256 파일 목록이 다릅니다.")
    for path in paths:
        if recorded[path.name] != sha256_file(path):
            raise ModelPromotionError(
                f"모델 승격 증적 SHA-256이 다릅니다: {path.name}"
            )


def verify_report(
    *,
    root: Path,
    report_path: Path,
) -> tuple[Path, dict[str, Any]]:
    root = root.resolve()
    report_path = resolve_inside(root, report_path, "모델 승격 보고서")
    html_path = report_path.with_suffix(".html")
    sidecar_path = report_path.with_suffix(".sha256")
    for path in (html_path, sidecar_path):
        if not path.is_file() or path.is_symlink():
            raise ModelPromotionError(
                f"모델 승격 증적 파일이 없습니다: {path.name}"
            )
    verify_sidecar(sidecar_path, [report_path, html_path])
    report = read_json(report_path, "모델 승격 보고서")
    if (
        report.get("schemaVersion") != SCHEMA_VERSION
        or report.get("project") != PROJECT_NAME
        or report.get("operation") != OPERATION
        or report.get("status")
        not in {READY_STATUS, REVIEW_STATUS, BLOCKED_STATUS}
    ):
        raise ModelPromotionError("VisionFlow 모델 승격 보고서가 아닙니다.")

    inputs = report.get("inputs")
    policy = report.get("policy")
    model = report.get("model")
    if (
        not isinstance(inputs, list)
        or len(inputs) != 3
        or not isinstance(policy, Mapping)
        or not isinstance(model, Mapping)
    ):
        raise ModelPromotionError("모델 승격 입력 또는 정책이 없습니다.")
    promotion_id = report.get("promotionId")
    try:
        uuid.UUID(str(promotion_id))
    except (ValueError, AttributeError) as error:
        raise ModelPromotionError("모델 승격 ID가 올바르지 않습니다.") from error
    by_key: dict[str, Path] = {}
    for item in inputs:
        if not isinstance(item, Mapping):
            raise ModelPromotionError("모델 승격 입력 항목이 올바르지 않습니다.")
        key = item.get("key")
        path_value = item.get("path")
        if (
            not isinstance(key, str)
            or key in by_key
            or not isinstance(path_value, str)
        ):
            raise ModelPromotionError("모델 승격 입력 경로가 올바르지 않습니다.")
        path = resolve_inside(root, path_value, f"{key} 입력")
        if (
            path.stat().st_size != item.get("sizeBytes")
            or sha256_file(path) != item.get("sha256")
        ):
            raise ModelPromotionError(
                f"모델 승격 입력 동일성이 다릅니다: {key}"
            )
        by_key[key] = path
    if set(by_key) != {
        "hp-activation",
        "performance-comparison",
        "accuracy-evaluation",
    }:
        raise ModelPromotionError("모델 승격 입력 종류가 다릅니다.")

    model_name = model.get("fileName")
    if (
        not isinstance(model_name, str)
        or not model_name
        or Path(model_name).name != model_name
    ):
        raise ModelPromotionError("승격 모델 파일명이 올바르지 않습니다.")
    model_path = resolve_inside(
        root,
        DEFAULT_MODEL.parent / model_name,
        "현재 승격 모델",
    )
    generated_at = parse_timestamp(
        report.get("generatedAt"),
        "모델 승격 보고서",
    )
    rebuilt = build_report(
        root=root,
        activation_path=by_key["hp-activation"],
        comparison_path=by_key["performance-comparison"],
        accuracy_path=by_key["accuracy-evaluation"],
        model_path=model_path,
        now=generated_at,
        activation_max_age_hours=metric(
            policy.get("activationMaxAgeHours"),
            "활성화 최신성 정책",
        ),
        comparison_max_age_hours=metric(
            policy.get("comparisonMaxAgeHours"),
            "성능 최신성 정책",
        ),
        accuracy_max_age_hours=metric(
            policy.get("accuracyMaxAgeHours"),
            "정확도 최신성 정책",
        ),
        promotion_id=str(promotion_id),
    )
    if rebuilt != report:
        raise ModelPromotionError(
            "현재 모델·증적을 다시 계산한 승격 판정이 보고서와 다릅니다."
        )
    if html_path.read_text(encoding="utf-8-sig") != render_html(report):
        raise ModelPromotionError(
            "모델 승격 JSON과 HTML 내용이 일치하지 않습니다."
        )
    return report_path, report


def build_plan() -> list[str]:
    return [
        "HP_OMEN_RUNTIME_READY_WITH_DEFERRED 활성화 보고서 검증",
        "동일 입력 yolo26n.pt·best.pt A/B 성능 비교 검증",
        "명시적 정확도 기준과 승인된 클래스 매핑 검증",
        "활성화·성능·정확도·현재 best.pt SHA-256 교차 검증",
        "MODEL_PROMOTION_READY 또는 REVIEW_REQUIRED/BLOCKED 판정",
    ]


def parser(default_root: Path) -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="VisionFlow best.pt model-promotion gate"
    )
    value.add_argument("--root", default=str(default_root))
    subparsers = value.add_subparsers(dest="command", required=True)
    subparsers.add_parser("plan")
    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("--activation")
    evaluate.add_argument("--comparison")
    evaluate.add_argument("--accuracy")
    evaluate.add_argument("--model", default=DEFAULT_MODEL.as_posix())
    evaluate.add_argument("--output", default=DEFAULT_OUTPUT.as_posix())
    evaluate.add_argument("--activation-max-age-hours", type=float, default=24)
    evaluate.add_argument("--comparison-max-age-hours", type=float, default=24)
    evaluate.add_argument("--accuracy-max-age-hours", type=float, default=168)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--report", required=True)
    return value


def main(argv: Sequence[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    arguments = parser(default_root).parse_args(argv)
    root = Path(arguments.root).resolve()
    try:
        if arguments.command == "plan":
            print("VisionFlow model promotion: PLAN")
            for index, item in enumerate(build_plan(), start=1):
                print(f"{index:02d}. {item}")
            print("No model, database, Docker, service, or evidence was changed.")
            return 0

        if arguments.command == "verify":
            report_path, report = verify_report(
                root=root,
                report_path=Path(arguments.report),
            )
            print("VisionFlow model promotion: VERIFIED")
            print(f"Status: {report['status']}")
            print(f"Report: {report_path}")
            return 0

        limits = (
            arguments.activation_max_age_hours,
            arguments.comparison_max_age_hours,
            arguments.accuracy_max_age_hours,
        )
        if any(value <= 0 for value in limits):
            raise ModelPromotionError("증적 최신성 제한은 양수여야 합니다.")
        activation = resolve_input(
            root,
            arguments.activation,
            (
                "artifacts/hp-omen-restore/activation-*/"
                "visionflow-hp-omen-activation.json"
            ),
            "HP 활성화 보고서",
        )
        comparison = resolve_input(
            root,
            arguments.comparison,
            (
                "artifacts/ai-benchmark-comparison/"
                "visionflow-ai-comparison-*.json"
            ),
            "A/B 성능 비교",
        )
        accuracy = resolve_input(
            root,
            arguments.accuracy,
            "artifacts/model-evaluation/*/evaluation-report.json",
            "정확도 평가",
        )
        model = resolve_inside(root, arguments.model, "승격 후보 모델")
        output = resolve_inside(
            root,
            arguments.output,
            "모델 승격 출력",
            require_file=False,
        )
        if not is_within(
            output,
            (root / DEFAULT_OUTPUT).resolve(),
        ):
            raise ModelPromotionError(
                "모델 승격 출력은 artifacts/model-promotion 안에 있어야 합니다."
            )
        report = build_report(
            root=root,
            activation_path=activation,
            comparison_path=comparison,
            accuracy_path=accuracy,
            model_path=model,
            now=datetime.now(timezone.utc),
            activation_max_age_hours=limits[0],
            comparison_max_age_hours=limits[1],
            accuracy_max_age_hours=limits[2],
        )
        json_path, html_path, sidecar_path = write_report(
            output_directory=output,
            report=report,
        )
        verify_report(root=root, report_path=json_path)
        print(f"VisionFlow model promotion: {report['status']}")
        print(f"JSON report: {json_path}")
        print(f"HTML report: {html_path}")
        print(f"SHA-256   : {sidecar_path}")
        if report["status"] == READY_STATUS:
            return 0
        return 2 if report["status"] == REVIEW_STATUS else 1
    except (ModelPromotionError, OSError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
