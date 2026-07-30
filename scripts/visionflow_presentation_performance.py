"""Analyze and independently verify VisionFlow presentation rehearsal timing."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import statistics
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    from visionflow_presentation_rehearsal import (
        READY_STATUS as REHEARSAL_READY_STATUS,
        REPORT_ROOT as REHEARSAL_ROOT,
        PresentationRehearsalError,
        relative_path,
        verify_rehearsal_report,
    )
except ModuleNotFoundError:  # pragma: no cover - package import during tests
    from scripts.visionflow_presentation_rehearsal import (
        READY_STATUS as REHEARSAL_READY_STATUS,
        REPORT_ROOT as REHEARSAL_ROOT,
        PresentationRehearsalError,
        relative_path,
        verify_rehearsal_report,
    )


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
SCOPE = "SECOND_PROJECT_DIGITAL_TWIN"
OPERATION = "PRESENTATION_PERFORMANCE_ANALYSIS"
REPORT_ROOT = Path("artifacts/presentation-performance")
READY_STATUS = "PRESENTATION_PERFORMANCE_READY_WITH_DEFERRED"
REVIEW_STATUS = "PRESENTATION_PERFORMANCE_REVIEW_REQUIRED"
MAX_JSON_BYTES = 5 * 1024 * 1024
DEFAULT_WARNING_BUDGET_PERCENT = 70.0
DEFAULT_WARNING_CV_PERCENT = 60.0
DEFAULT_VARIABILITY_MINIMUM_MS = 250.0


class PresentationPerformanceError(RuntimeError):
    """Raised when presentation performance evidence cannot be trusted."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_checksum(value: Any) -> bool:
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


def sanitize_error(error: Exception, root: Path) -> str:
    value = str(error)
    for candidate in {
        str(root.resolve()),
        str(root.resolve()).replace("\\", "/"),
        str(root.resolve()).replace("/", "\\"),
    }:
        value = value.replace(candidate, "<PROJECT_ROOT>")
    return value


