"""Create and independently verify a VisionFlow presentation-day signoff."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    from visionflow_project_closeout import (
        CLOSEOUT_STATUS,
        ProjectCloseoutError,
        verify_closeout_file,
    )
    from visionflow_release_evidence import (
        EvidenceBundleError,
        validate_readiness_report,
    )
    from visionflow_transfer_day_gate import (
        TransferDayGateError,
        verify_release_evidence_bundle,
    )
except ModuleNotFoundError:  # pragma: no cover - package import during tests
    from scripts.visionflow_project_closeout import (
        CLOSEOUT_STATUS,
        ProjectCloseoutError,
        verify_closeout_file,
    )
    from scripts.visionflow_release_evidence import (
        EvidenceBundleError,
        validate_readiness_report,
    )
    from scripts.visionflow_transfer_day_gate import (
        TransferDayGateError,
        verify_release_evidence_bundle,
    )


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
SCOPE = "SECOND_PROJECT_DIGITAL_TWIN"
OPERATION = "PRESENTATION_DAY_SIGNOFF"
REPORT_ROOT = Path("artifacts/presentation-gate")
READY_STATUS = "PRESENTATION_READY_WITH_DEFERRED"
BLOCKED_STATUS = "PRESENTATION_BLOCKED"
CHECK_ORDER = (
    "full-security-acceptance",
    "release-readiness",
    "release-evidence",
    "project-closeout",
    "evidence-lineage",
)
ARTIFACT_POLICIES = {
    "full-security-acceptance": (
        Path("artifacts/visionflow-acceptance"),
        "visionflow-acceptance-*.json",
    ),
    "release-readiness": (
        Path("artifacts/release-readiness"),
        "visionflow-release-readiness-*.json",
    ),
    "release-evidence": (
        Path("artifacts/release-evidence"),
        "visionflow-release-evidence-*.zip",
    ),
    "project-closeout": (
        Path("artifacts/project-closeout"),
        "visionflow-project-closeout-*.json",
    ),
}
REQUIRED_ACCEPTANCE_RESULTS = {
    "Backend health",
    "Backend drone list",
    "Frontend dashboard",
    "Frontend security headers",
    "AI ingest status",
    "AI stream status",
    "RBAC enabled mode",
    "Operator browser session mode",
    "Demo flight complete",
}
AGREED_DEFERRED = [
    {
        "key": "hp-omen-gpu-best-model",
        "status": "DEFERRED",
        "scope": "SECOND_PROJECT_FOLLOW_UP",
        "reason": "HP OMEN RTX 5060 작업공간과 파인튜닝 best.pt 준비 후 성능을 검증합니다.",
    },
    {
        "key": "enforced-csp-hsts",
        "status": "DEFERRED",
        "scope": "SECOND_PROJECT_FOLLOW_UP",
        "reason": "배치 주소 확정과 CSP Report-Only 관찰 검토 후 강제 정책으로 전환합니다.",
    },
    {
        "key": "dji-mini4-pro-integration",
        "status": "OUT_OF_SCOPE",
        "scope": "THIRD_PROJECT",
        "reason": "DJI Mini 4 Pro RTSP와 기체 종속 연동은 3차 프로젝트 범위입니다.",
    },
]
MAX_JSON_BYTES = 5 * 1024 * 1024
FUTURE_TOLERANCE = timedelta(minutes=10)


class PresentationGateError(RuntimeError):
    """Raised when presentation evidence cannot be resolved or verified."""


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


def relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as error:
        raise PresentationGateError(
            "프로젝트 내부 증적 경로를 상대경로로 기록할 수 없습니다."
        ) from error


def read_json(path: Path, title: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise PresentationGateError(f"{title} 파일을 찾을 수 없습니다.")
    if path.stat().st_size > MAX_JSON_BYTES:
        raise PresentationGateError(f"{title} JSON 크기가 허용 범위를 초과했습니다.")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PresentationGateError(f"{title} JSON 형식이 올바르지 않습니다.") from error
    if not isinstance(value, dict):
        raise PresentationGateError(f"{title} JSON 최상위 값은 객체여야 합니다.")
    return value


def parse_timestamp(value: Any, title: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise PresentationGateError(f"{title} 생성 시각이 없습니다.")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise PresentationGateError(f"{title} 생성 시각 형식이 올바르지 않습니다.") from error
    if result.tzinfo is None:
        raise PresentationGateError(f"{title} 생성 시각에 시간대가 없습니다.")
    return result.astimezone(timezone.utc)


def age_hours(value: Any, title: str, now: datetime) -> float:
    age = now.astimezone(timezone.utc) - parse_timestamp(value, title)
    if age < -FUTURE_TOLERANCE:
        raise PresentationGateError(f"{title} 생성 시각이 미래입니다.")
    return age.total_seconds() / 3600


def write_text_atomic(path: Path, value: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    try:
        temporary.write_text(value, encoding=encoding)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def sanitize_error(error: Exception, root: Path) -> str:
    value = str(error)
    for candidate in {
        str(root.resolve()),
        str(root.resolve()).replace("\\", "/"),
        str(root.resolve()).replace("/", "\\"),
    }:
        value = value.replace(candidate, "<PROJECT_ROOT>")
    return value


def artifact_entry(root: Path, path: Path) -> dict[str, Any]:
    return {
        "path": relative_path(root, path),
        "fileName": path.name,
        "sizeBytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def check_result(
    key: str,
    title: str,
    status: str,
    detail: str,
    *,
    artifact: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "title": title,
        "status": status,
        "detail": detail,
        "artifact": artifact,
        "metrics": metrics or {},
    }


def resolve_artifact(
    root: Path,
    key: str,
    value: str | None,
) -> Path | None:
    directory, pattern = ARTIFACT_POLICIES[key]
    allowed = (root / directory).resolve()
    if value:
        candidate = Path(value)
        path = (
            candidate.resolve()
            if candidate.is_absolute()
            else (root / candidate).resolve()
        )
        if (
            not is_within(path, allowed)
            or not path.is_file()
            or path.is_symlink()
        ):
            raise PresentationGateError(
                f"{key} 증적 경로가 허용 영역을 벗어났습니다."
            )
        return path
    if not allowed.is_dir():
        return None
    candidates = [
        item.resolve()
        for item in allowed.glob(pattern)
        if item.is_file() and not item.is_symlink()
    ]
    return max(
        candidates,
        key=lambda item: (item.stat().st_mtime_ns, item.name),
        default=None,
    )


def inspect_acceptance(
    root: Path,
    path: Path | None,
    *,
    now: datetime,
    max_age_hours: float,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    key = "full-security-acceptance"
    title = "전체 보안 인수 및 영속 데모"
    if path is None:
        return (
            check_result(
                key,
                title,
                "MISSING",
                "전체 인수 테스트 JSON이 없습니다.",
            ),
            None,
        )
    artifact = artifact_entry(root, path)
    try:
        report = read_json(path, title)
        age = age_hours(report.get("generatedAt"), title, now)
        configuration = report.get("configuration")
        summary = report.get("summary")
        scenario = report.get("scenario")
        results = report.get("results")
        if not isinstance(configuration, Mapping):
            raise PresentationGateError("인수 테스트 configuration이 없습니다.")
        for flag in ("runDemo", "runRbac", "runSession"):
            if configuration.get(flag) is not True:
                raise PresentationGateError(f"인수 테스트 {flag}=true가 필요합니다.")
        if configuration.get("skipAi") is not False:
            raise PresentationGateError("AI 검증이 제외된 인수 테스트입니다.")
        if not isinstance(summary, Mapping):
            raise PresentationGateError("인수 테스트 summary가 없습니다.")
        total = summary.get("total")
        passed = summary.get("passed")
        failed = summary.get("failed")
        if (
            not all(
                isinstance(item, int) and not isinstance(item, bool)
                for item in (total, passed, failed)
            )
            or total <= 0
            or passed != total
            or failed != 0
        ):
            raise PresentationGateError("인수 테스트에 실패 항목이 있습니다.")
        if not isinstance(scenario, Mapping) or scenario.get("stage") != "COMPLETED":
            raise PresentationGateError("영속 데모가 COMPLETED 상태가 아닙니다.")
        if not isinstance(results, list):
            raise PresentationGateError("인수 테스트 results가 없습니다.")
        passed_names = {
            str(item.get("Name") or item.get("name"))
            for item in results
            if isinstance(item, Mapping)
            and (item.get("Passed") is True or item.get("passed") is True)
        }
        missing = sorted(REQUIRED_ACCEPTANCE_RESULTS - passed_names)
        if missing:
            raise PresentationGateError(
                "필수 인수 항목이 없습니다: " + ", ".join(missing)
            )
        if age > max_age_hours:
            raise PresentationGateError(
                f"인수 테스트가 오래됐습니다: {age:.2f}시간"
            )
        return (
            check_result(
                key,
                title,
                "PASS",
                "핵심 서비스·AI·보안·RBAC·세션·영속 데모가 모두 통과했습니다.",
                artifact=artifact,
                metrics={
                    "ageHours": round(age, 3),
                    "total": total,
                    "passed": passed,
                    "runDemo": True,
                    "runRbac": True,
                    "runSession": True,
                },
            ),
            report,
        )
    except (PresentationGateError, OSError) as error:
        return (
            check_result(
                key,
                title,
                "FAILED",
                sanitize_error(error, root),
                artifact=artifact,
            ),
            None,
        )


def inspect_readiness(
    root: Path,
    path: Path | None,
    acceptance_path: Path | None,
    *,
    now: datetime,
    max_age_hours: float,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    key = "release-readiness"
    title = "2차 프로젝트 릴리스 준비도"
    if path is None:
        return check_result(key, title, "MISSING", "릴리스 준비도 JSON이 없습니다."), None
    artifact = artifact_entry(root, path)
    try:
        report = read_json(path, title)
        validate_readiness_report(report)
        age = age_hours(report.get("generatedAt"), title, now)
        if age > max_age_hours:
            raise PresentationGateError(
                f"릴리스 준비도 보고서가 오래됐습니다: {age:.2f}시간"
            )
        acceptance_checks = [
            item
            for item in report.get("checks", [])
            if isinstance(item, Mapping) and item.get("key") == "acceptance-demo"
        ]
        if len(acceptance_checks) != 1 or acceptance_path is None:
            raise PresentationGateError("릴리스 준비도에 인수 테스트 연결이 없습니다.")
        source = acceptance_checks[0].get("evidence")
        if not isinstance(source, Mapping):
            raise PresentationGateError("인수 테스트 증적 메타데이터가 없습니다.")
        expected = artifact_entry(root, acceptance_path)
        if (
            source.get("path") != expected["path"]
            or source.get("sizeBytes") != expected["sizeBytes"]
            or source.get("sha256") != expected["sha256"]
        ):
            raise PresentationGateError(
                "릴리스 준비도와 전체 인수 테스트의 동일성이 다릅니다."
            )
        return (
            check_result(
                key,
                title,
                "PASS",
                f"릴리스 상태 {report.get('status')}이며 차단 항목이 없습니다.",
                artifact=artifact,
                metrics={
                    "ageHours": round(age, 3),
                    "readinessStatus": report.get("status"),
                    "blocked": 0,
                },
            ),
            report,
        )
    except (
        PresentationGateError,
        EvidenceBundleError,
        KeyError,
        TypeError,
        OSError,
    ) as error:
        return (
            check_result(
                key,
                title,
                "FAILED",
                sanitize_error(error, root),
                artifact=artifact,
            ),
            None,
        )


def inspect_release_evidence(
    root: Path,
    path: Path | None,
    readiness_path: Path | None,
    acceptance_path: Path | None,
    *,
    now: datetime,
    max_age_hours: float,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    key = "release-evidence"
    title = "릴리스 증빙 번들"
    if path is None:
        return check_result(key, title, "MISSING", "릴리스 증빙 ZIP이 없습니다."), None
    artifact = artifact_entry(root, path)
    try:
        verified_path, manifest = verify_release_evidence_bundle(root, str(path))
        if verified_path.resolve() != path.resolve():
            raise PresentationGateError("검증된 릴리스 증빙 경로가 요청과 다릅니다.")
        age = age_hours(manifest.get("createdAt"), title, now)
        if age > max_age_hours:
            raise PresentationGateError(
                f"릴리스 증빙 번들이 오래됐습니다: {age:.2f}시간"
            )
        readiness = manifest.get("readiness")
        if not isinstance(readiness, Mapping) or readiness_path is None:
            raise PresentationGateError("릴리스 증빙에 준비도 연결이 없습니다.")
        readiness_entry = artifact_entry(root, readiness_path)
        if (
            readiness.get("sourcePath") != readiness_entry["path"]
            or readiness.get("sourceSha256") != readiness_entry["sha256"]
        ):
            raise PresentationGateError(
                "릴리스 증빙과 릴리스 준비도의 동일성이 다릅니다."
            )
        acceptance_entries = [
            item
            for item in manifest.get("evidence", [])
            if isinstance(item, Mapping) and item.get("key") == "acceptance-demo"
        ]
        if len(acceptance_entries) != 1 or acceptance_path is None:
            raise PresentationGateError("릴리스 증빙에 인수 테스트 연결이 없습니다.")
        acceptance_entry = artifact_entry(root, acceptance_path)
        if (
            acceptance_entries[0].get("sourcePath") != acceptance_entry["path"]
            or acceptance_entries[0].get("sourceSizeBytes")
            != acceptance_entry["sizeBytes"]
            or acceptance_entries[0].get("sourceSha256")
            != acceptance_entry["sha256"]
        ):
            raise PresentationGateError(
                "릴리스 증빙과 전체 인수 테스트의 동일성이 다릅니다."
            )
        return (
            check_result(
                key,
                title,
                "PASS",
                "ZIP·sidecar·내부 manifest와 인수/준비도 연결이 유효합니다.",
                artifact=artifact,
                metrics={
                    "ageHours": round(age, 3),
                    "includedFiles": len(manifest.get("includedFiles", [])),
                },
            ),
            manifest,
        )
    except (
        PresentationGateError,
        TransferDayGateError,
        EvidenceBundleError,
        KeyError,
        TypeError,
        OSError,
    ) as error:
        return (
            check_result(
                key,
                title,
                "FAILED",
                sanitize_error(error, root),
                artifact=artifact,
            ),
            None,
        )


def inspect_closeout(
    root: Path,
    path: Path | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    key = "project-closeout"
    title = "2차 프로젝트 종결 증적"
    if path is None:
        return check_result(key, title, "MISSING", "프로젝트 종결 JSON이 없습니다."), None
    artifact = artifact_entry(root, path)
    try:
        verified_path, report = verify_closeout_file(root, str(path))
        if verified_path.resolve() != path.resolve():
            raise PresentationGateError("검증된 종결 증적 경로가 요청과 다릅니다.")
        if (
            report.get("status") != CLOSEOUT_STATUS
            or not isinstance(report.get("summary"), Mapping)
            or report["summary"].get("blocking") != 0
        ):
            raise PresentationGateError("2차 프로젝트 종결 상태가 올바르지 않습니다.")
        return (
            check_result(
                key,
                title,
                "PASS",
                "종결 JSON·HTML·Markdown·sidecar와 원본 이관 패키지가 유효합니다.",
                artifact=artifact,
                metrics={
                    "closeoutStatus": report.get("status"),
                    "blocking": 0,
                },
            ),
            report,
        )
    except (
        PresentationGateError,
        ProjectCloseoutError,
        KeyError,
        TypeError,
        OSError,
    ) as error:
        return (
            check_result(
                key,
                title,
                "FAILED",
                sanitize_error(error, root),
                artifact=artifact,
            ),
            None,
        )


def normalized_deferred(readiness: Mapping[str, Any] | None) -> list[dict[str, str]]:
    if readiness is None or not isinstance(readiness.get("deferred"), list):
        return [dict(item) for item in AGREED_DEFERRED]
    items = readiness["deferred"]
    if (
        len(items) != len(AGREED_DEFERRED)
        or {
            (item.get("key"), item.get("status"))
            for item in items
            if isinstance(item, Mapping)
        }
        != {(item["key"], item["status"]) for item in AGREED_DEFERRED}
    ):
        return [dict(item) for item in AGREED_DEFERRED]
    return [
        {
            "key": str(item.get("key")),
            "status": str(item.get("status")),
            "scope": str(item.get("scope")),
            "reason": str(item.get("reason")),
        }
        for item in items
    ]


def evaluate(
    root: Path,
    *,
    acceptance_path: Path | None,
    readiness_path: Path | None,
    release_evidence_path: Path | None,
    closeout_path: Path | None,
    now: datetime,
    acceptance_max_age_hours: float,
    readiness_max_age_hours: float,
    release_evidence_max_age_hours: float,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    acceptance_check, acceptance = inspect_acceptance(
        root,
        acceptance_path,
        now=now,
        max_age_hours=acceptance_max_age_hours,
    )
    readiness_check, readiness = inspect_readiness(
        root,
        readiness_path,
        acceptance_path if acceptance is not None else None,
        now=now,
        max_age_hours=readiness_max_age_hours,
    )
    evidence_check, manifest = inspect_release_evidence(
        root,
        release_evidence_path,
        readiness_path if readiness is not None else None,
        acceptance_path if acceptance is not None else None,
        now=now,
        max_age_hours=release_evidence_max_age_hours,
    )
    closeout_check, closeout = inspect_closeout(root, closeout_path)
    prerequisite_checks = [
        acceptance_check,
        readiness_check,
        evidence_check,
        closeout_check,
    ]
    if all(item["status"] == "PASS" for item in prerequisite_checks):
        readiness_status = readiness.get("status") if readiness else None
        manifest_status = (
            manifest.get("readiness", {}).get("status")
            if isinstance(manifest, Mapping)
            and isinstance(manifest.get("readiness"), Mapping)
            else None
        )
        closeout_status = closeout.get("status") if closeout else None
        if (
            readiness_status in {"READY", "READY_WITH_DEFERRED"}
            and manifest_status == readiness_status
            and closeout_status == CLOSEOUT_STATUS
        ):
            lineage_check = check_result(
                "evidence-lineage",
                "발표 증적 계보",
                "PASS",
                "인수 테스트 → 릴리스 준비도 → 증빙 번들과 프로젝트 종결 판정이 일치합니다.",
                metrics={
                    "readinessStatus": readiness_status,
                    "closeoutStatus": closeout_status,
                },
            )
        else:
            lineage_check = check_result(
                "evidence-lineage",
                "발표 증적 계보",
                "FAILED",
                "릴리스 준비도·증빙 번들·프로젝트 종결 상태의 연결이 다릅니다.",
            )
    else:
        lineage_check = check_result(
            "evidence-lineage",
            "발표 증적 계보",
            "BLOCKED",
            "선행 증적 검증이 통과해야 계보를 확정할 수 있습니다.",
        )
    return prerequisite_checks + [lineage_check], normalized_deferred(readiness)


def build_report(
    *,
    checks: list[dict[str, Any]],
    deferred: list[dict[str, str]],
    now: datetime,
    acceptance_max_age_hours: float,
    readiness_max_age_hours: float,
    release_evidence_max_age_hours: float,
) -> dict[str, Any]:
    blocking = sum(item["status"] != "PASS" for item in checks)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "scope": SCOPE,
        "operation": OPERATION,
        "signoffId": str(uuid.uuid4()),
        "generatedAt": now.astimezone(timezone.utc).isoformat(),
        "status": READY_STATUS if blocking == 0 else BLOCKED_STATUS,
        "policy": {
            "acceptanceMaxAgeHours": acceptance_max_age_hours,
            "readinessMaxAgeHours": readiness_max_age_hours,
            "releaseEvidenceMaxAgeHours": release_evidence_max_age_hours,
        },
        "checks": checks,
        "deferred": deferred,
        "summary": {
            "total": len(checks),
            "passed": sum(item["status"] == "PASS" for item in checks),
            "blocking": blocking,
            "deferred": sum(item["status"] == "DEFERRED" for item in deferred),
            "outOfScope": sum(item["status"] == "OUT_OF_SCOPE" for item in deferred),
        },
        "safety": {
            "sourceArtifactsModified": False,
            "databaseMutation": False,
            "dockerStartedByGate": False,
            "gpuExecutedByGate": False,
            "absolutePathsRecorded": False,
            "environmentValuesRecorded": False,
            "operatorKeysRecorded": False,
            "privateKeysRecorded": False,
        },
    }


def render_html(report: Mapping[str, Any]) -> str:
    ready = report["status"] == READY_STATUS
    check_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['title']))}</td>"
        f"<td class='{html.escape(str(item['status']).lower())}'>"
        f"{html.escape(str(item['status']))}</td>"
        f"<td>{html.escape(str(item['detail']))}</td>"
        f"<td><code>{html.escape(str((item.get('artifact') or {}).get('path', '-')))}</code></td>"
        "</tr>"
        for item in report["checks"]
    )
    deferred_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['key']))}</td>"
        f"<td>{html.escape(str(item['status']))}</td>"
        f"<td>{html.escape(str(item['scope']))}</td>"
        f"<td>{html.escape(str(item['reason']))}</td>"
        "</tr>"
        for item in report["deferred"]
    )
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VisionFlow 발표 시연 운영 게이트</title><style>
body {{ margin:0; background:#eef3f8; color:#0f172a; font-family:Arial,'Noto Sans KR',sans-serif; }}
main {{ max-width:1180px; margin:32px auto; padding:0 20px; }}
section {{ background:#fff; border:1px solid #dbe4ee; border-radius:16px; padding:24px; margin:16px 0; }}
h1,h2 {{ margin-top:0; }} .status {{ color:{'#047857' if ready else '#b91c1c'}; font-size:1.35rem; font-weight:800; }}
table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:10px; border-bottom:1px solid #e2e8f0; text-align:left; vertical-align:top; }}
.pass {{ color:#047857; font-weight:700; }} .failed,.missing,.blocked {{ color:#b91c1c; font-weight:700; }}
code {{ word-break:break-all; }}
</style></head><body><main>
<section><h1>VisionFlow 발표 시연 운영 게이트</h1>
<p class="status">{html.escape(str(report['status']))}</p>
<p>생성 시각: {html.escape(str(report['generatedAt']))}</p>
<p>통과 {report['summary']['passed']}/{report['summary']['total']} · 차단 {report['summary']['blocking']}</p></section>
<section><h2>발표 전 필수 검증</h2><table><thead><tr><th>항목</th><th>상태</th><th>내용</th><th>증적</th></tr></thead>
<tbody>{check_rows}</tbody></table></section>
<section><h2>합의된 보류·범위 외 항목</h2><table><thead><tr><th>키</th><th>상태</th><th>범위</th><th>사유</th></tr></thead>
<tbody>{deferred_rows}</tbody></table></section>
<section><h2>운영 원칙</h2><p>이 게이트는 기존 증적을 읽어 판정 보고서만 생성합니다. DB 데이터, 서비스 상태,
환경변수 값, 운영자 키, 인증서 개인키와 모델 가중치를 변경하거나 기록하지 않습니다.</p></section>
</main></body></html>"""


