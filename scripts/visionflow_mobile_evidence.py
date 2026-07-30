"""Create a privacy-preserving VisionFlow smartphone E2E evidence report."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
OPERATION = "SMARTPHONE_E2E_VERIFICATION"
OUTPUT_PREFIX = "visionflow-smartphone-e2e"
MAX_RESPONSE_BYTES = 10 * 1024 * 1024


class MobileEvidenceError(RuntimeError):
    """Raised when smartphone evidence cannot be collected safely."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_text_atomic(path: Path, value: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding=encoding)
    os.replace(temporary, path)


def write_json(path: Path, value: dict[str, Any]) -> None:
    write_text_atomic(
        path,
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )


def read_limited(response: Any) -> bytes:
    value = response.read(MAX_RESPONSE_BYTES + 1)
    if len(value) > MAX_RESPONSE_BYTES:
        raise MobileEvidenceError("API 응답 크기가 허용 범위를 초과했습니다.")
    return value


def request(
    url: str,
    *,
    timeout_seconds: int,
    operator_key: str | None = None,
    accept: str = "application/json",
) -> tuple[int, dict[str, str], bytes]:
    headers = {"Accept": accept, "User-Agent": "VisionFlow-Mobile-Evidence/1"}
    if operator_key:
        headers["X-VisionFlow-Operator-Key"] = operator_key
    outgoing = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(outgoing, timeout=timeout_seconds) as response:
            return (
                int(response.status),
                {key.lower(): value for key, value in response.headers.items()},
                read_limited(response),
            )
    except urllib.error.HTTPError as error:
        detail = read_limited(error).decode("utf-8", errors="replace")[:1000]
        raise MobileEvidenceError(
            f"HTTP {error.code} 응답: {url} {detail}"
        ) from error
    except urllib.error.URLError as error:
        raise MobileEvidenceError(f"API에 연결할 수 없습니다: {url} ({error.reason})") from error


def request_json(
    url: str,
    *,
    timeout_seconds: int,
    operator_key: str | None,
) -> Any:
    status, _, body = request(
        url,
        timeout_seconds=timeout_seconds,
        operator_key=operator_key,
    )
    if status != 200:
        raise MobileEvidenceError(f"예상하지 못한 HTTP 상태입니다: {status} {url}")
    try:
        return json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MobileEvidenceError(f"JSON 응답 형식이 올바르지 않습니다: {url}") from error


def unwrap_data(value: Any) -> Any:
    if isinstance(value, dict) and "data" in value:
        return value["data"]
    return value


def require_list(value: Any, title: str) -> list[Any]:
    unwrapped = unwrap_data(value)
    if not isinstance(unwrapped, list):
        raise MobileEvidenceError(f"{title} 응답은 배열이어야 합니다.")
    return unwrapped


def require_object(value: Any, title: str) -> dict[str, Any]:
    unwrapped = unwrap_data(value)
    if not isinstance(unwrapped, dict):
        raise MobileEvidenceError(f"{title} 응답은 객체여야 합니다.")
    return unwrapped


