"""Run and independently verify a read-only VisionFlow presentation quick check."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

try:
    from visionflow_presentation_performance import (
        READY_STATUS as PERFORMANCE_READY_STATUS,
        REPORT_ROOT as PERFORMANCE_ROOT,
        PresentationPerformanceError,
        verify_performance_report,
    )
    from visionflow_presentation_rehearsal import relative_path
except ModuleNotFoundError:  # pragma: no cover - package import during tests
    from scripts.visionflow_presentation_performance import (
        READY_STATUS as PERFORMANCE_READY_STATUS,
        REPORT_ROOT as PERFORMANCE_ROOT,
        PresentationPerformanceError,
        verify_performance_report,
    )
    from scripts.visionflow_presentation_rehearsal import relative_path


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
SCOPE = "SECOND_PROJECT_DIGITAL_TWIN"
OPERATION = "PRESENTATION_QUICK_CHECK"
REPORT_ROOT = Path("artifacts/presentation-quick-check")
READY_STATUS = "PRESENTATION_QUICK_CHECK_READY_WITH_DEFERRED"
BLOCKED_STATUS = "PRESENTATION_QUICK_CHECK_BLOCKED"
MAX_JSON_BYTES = 5 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 5.0
MAX_RESPONSE_BYTES = 64 * 1024

ENDPOINTS = (
    {
        "key": "backend-health",
        "title": "Backend health",
        "base": "backend",
        "path": "/api/health",
    },
    {
        "key": "backend-drones",
        "title": "Backend drone list",
        "base": "backend",
        "path": "/api/drones",
    },
    {
        "key": "frontend-dashboard",
        "title": "Frontend dashboard",
        "base": "frontend",
        "path": "/dashboard",
    },
    {
        "key": "frontend-drones",
        "title": "Frontend drone control",
        "base": "frontend",
        "path": "/drones",
    },
    {
        "key": "frontend-demo",
        "title": "Frontend demo console",
        "base": "frontend",
        "path": "/demo-scenario",
    },
    {
        "key": "frontend-drone-proxy",
        "title": "Frontend drone proxy",
        "base": "frontend",
        "path": "/api/drones",
    },
    {
        "key": "ai-ingest",
        "title": "AI ingest status",
        "base": "ai",
        "path": "/api/ingest/status",
    },
    {
        "key": "ai-stream",
        "title": "AI stream status",
        "base": "ai",
        "path": "/api/streams/status",
    },
    {
        "key": "frontend-ai-ingest-proxy",
        "title": "Frontend AI ingest proxy",
        "base": "frontend",
        "path": "/api/ai/ingest/status",
    },
    {
        "key": "frontend-ai-stream-proxy",
        "title": "Frontend AI stream proxy",
        "base": "frontend",
        "path": "/api/ai/stream/status",
    },
)


class PresentationQuickCheckError(RuntimeError):
    """Raised when presentation quick-check evidence cannot be trusted."""


Probe = Callable[[Mapping[str, str], float], dict[str, Any]]


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
        raise PresentationQuickCheckError(
            f"{title} 파일을 찾을 수 없습니다."
        )
    if path.stat().st_size > MAX_JSON_BYTES:
        raise PresentationQuickCheckError(
            f"{title} JSON 크기가 너무 큽니다."
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PresentationQuickCheckError(
            f"{title} JSON 형식이 올바르지 않습니다."
        ) from error
    if not isinstance(value, dict):
        raise PresentationQuickCheckError(
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


def resolve_source_performance(root: Path, value: str | None) -> Path:
    allowed = (root / PERFORMANCE_ROOT).resolve()
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
                "visionflow-presentation-performance-*.json"
            )
            if item.is_file() and not item.is_symlink()
        ] if allowed.is_dir() else []
        if not candidates:
            raise PresentationQuickCheckError(
                "발표 성능 분석 JSON이 없습니다."
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
        raise PresentationQuickCheckError(
            "발표 성능 분석 보고서 경로가 올바르지 않습니다."
        )
    return path


def verify_source_performance(
    root: Path,
    value: str | None,
) -> tuple[Path, dict[str, Any]]:
    path = resolve_source_performance(root, value)
    try:
        verified_path, report = verify_performance_report(
            root,
            relative_path(root, path),
        )
    except PresentationPerformanceError as error:
        raise PresentationQuickCheckError(str(error)) from error
    if report.get("status") != PERFORMANCE_READY_STATUS:
        raise PresentationQuickCheckError(
            f"최신 발표 성능 판정이 READY가 아닙니다: {report.get('status')}"
        )
    return verified_path, report


def build_url(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


def default_probe_factory(
    *,
    frontend_url: str,
    backend_url: str,
    ai_url: str,
) -> Probe:
    bases = {
        "frontend": frontend_url,
        "backend": backend_url,
        "ai": ai_url,
    }

    def probe(endpoint: Mapping[str, str], timeout: float) -> dict[str, Any]:
        url = build_url(bases[endpoint["base"]], endpoint["path"])
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
                "User-Agent": "VisionFlow-Presentation-Quick-Check/1.0",
            },
        )
        started = time.monotonic()
        status_code = 0
        error_code = None
        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout,
            ) as response:
                status_code = int(response.status)
                response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as error:
            status_code = int(error.code)
            error_code = f"HTTP_{status_code}"
        except urllib.error.URLError as error:
            reason = getattr(error, "reason", None)
            error_code = (
                type(reason).__name__.upper()
                if reason is not None
                else "URL_ERROR"
            )
        except TimeoutError:
            error_code = "TIMEOUT"
        except OSError as error:
            error_code = type(error).__name__.upper()
        duration_ms = int(round((time.monotonic() - started) * 1000))
        passed = 200 <= status_code < 300
        return {
            "key": endpoint["key"],
            "title": endpoint["title"],
            "base": endpoint["base"],
            "path": endpoint["path"],
            "status": "PASS" if passed else "FAILED",
            "statusCode": status_code,
            "durationMs": max(0, duration_ms),
            "errorCode": None if passed else (error_code or "HTTP_ERROR"),
        }

    return probe


def validate_probe_result(
    endpoint: Mapping[str, str],
    value: Any,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PresentationQuickCheckError(
            f"점검 결과 형식이 올바르지 않습니다: {endpoint['key']}"
        )
    expected = {
        "key": endpoint["key"],
        "title": endpoint["title"],
        "base": endpoint["base"],
        "path": endpoint["path"],
    }
    if any(value.get(key) != item for key, item in expected.items()):
        raise PresentationQuickCheckError(
            f"점검 결과 대상이 다릅니다: {endpoint['key']}"
        )
    status = value.get("status")
    status_code = value.get("statusCode")
    duration = value.get("durationMs")
    error_code = value.get("errorCode")
    if (
        status not in {"PASS", "FAILED"}
        or not isinstance(status_code, int)
        or isinstance(status_code, bool)
        or status_code < 0
        or not isinstance(duration, int)
        or isinstance(duration, bool)
        or duration < 0
        or (
            status == "PASS"
            and (
                not 200 <= status_code < 300
                or error_code is not None
            )
        )
        or (
            status == "FAILED"
            and (
                200 <= status_code < 300
                or not isinstance(error_code, str)
                or not error_code
            )
        )
    ):
        raise PresentationQuickCheckError(
            f"점검 결과 상태가 올바르지 않습니다: {endpoint['key']}"
        )
    return dict(value)


def diagnosis_for(checks: list[Mapping[str, Any]]) -> dict[str, Any]:
    failed = {
        str(item["key"])
        for item in checks
        if item.get("status") == "FAILED"
    }
    if not failed:
        return {
            "code": "PRESENTATION_PATHS_HEALTHY",
            "layer": "NONE",
            "summary": "발표 핵심 경로가 모두 응답합니다.",
            "actions": [
                "브라우저에서 /demo-scenario를 열고 발표를 시작합니다.",
                "발표 중에는 설정·컨테이너·모델을 변경하지 않습니다.",
            ],
        }
    backend_failed = bool(
        failed & {"backend-health", "backend-drones"}
    )
    frontend_page_failed = bool(
        failed
        & {"frontend-dashboard", "frontend-drones", "frontend-demo"}
    )
    ai_failed = bool(failed & {"ai-ingest", "ai-stream"})
    drone_proxy_failed = "frontend-drone-proxy" in failed
    ai_proxy_failed = bool(
        failed
        & {
            "frontend-ai-ingest-proxy",
            "frontend-ai-stream-proxy",
        }
    )
    major_layers = sum(
        (backend_failed, frontend_page_failed, ai_failed)
    )
    if major_layers >= 2:
        return {
            "code": "MULTIPLE_SERVICE_FAILURES",
            "layer": "STACK",
            "summary": "두 개 이상의 핵심 서비스 계층이 응답하지 않습니다.",
            "actions": [
                "docker compose --env-file .env.docker ps를 확인합니다.",
                "scripts\\collect-visionflow-diagnostics.bat를 실행합니다.",
                "무작정 재빌드하기 전에 최초 실패 컨테이너 로그를 확인합니다.",
            ],
        }
    if backend_failed:
        return {
            "code": "BACKEND_OR_DATABASE_UNAVAILABLE",
            "layer": "BACKEND",
            "summary": "Spring Boot 또는 MySQL 연결 경로가 응답하지 않습니다.",
            "actions": [
                "docker compose --env-file .env.docker ps를 확인합니다.",
                "docker compose --env-file .env.docker logs --tail 200 backend-api mysql를 확인합니다.",
                "MySQL healthy 이후 backend-api 상태를 다시 확인합니다.",
            ],
        }
    if ai_failed:
        return {
            "code": "AI_SERVER_UNAVAILABLE",
            "layer": "AI",
            "summary": "AI 직접 상태 경로가 응답하지 않습니다.",
            "actions": [
                "docker compose --env-file .env.docker ps ai-server를 확인합니다.",
                "docker compose --env-file .env.docker logs --tail 200 ai-server를 확인합니다.",
                "현재 LG GRAM 기준 yolo26n.pt와 AI 환경변수 경로를 확인합니다.",
            ],
        }
    if frontend_page_failed:
        return {
            "code": "FRONTEND_UNAVAILABLE",
            "layer": "FRONTEND",
            "summary": "Next.js 발표 화면이 응답하지 않습니다.",
            "actions": [
                "docker compose --env-file .env.docker ps frontend-web을 확인합니다.",
                "docker compose --env-file .env.docker logs --tail 200 frontend-web를 확인합니다.",
                "포트 3000 점유와 컨테이너 health 상태를 확인합니다.",
            ],
        }
    if drone_proxy_failed and ai_proxy_failed:
        return {
            "code": "MULTIPLE_FRONTEND_PROXY_FAILURES",
            "layer": "FRONTEND_PROXY",
            "summary": "Frontend의 Backend·AI 프록시가 모두 실패했습니다.",
            "actions": [
                "Frontend 컨테이너의 Backend·AI 내부 URL 설정을 확인합니다.",
                "Docker Compose 서비스 이름과 네트워크 상태를 확인합니다.",
                "설정 변경 후 frontend-web만 재기동하고 다시 점검합니다.",
            ],
        }
    if drone_proxy_failed:
        return {
            "code": "FRONTEND_BACKEND_PROXY_FAILURE",
            "layer": "FRONTEND_PROXY",
            "summary": "Backend 직접 경로는 정상이나 드론 프록시가 실패했습니다.",
            "actions": [
                "Frontend의 BACKEND_API_URL 설정을 확인합니다.",
                "컨테이너 내부에서 backend-api:8080 연결을 확인합니다.",
                "Frontend 로그의 502·503 원인을 확인합니다.",
            ],
        }
    if ai_proxy_failed:
        return {
            "code": "FRONTEND_AI_PROXY_FAILURE",
            "layer": "FRONTEND_PROXY",
            "summary": "AI 직접 경로는 정상이나 AI 프록시가 실패했습니다.",
            "actions": [
                "Frontend의 AI 서버 URL 설정을 확인합니다.",
                "컨테이너 내부에서 ai-server:8000 연결을 확인합니다.",
                "Frontend 로그의 ECONNREFUSED·502 원인을 확인합니다.",
            ],
        }
    return {
        "code": "UNCLASSIFIED_ENDPOINT_FAILURE",
        "layer": "UNKNOWN",
        "summary": "일부 발표 경로 실패를 자동 분류하지 못했습니다.",
        "actions": [
            "실패한 endpoint key와 HTTP 상태를 확인합니다.",
            "scripts\\collect-visionflow-diagnostics.bat를 실행합니다.",
        ],
    }


def build_report(
    *,
    root: Path,
    performance_path: Path,
    performance: Mapping[str, Any],
    checks: list[dict[str, Any]],
    timeout_seconds: float,
    frontend_url: str,
    backend_url: str,
    ai_url: str,
    now: datetime,
) -> dict[str, Any]:
    diagnosis = diagnosis_for(checks)
    ready = not any(item["status"] == "FAILED" for item in checks)
    deferred = [
        {
            "key": str(item.get("key")),
            "status": str(item.get("status")),
            "scope": str(item.get("scope")),
            "reason": str(item.get("reason")),
        }
        for item in performance.get("deferred", [])
        if isinstance(item, Mapping)
    ]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "scope": SCOPE,
        "operation": OPERATION,
        "quickCheckId": str(uuid.uuid4()),
        "generatedAt": now.astimezone(timezone.utc).isoformat(),
        "status": READY_STATUS if ready else BLOCKED_STATUS,
        "configuration": {
            "timeoutSeconds": timeout_seconds,
            "origins": {
                "frontend": frontend_url.rstrip("/"),
                "backend": backend_url.rstrip("/"),
                "ai": ai_url.rstrip("/"),
            },
            "endpointKeys": [item["key"] for item in ENDPOINTS],
        },
        "sourcePerformance": artifact_entry(root, performance_path),
        "sourcePerformanceAnalysisId": str(performance.get("analysisId")),
        "checks": checks,
        "diagnosis": diagnosis,
        "deferred": deferred,
        "summary": {
            "total": len(checks),
            "passed": sum(item["status"] == "PASS" for item in checks),
            "failed": sum(item["status"] == "FAILED" for item in checks),
            "blocking": 0 if ready else 1,
            "diagnosisCode": diagnosis["code"],
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
            "automaticRestart": False,
            "responseBodiesRecorded": False,
            "environmentValuesRecorded": False,
            "operatorKeysRecorded": False,
            "privateKeysRecorded": False,
            "absolutePathsRecorded": False,
            "gpuValidationExecuted": False,
            "smartphoneSensorValidationExecuted": False,
            "djiIntegrationExecuted": False,
        },
    }


def render_html(report: Mapping[str, Any]) -> str:
    ready = report["status"] == READY_STATUS
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['title']))}</td>"
        f"<td><code>{html.escape(str(item['path']))}</code></td>"
        f"<td class='{str(item['status']).lower()}'>"
        f"{html.escape(str(item['status']))}</td>"
        f"<td>{item['statusCode']}</td>"
        f"<td>{item['durationMs']}</td>"
        f"<td>{html.escape(str(item.get('errorCode') or '-'))}</td>"
        "</tr>"
        for item in report["checks"]
    )
    actions = "".join(
        f"<li>{html.escape(str(item))}</li>"
        for item in report["diagnosis"]["actions"]
    )
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VisionFlow 발표 당일 퀵체크</title><style>
body {{ margin:0; background:#eef3f8; color:#0f172a; font-family:Arial,'Noto Sans KR',sans-serif; }}
main {{ max-width:1180px; margin:32px auto; padding:0 20px; }}
section {{ background:#fff; border:1px solid #dbe4ee; border-radius:16px; padding:24px; margin:16px 0; }}
h1,h2 {{ margin-top:0; }} .status {{ color:{'#047857' if ready else '#b91c1c'}; font-size:1.35rem; font-weight:800; }}
table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:10px; border-bottom:1px solid #e2e8f0; text-align:left; vertical-align:top; }}
.pass {{ color:#047857; font-weight:700; }} .failed {{ color:#b91c1c; font-weight:700; }}
code {{ word-break:break-all; }}
</style></head><body><main>
<section><h1>VisionFlow 발표 당일 퀵체크</h1>
<p class="status">{html.escape(str(report['status']))}</p>
<p>통과 {report['summary']['passed']}/{report['summary']['total']} ·
실패 {report['summary']['failed']} ·
진단 {html.escape(str(report['diagnosis']['code']))}</p></section>
<section><h2>핵심 경로</h2><table><thead><tr><th>항목</th><th>경로</th><th>상태</th><th>HTTP</th><th>ms</th><th>오류</th></tr></thead>
<tbody>{rows}</tbody></table></section>
<section><h2>자동 진단</h2>
<p>{html.escape(str(report['diagnosis']['summary']))}</p><ol>{actions}</ol>
</section></main></body></html>
"""


