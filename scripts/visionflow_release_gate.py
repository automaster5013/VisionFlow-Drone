"""Build a non-mutating VisionFlow second-project release readiness report."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from visionflow_retention import (
    RetentionError,
    load_audit_report,
    parse_datetime,
    sha256_file,
    verify_backup,
)


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
SCOPE = "SECOND_PROJECT_DIGITAL_TWIN"
EVIDENCE_ROOTS = {
    "acceptance": Path("artifacts/visionflow-acceptance"),
    "backup": Path("backups"),
    "audit": Path("artifacts/storage-audit"),
    "drill": Path("artifacts/retention-drill"),
    "benchmark": Path("artifacts/ai-benchmark"),
    "csp": Path("artifacts/csp-observability"),
    "maintenance": Path("artifacts/maintenance-acceptance"),
    "mobile": Path("artifacts/mobile-readiness"),
}

REQUIRED_SECURITY_RESULTS = {
    "Backend health",
    "Frontend dashboard",
    "AI ingest status",
    "AI stream status",
    "Frontend security headers",
    "Frontend CSP report observability",
    "RBAC enabled mode",
    "Operator browser session mode",
    "Demo flight complete",
}
REQUIRED_MOBILE_EVIDENCE_CHECKS = {
    "trusted-https-endpoint",
    "browser-permission-policy",
    "completed-flight-session",
    "mobile-source-identity",
    "telemetry-minimum",
    "mobile-sensor-source",
    "gps-values",
    "orientation-values",
    "ai-events",
    "ai-detections",
}


class ReleaseGateError(RuntimeError):
    """Raised when release evidence cannot be inspected safely."""


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def write_json(path: Path, value: dict[str, Any]) -> None:
    write_text_atomic(
        path,
        json.dumps(value, ensure_ascii=False, indent=2),
    )


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise ReleaseGateError(f"JSON 형식이 올바르지 않습니다: {path}") from error
    if not isinstance(value, dict):
        raise ReleaseGateError(f"JSON 최상위 값은 객체여야 합니다: {path}")
    return value


def current_age_hours(value: Any, label: str, now: datetime) -> float:
    generated_at = parse_datetime(value, label)
    age = (now - generated_at).total_seconds() / 3600.0
    if age < -0.1:
        raise ReleaseGateError(f"{label} 시각이 미래입니다: {generated_at.isoformat()}")
    return age


def resolve_override(root: Path, value: str | None, category: str) -> Path | None:
    if not value:
        return None
    path = Path(value)
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    allowed_root = (root / EVIDENCE_ROOTS[category]).resolve()
    if not is_within(resolved, allowed_root):
        raise ReleaseGateError(
            f"{category} 증빙이 허용 경로를 벗어났습니다: {resolved}"
        )
    if not resolved.is_file() or resolved.is_symlink():
        raise ReleaseGateError(f"{category} 증빙 파일을 찾을 수 없습니다: {resolved}")
    return resolved


def newest_file(root: Path, category: str, pattern: str) -> Path | None:
    evidence_root = (root / EVIDENCE_ROOTS[category]).resolve()
    if not evidence_root.is_dir():
        return None
    candidates = [
        path.resolve()
        for path in evidence_root.rglob(pattern)
        if path.is_file() and not path.is_symlink()
    ]
    return max(candidates, key=lambda path: path.stat().st_mtime, default=None)


def newest_demo_acceptance(root: Path) -> Path | None:
    evidence_root = (root / EVIDENCE_ROOTS["acceptance"]).resolve()
    if not evidence_root.is_dir():
        return None
    candidates = sorted(
        (
            path.resolve()
            for path in evidence_root.rglob("visionflow-acceptance-*.json")
            if path.is_file() and not path.is_symlink()
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    newest_readable = None
    newest_demo = None
    for path in candidates:
        try:
            report = read_json(path)
        except ReleaseGateError:
            continue
        if newest_readable is None:
            newest_readable = path
        configuration = report.get("configuration")
        if not isinstance(configuration, dict):
            continue
        if configuration.get("runDemo") is True and newest_demo is None:
            newest_demo = path
        if all(
            configuration.get(flag) is True
            for flag in ("runDemo", "runRbac", "runSession")
        ):
            return path
    return newest_demo or newest_readable


def evidence_reference(root: Path, path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sizeBytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def check_result(
    key: str,
    title: str,
    status: str,
    detail: str,
    *,
    evidence: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "title": title,
        "requirement": "REQUIRED",
        "status": status,
        "detail": detail,
        "evidence": evidence,
        "metrics": metrics or {},
    }


def missing_result(key: str, title: str, expected_root: Path) -> dict[str, Any]:
    return check_result(
        key,
        title,
        "MISSING",
        f"증빙 파일이 없습니다: {expected_root.as_posix()}",
    )


def inspect_acceptance(
    root: Path,
    path: Path | None,
    *,
    now: datetime,
    max_age_hours: float,
) -> dict[str, Any]:
    key = "acceptance-demo"
    title = "통합 자동 인수·영속 데모·운영 보안"
    if path is None:
        return missing_result(key, title, EVIDENCE_ROOTS["acceptance"])
    try:
        report = read_json(path)
        age = current_age_hours(report.get("generatedAt"), "인수 테스트", now)
        configuration = report.get("configuration")
        summary = report.get("summary")
        if not isinstance(configuration, dict):
            raise ReleaseGateError("인수 테스트 configuration이 없습니다.")
        missing_modes = [
            flag
            for flag in ("runDemo", "runRbac", "runSession")
            if configuration.get(flag) is not True
        ]
        if missing_modes:
            raise ReleaseGateError(
                "통합 인수 테스트 실행 옵션이 빠졌습니다: " + ", ".join(missing_modes)
            )
        if configuration.get("skipAi") is not False:
            raise ReleaseGateError("통합 인수 테스트에서 AI 검증이 제외되었습니다.")
        if not isinstance(summary, dict):
            raise ReleaseGateError("인수 테스트 summary가 없습니다.")
        total = summary.get("total")
        passed = summary.get("passed")
        failed = summary.get("failed")
        if not all(isinstance(value, int) and not isinstance(value, bool) for value in (total, passed, failed)):
            raise ReleaseGateError("인수 테스트 집계 값이 올바르지 않습니다.")
        if total <= 0 or failed != 0 or passed != total:
            raise ReleaseGateError(
                f"인수 테스트 실패가 있습니다: total={total}, passed={passed}, failed={failed}"
            )
        results = report.get("results")
        if not isinstance(results, list):
            raise ReleaseGateError("인수 테스트 results가 없습니다.")
        passed_result_names = {
            str(item.get("Name") or item.get("name"))
            for item in results
            if isinstance(item, dict)
            and (item.get("Passed") is True or item.get("passed") is True)
        }
        missing_results = sorted(REQUIRED_SECURITY_RESULTS - passed_result_names)
        if missing_results:
            raise ReleaseGateError(
                "필수 통합 검증 결과가 없습니다: " + ", ".join(missing_results)
            )
        scenario = report.get("scenario")
        if not isinstance(scenario, dict) or scenario.get("stage") != "COMPLETED":
            raise ReleaseGateError("영속 데모 시나리오가 COMPLETED 상태가 아닙니다.")
        if age > max_age_hours:
            raise ReleaseGateError(
                f"인수 테스트 보고서가 오래됐습니다: {age:.2f}시간"
            )
        return check_result(
            key,
            title,
            "PASS",
            "핵심 서비스, 영속 데모, RBAC, 브라우저 세션·CSRF와 보안 헤더가 모두 통과했습니다.",
            evidence=evidence_reference(root, path),
            metrics={
                "ageHours": round(age, 3),
                "total": total,
                "passed": passed,
                "runDemo": True,
                "runRbac": True,
                "runSession": True,
            },
        )
    except (ReleaseGateError, RetentionError, OSError) as error:
        return check_result(
            key,
            title,
            "FAILED",
            str(error),
            evidence=evidence_reference(root, path),
        )


def inspect_maintenance_acceptance(
    root: Path,
    path: Path | None,
    *,
    now: datetime,
    max_age_hours: float,
) -> dict[str, Any]:
    key = "maintenance-operations"
    title = "정비 비행 게이트·운영 KPI"
    if path is None:
        return missing_result(key, title, EVIDENCE_ROOTS["maintenance"])
    try:
        report = read_json(path)
        if report.get("schemaVersion") != SCHEMA_VERSION:
            raise ReleaseGateError("지원하지 않는 정비 인수 스키마입니다.")
        if report.get("project") != PROJECT_NAME:
            raise ReleaseGateError("VisionFlow 정비 인수 보고서가 아닙니다.")
        if (
            report.get("operation")
            != "MAINTENANCE_FLIGHT_GATE_ACCEPTANCE"
        ):
            raise ReleaseGateError("정비 운영 인수 보고서가 아닙니다.")
        if report.get("status") != "MAINTENANCE_GATE_READY":
            raise ReleaseGateError(
                "정비 운영 인수 테스트가 통과하지 않았습니다: "
                f"{report.get('status')}"
            )
        age = current_age_hours(
            report.get("generatedAt"),
            "정비 운영 인수 테스트",
            now,
        )
        if age > max_age_hours:
            raise ReleaseGateError(
                f"정비 운영 인수 보고서가 오래됐습니다: {age:.2f}시간"
            )
        summary = report.get("summary")
        if not isinstance(summary, dict):
            raise ReleaseGateError("정비 인수 summary가 없습니다.")
        total = summary.get("total")
        passed = summary.get("passed")
        failed = summary.get("failed")
        if not all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in (total, passed, failed)
        ):
            raise ReleaseGateError("정비 인수 집계 값이 올바르지 않습니다.")
        if total <= 0 or passed != total or failed != 0:
            raise ReleaseGateError(
                "정비 인수 테스트 실패가 있습니다: "
                f"total={total}, passed={passed}, failed={failed}"
            )
        checks = report.get("checks")
        if not isinstance(checks, list):
            raise ReleaseGateError("정비 인수 checks가 없습니다.")
        required_checks = {
            "backend-maintenance-metrics",
            "frontend-maintenance-metrics-proxy",
            "backend-maintenance-metrics-window-validation",
            "frontend-maintenance-metrics-window-validation",
            "frontend-maintenance-kpi-content",
        }
        passed_checks = {
            item.get("key")
            for item in checks
            if isinstance(item, dict) and item.get("status") == "PASS"
        }
        missing_checks = sorted(required_checks - passed_checks)
        if missing_checks:
            raise ReleaseGateError(
                "정비 KPI 필수 검증 결과가 없습니다: "
                + ", ".join(missing_checks)
            )
        safety = report.get("safety")
        if (
            not isinstance(safety, dict)
            or safety.get("readOnly") is not True
            or safety.get("databaseMutation") is not False
            or safety.get("httpMethods") != ["GET"]
        ):
            raise ReleaseGateError(
                "정비 운영 인수 보고서가 읽기 전용이 아닙니다."
            )
        evidence = report.get("evidence")
        if not isinstance(evidence, dict):
            raise ReleaseGateError("정비 KPI evidence가 없습니다.")
        return check_result(
            key,
            title,
            "PASS",
            "정비 비행 게이트와 기간별 운영 KPI가 모두 통과했습니다.",
            evidence=evidence_reference(root, path),
            metrics={
                "ageHours": round(age, 3),
                "total": total,
                "passed": passed,
                "windowDays": evidence.get("metricsWindowDays"),
                "totalWorkOrders":
                    evidence.get("metricsTotalWorkOrders"),
                "resolutionRatePercent":
                    evidence.get("metricsResolutionRatePercent"),
            },
        )
    except (ReleaseGateError, RetentionError, OSError) as error:
        return check_result(
            key,
            title,
            "FAILED",
            str(error),
            evidence=evidence_reference(root, path),
        )


def inspect_backup(
    root: Path,
    path: Path | None,
    *,
    now: datetime,
    max_age_days: float,
) -> dict[str, Any]:
    key = "verified-backup"
    title = "복구 가능한 최신 백업"
    if path is None:
        return missing_result(key, title, EVIDENCE_ROOTS["backup"])
    try:
        verified = verify_backup(path, max_age_days=max_age_days, now=now)
        return check_result(
            key,
            title,
            "PASS",
            "백업 ZIP의 manifest, MySQL 덤프, 크기와 SHA-256이 유효합니다.",
            evidence=evidence_reference(root, path),
            metrics={"ageDays": round(verified["ageDays"], 3)},
        )
    except (RetentionError, OSError) as error:
        return check_result(
            key,
            title,
            "FAILED",
            str(error),
            evidence=evidence_reference(root, path),
        )


def inspect_storage_audit(
    root: Path,
    path: Path | None,
    *,
    now: datetime,
    max_age_hours: float,
) -> dict[str, Any]:
    key = "storage-audit"
    title = "저장공간 및 보존 정책 감사"
    if path is None:
        return missing_result(key, title, EVIDENCE_ROOTS["audit"])
    try:
        report = load_audit_report(
            path,
            root,
            max_age_hours=max_age_hours,
            now=now,
        )
        status = report.get("status")
        if status not in {"HEALTHY", "WARNING"}:
            raise ReleaseGateError(f"지원하지 않는 저장공간 감사 상태입니다: {status}")
        result_status = "WARNING" if status == "WARNING" else "PASS"
        retention = report["retention"]
        return check_result(
            key,
            title,
            result_status,
            f"저장공간 감사 상태는 {status}이며 삭제 없는 정책 보고서입니다.",
            evidence=evidence_reference(root, path),
            metrics={
                "auditStatus": status,
                "candidateCount": retention.get("candidateCount", 0),
            },
        )
    except (RetentionError, OSError) as error:
        return check_result(
            key,
            title,
            "FAILED",
            str(error),
            evidence=evidence_reference(root, path),
        )


def inspect_recovery_drill(
    root: Path,
    path: Path | None,
    *,
    now: datetime,
    max_age_hours: float,
) -> dict[str, Any]:
    key = "retention-recovery-drill"
    title = "격리 및 원위치 복원 리허설"
    if path is None:
        return missing_result(key, title, EVIDENCE_ROOTS["drill"])
    try:
        report = read_json(path)
        if report.get("schemaVersion") != SCHEMA_VERSION:
            raise ReleaseGateError("지원하지 않는 복구 리허설 스키마입니다.")
        if report.get("project") != PROJECT_NAME:
            raise ReleaseGateError("VisionFlow 복구 리허설 보고서가 아닙니다.")
        if report.get("operation") != "RETENTION_RECOVERY_DRILL":
            raise ReleaseGateError("보존 정책 복구 리허설 보고서가 아닙니다.")
        status = report.get("status")
        if status not in {"PASSED", "NO_CANDIDATES"}:
            raise ReleaseGateError(f"복구 리허설이 완료되지 않았습니다: {status}")
        timestamp = report.get("completedAt") or report.get("startedAt")
        age = current_age_hours(timestamp, "복구 리허설", now)
        if age > max_age_hours:
            raise ReleaseGateError(f"복구 리허설 보고서가 오래됐습니다: {age:.2f}시간")
        return check_result(
            key,
            title,
            "PASS",
            f"복구 리허설 상태가 {status}입니다.",
            evidence=evidence_reference(root, path),
            metrics={"ageHours": round(age, 3), "drillStatus": status},
        )
    except (ReleaseGateError, RetentionError, OSError) as error:
        return check_result(
            key,
            title,
            "FAILED",
            str(error),
            evidence=evidence_reference(root, path),
        )


def inspect_benchmark(
    root: Path,
    path: Path | None,
    *,
    now: datetime,
    max_age_days: float,
) -> dict[str, Any]:
    key = "ai-cpu-baseline"
    title = "LG GRAM AI CPU 성능 기준선"
    if path is None:
        return missing_result(key, title, EVIDENCE_ROOTS["benchmark"])
    try:
        report = read_json(path)
        age_hours = current_age_hours(report.get("generatedAt"), "AI 벤치마크", now)
        sample_count = report.get("sampleCount")
        processed = report.get("processedFrameDelta")
        inference_ms = report.get("averageInferenceMs")
        model_name = report.get("modelName")
        device = report.get("device")
        if not isinstance(sample_count, int) or isinstance(sample_count, bool) or sample_count <= 0:
            raise ReleaseGateError("AI 벤치마크 샘플이 없습니다.")
        if not isinstance(processed, int) or isinstance(processed, bool) or processed <= 0:
            raise ReleaseGateError("AI 벤치마크 처리 프레임이 없습니다.")
        if not isinstance(inference_ms, (int, float)) or isinstance(inference_ms, bool) or inference_ms <= 0:
            raise ReleaseGateError("평균 추론 시간이 올바르지 않습니다.")
        if not isinstance(model_name, str) or not model_name.strip():
            raise ReleaseGateError("벤치마크 모델명이 없습니다.")
        if not isinstance(device, str) or not device.strip():
            raise ReleaseGateError("벤치마크 실행 장치가 없습니다.")
        age_days = age_hours / 24.0
        if age_days > max_age_days:
            raise ReleaseGateError(f"AI 벤치마크가 오래됐습니다: {age_days:.2f}일")
        return check_result(
            key,
            title,
            "PASS",
            "현재 노트북의 비교 기준선으로 사용할 측정 결과가 존재합니다.",
            evidence=evidence_reference(root, path),
            metrics={
                "ageDays": round(age_days, 3),
                "modelName": model_name,
                "device": device,
                "sampleCount": sample_count,
                "processedFrameDelta": processed,
                "averageInferenceMs": inference_ms,
            },
        )
    except (ReleaseGateError, RetentionError, OSError) as error:
        return check_result(
            key,
            title,
            "FAILED",
            str(error),
            evidence=evidence_reference(root, path),
        )


def verify_csp_sidecar(path: Path) -> dict[str, str]:
    sidecar = path.with_suffix(".sha256")
    if not sidecar.is_file() or sidecar.is_symlink():
        raise ReleaseGateError(f"CSP 증적 SHA-256 파일이 없습니다: {sidecar}")
    entries: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        sidecar.read_text(encoding="utf-8-sig").splitlines(), start=1
    ):
        if not raw_line.strip():
            continue
        match = re.fullmatch(r"([0-9a-fA-F]{64})  ([^/\\]+)", raw_line.strip())
        if not match:
            raise ReleaseGateError(
                f"CSP SHA-256 {line_number}행 형식이 올바르지 않습니다."
            )
        digest, filename = match.groups()
        if filename in entries:
            raise ReleaseGateError(f"CSP SHA-256 파일명이 중복됩니다: {filename}")
        entries[filename] = digest.lower()
    expected_names = {
        path.name,
        path.with_suffix(".csv").name,
        path.with_suffix(".html").name,
    }
    if set(entries) != expected_names:
        raise ReleaseGateError("CSP SHA-256 파일 목록이 JSON·CSV·HTML 증적과 다릅니다.")
    for filename, expected_digest in entries.items():
        evidence_path = path.parent / filename
        if not evidence_path.is_file() or evidence_path.is_symlink():
            raise ReleaseGateError(f"CSP 증적 파일이 없습니다: {evidence_path}")
        if sha256_file(evidence_path) != expected_digest:
            raise ReleaseGateError(f"CSP 증적 SHA-256이 일치하지 않습니다: {filename}")
    return entries


def verify_single_file_sidecar(path: Path, title: str) -> str:
    sidecar = path.with_suffix(".sha256")
    if not sidecar.is_file() or sidecar.is_symlink():
        raise ReleaseGateError(f"{title} SHA-256 파일이 없습니다: {sidecar}")
    lines = [
        line.strip()
        for line in sidecar.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    if len(lines) != 1:
        raise ReleaseGateError(f"{title} SHA-256 파일은 한 행이어야 합니다.")
    match = re.fullmatch(r"([0-9a-fA-F]{64})  ([^/\\]+)", lines[0])
    if not match or match.group(2) != path.name:
        raise ReleaseGateError(f"{title} SHA-256 형식 또는 파일명이 올바르지 않습니다.")
    expected = match.group(1).lower()
    actual = sha256_file(path)
    if actual != expected:
        raise ReleaseGateError(f"{title} SHA-256이 일치하지 않습니다.")
    return actual


def mobile_deferred(reason: str) -> dict[str, str]:
    return {
        "key": "smartphone-real-sensor-https",
        "title": "스마트폰 실센서·카메라 HTTPS E2E 검증",
        "status": "DEFERRED",
        "scope": "SECOND_PROJECT_FOLLOW_UP",
        "reason": reason,
    }


def inspect_mobile_evidence(
    root: Path,
    path: Path | None,
    *,
    now: datetime,
    max_age_days: float,
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    title = "스마트폰 실센서·카메라 HTTPS E2E 검증"
    if path is None:
        return None, mobile_deferred(
            "아직 SMARTPHONE_E2E_PASS 증적이 없어 후속 검증으로 유지합니다."
        )
    try:
        report = read_json(path)
        if (
            report.get("schemaVersion") != SCHEMA_VERSION
            or report.get("project") != PROJECT_NAME
            or report.get("operation") != "SMARTPHONE_E2E_VERIFICATION"
        ):
            raise ReleaseGateError("VisionFlow 스마트폰 E2E 증적이 아닙니다.")
        if report.get("status") != "SMARTPHONE_E2E_PASS":
            raise ReleaseGateError(
                f"스마트폰 E2E 상태가 PASS가 아닙니다: {report.get('status')}"
            )
        age_hours = current_age_hours(report.get("generatedAt"), title, now)
        if age_hours > max_age_days * 24:
            raise ReleaseGateError(
                f"스마트폰 E2E 증적이 오래됐습니다: {age_hours / 24:.2f}일"
            )
        checks = report.get("checks")
        if not isinstance(checks, list) or not checks:
            raise ReleaseGateError("스마트폰 E2E 세부 검증이 없습니다.")
        checks_by_key = {
            item.get("key"): item
            for item in checks
            if isinstance(item, dict) and isinstance(item.get("key"), str)
        }
        missing = REQUIRED_MOBILE_EVIDENCE_CHECKS - checks_by_key.keys()
        if missing:
            raise ReleaseGateError(
                "스마트폰 E2E 필수 검증 항목이 없습니다: "
                + ", ".join(sorted(missing))
            )
        if any(
            checks_by_key[key].get("status") != "PASS"
            for key in REQUIRED_MOBILE_EVIDENCE_CHECKS
        ):
            raise ReleaseGateError("스마트폰 E2E 세부 검증에 미통과 항목이 있습니다.")
        privacy = report.get("privacy")
        if not isinstance(privacy, dict) or any(
            privacy.get(key) is not False
            for key in (
                "exactCoordinatesRecorded",
                "operatorKeyRecorded",
                "sessionTokenRecorded",
                "rawImageRecorded",
                "rawVideoRecorded",
            )
        ):
            raise ReleaseGateError("스마트폰 E2E 개인정보 보호 정보가 올바르지 않습니다.")
        safety = report.get("safety")
        if (
            not isinstance(safety, dict)
            or safety.get("readOnly") is not True
            or safety.get("databaseMutation") is not False
            or safety.get("externalMessagesSent") is not False
        ):
            raise ReleaseGateError("스마트폰 E2E 증적이 읽기 전용 검증이 아닙니다.")
        digest = verify_single_file_sidecar(path, title)
        evidence = report.get("evidence")
        if not isinstance(evidence, dict):
            raise ReleaseGateError("스마트폰 E2E 비식별 증거 요약이 없습니다.")
        return (
            check_result(
                "smartphone-real-sensor-https",
                title,
                "PASS",
                "신뢰된 HTTPS에서 GPS·방향 센서·카메라·AI 세션 E2E 검증을 완료했습니다.",
                evidence=evidence_reference(root, path),
                metrics={
                    "ageDays": round(age_hours / 24, 3),
                    "sidecarVerified": True,
                    "reportSha256": digest,
                    "droneId": evidence.get("droneId"),
                    "sessionId": evidence.get("sessionId"),
                    "telemetryCount": evidence.get("telemetryCount"),
                    "mobileSensorCount": evidence.get("mobileSensorCount"),
                    "aiEventCount": evidence.get("aiEventCount"),
                    "detectionCount": evidence.get("detectionCount"),
                },
            ),
            None,
        )
    except (ReleaseGateError, RetentionError, OSError) as error:
        return None, mobile_deferred(f"스마트폰 E2E 증적 확인 필요: {error}")


def inspect_csp_observation(
    root: Path,
    path: Path | None,
    *,
    now: datetime,
    max_age_hours: float,
) -> dict[str, Any]:
    key = "csp-report-only-observation"
    title = "CSP Report-Only 관찰 증적"
    if path is None:
        return missing_result(key, title, EVIDENCE_ROOTS["csp"])
    try:
        report = read_json(path)
        if report.get("schemaVersion") != SCHEMA_VERSION:
            raise ReleaseGateError("지원하지 않는 CSP 증적 스키마입니다.")
        if report.get("project") != PROJECT_NAME:
            raise ReleaseGateError("VisionFlow CSP 증적이 아닙니다.")
        if report.get("operation") != "CSP_REPORT_ONLY_OBSERVATION":
            raise ReleaseGateError("CSP Report-Only 관찰 증적이 아닙니다.")
        status = report.get("status")
        if status not in {
            "CSP_OBSERVATION_CLEAN",
            "CSP_OBSERVATION_REVIEW_REQUIRED",
        }:
            raise ReleaseGateError(f"지원하지 않는 CSP 관찰 상태입니다: {status}")
        age = current_age_hours(report.get("generatedAt"), "CSP 관찰 증적", now)
        if age > max_age_hours:
            raise ReleaseGateError(f"CSP 관찰 증적이 오래됐습니다: {age:.2f}시간")
        summary = report.get("summary")
        observation = report.get("observation")
        if not isinstance(summary, dict) or not isinstance(observation, dict):
            raise ReleaseGateError("CSP 증적 summary 또는 observation이 없습니다.")
        total = summary.get("totalReports")
        retained = summary.get("retainedReports")
        if not all(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for value in (total, retained)
        ):
            raise ReleaseGateError("CSP 증적 건수가 올바르지 않습니다.")
        if observation.get("mode") != "REPORT_ONLY":
            raise ReleaseGateError("CSP 증적 모드가 REPORT_ONLY가 아닙니다.")
        if observation.get("persisted") is not False:
            raise ReleaseGateError("CSP 증적이 비영속 관찰 모드가 아닙니다.")
        if observation.get("storage") != "BOUNDED_PROCESS_MEMORY":
            raise ReleaseGateError("CSP 증적 저장 방식이 제한된 메모리가 아닙니다.")
        if observation.get("totalReports") != total:
            raise ReleaseGateError("CSP summary와 observation의 전체 건수가 다릅니다.")
        if observation.get("retainedReports") != retained:
            raise ReleaseGateError("CSP summary와 observation의 보관 건수가 다릅니다.")
        if status == "CSP_OBSERVATION_CLEAN" and total != 0:
            raise ReleaseGateError("CSP CLEAN 상태에 위반 보고서가 존재합니다.")
        if status == "CSP_OBSERVATION_REVIEW_REQUIRED" and total <= 0:
            raise ReleaseGateError("CSP REVIEW_REQUIRED 상태에 위반 보고서가 없습니다.")
        reports = observation.get("reports")
        if not isinstance(reports, list) or len(reports) != retained:
            raise ReleaseGateError("CSP 증적의 보관 건수와 보고서 배열이 다릅니다.")
        for index, item in enumerate(reports):
            if not isinstance(item, dict):
                raise ReleaseGateError(f"CSP reports[{index}]가 객체가 아닙니다.")
            for field in ("documentUri", "blockedUri", "sourceFile"):
                value = item.get(field)
                if isinstance(value, str) and ("?" in value or "#" in value):
                    raise ReleaseGateError(
                        f"CSP reports[{index}].{field}에 정제되지 않은 URL이 있습니다."
                    )
        verify_csp_sidecar(path)
        result_status = (
            "WARNING"
            if status == "CSP_OBSERVATION_REVIEW_REQUIRED"
            else "PASS"
        )
        detail = (
            f"CSP 위반 후보 {total}건이 관찰되어 강제 정책 전 검토가 필요합니다."
            if result_status == "WARNING"
            else "관찰 기간에 CSP 위반 후보가 없었습니다."
        )
        return check_result(
            key,
            title,
            result_status,
            detail,
            evidence=evidence_reference(root, path),
            metrics={
                "ageHours": round(age, 3),
                "observationStatus": status,
                "totalReports": total,
                "retainedReports": retained,
                "sidecarVerified": True,
            },
        )
    except (ReleaseGateError, RetentionError, OSError) as error:
        return check_result(
            key,
            title,
            "FAILED",
            str(error),
            evidence=evidence_reference(root, path),
        )


def deferred_items(
    smartphone: dict[str, str] | None,
) -> list[dict[str, str]]:
    items = [
        {
            "key": "hp-omen-gpu-best-model",
            "title": "HP OMEN RTX 5060·파인튜닝 best.pt 검증",
            "status": "DEFERRED",
            "scope": "SECOND_PROJECT_FOLLOW_UP",
            "reason": (
                "HP OMEN 작업공간 이동과 best.pt 이식 후 "
                "별도 성능 검증하기로 합의했습니다."
            ),
        },
        {
            "key": "enforced-csp-hsts",
            "title": "강제 CSP·HSTS 전환",
            "status": "DEFERRED",
            "scope": "SECOND_PROJECT_FOLLOW_UP",
            "reason": (
                "스마트폰 HTTPS 인증서와 HP OMEN AI 배치 주소가 확정된 뒤 "
                "Report-Only 관찰 결과를 반영해 적용합니다."
            ),
        },
        {
            "key": "dji-mini4-pro-integration",
            "title": "DJI Mini 4 Pro 전용 연동",
            "status": "OUT_OF_SCOPE",
            "scope": "THIRD_PROJECT",
            "reason": "DJI RTSP 및 기체 종속 코드는 3차 프로젝트 범위입니다.",
        },
    ]
    return ([smartphone] if smartphone is not None else []) + items


def render_html(report: dict[str, Any]) -> str:
    status_class = "ready" if report["status"].startswith("READY") else "blocked"
    check_rows = []
    for item in report["checks"]:
        evidence = item.get("evidence") or {}
        check_rows.append(
            "<tr>"
            f"<td>{html.escape(item['title'])}</td>"
            f"<td><span class='badge {html.escape(item['status'].lower())}'>"
            f"{html.escape(item['status'])}</span></td>"
            f"<td>{html.escape(item['detail'])}</td>"
            f"<td><code>{html.escape(str(evidence.get('path', '-')))}</code></td>"
            "</tr>"
        )
    deferred_rows = []
    for item in report["deferred"]:
        deferred_rows.append(
            "<tr>"
            f"<td>{html.escape(item['title'])}</td>"
            f"<td>{html.escape(item['status'])}</td>"
            f"<td>{html.escape(item['scope'])}</td>"
            f"<td>{html.escape(item['reason'])}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VisionFlow 2차 프로젝트 릴리스 준비도</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #0f172a; background: #f1f5f9; }}
    main {{ max-width: 1280px; margin: auto; }}
    .hero, section {{
      background: white; border: 1px solid #cbd5e1; border-radius: 16px;
      padding: 24px; margin-bottom: 20px;
    }}
    .status {{ font-size: 28px; font-weight: 800; }}
    .ready {{ color: #047857; }} .blocked {{ color: #b91c1c; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #e2e8f0; padding: 12px; text-align: left; vertical-align: top; }}
    th {{ background: #f8fafc; }}
    .badge {{ font-weight: 700; }} .pass {{ color: #047857; }} .warning {{ color: #b45309; }}
    .failed, .missing {{ color: #b91c1c; }} code {{ word-break: break-all; }}
  </style>
</head>
<body><main>
  <div class="hero">
    <h1>VisionFlow 2차 프로젝트 릴리스 준비도</h1>
    <p class="status {status_class}">{html.escape(report['status'])}</p>
    <p>생성 시각: {html.escape(report['generatedAt'])}</p>
    <p>필수 통과 {report['summary']['passedRequired']}/{report['summary']['totalRequired']},
       경고 {report['summary']['warnings']}, 차단 {report['summary']['blocked']}</p>
  </div>
  <section><h2>필수 검증</h2><table>
    <thead><tr><th>항목</th><th>상태</th><th>판정</th><th>증빙</th></tr></thead>
    <tbody>{''.join(check_rows)}</tbody>
  </table></section>
  <section><h2>합의된 보류·범위 제외</h2><table>
    <thead><tr><th>항목</th><th>상태</th><th>범위</th><th>사유</th></tr></thead>
    <tbody>{''.join(deferred_rows)}</tbody>
  </table></section>
  <section><p>이 보고서는 읽기 전용 증빙 검사 결과이며 파일 삭제와 서비스 데이터 변경을
  수행하지 않습니다.</p></section>
</main></body></html>
"""