def normalize_base_url(value: str, title: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urllib.parse.urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise MobileEvidenceError(f"{title} URL 형식이 올바르지 않습니다.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise MobileEvidenceError(f"{title} URL에 자격증명, 쿼리 또는 fragment를 넣을 수 없습니다.")
    return normalized


def check(key: str, passed: bool, detail: str, actual: Any = None) -> dict[str, Any]:
    return {
        "key": key,
        "status": "PASS" if passed else "BLOCKED",
        "detail": detail,
        "actual": actual,
    }


def int_value(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def present_number(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def resolve_frontend_url(root: Path, explicit_url: str | None) -> str:
    if explicit_url and explicit_url.strip():
        return explicit_url

    metadata_path = (
        root
        / "artifacts/mobile-https/certificates/visionflow-mobile-https.json"
    )
    if not metadata_path.is_file() or metadata_path.is_symlink():
        raise MobileEvidenceError(
            "모바일 HTTPS 메타데이터가 없습니다. "
            "run-visionflow-mobile-https.bat를 먼저 실행하거나 "
            "--frontend-url에 실제 LAN HTTPS 주소를 지정하세요."
        )
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MobileEvidenceError(
            f"모바일 HTTPS 메타데이터를 읽을 수 없습니다: {metadata_path}"
        ) from error
    mobile_url = metadata.get("mobileUrl") if isinstance(metadata, dict) else None
    if not isinstance(mobile_url, str) or not mobile_url.strip():
        raise MobileEvidenceError("모바일 HTTPS 메타데이터에 mobileUrl이 없습니다.")
    parsed = urllib.parse.urlparse(mobile_url.strip())
    return urllib.parse.urlunparse(
        (parsed.scheme, parsed.netloc, "", "", "", "")
    )


def timestamp_sort_key(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        return datetime.min.replace(tzinfo=timezone.utc)

    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def find_drone_ids(drones: list[Any]) -> list[int]:
    drone_ids = {
        item.get("id")
        for item in drones
        if isinstance(item, dict)
        and isinstance(item.get("id"), int)
        and not isinstance(item.get("id"), bool)
        and item.get("id") > 0
    }

    if not drone_ids:
        raise MobileEvidenceError("증적을 조회할 등록 드론을 찾지 못했습니다.")

    return sorted(drone_ids)


def find_session(
    sessions: list[Any],
    *,
    session_id: str | None,
    min_telemetry: int,
) -> dict[str, Any]:
    candidates = [item for item in sessions if isinstance(item, dict)]
    if session_id:
        matches = [item for item in candidates if item.get("sessionId") == session_id]
        if not matches:
            raise MobileEvidenceError(f"지정한 비행 세션을 찾을 수 없습니다: {session_id}")
        return matches[0]

    eligible = [
        item
        for item in candidates
        if item.get("status") == "COMPLETED"
        and bool(item.get("sourceDeviceId"))
        and int_value(item.get("telemetryCount")) >= min_telemetry
    ]
    if not eligible:
        raise MobileEvidenceError(
            "완료된 스마트폰 비행 세션을 찾지 못했습니다. "
            "스마트폰에서 비행을 완료하거나 --session-id를 지정하세요."
        )

    return max(
        eligible,
        key=lambda item: (
            timestamp_sort_key(item.get("startedAt")),
            timestamp_sort_key(item.get("endedAt")),
        ),
    )


def evaluate(
    session: dict[str, Any],
    replay: dict[str, Any],
    *,
    frontend_status: int,
    frontend_headers: dict[str, str],
    min_telemetry: int,
    min_ai_events: int,
    min_detections: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    telemetry = replay.get("telemetry")
    events = replay.get("aiEvents")
    if not isinstance(telemetry, list) or not isinstance(events, list):
        raise MobileEvidenceError("비행 리플레이에 telemetry 또는 aiEvents 배열이 없습니다.")

    telemetry_objects = [item for item in telemetry if isinstance(item, dict)]
    event_objects = [item for item in events if isinstance(item, dict)]
    mobile_sensor_count = sum(
        item.get("telemetrySource") == "MOBILE_SENSOR" for item in telemetry_objects
    )
    location_count = sum(
        present_number(item.get("latitude")) and present_number(item.get("longitude"))
        for item in telemetry_objects
    )
    orientation_count = sum(
        any(present_number(item.get(key)) for key in ("heading", "pitch", "roll"))
        for item in telemetry_objects
    )
    telemetry_count = int_value(replay.get("telemetryCount"))
    ai_event_count = int_value(replay.get("aiEventCount"))
    detection_count = int_value(replay.get("detectionCount"))
    permissions = frontend_headers.get("permissions-policy", "")
    permissions_ready = (
        "camera=(self)" in permissions
        and "geolocation=(self)" in permissions
        and "microphone=()" in permissions
    )
    checks = [
        check(
            "trusted-https-endpoint",
            frontend_status == 200,
            "LAN HTTPS 페이지가 PC 신뢰 체인과 IP SAN 검증을 통과",
            frontend_status,
        ),
        check(
            "browser-permission-policy",
            permissions_ready,
            "카메라와 위치는 self 전용, 마이크는 비활성",
            permissions if permissions_ready else "INVALID",
        ),
        check(
            "completed-flight-session",
            session.get("status") == "COMPLETED",
            "서버 관리 비행 세션이 정상 완료됨",
            session.get("status"),
        ),
        check(
            "mobile-source-identity",
            bool(session.get("sourceDeviceId")),
            "스마트폰 소스 식별자가 기록됨",
            bool(session.get("sourceDeviceId")),
        ),
        check(
            "telemetry-minimum",
            telemetry_count >= min_telemetry,
            f"텔레메트리 {min_telemetry}건 이상 저장",
            telemetry_count,
        ),
        check(
            "mobile-sensor-source",
            mobile_sensor_count >= min_telemetry,
            "MOBILE_SENSOR 원본 텔레메트리 저장",
            mobile_sensor_count,
        ),
        check(
            "gps-values",
            location_count >= min_telemetry,
            "유효한 GPS 위도·경도 저장",
            location_count,
        ),
        check(
            "orientation-values",
            orientation_count >= 1,
            "방위·피치·롤 중 하나 이상의 실센서 값 저장",
            orientation_count,
        ),
        check(
            "ai-events",
            ai_event_count >= min_ai_events,
            f"동일 세션 AI 이벤트 {min_ai_events}건 이상 저장",
            ai_event_count,
        ),
        check(
            "ai-detections",
            detection_count >= min_detections,
            f"동일 세션 AI 탐지 {min_detections}건 이상 저장",
            detection_count,
        ),
    ]
    source_id = str(session.get("sourceDeviceId") or "")
    summary = {
        "sessionId": str(session.get("sessionId") or ""),
        "droneId": session.get("droneId"),
        "sessionStatus": session.get("status"),
        "startedAt": session.get("startedAt"),
        "endedAt": session.get("endedAt"),
        "durationSeconds": int_value(session.get("durationSeconds")),
        "sourceDeviceIdRecorded": bool(source_id),
        "sourceDeviceIdSha256Prefix": sha256_bytes(source_id.encode("utf-8"))[:16]
        if source_id
        else None,
        "telemetryCount": telemetry_count,
        "mobileSensorCount": mobile_sensor_count,
        "gpsValueCount": location_count,
        "orientationValueCount": orientation_count,
        "aiEventCount": ai_event_count,
        "detectionCount": detection_count,
    }
    return checks, summary


def render_html(report: dict[str, Any]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['key']))}</td>"
        f"<td class=\"{html.escape(str(item['status']).lower())}\">"
        f"{html.escape(str(item['status']))}</td>"
        f"<td>{html.escape(str(item['detail']))}</td>"
        f"<td>{html.escape(str(item.get('actual', '-')))}</td>"
        "</tr>"
        for item in report["checks"]
    )
    summary_rows = "".join(
        "<tr>"
        f"<th>{html.escape(str(key))}</th>"
        f"<td>{html.escape(str(value))}</td>"
        "</tr>"
        for key, value in report["evidence"].items()
    )
    return f"""<!doctype html>
<html lang=\"ko\"><head><meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>VisionFlow Smartphone E2E Evidence</title>
<style>
body{{font-family:Arial,sans-serif;margin:32px;color:#0f172a}}
table{{border-collapse:collapse;width:100%;margin:18px 0}}
th,td{{border:1px solid #cbd5e1;padding:9px;text-align:left}}
th{{background:#f1f5f9}}.pass{{color:#047857;font-weight:700}}
.blocked{{color:#b91c1c;font-weight:700}}code{{word-break:break-all}}
</style></head><body>
<h1>VisionFlow 스마트폰 실기기 E2E 검증</h1>
<p>상태: <strong>{html.escape(str(report['status']))}</strong></p>
<p>생성: <code>{html.escape(str(report['generatedAt']))}</code></p>
<h2>검증 결과</h2><table><thead><tr><th>항목</th><th>상태</th><th>설명</th><th>값</th></tr></thead>
<tbody>{rows}</tbody></table>
<h2>비식별 증거 요약</h2><table><tbody>{summary_rows}</tbody></table>
<p>정확한 GPS 좌표, 운영자 키, 세션 토큰, 원본 영상은 기록하지 않았습니다.</p>
</body></html>"""


def create_output_paths(root: Path, output: str, now: datetime) -> tuple[Path, Path]:
    requested = Path(output)
    output_root = requested.resolve() if requested.is_absolute() else (root / requested).resolve()
    allowed_root = (root / "artifacts/mobile-readiness").resolve()
    try:
        output_root.relative_to(allowed_root)
    except ValueError as error:
        raise MobileEvidenceError("출력 폴더는 artifacts/mobile-readiness 내부여야 합니다.") from error
    output_root.mkdir(parents=True, exist_ok=True)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    json_path = output_root / f"{OUTPUT_PREFIX}-{timestamp}.json"
    if json_path.exists():
        json_path = output_root / f"{OUTPUT_PREFIX}-{timestamp}-{uuid.uuid4().hex[:8]}.json"
    return json_path, json_path.with_suffix(".html")


def collect(
    root: Path,
    *,
    backend_url: str,
    frontend_url: str,
    operator_key: str | None,
    drone_id: int | None,
    session_id: str | None,
    min_telemetry: int,
    min_ai_events: int,
    min_detections: int,
    timeout_seconds: int,
    output: str,
    now: datetime,
) -> tuple[Path, Path, dict[str, Any], int]:
    backend = normalize_base_url(backend_url, "백엔드")
    frontend = normalize_base_url(frontend_url, "프런트엔드")
    if urllib.parse.urlparse(frontend).scheme != "https":
        raise MobileEvidenceError("스마트폰 E2E 증거는 HTTPS 프런트엔드가 필요합니다.")
    if drone_id is None:
        drones = require_list(
            request_json(
                f"{backend}/api/drones",
                timeout_seconds=timeout_seconds,
                operator_key=operator_key,
            ),
            "드론 목록",
        )
        drone_ids = find_drone_ids(drones)
    else:
        drone_ids = [drone_id]

    session_query = urllib.parse.urlencode({"limit": 100})
    sessions: list[Any] = []

    for candidate_drone_id in drone_ids:
        drone_sessions = require_list(
            request_json(
                f"{backend}/api/drones/{candidate_drone_id}/flight-sessions?"
                f"{session_query}",
                timeout_seconds=timeout_seconds,
                operator_key=operator_key,
            ),
            f"드론 {candidate_drone_id} 비행 세션 목록",
        )

        for item in drone_sessions:
            if not isinstance(item, dict):
                continue

            normalized = dict(item)
            normalized.setdefault("droneId", candidate_drone_id)
            sessions.append(normalized)

    session = find_session(
        sessions,
        session_id=session_id,
        min_telemetry=min_telemetry,
    )
    selected_drone_id = int_value(session.get("droneId"))
    if selected_drone_id <= 0:
        raise MobileEvidenceError("선택된 세션에 유효한 droneId가 없습니다.")

    selected_session_id = str(session.get("sessionId") or "")
    if not selected_session_id:
        raise MobileEvidenceError("선택된 세션에 sessionId가 없습니다.")
    encoded_session = urllib.parse.quote(selected_session_id, safe="")
    replay_query = urllib.parse.urlencode(
        {"telemetryLimit": 5000, "eventLimit": 1000}
    )
    replay = require_object(
        request_json(
            f"{backend}/api/drones/{selected_drone_id}/flight-sessions/"
            f"{encoded_session}/replay?{replay_query}",
            timeout_seconds=timeout_seconds,
            operator_key=operator_key,
        ),
        "비행 리플레이",
    )
    frontend_status, frontend_headers, _ = request(
        f"{frontend}/mobile-flight",
        timeout_seconds=timeout_seconds,
        accept="text/html",
    )
    checks, evidence = evaluate(
        session,
        replay,
        frontend_status=frontend_status,
        frontend_headers=frontend_headers,
        min_telemetry=min_telemetry,
        min_ai_events=min_ai_events,
        min_detections=min_detections,
    )
    blocked = [item for item in checks if item["status"] == "BLOCKED"]
    report = {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "operation": OPERATION,
        "reportId": str(uuid.uuid4()),
        "generatedAt": now.isoformat(),
        "status": "SMARTPHONE_E2E_PASS" if not blocked else "SMARTPHONE_E2E_BLOCKED",
        "checks": checks,
        "evidence": evidence,
        "privacy": {
            "exactCoordinatesRecorded": False,
            "operatorKeyRecorded": False,
            "sessionTokenRecorded": False,
            "rawImageRecorded": False,
            "rawVideoRecorded": False,
        },
        "safety": {
            "readOnly": True,
            "databaseMutation": False,
            "externalMessagesSent": False,
        },
        "summary": {"passed": len(checks) - len(blocked), "blocked": len(blocked)},
    }
    json_path, html_path = create_output_paths(root, output, now)
    write_json(json_path, report)
    write_text_atomic(html_path, render_html(report))
    checksum = sha256_file(json_path)
    write_text_atomic(
        json_path.with_suffix(".sha256"),
        f"{checksum}  {json_path.name}\n",
    )
    return json_path, html_path, report, 1 if blocked else 0


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VisionFlow smartphone E2E evidence")
    parser.add_argument("--root", default=str(default_root))
    parser.add_argument(
        "--backend-url",
        default=os.environ.get("BACKEND_API_URL", "http://localhost:8080"),
    )
    parser.add_argument(
        "--frontend-url",
        default=os.environ.get("VISIONFLOW_MOBILE_FRONTEND_URL"),
        help=(
            "실제 LAN HTTPS 기본 URL. 생략하면 "
            "artifacts/mobile-https 인증서 메타데이터의 mobileUrl을 사용합니다."
        ),
    )
    parser.add_argument("--operator-key-env", default="VISIONFLOW_ACCEPTANCE_OPERATOR_KEY")
    parser.add_argument(
        "--drone-id",
        type=int,
        help="생략하면 등록된 모든 드론에서 최신 완료 세션을 자동 선택합니다.",
    )
    parser.add_argument("--session-id")
    parser.add_argument("--min-telemetry", type=int, default=3)
    parser.add_argument("--min-ai-events", type=int, default=1)
    parser.add_argument("--min-detections", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=15)
    parser.add_argument("--output", default="artifacts/mobile-readiness")
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    args = build_parser(default_root).parse_args(arguments)
    root = Path(args.root).resolve()
    try:
        if not root.is_dir():
            raise MobileEvidenceError(f"프로젝트 루트를 찾을 수 없습니다: {root}")
        if args.drone_id is not None and args.drone_id <= 0:
            raise MobileEvidenceError("드론 ID는 1 이상이어야 합니다.")
        if min(args.min_telemetry, args.min_ai_events, args.min_detections) < 0:
            raise MobileEvidenceError("최소 검증 건수는 음수일 수 없습니다.")
        if args.min_telemetry < 1:
            raise MobileEvidenceError("최소 텔레메트리 건수는 1 이상이어야 합니다.")
        if args.timeout_seconds <= 0:
            raise MobileEvidenceError("요청 제한 시간은 양수여야 합니다.")
        operator_key = os.environ.get(args.operator_key_env, "").strip() or None
        frontend_url = resolve_frontend_url(root, args.frontend_url)
        json_path, html_path, report, exit_code = collect(
            root,
            backend_url=args.backend_url,
            frontend_url=frontend_url,
            operator_key=operator_key,
            drone_id=args.drone_id,
            session_id=args.session_id,
            min_telemetry=args.min_telemetry,
            min_ai_events=args.min_ai_events,
            min_detections=args.min_detections,
            timeout_seconds=args.timeout_seconds,
            output=args.output,
            now=datetime.now(timezone.utc),
        )
        print(f"VisionFlow smartphone E2E evidence: {report['status']}")
        print(f"Selected drone : {report['evidence']['droneId']}")
        print(f"Selected session: {report['evidence']['sessionId']}")
        print(f"JSON evidence: {json_path}")
        print(f"HTML evidence: {html_path}")
        return exit_code
    except (MobileEvidenceError, OSError, ValueError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