def validate_output_root(root: Path, output_root: Path) -> None:
    allowed = (root / REPORT_ROOT).resolve()
    output = output_root.resolve()
    if output != allowed or output_root.is_symlink():
        raise PresentationQuickCheckError(
            "발표 퀵체크 출력 폴더는 "
            "artifacts/presentation-quick-check여야 합니다."
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
    base = output_root / f"visionflow-presentation-quick-check-{stamp}"
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
        raise PresentationQuickCheckError(
            "발표 퀵체크 sidecar가 없습니다."
        )
    try:
        lines = [
            line.strip().split()
            for line in sidecar.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
    except UnicodeDecodeError as error:
        raise PresentationQuickCheckError(
            "발표 퀵체크 sidecar가 UTF-8이 아닙니다."
        ) from error
    if len(lines) != 2 or any(len(parts) != 2 for parts in lines):
        raise PresentationQuickCheckError(
            "발표 퀵체크 sidecar 형식이 올바르지 않습니다."
        )
    recorded = {parts[1]: parts[0].lower() for parts in lines}
    if set(recorded) != {json_path.name, html_path.name}:
        raise PresentationQuickCheckError(
            "발표 퀵체크 sidecar 파일 목록이 다릅니다."
        )
    for path in (json_path, html_path):
        checksum = recorded[path.name]
        if (
            not is_checksum(checksum)
            or not path.is_file()
            or path.is_symlink()
            or checksum != sha256_file(path)
        ):
            raise PresentationQuickCheckError(
                f"발표 퀵체크 SHA-256이 다릅니다: {path.name}"
            )


def verify_source_artifact(root: Path, value: Any) -> Path:
    if not isinstance(value, Mapping):
        raise PresentationQuickCheckError(
            "원본 발표 성능 메타데이터가 없습니다."
        )
    relative = value.get("path")
    if not isinstance(relative, str):
        raise PresentationQuickCheckError(
            "원본 발표 성능 상대경로가 없습니다."
        )
    allowed = (root / PERFORMANCE_ROOT).resolve()
    path = (root / relative).resolve()
    if (
        not is_within(path, allowed)
        or not path.is_file()
        or path.is_symlink()
        or value.get("fileName") != path.name
        or value.get("sizeBytes") != path.stat().st_size
        or value.get("sha256") != sha256_file(path)
    ):
        raise PresentationQuickCheckError(
            "원본 발표 성능 파일 동일성이 다릅니다."
        )
    return path


def resolve_quick_check_report(root: Path, value: str) -> Path:
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
        raise PresentationQuickCheckError(
            "발표 퀵체크 보고서 경로가 올바르지 않습니다."
        )
    return path


def validate_configuration(value: Any) -> tuple[float, dict[str, str]]:
    if not isinstance(value, Mapping):
        raise PresentationQuickCheckError(
            "발표 퀵체크 설정이 없습니다."
        )
    timeout = value.get("timeoutSeconds")
    origins = value.get("origins")
    keys = value.get("endpointKeys")
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or not 0 < timeout <= 60
        or not isinstance(origins, Mapping)
        or keys != [item["key"] for item in ENDPOINTS]
    ):
        raise PresentationQuickCheckError(
            "발표 퀵체크 설정이 올바르지 않습니다."
        )
    normalized = {}
    for key in ("frontend", "backend", "ai"):
        origin = origins.get(key)
        if (
            not isinstance(origin, str)
            or not origin.startswith(("http://", "https://"))
            or origin.endswith("/")
        ):
            raise PresentationQuickCheckError(
                "발표 퀵체크 서비스 주소가 올바르지 않습니다."
            )
        normalized[key] = origin
    return float(timeout), normalized


def verify_quick_check_report(
    root: Path,
    value: str,
) -> tuple[Path, dict[str, Any]]:
    json_path = resolve_quick_check_report(root, value)
    html_path = json_path.with_suffix(".html")
    verify_sidecar(json_path, html_path)
    report = read_json(json_path, "발표 퀵체크")
    checks = report.get("checks")
    deferred = report.get("deferred")
    summary = report.get("summary")
    safety = report.get("safety")
    if (
        report.get("schemaVersion") != SCHEMA_VERSION
        or report.get("project") != PROJECT_NAME
        or report.get("scope") != SCOPE
        or report.get("operation") != OPERATION
        or report.get("status") not in {READY_STATUS, BLOCKED_STATUS}
        or not isinstance(report.get("quickCheckId"), str)
        or not isinstance(report.get("generatedAt"), str)
        or not isinstance(checks, list)
        or not isinstance(report.get("diagnosis"), Mapping)
        or not isinstance(deferred, list)
        or not isinstance(summary, Mapping)
        or not isinstance(safety, Mapping)
    ):
        raise PresentationQuickCheckError(
            "발표 퀵체크 보고서 형식이 올바르지 않습니다."
        )
    validate_configuration(report.get("configuration"))
    if len(checks) != len(ENDPOINTS):
        raise PresentationQuickCheckError(
            "발표 퀵체크 항목 수가 다릅니다."
        )
    validated_checks = [
        validate_probe_result(endpoint, result)
        for endpoint, result in zip(ENDPOINTS, checks, strict=True)
    ]
    diagnosis = diagnosis_for(validated_checks)
    ready = not any(
        item["status"] == "FAILED" for item in validated_checks
    )
    source_path = verify_source_artifact(
        root,
        report.get("sourcePerformance"),
    )
    try:
        _, performance = verify_performance_report(
            root,
            relative_path(root, source_path),
        )
    except PresentationPerformanceError as error:
        raise PresentationQuickCheckError(str(error)) from error
    expected_deferred = [
        {
            "key": str(item.get("key")),
            "status": str(item.get("status")),
            "scope": str(item.get("scope")),
            "reason": str(item.get("reason")),
        }
        for item in performance.get("deferred", [])
        if isinstance(item, Mapping)
    ]
    expected_summary = {
        "total": len(validated_checks),
        "passed": sum(
            item["status"] == "PASS" for item in validated_checks
        ),
        "failed": sum(
            item["status"] == "FAILED" for item in validated_checks
        ),
        "blocking": 0 if ready else 1,
        "diagnosisCode": diagnosis["code"],
        "deferred": sum(
            item["status"] == "DEFERRED" for item in expected_deferred
        ),
        "outOfScope": sum(
            item["status"] == "OUT_OF_SCOPE" for item in expected_deferred
        ),
    }
    if (
        performance.get("status") != PERFORMANCE_READY_STATUS
        or report.get("sourcePerformanceAnalysisId")
        != str(performance.get("analysisId"))
        or report.get("checks") != validated_checks
        or report.get("diagnosis") != diagnosis
        or report.get("deferred") != expected_deferred
        or report.get("summary") != expected_summary
        or report.get("status") != (READY_STATUS if ready else BLOCKED_STATUS)
        or safety.get("readOnly") is not True
        or safety.get("databaseMutation") is not False
        or safety.get("serviceMutation") is not False
        or safety.get("automaticRestart") is not False
        or safety.get("responseBodiesRecorded") is not False
        or safety.get("environmentValuesRecorded") is not False
        or safety.get("operatorKeysRecorded") is not False
        or safety.get("privateKeysRecorded") is not False
        or safety.get("absolutePathsRecorded") is not False
        or safety.get("gpuValidationExecuted") is not False
        or safety.get("smartphoneSensorValidationExecuted") is not False
        or safety.get("djiIntegrationExecuted") is not False
    ):
        raise PresentationQuickCheckError(
            "발표 퀵체크 판정 또는 안전 메타데이터가 다릅니다."
        )
    try:
        html_value = html_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise PresentationQuickCheckError(
            "발표 퀵체크 HTML이 UTF-8이 아닙니다."
        ) from error
    lowered = html_value.lower()
    if any(
        token in lowered
        for token in ("<script", "<iframe", "<object", "<embed", "javascript:")
    ):
        raise PresentationQuickCheckError(
            "발표 퀵체크 HTML에 실행 가능한 콘텐츠가 있습니다."
        )
    if html_value != render_html(report):
        raise PresentationQuickCheckError(
            "발표 퀵체크 JSON과 HTML 내용이 일치하지 않습니다."
        )
    return json_path, report


def run_quick_check(
    root: Path,
    *,
    performance_value: str | None,
    output_root: Path,
    probe: Probe,
    timeout_seconds: float,
    frontend_url: str,
    backend_url: str,
    ai_url: str,
    now: datetime,
) -> tuple[Path, Path, Path, dict[str, Any], int]:
    if not 0 < timeout_seconds <= 60:
        raise PresentationQuickCheckError(
            "요청 제한 시간은 0초 초과 60초 이하여야 합니다."
        )
    performance_path, performance = verify_source_performance(
        root,
        performance_value,
    )
    checks = [
        validate_probe_result(endpoint, probe(endpoint, timeout_seconds))
        for endpoint in ENDPOINTS
    ]
    report = build_report(
        root=root,
        performance_path=performance_path,
        performance=performance,
        checks=checks,
        timeout_seconds=timeout_seconds,
        frontend_url=frontend_url,
        backend_url=backend_url,
        ai_url=ai_url,
        now=now,
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


def build_plan() -> list[dict[str, str]]:
    return [
        {
            "order": "01",
            "mode": "READ_ONLY",
            "detail": "최신 READY 발표 성능 판정과 전체 증적 계보 검증",
        },
        {
            "order": "02",
            "mode": "PROBE",
            "detail": "Backend·AI·Frontend·프록시 핵심 GET 경로 점검",
        },
        {
            "order": "03",
            "mode": "DIAGNOSE",
            "detail": "실패 계층과 안전한 다음 확인 명령 자동 분류",
        },
        {
            "order": "04",
            "mode": "EVIDENCE",
            "detail": "JSON·HTML·SHA-256 퀵체크 증적 생성 및 재검증",
        },
    ]


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="VisionFlow presentation quick check"
    )
    parser.add_argument("--root", default=str(default_root))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("plan", help="변경 없는 점검 계획 출력")
    check = subparsers.add_parser(
        "check",
        help="발표 핵심 경로 읽기 전용 점검",
    )
    check.add_argument("--performance")
    check.add_argument(
        "--frontend-url",
        default="http://localhost:3000",
    )
    check.add_argument(
        "--backend-url",
        default="http://localhost:8080",
    )
    check.add_argument(
        "--ai-url",
        default="http://localhost:8000",
    )
    check.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
    )
    check.add_argument("--output", default=REPORT_ROOT.as_posix())
    verify = subparsers.add_parser(
        "verify",
        help="발표 퀵체크 증적 독립 재검증",
    )
    verify.add_argument("--report", required=True)
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    args = build_parser(default_root).parse_args(arguments)
    root = Path(args.root).resolve()
    try:
        if not root.is_dir():
            raise PresentationQuickCheckError(
                "프로젝트 루트를 찾을 수 없습니다."
            )
        if args.command == "plan":
            print("VisionFlow presentation quick check: PLAN")
            for item in build_plan():
                print(f"{item['order']}. [{item['mode']}] {item['detail']}")
            print(
                "No database write, service restart, GPU, smartphone, "
                "or DJI action was executed."
            )
            return 0
        if args.command == "verify":
            path, report = verify_quick_check_report(root, args.report)
            print("VisionFlow presentation quick check: VERIFIED")
            print(f"Status: {report['status']}")
            print(f"Report: {path}")
            return 0
        origins = {
            "frontend": args.frontend_url.rstrip("/"),
            "backend": args.backend_url.rstrip("/"),
            "ai": args.ai_url.rstrip("/"),
        }
        validate_configuration(
            {
                "timeoutSeconds": args.timeout_seconds,
                "origins": origins,
                "endpointKeys": [item["key"] for item in ENDPOINTS],
            }
        )
        output_value = Path(args.output)
        output = (
            output_value.resolve()
            if output_value.is_absolute()
            else (root / output_value).resolve()
        )
        probe = default_probe_factory(
            frontend_url=origins["frontend"],
            backend_url=origins["backend"],
            ai_url=origins["ai"],
        )
        json_path, html_path, sidecar, report, exit_code = run_quick_check(
            root,
            performance_value=args.performance,
            output_root=output,
            probe=probe,
            timeout_seconds=args.timeout_seconds,
            frontend_url=origins["frontend"],
            backend_url=origins["backend"],
            ai_url=origins["ai"],
            now=datetime.now(timezone.utc),
        )
        print(f"VisionFlow presentation quick check: {report['status']}")
        print(
            "Checks: "
            f"{report['summary']['passed']}/"
            f"{report['summary']['total']} passed"
        )
        print(f"Diagnosis: {report['diagnosis']['code']}")
        for action in report["diagnosis"]["actions"]:
            print(f"- {action}")
        print(f"JSON report: {json_path}")
        print(f"HTML report: {html_path}")
        print(f"SHA-256: {sidecar}")
        return exit_code
    except (
        PresentationQuickCheckError,
        PresentationPerformanceError,
        FileNotFoundError,
        OSError,
        ValueError,
    ) as error:
        print(f"[FAIL] {sanitize_error(error, root)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