def write_report(
    root: Path,
    report: dict[str, Any],
    *,
    output_root: Path,
    now: datetime,
) -> tuple[Path, Path, Path]:
    allowed = (root / REPORT_ROOT).resolve()
    output = output_root.resolve()
    if not is_within(output, allowed):
        raise PresentationGateError(
            "출력 폴더는 artifacts/presentation-gate 내부여야 합니다."
        )
    output.mkdir(parents=True, exist_ok=True)
    timestamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = output / f"visionflow-presentation-gate-{timestamp}"
    if base.with_suffix(".json").exists() or base.with_suffix(".html").exists():
        base = output / (
            f"visionflow-presentation-gate-{timestamp}-{uuid.uuid4().hex[:8]}"
        )
    json_path = base.with_suffix(".json")
    html_path = base.with_suffix(".html")
    sidecar = base.with_suffix(".sha256")
    write_text_atomic(
        json_path,
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    write_text_atomic(html_path, render_html(report))
    write_text_atomic(
        sidecar,
        (
            f"{sha256_file(json_path)}  {json_path.name}\n"
            f"{sha256_file(html_path)}  {html_path.name}\n"
        ),
    )
    return json_path, html_path, sidecar


def run_gate(
    root: Path,
    *,
    acceptance: str | None,
    readiness: str | None,
    release_evidence: str | None,
    closeout: str | None,
    output_root: Path,
    now: datetime,
    acceptance_max_age_hours: float,
    readiness_max_age_hours: float,
    release_evidence_max_age_hours: float,
) -> tuple[Path, Path, Path, dict[str, Any], int]:
    for value, title in (
        (acceptance_max_age_hours, "인수 테스트"),
        (readiness_max_age_hours, "릴리스 준비도"),
        (release_evidence_max_age_hours, "릴리스 증빙"),
    ):
        if value <= 0:
            raise PresentationGateError(f"{title} 최대 유효시간은 양수여야 합니다.")
    paths = {
        key: resolve_artifact(
            root,
            key,
            {
                "full-security-acceptance": acceptance,
                "release-readiness": readiness,
                "release-evidence": release_evidence,
                "project-closeout": closeout,
            }[key],
        )
        for key in ARTIFACT_POLICIES
    }
    checks, deferred = evaluate(
        root,
        acceptance_path=paths["full-security-acceptance"],
        readiness_path=paths["release-readiness"],
        release_evidence_path=paths["release-evidence"],
        closeout_path=paths["project-closeout"],
        now=now,
        acceptance_max_age_hours=acceptance_max_age_hours,
        readiness_max_age_hours=readiness_max_age_hours,
        release_evidence_max_age_hours=release_evidence_max_age_hours,
    )
    report = build_report(
        checks=checks,
        deferred=deferred,
        now=now,
        acceptance_max_age_hours=acceptance_max_age_hours,
        readiness_max_age_hours=readiness_max_age_hours,
        release_evidence_max_age_hours=release_evidence_max_age_hours,
    )
    json_path, html_path, sidecar = write_report(
        root,
        report,
        output_root=output_root,
        now=now,
    )
    return (
        json_path,
        html_path,
        sidecar,
        report,
        0 if report["status"] == READY_STATUS else 1,
    )


def resolve_report(root: Path, value: str) -> Path:
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
        raise PresentationGateError("발표 게이트 보고서 경로가 올바르지 않습니다.")
    return path


def verify_sidecar(json_path: Path, html_path: Path) -> None:
    sidecar = json_path.with_suffix(".sha256")
    if not sidecar.is_file() or sidecar.is_symlink():
        raise PresentationGateError("발표 게이트 SHA-256 sidecar가 없습니다.")
    try:
        lines = [
            line.strip().split()
            for line in sidecar.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
    except UnicodeDecodeError as error:
        raise PresentationGateError("발표 게이트 sidecar가 UTF-8이 아닙니다.") from error
    if len(lines) != 2 or any(len(parts) != 2 for parts in lines):
        raise PresentationGateError("발표 게이트 sidecar 형식이 올바르지 않습니다.")
    recorded = {parts[1]: parts[0].lower() for parts in lines}
    expected = {json_path.name, html_path.name}
    if set(recorded) != expected:
        raise PresentationGateError("발표 게이트 sidecar 파일 목록이 다릅니다.")
    for path in (json_path, html_path):
        digest = recorded[path.name]
        if (
            not is_checksum(digest)
            or not path.is_file()
            or path.is_symlink()
            or digest != sha256_file(path)
        ):
            raise PresentationGateError(
                f"발표 게이트 SHA-256이 다릅니다: {path.name}"
            )


def validate_report_shape(report: Mapping[str, Any]) -> None:
    checks = report.get("checks")
    summary = report.get("summary")
    safety = report.get("safety")
    policy = report.get("policy")
    deferred = report.get("deferred")
    if (
        report.get("schemaVersion") != SCHEMA_VERSION
        or report.get("project") != PROJECT_NAME
        or report.get("scope") != SCOPE
        or report.get("operation") != OPERATION
        or report.get("status") not in {READY_STATUS, BLOCKED_STATUS}
        or not isinstance(report.get("signoffId"), str)
        or not isinstance(checks, list)
        or [item.get("key") for item in checks if isinstance(item, Mapping)]
        != list(CHECK_ORDER)
        or not isinstance(summary, Mapping)
        or not isinstance(policy, Mapping)
        or not isinstance(deferred, list)
        or not isinstance(safety, Mapping)
    ):
        raise PresentationGateError("발표 게이트 보고서 형식이 올바르지 않습니다.")
    blocking = sum(
        not isinstance(item, Mapping) or item.get("status") != "PASS"
        for item in checks
    )
    expected_status = READY_STATUS if blocking == 0 else BLOCKED_STATUS
    if (
        report.get("status") != expected_status
        or summary.get("total") != len(checks)
        or summary.get("passed")
        != sum(
            isinstance(item, Mapping) and item.get("status") == "PASS"
            for item in checks
        )
        or summary.get("blocking") != blocking
        or summary.get("deferred")
        != sum(
            isinstance(item, Mapping) and item.get("status") == "DEFERRED"
            for item in deferred
        )
        or summary.get("outOfScope")
        != sum(
            isinstance(item, Mapping) and item.get("status") == "OUT_OF_SCOPE"
            for item in deferred
        )
    ):
        raise PresentationGateError("발표 게이트 집계가 상세 결과와 다릅니다.")
    if (
        safety.get("sourceArtifactsModified") is not False
        or safety.get("databaseMutation") is not False
        or safety.get("dockerStartedByGate") is not False
        or safety.get("gpuExecutedByGate") is not False
        or safety.get("absolutePathsRecorded") is not False
        or safety.get("environmentValuesRecorded") is not False
        or safety.get("operatorKeysRecorded") is not False
        or safety.get("privateKeysRecorded") is not False
    ):
        raise PresentationGateError("발표 게이트 안전 메타데이터가 올바르지 않습니다.")
    for key in (
        "acceptanceMaxAgeHours",
        "readinessMaxAgeHours",
        "releaseEvidenceMaxAgeHours",
    ):
        value = policy.get(key)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or value <= 0
        ):
            raise PresentationGateError("발표 게이트 유효시간 정책이 올바르지 않습니다.")


def artifact_path_from_check(
    root: Path,
    check: Mapping[str, Any],
) -> Path:
    artifact = check.get("artifact")
    key = str(check.get("key"))
    if not isinstance(artifact, Mapping) or key not in ARTIFACT_POLICIES:
        raise PresentationGateError(f"{key} 증적 메타데이터가 없습니다.")
    value = artifact.get("path")
    if not isinstance(value, str):
        raise PresentationGateError(f"{key} 증적 상대경로가 없습니다.")
    path = resolve_artifact(root, key, value)
    if path is None:
        raise PresentationGateError(f"{key} 증적 파일을 찾을 수 없습니다.")
    if (
        artifact.get("fileName") != path.name
        or artifact.get("sizeBytes") != path.stat().st_size
        or artifact.get("sha256") != sha256_file(path)
    ):
        raise PresentationGateError(f"{key} 증적 동일성이 다릅니다.")
    return path


def verify_gate_report(
    root: Path,
    value: str,
) -> tuple[Path, dict[str, Any]]:
    json_path = resolve_report(root, value)
    html_path = json_path.with_suffix(".html")
    verify_sidecar(json_path, html_path)
    report = read_json(json_path, "발표 게이트")
    validate_report_shape(report)
    try:
        html_value = html_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise PresentationGateError("발표 게이트 HTML이 UTF-8이 아닙니다.") from error
    lowered = html_value.lower()
    if any(
        token in lowered
        for token in ("<script", "<iframe", "<object", "<embed", "javascript:")
    ):
        raise PresentationGateError("발표 게이트 HTML에 실행 가능한 콘텐츠가 있습니다.")
    if html_value != render_html(report):
        raise PresentationGateError("발표 게이트 JSON과 HTML 내용이 일치하지 않습니다.")
    if report["status"] == READY_STATUS:
        checks_by_key = {item["key"]: item for item in report["checks"]}
        paths = {
            key: artifact_path_from_check(root, checks_by_key[key])
            for key in ARTIFACT_POLICIES
        }
        policy = report["policy"]
        generated_at = parse_timestamp(report.get("generatedAt"), "발표 게이트")
        expected_checks, expected_deferred = evaluate(
            root,
            acceptance_path=paths["full-security-acceptance"],
            readiness_path=paths["release-readiness"],
            release_evidence_path=paths["release-evidence"],
            closeout_path=paths["project-closeout"],
            now=generated_at,
            acceptance_max_age_hours=float(policy["acceptanceMaxAgeHours"]),
            readiness_max_age_hours=float(policy["readinessMaxAgeHours"]),
            release_evidence_max_age_hours=float(
                policy["releaseEvidenceMaxAgeHours"]
            ),
        )
        if (
            expected_checks != report["checks"]
            or expected_deferred != report["deferred"]
            or any(item["status"] != "PASS" for item in expected_checks)
        ):
            raise PresentationGateError(
                "발표 게이트 재평가 결과가 저장된 판정과 다릅니다."
            )
    return json_path, report


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="VisionFlow presentation-day signoff gate"
    )
    parser.add_argument("--root", default=str(default_root))
    subparsers = parser.add_subparsers(dest="command", required=True)
    evaluate_parser = subparsers.add_parser(
        "evaluate",
        help="최신 발표 증적을 평가하고 서명 보고서 생성",
    )
    evaluate_parser.add_argument("--acceptance")
    evaluate_parser.add_argument("--readiness")
    evaluate_parser.add_argument("--release-evidence")
    evaluate_parser.add_argument("--closeout")
    evaluate_parser.add_argument("--output", default=REPORT_ROOT.as_posix())
    evaluate_parser.add_argument("--acceptance-max-age-hours", type=float, default=2.0)
    evaluate_parser.add_argument("--readiness-max-age-hours", type=float, default=2.0)
    evaluate_parser.add_argument(
        "--release-evidence-max-age-hours",
        type=float,
        default=2.0,
    )
    verify_parser = subparsers.add_parser(
        "verify",
        help="기존 발표 게이트 보고서 독립 재검증",
    )
    verify_parser.add_argument("--report", required=True)
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    args = build_parser(default_root).parse_args(arguments)
    root = Path(args.root).resolve()
    try:
        if not root.is_dir():
            raise PresentationGateError("프로젝트 루트를 찾을 수 없습니다.")
        if args.command == "evaluate":
            output_value = Path(args.output)
            output = (
                output_value.resolve()
                if output_value.is_absolute()
                else (root / output_value).resolve()
            )
            json_path, html_path, sidecar, report, exit_code = run_gate(
                root,
                acceptance=args.acceptance,
                readiness=args.readiness,
                release_evidence=args.release_evidence,
                closeout=args.closeout,
                output_root=output,
                now=datetime.now(timezone.utc),
                acceptance_max_age_hours=args.acceptance_max_age_hours,
                readiness_max_age_hours=args.readiness_max_age_hours,
                release_evidence_max_age_hours=args.release_evidence_max_age_hours,
            )
            print(f"VisionFlow presentation gate: {report['status']}")
            print(f"JSON report: {json_path}")
            print(f"HTML report: {html_path}")
            print(f"SHA-256: {sidecar}")
            return exit_code
        report_path, report = verify_gate_report(root, args.report)
        print("VisionFlow presentation gate: VERIFIED")
        print(f"Status: {report['status']}")
        print(f"Report: {report_path}")
        return 0
    except (
        PresentationGateError,
        ProjectCloseoutError,
        TransferDayGateError,
        EvidenceBundleError,
        FileNotFoundError,
        OSError,
    ) as error:
        print(f"[FAIL] {sanitize_error(error, root)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