def read_json(path: Path, title: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise PresentationPerformanceError(f"{title} 파일을 찾을 수 없습니다.")
    if path.stat().st_size > MAX_JSON_BYTES:
        raise PresentationPerformanceError(f"{title} JSON 크기가 너무 큽니다.")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PresentationPerformanceError(
            f"{title} JSON 형식이 올바르지 않습니다."
        ) from error
    if not isinstance(value, dict):
        raise PresentationPerformanceError(
            f"{title} JSON 최상위 값은 객체여야 합니다."
        )
    return value


def write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    try:
        temporary.write_text(value, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def artifact_entry(root: Path, path: Path) -> dict[str, Any]:
    return {
        "path": relative_path(root, path),
        "fileName": path.name,
        "sizeBytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def percentile_nearest_rank(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[min(rank - 1, len(ordered) - 1)]


def resolve_source_rehearsal(root: Path, value: str | None) -> Path:
    allowed = (root / REHEARSAL_ROOT).resolve()
    if value:
        candidate = Path(value)
        path = (
            candidate.resolve()
            if candidate.is_absolute()
            else (root / candidate).resolve()
        )
    else:
        candidates = [
            item.resolve()
            for item in allowed.glob(
                "visionflow-presentation-rehearsal-*.json"
            )
            if item.is_file() and not item.is_symlink()
        ] if allowed.is_dir() else []
        if not candidates:
            raise PresentationPerformanceError(
                "발표 리허설 JSON이 없습니다."
            )
        path = max(
            candidates,
            key=lambda item: (item.stat().st_mtime_ns, item.name),
        )
    if (
        not is_within(path, allowed)
        or not path.is_file()
        or path.is_symlink()
        or path.suffix.lower() != ".json"
    ):
        raise PresentationPerformanceError(
            "발표 리허설 보고서 경로가 올바르지 않습니다."
        )
    return path


def verify_source_rehearsal(
    root: Path,
    value: str | None,
) -> tuple[Path, dict[str, Any]]:
    path = resolve_source_rehearsal(root, value)
    try:
        verified_path, report = verify_rehearsal_report(
            root,
            relative_path(root, path),
        )
    except PresentationRehearsalError as error:
        raise PresentationPerformanceError(str(error)) from error
    if report.get("status") != REHEARSAL_READY_STATUS:
        raise PresentationPerformanceError(
            f"최신 발표 리허설이 READY가 아닙니다: {report.get('status')}"
        )
    return verified_path, report


def coefficient_of_variation(values: list[float]) -> float:
    if not values:
        return 0.0
    average = sum(values) / len(values)
    if average == 0:
        return 0.0
    return round(statistics.pstdev(values) / average * 100, 3)


def timing_rating(
    *,
    average_ms: float,
    budget_usage_percent: float,
    cv_percent: float,
    warning_budget_percent: float,
    warning_cv_percent: float,
    variability_minimum_ms: float,
) -> tuple[str, list[str]]:
    reasons = []
    if budget_usage_percent > warning_budget_percent:
        reasons.append(
            f"시간 예산 사용률 {budget_usage_percent}%가 "
            f"주의 기준 {warning_budget_percent}%를 초과"
        )
    if (
        average_ms >= variability_minimum_ms
        and cv_percent > warning_cv_percent
    ):
        reasons.append(
            f"변동계수 {cv_percent}%가 "
            f"주의 기준 {warning_cv_percent}%를 초과"
        )
    return ("WATCH" if reasons else "READY", reasons)


def collect_stage_durations(
    rehearsal: Mapping[str, Any],
) -> dict[str, list[int]]:
    policy = rehearsal.get("policy")
    runs = rehearsal.get("runs")
    if not isinstance(policy, Mapping) or not isinstance(runs, list):
        raise PresentationPerformanceError(
            "발표 리허설 실행 정책 또는 회차 정보가 없습니다."
        )
    names = policy.get("requiredDemoResults")
    if not isinstance(names, list) or not names:
        raise PresentationPerformanceError(
            "발표 리허설 필수 단계 목록이 없습니다."
        )
    values: dict[str, list[int]] = {
        str(name): []
        for name in names
        if isinstance(name, str) and name
    }
    if len(values) != len(names):
        raise PresentationPerformanceError(
            "발표 리허설 필수 단계 목록이 올바르지 않습니다."
        )
    for run in runs:
        if not isinstance(run, Mapping) or run.get("status") != "PASS":
            raise PresentationPerformanceError(
                "성능 분석 원본에 통과하지 않은 회차가 있습니다."
            )
        seen = set()
        for stage in run.get("stages", []):
            if not isinstance(stage, Mapping):
                continue
            name = stage.get("name")
            duration = stage.get("durationMs")
            if (
                name in values
                and isinstance(duration, int)
                and not isinstance(duration, bool)
                and duration >= 0
            ):
                values[str(name)].append(duration)
                seen.add(str(name))
        missing = set(values) - seen
        if missing:
            raise PresentationPerformanceError(
                "성능 분석 원본에 필수 단계 시간이 누락되었습니다: "
                + ", ".join(sorted(missing))
            )
    if not runs or any(len(item) != len(runs) for item in values.values()):
        raise PresentationPerformanceError(
            "성능 분석 원본의 단계별 표본 수가 다릅니다."
        )
    return values


def calculate_analysis(
    rehearsal: Mapping[str, Any],
    *,
    warning_budget_percent: float,
    warning_cv_percent: float,
    variability_minimum_ms: float,
) -> dict[str, Any]:
    policy = rehearsal["policy"]
    max_run_seconds = float(policy["maxRunSeconds"])
    max_step_ms = int(policy["maxStepMs"])
    run_values = [
        float(item["elapsedSeconds"])
        for item in rehearsal["runs"]
    ]
    stage_values = collect_stage_durations(rehearsal)
    total_stage_average = sum(
        sum(values) / len(values)
        for values in stage_values.values()
    )
    stage_results = []
    for name, raw_values in stage_values.items():
        values = [float(value) for value in raw_values]
        average = sum(values) / len(values)
        maximum = max(raw_values)
        cv_percent = coefficient_of_variation(values)
        budget_usage = round(maximum / max_step_ms * 100, 3)
        rating, reasons = timing_rating(
            average_ms=average,
            budget_usage_percent=budget_usage,
            cv_percent=cv_percent,
            warning_budget_percent=warning_budget_percent,
            warning_cv_percent=warning_cv_percent,
            variability_minimum_ms=variability_minimum_ms,
        )
        stage_results.append(
            {
                "name": name,
                "samples": len(raw_values),
                "minimumMs": min(raw_values),
                "averageMs": round(average, 3),
                "p95Ms": int(percentile_nearest_rank(values, 0.95)),
                "maximumMs": maximum,
                "standardDeviationMs": round(
                    statistics.pstdev(values),
                    3,
                ),
                "coefficientOfVariationPercent": cv_percent,
                "stageSharePercent": (
                    round(average / total_stage_average * 100, 3)
                    if total_stage_average
                    else 0.0
                ),
                "budgetUsagePercent": budget_usage,
                "rating": rating,
                "reasons": reasons,
            }
        )
    stage_results.sort(
        key=lambda item: (-float(item["averageMs"]), str(item["name"]))
    )
    run_average = sum(run_values) / len(run_values)
    run_budget_usage = round(
        max(run_values) / max_run_seconds * 100,
        3,
    )
    run_cv = coefficient_of_variation(run_values)
    run_rating, run_reasons = timing_rating(
        average_ms=run_average * 1000,
        budget_usage_percent=run_budget_usage,
        cv_percent=run_cv,
        warning_budget_percent=warning_budget_percent,
        warning_cv_percent=warning_cv_percent,
        variability_minimum_ms=variability_minimum_ms,
    )
    watch_stages = [
        item["name"]
        for item in stage_results
        if item["rating"] == "WATCH"
    ]
    return {
        "runTiming": {
            "samples": len(run_values),
            "minimumSeconds": round(min(run_values), 3),
            "averageSeconds": round(run_average, 3),
            "p95Seconds": round(
                percentile_nearest_rank(run_values, 0.95),
                3,
            ),
            "maximumSeconds": round(max(run_values), 3),
            "standardDeviationSeconds": round(
                statistics.pstdev(run_values),
                3,
            ),
            "coefficientOfVariationPercent": run_cv,
            "budgetUsagePercent": run_budget_usage,
            "rating": run_rating,
            "reasons": run_reasons,
        },
        "stages": stage_results,
        "bottleneck": {
            "name": stage_results[0]["name"],
            "averageMs": stage_results[0]["averageMs"],
            "stageSharePercent": stage_results[0]["stageSharePercent"],
        },
        "topThreeSlowest": [
            {
                "name": item["name"],
                "averageMs": item["averageMs"],
                "maximumMs": item["maximumMs"],
            }
            for item in stage_results[:3]
        ],
        "watchStages": watch_stages,
        "summary": {
            "runWatch": run_rating == "WATCH",
            "watchStageCount": len(watch_stages),
            "ready": run_rating == "READY" and not watch_stages,
        },
    }


def build_report(
    *,
    root: Path,
    source_path: Path,
    rehearsal: Mapping[str, Any],
    warning_budget_percent: float,
    warning_cv_percent: float,
    variability_minimum_ms: float,
    now: datetime,
) -> dict[str, Any]:
    analysis = calculate_analysis(
        rehearsal,
        warning_budget_percent=warning_budget_percent,
        warning_cv_percent=warning_cv_percent,
        variability_minimum_ms=variability_minimum_ms,
    )
    ready = analysis["summary"]["ready"]
    deferred = [
        {
            "key": str(item.get("key")),
            "status": str(item.get("status")),
            "scope": str(item.get("scope")),
            "reason": str(item.get("reason")),
        }
        for item in rehearsal.get("deferred", [])
        if isinstance(item, Mapping)
    ]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "scope": SCOPE,
        "operation": OPERATION,
        "analysisId": str(uuid.uuid4()),
        "generatedAt": now.astimezone(timezone.utc).isoformat(),
        "status": READY_STATUS if ready else REVIEW_STATUS,
        "policy": {
            "warningBudgetUsagePercent": warning_budget_percent,
            "warningCoefficientOfVariationPercent": warning_cv_percent,
            "variabilityMinimumAverageMs": variability_minimum_ms,
        },
        "sourceRehearsal": artifact_entry(root, source_path),
        "sourceRehearsalId": str(rehearsal.get("rehearsalId")),
        "analysis": analysis,
        "deferred": deferred,
        "summary": {
            "blocking": 0,
            "reviewRequired": 0 if ready else 1,
            "bottleneck": analysis["bottleneck"]["name"],
            "watchStageCount": analysis["summary"]["watchStageCount"],
            "deferred": sum(
                item["status"] == "DEFERRED" for item in deferred
            ),
            "outOfScope": sum(
                item["status"] == "OUT_OF_SCOPE" for item in deferred
            ),
        },
        "safety": {
            "readOnly": True,
            "databaseMutation": False,
            "serviceMutation": False,
            "sourceEvidenceModified": False,
            "environmentValuesRecorded": False,
            "operatorKeysRecorded": False,
            "absolutePathsRecorded": False,
            "gpuValidationExecuted": False,
            "smartphoneSensorValidationExecuted": False,
            "djiIntegrationExecuted": False,
        },
    }


def render_html(report: Mapping[str, Any]) -> str:
    ready = report["status"] == READY_STATUS
    analysis = report["analysis"]
    run = analysis["runTiming"]
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['name']))}</td>"
        f"<td>{item['averageMs']}</td>"
        f"<td>{item['p95Ms']}</td>"
        f"<td>{item['maximumMs']}</td>"
        f"<td>{item['stageSharePercent']}%</td>"
        f"<td>{item['budgetUsagePercent']}%</td>"
        f"<td class='{str(item['rating']).lower()}'>"
        f"{html.escape(str(item['rating']))}</td>"
        "</tr>"
        for item in analysis["stages"]
    )
    deferred_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['key']))}</td>"
        f"<td>{html.escape(str(item['status']))}</td>"
        f"<td>{html.escape(str(item['reason']))}</td>"
        "</tr>"
        for item in report["deferred"]
    )
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VisionFlow 발표 성능 판정표</title><style>
body {{ margin:0; background:#eef3f8; color:#0f172a; font-family:Arial,'Noto Sans KR',sans-serif; }}
main {{ max-width:1180px; margin:32px auto; padding:0 20px; }}
section {{ background:#fff; border:1px solid #dbe4ee; border-radius:16px; padding:24px; margin:16px 0; }}
h1,h2 {{ margin-top:0; }} .status {{ color:{'#047857' if ready else '#b45309'}; font-size:1.35rem; font-weight:800; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:12px; }}
.card {{ background:#f8fafc; border-radius:12px; padding:16px; }}
table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:10px; border-bottom:1px solid #e2e8f0; text-align:left; vertical-align:top; }}
.ready {{ color:#047857; font-weight:700; }} .watch {{ color:#b45309; font-weight:700; }}
code {{ word-break:break-all; }}
</style></head><body><main>
<section><h1>VisionFlow 발표 성능 판정표</h1>
<p class="status">{html.escape(str(report['status']))}</p>
<div class="cards">
<div class="card"><strong>최대 전체 시간</strong><p>{run['maximumSeconds']}초</p></div>
<div class="card"><strong>전체 예산 사용률</strong><p>{run['budgetUsagePercent']}%</p></div>
<div class="card"><strong>최대 병목</strong><p>{html.escape(str(analysis['bottleneck']['name']))}</p></div>
<div class="card"><strong>주의 단계</strong><p>{analysis['summary']['watchStageCount']}개</p></div>
</div></section>
<section><h2>단계별 성능</h2><table><thead><tr><th>단계</th><th>평균 ms</th><th>P95 ms</th><th>최대 ms</th><th>비중</th><th>예산 사용</th><th>판정</th></tr></thead>
<tbody>{rows}</tbody></table></section>
<section><h2>보류·범위 외</h2><table><thead><tr><th>항목</th><th>상태</th><th>사유</th></tr></thead>
<tbody>{deferred_rows}</tbody></table></section>
</main></body></html>
"""


def validate_output_root(root: Path, output_root: Path) -> None:
    allowed = (root / REPORT_ROOT).resolve()
    output = output_root.resolve()
    if output != allowed or output_root.is_symlink():
        raise PresentationPerformanceError(
            "발표 성능 출력 폴더는 artifacts/presentation-performance여야 합니다."
        )


def write_report(
    root: Path,
    report: Mapping[str, Any],
    *,
    output_root: Path,
    now: datetime,
) -> tuple[Path, Path, Path]:
    validate_output_root(root, output_root)
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = output_root / f"visionflow-presentation-performance-{stamp}"
    json_path = base.with_suffix(".json")
    html_path = base.with_suffix(".html")
    sidecar = base.with_suffix(".sha256")
    write_text_atomic(
        json_path,
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    )
    write_text_atomic(html_path, render_html(report))
    write_text_atomic(
        sidecar,
        f"{sha256_file(json_path)}  {json_path.name}\n"
        f"{sha256_file(html_path)}  {html_path.name}\n",
    )
    return json_path, html_path, sidecar


def verify_sidecar(json_path: Path, html_path: Path) -> None:
    sidecar = json_path.with_suffix(".sha256")
    if not sidecar.is_file() or sidecar.is_symlink():
        raise PresentationPerformanceError(
            "발표 성능 보고서 sidecar가 없습니다."
        )
    try:
        lines = [
            line.strip().split()
            for line in sidecar.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
    except UnicodeDecodeError as error:
        raise PresentationPerformanceError(
            "발표 성능 보고서 sidecar가 UTF-8이 아닙니다."
        ) from error
    if len(lines) != 2 or any(len(parts) != 2 for parts in lines):
        raise PresentationPerformanceError(
            "발표 성능 보고서 sidecar 형식이 올바르지 않습니다."
        )
    recorded = {parts[1]: parts[0].lower() for parts in lines}
    if set(recorded) != {json_path.name, html_path.name}:
        raise PresentationPerformanceError(
            "발표 성능 보고서 sidecar 파일 목록이 다릅니다."
        )
    for path in (json_path, html_path):
        checksum = recorded[path.name]
        if (
            not is_checksum(checksum)
            or not path.is_file()
            or path.is_symlink()
            or checksum != sha256_file(path)
        ):
            raise PresentationPerformanceError(
                f"발표 성능 보고서 SHA-256이 다릅니다: {path.name}"
            )


def verify_source_artifact(root: Path, value: Any) -> Path:
    if not isinstance(value, Mapping):
        raise PresentationPerformanceError(
            "원본 발표 리허설 메타데이터가 없습니다."
        )
    relative = value.get("path")
    if not isinstance(relative, str):
        raise PresentationPerformanceError(
            "원본 발표 리허설 상대경로가 없습니다."
        )
    allowed = (root / REHEARSAL_ROOT).resolve()
    path = (root / relative).resolve()
    if (
        not is_within(path, allowed)
        or not path.is_file()
        or path.is_symlink()
        or value.get("fileName") != path.name
        or value.get("sizeBytes") != path.stat().st_size
        or value.get("sha256") != sha256_file(path)
    ):
        raise PresentationPerformanceError(
            "원본 발표 리허설 파일 동일성이 다릅니다."
        )
    return path


def resolve_performance_report(root: Path, value: str) -> Path:
    candidate = Path(value)
    path = (
        candidate.resolve()
        if candidate.is_absolute()
        else (root / candidate).resolve()
    )
    allowed = (root / REPORT_ROOT).resolve()
    if (
        not is_within(path, allowed)
        or not path.is_file()
        or path.is_symlink()
        or path.suffix.lower() != ".json"
    ):
        raise PresentationPerformanceError(
            "발표 성능 보고서 경로가 올바르지 않습니다."
        )
    return path


def validate_policy(policy: Any) -> tuple[float, float, float]:
    if not isinstance(policy, Mapping):
        raise PresentationPerformanceError(
            "발표 성능 분석 정책이 없습니다."
        )
    values = (
        policy.get("warningBudgetUsagePercent"),
        policy.get("warningCoefficientOfVariationPercent"),
        policy.get("variabilityMinimumAverageMs"),
    )
    if any(
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or value <= 0
        for value in values
    ):
        raise PresentationPerformanceError(
            "발표 성능 분석 정책이 올바르지 않습니다."
        )
    warning_budget, warning_cv, variability_minimum = (
        float(item) for item in values
    )
    if warning_budget > 100 or warning_cv > 500:
        raise PresentationPerformanceError(
            "발표 성능 분석 정책 범위가 올바르지 않습니다."
        )
    return warning_budget, warning_cv, variability_minimum


def verify_performance_report(
    root: Path,
    value: str,
) -> tuple[Path, dict[str, Any]]:
    json_path = resolve_performance_report(root, value)
    html_path = json_path.with_suffix(".html")
    verify_sidecar(json_path, html_path)
    report = read_json(json_path, "발표 성능")
    if (
        report.get("schemaVersion") != SCHEMA_VERSION
        or report.get("project") != PROJECT_NAME
        or report.get("scope") != SCOPE
        or report.get("operation") != OPERATION
        or report.get("status") not in {READY_STATUS, REVIEW_STATUS}
        or not isinstance(report.get("analysisId"), str)
        or not isinstance(report.get("generatedAt"), str)
        or not isinstance(report.get("analysis"), Mapping)
        or not isinstance(report.get("deferred"), list)
        or not isinstance(report.get("summary"), Mapping)
        or not isinstance(report.get("safety"), Mapping)
    ):
        raise PresentationPerformanceError(
            "발표 성능 보고서 형식이 올바르지 않습니다."
        )
    warning_budget, warning_cv, variability_minimum = validate_policy(
        report.get("policy")
    )
    source_path = verify_source_artifact(
        root,
        report.get("sourceRehearsal"),
    )
    try:
        _, rehearsal = verify_rehearsal_report(
            root,
            relative_path(root, source_path),
        )
    except PresentationRehearsalError as error:
        raise PresentationPerformanceError(str(error)) from error
    if (
        rehearsal.get("status") != REHEARSAL_READY_STATUS
        or report.get("sourceRehearsalId")
        != str(rehearsal.get("rehearsalId"))
    ):
        raise PresentationPerformanceError(
            "원본 발표 리허설 상태 또는 식별자가 다릅니다."
        )
    expected_analysis = calculate_analysis(
        rehearsal,
        warning_budget_percent=warning_budget,
        warning_cv_percent=warning_cv,
        variability_minimum_ms=variability_minimum,
    )
    if report.get("analysis") != expected_analysis:
        raise PresentationPerformanceError(
            "발표 성능 분석이 원본 리허설과 다릅니다."
        )
    deferred = [
        {
            "key": str(item.get("key")),
            "status": str(item.get("status")),
            "scope": str(item.get("scope")),
            "reason": str(item.get("reason")),
        }
        for item in rehearsal.get("deferred", [])
        if isinstance(item, Mapping)
    ]
    ready = expected_analysis["summary"]["ready"]
    expected_summary = {
        "blocking": 0,
        "reviewRequired": 0 if ready else 1,
        "bottleneck": expected_analysis["bottleneck"]["name"],
        "watchStageCount": expected_analysis["summary"]["watchStageCount"],
        "deferred": sum(
            item["status"] == "DEFERRED" for item in deferred
        ),
        "outOfScope": sum(
            item["status"] == "OUT_OF_SCOPE" for item in deferred
        ),
    }
    safety = report["safety"]
    if (
        report.get("deferred") != deferred
        or report.get("summary") != expected_summary
        or report.get("status") != (READY_STATUS if ready else REVIEW_STATUS)
        or safety.get("readOnly") is not True
        or safety.get("databaseMutation") is not False
        or safety.get("serviceMutation") is not False
        or safety.get("sourceEvidenceModified") is not False
        or safety.get("environmentValuesRecorded") is not False
        or safety.get("operatorKeysRecorded") is not False
        or safety.get("absolutePathsRecorded") is not False
        or safety.get("gpuValidationExecuted") is not False
        or safety.get("smartphoneSensorValidationExecuted") is not False
        or safety.get("djiIntegrationExecuted") is not False
    ):
        raise PresentationPerformanceError(
            "발표 성능 최종 판정 또는 안전 메타데이터가 다릅니다."
        )
    try:
        html_value = html_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise PresentationPerformanceError(
            "발표 성능 HTML이 UTF-8이 아닙니다."
        ) from error
    lowered = html_value.lower()
    if any(
        token in lowered
        for token in ("<script", "<iframe", "<object", "<embed", "javascript:")
    ):
        raise PresentationPerformanceError(
            "발표 성능 HTML에 실행 가능한 콘텐츠가 있습니다."
        )
    if html_value != render_html(report):
        raise PresentationPerformanceError(
            "발표 성능 JSON과 HTML 내용이 일치하지 않습니다."
        )
    return json_path, report


def analyze_performance(
    root: Path,
    *,
    rehearsal_value: str | None,
    output_root: Path,
    warning_budget_percent: float,
    warning_cv_percent: float,
    variability_minimum_ms: float,
    now: datetime,
) -> tuple[Path, Path, Path, dict[str, Any]]:
    source_path, rehearsal = verify_source_rehearsal(
        root,
        rehearsal_value,
    )
    report = build_report(
        root=root,
        source_path=source_path,
        rehearsal=rehearsal,
        warning_budget_percent=warning_budget_percent,
        warning_cv_percent=warning_cv_percent,
        variability_minimum_ms=variability_minimum_ms,
        now=now,
    )
    json_path, html_path, sidecar = write_report(
        root,
        report,
        output_root=output_root,
        now=now,
    )
    return json_path, html_path, sidecar, report


def build_plan() -> list[dict[str, str]]:
    return [
        {
            "order": "01",
            "mode": "READ_ONLY",
            "detail": "최신 READY 발표 리허설과 연결 증적 독립 검증",
        },
        {
            "order": "02",
            "mode": "ANALYZE",
            "detail": "전체 실행시간·단계별 평균·P95·최대·변동성 계산",
        },
        {
            "order": "03",
            "mode": "ASSESS",
            "detail": "병목·시간 예산 사용률·주의 단계 판정",
        },
        {
            "order": "04",
            "mode": "EVIDENCE",
            "detail": "JSON·HTML·SHA-256 성능 판정표 생성 및 재검증",
        },
    ]


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="VisionFlow presentation performance analyzer"
    )
    parser.add_argument("--root", default=str(default_root))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("plan", help="변경 없는 분석 계획 출력")
    analyze = subparsers.add_parser(
        "analyze",
        help="최신 발표 리허설 성능 분석",
    )
    analyze.add_argument("--rehearsal")
    analyze.add_argument(
        "--warning-budget-percent",
        type=float,
        default=DEFAULT_WARNING_BUDGET_PERCENT,
    )
    analyze.add_argument(
        "--warning-cv-percent",
        type=float,
        default=DEFAULT_WARNING_CV_PERCENT,
    )
    analyze.add_argument(
        "--variability-minimum-ms",
        type=float,
        default=DEFAULT_VARIABILITY_MINIMUM_MS,
    )
    analyze.add_argument("--output", default=REPORT_ROOT.as_posix())
    verify = subparsers.add_parser(
        "verify",
        help="발표 성능 증적 독립 재검증",
    )
    verify.add_argument("--report", required=True)
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    args = build_parser(default_root).parse_args(arguments)
    root = Path(args.root).resolve()
    try:
        if not root.is_dir():
            raise PresentationPerformanceError(
                "프로젝트 루트를 찾을 수 없습니다."
            )
        if args.command == "plan":
            print("VisionFlow presentation performance: PLAN")
            for item in build_plan():
                print(f"{item['order']}. [{item['mode']}] {item['detail']}")
            print(
                "No database, service, GPU, smartphone, or DJI action "
                "was executed."
            )
            return 0
        if args.command == "verify":
            path, report = verify_performance_report(root, args.report)
            print("VisionFlow presentation performance: VERIFIED")
            print(f"Status: {report['status']}")
            print(f"Report: {path}")
            return 0
        validate_policy(
            {
                "warningBudgetUsagePercent": args.warning_budget_percent,
                "warningCoefficientOfVariationPercent":
                    args.warning_cv_percent,
                "variabilityMinimumAverageMs":
                    args.variability_minimum_ms,
            }
        )
        output_value = Path(args.output)
        output = (
            output_value.resolve()
            if output_value.is_absolute()
            else (root / output_value).resolve()
        )
        json_path, html_path, sidecar, report = analyze_performance(
            root,
            rehearsal_value=args.rehearsal,
            output_root=output,
            warning_budget_percent=args.warning_budget_percent,
            warning_cv_percent=args.warning_cv_percent,
            variability_minimum_ms=args.variability_minimum_ms,
            now=datetime.now(timezone.utc),
        )
        print(f"VisionFlow presentation performance: {report['status']}")
        print(
            "Bottleneck: "
            f"{report['analysis']['bottleneck']['name']} "
            f"({report['analysis']['bottleneck']['averageMs']} ms avg)"
        )
        print(
            "Run budget usage: "
            f"{report['analysis']['runTiming']['budgetUsagePercent']}%"
        )
        print(
            "Watch stages: "
            f"{report['analysis']['summary']['watchStageCount']}"
        )
        print(f"JSON report: {json_path}")
        print(f"HTML report: {html_path}")
        print(f"SHA-256: {sidecar}")
        return 0 if report["status"] == READY_STATUS else 2
    except (
        PresentationPerformanceError,
        PresentationRehearsalError,
        FileNotFoundError,
        OSError,
        ValueError,
    ) as error:
        print(f"[FAIL] {sanitize_error(error, root)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