def create_output_paths(root: Path, output_root: Path, now: datetime) -> tuple[Path, Path]:
    allowed_root = (root / "artifacts/release-readiness").resolve()
    resolved_output = output_root.resolve()
    if not is_within(resolved_output, allowed_root):
        raise ReleaseGateError(
            "출력 폴더는 artifacts/release-readiness 내부여야 합니다."
        )
    resolved_output.mkdir(parents=True, exist_ok=True)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    stem = f"visionflow-release-readiness-{timestamp}"
    json_path = resolved_output / f"{stem}.json"
    html_path = resolved_output / f"{stem}.html"
    if json_path.exists() or html_path.exists():
        suffix = uuid.uuid4().hex[:8]
        json_path = resolved_output / f"{stem}-{suffix}.json"
        html_path = resolved_output / f"{stem}-{suffix}.html"
    return json_path, html_path


def run_release_gate(
    root: Path,
    *,
    acceptance: Path | None,
    backup: Path | None,
    audit: Path | None,
    drill: Path | None,
    benchmark: Path | None,
    csp: Path | None,
    maintenance: Path | None,
    mobile: Path | None,
    output_root: Path,
    now: datetime,
    acceptance_max_age_hours: float,
    backup_max_age_days: float,
    audit_max_age_hours: float,
    drill_max_age_hours: float,
    benchmark_max_age_days: float,
    csp_max_age_hours: float,
    maintenance_max_age_hours: float,
    mobile_max_age_days: float,
) -> tuple[Path, Path, dict[str, Any], int]:
    mobile_check, mobile_deferred_item = inspect_mobile_evidence(
        root,
        mobile,
        now=now,
        max_age_days=mobile_max_age_days,
    )
    checks = [
        inspect_acceptance(
            root,
            acceptance,
            now=now,
            max_age_hours=acceptance_max_age_hours,
        ),
        inspect_maintenance_acceptance(
            root,
            maintenance,
            now=now,
            max_age_hours=maintenance_max_age_hours,
        ),
        inspect_backup(
            root,
            backup,
            now=now,
            max_age_days=backup_max_age_days,
        ),
        inspect_storage_audit(
            root,
            audit,
            now=now,
            max_age_hours=audit_max_age_hours,
        ),
        inspect_recovery_drill(
            root,
            drill,
            now=now,
            max_age_hours=drill_max_age_hours,
        ),
        inspect_benchmark(
            root,
            benchmark,
            now=now,
            max_age_days=benchmark_max_age_days,
        ),
        inspect_csp_observation(
            root,
            csp,
            now=now,
            max_age_hours=csp_max_age_hours,
        ),
    ]
    if mobile_check is not None:
        checks.append(mobile_check)
    blocking = [item for item in checks if item["status"] not in {"PASS", "WARNING"}]
    warnings = [item for item in checks if item["status"] == "WARNING"]
    deferred = deferred_items(mobile_deferred_item)
    if blocking:
        status = "BLOCKED"
        exit_code = 1
    elif deferred:
        status = "READY_WITH_DEFERRED"
        exit_code = 0
    elif warnings:
        status = "READY_WITH_WARNINGS"
        exit_code = 0
    else:
        status = "READY"
        exit_code = 0
    report = {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "scope": SCOPE,
        "generatedAt": now.isoformat(),
        "status": status,
        "summary": {
            "totalRequired": len(checks),
            "passedRequired": len(checks) - len(blocking),
            "warnings": len(warnings),
            "blocked": len(blocking),
            "deferred": sum(item["status"] == "DEFERRED" for item in deferred),
            "outOfScope": sum(item["status"] == "OUT_OF_SCOPE" for item in deferred),
        },
        "checks": checks,
        "deferred": deferred,
        "safety": {
            "readOnly": True,
            "permanentDelete": False,
            "databaseMutation": False,
        },
    }
    json_path, html_path = create_output_paths(root, output_root, now)
    write_json(json_path, report)
    write_text_atomic(html_path, render_html(report))
    return json_path, html_path, report, exit_code


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VisionFlow release readiness gate")
    parser.add_argument("--root", default=str(default_root))
    parser.add_argument("--acceptance")
    parser.add_argument("--backup")
    parser.add_argument("--audit")
    parser.add_argument("--drill")
    parser.add_argument("--benchmark")
    parser.add_argument("--csp")
    parser.add_argument("--maintenance")
    parser.add_argument("--mobile")
    parser.add_argument("--output", default="artifacts/release-readiness")
    parser.add_argument("--acceptance-max-age-hours", type=float, default=48.0)
    parser.add_argument("--backup-max-age-days", type=float, default=7.0)
    parser.add_argument("--audit-max-age-hours", type=float, default=24.0)
    parser.add_argument("--drill-max-age-hours", type=float, default=24.0)
    parser.add_argument("--benchmark-max-age-days", type=float, default=30.0)
    parser.add_argument("--csp-max-age-hours", type=float, default=24.0)
    parser.add_argument(
        "--maintenance-max-age-hours",
        type=float,
        default=24.0,
    )
    parser.add_argument("--mobile-max-age-days", type=float, default=30.0)
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    args = build_parser(default_root).parse_args(arguments)
    root = Path(args.root).resolve()
    try:
        if not root.is_dir():
            raise ReleaseGateError(f"프로젝트 루트를 찾을 수 없습니다: {root}")
        limits = (
            args.acceptance_max_age_hours,
            args.backup_max_age_days,
            args.audit_max_age_hours,
            args.drill_max_age_hours,
            args.benchmark_max_age_days,
            args.csp_max_age_hours,
            args.maintenance_max_age_hours,
            args.mobile_max_age_days,
        )
        if any(value <= 0 for value in limits):
            raise ReleaseGateError("증빙 최대 허용 시간은 모두 양수여야 합니다.")
        acceptance = resolve_override(root, args.acceptance, "acceptance")
        backup = resolve_override(root, args.backup, "backup")
        audit = resolve_override(root, args.audit, "audit")
        drill = resolve_override(root, args.drill, "drill")
        benchmark = resolve_override(root, args.benchmark, "benchmark")
        csp = resolve_override(root, args.csp, "csp")
        maintenance = resolve_override(
            root,
            args.maintenance,
            "maintenance",
        )
        mobile = resolve_override(root, args.mobile, "mobile")
        acceptance = acceptance or newest_demo_acceptance(root)
        backup = backup or newest_file(root, "backup", "visionflow-backup-*.zip")
        audit = audit or newest_file(root, "audit", "storage-audit.json")
        drill = drill or newest_file(root, "drill", "retention-recovery-drill.json")
        benchmark = benchmark or newest_file(
            root,
            "benchmark",
            "visionflow-ai-benchmark-*.json",
        )
        csp = csp or newest_file(
            root,
            "csp",
            "visionflow-csp-observation-*.json",
        )
        maintenance = maintenance or newest_file(
            root,
            "maintenance",
            "visionflow-maintenance-acceptance-*.json",
        )
        mobile = mobile or newest_file(
            root,
            "mobile",
            "visionflow-smartphone-e2e-*.json",
        )
        json_path, html_path, report, exit_code = run_release_gate(
            root,
            acceptance=acceptance,
            backup=backup,
            audit=audit,
            drill=drill,
            benchmark=benchmark,
            csp=csp,
            maintenance=maintenance,
            mobile=mobile,
            output_root=(root / args.output).resolve()
            if not Path(args.output).is_absolute()
            else Path(args.output).resolve(),
            now=datetime.now(timezone.utc),
            acceptance_max_age_hours=args.acceptance_max_age_hours,
            backup_max_age_days=args.backup_max_age_days,
            audit_max_age_hours=args.audit_max_age_hours,
            drill_max_age_hours=args.drill_max_age_hours,
            benchmark_max_age_days=args.benchmark_max_age_days,
            csp_max_age_hours=args.csp_max_age_hours,
            maintenance_max_age_hours=args.maintenance_max_age_hours,
            mobile_max_age_days=args.mobile_max_age_days,
        )
        print(f"VisionFlow release readiness: {report['status']}")
        print(f"JSON report: {json_path}")
        print(f"HTML report: {html_path}")
        return exit_code
    except (ReleaseGateError, RetentionError, FileNotFoundError, OSError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
