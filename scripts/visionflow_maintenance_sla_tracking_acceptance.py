from __future__ import annotations

import argparse
import html
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CheckResult:
    title: str
    status: str
    duration_ms: int
    detail: str


def request(
    url: str,
    *,
    timeout_seconds: float = 10.0,
) -> tuple[int, bytes, dict[str, str]]:
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"Accept": "application/json,text/html"},
    )
    try:
        with urllib.request.urlopen(
            req,
            timeout=timeout_seconds,
        ) as response:
            return (
                response.status,
                response.read(),
                dict(response.headers.items()),
            )
    except urllib.error.HTTPError as error:
        return (
            error.code,
            error.read(),
            dict(error.headers.items()),
        )


def run_check(title: str, action: Any) -> CheckResult:
    started = time.perf_counter()
    try:
        detail = action()
        status = "PASS"
    except Exception as error:  # noqa: BLE001
        detail = str(error)
        status = "FAIL"
    duration_ms = round((time.perf_counter() - started) * 1000)
    print(f"[{status}] {title} ({duration_ms} ms) - {detail}")
    return CheckResult(title, status, duration_ms, detail)


def decode_json(body: bytes) -> dict[str, Any]:
    value = json.loads(body.decode("utf-8-sig"))
    if isinstance(value, dict) and isinstance(value.get("data"), dict):
        value = value["data"]
    if not isinstance(value, dict):
        raise AssertionError("JSON 응답이 객체가 아닙니다.")
    return value


def validate_tracking(
    value: dict[str, Any],
) -> str:
    required = {
        "evaluatedAt",
        "windowDays",
        "totalWorkOrders",
        "connectedIncidents",
        "overdueWorkOrders",
        "escalatedIncidents",
        "monitoringWorkOrders",
        "escalationPendingIncidents",
        "assignmentRequiredIncidents",
        "inResponseIncidents",
        "completedResponses",
        "pendingWorkOrderClosures",
        "returnToServiceConfirmed",
        "groundedClosures",
        "closureConsistencyAlerts",
        "items",
    }
    missing = sorted(required - value.keys())
    if missing:
        raise AssertionError(
            "필수 필드 누락: " + ", ".join(missing)
        )
    items = value["items"]
    if not isinstance(items, list):
        raise AssertionError("items가 배열이 아닙니다.")
    if value["totalWorkOrders"] != len(items):
        raise AssertionError("totalWorkOrders와 items 수가 다릅니다.")

    valid_clearances = {
        "PENDING_INSPECTION",
        "CLEARED",
        "GROUNDED",
    }
    valid_closures = {
        "RESPONSE_ACTIVE",
        "WORK_ORDER_PENDING",
        "RETURN_TO_SERVICE_CONFIRMED",
        "GROUNDED_CONFIRMED",
        "REVIEW_REQUIRED",
    }
    for item in items:
        if item.get("flightClearanceStatus") not in valid_clearances:
            raise AssertionError(
                "유효하지 않은 비행 허가 상태가 있습니다."
            )
        if item.get("closureStatus") not in valid_closures:
            raise AssertionError(
                "유효하지 않은 마감 정합성 상태가 있습니다."
            )
        if not str(item.get("closureRecommendedAction") or "").strip():
            raise AssertionError(
                "마감 정합성 권고 조치가 누락되었습니다."
            )

    connected = sum(
        1 for item in items if item.get("incidentStatus") is not None
    )
    overdue = sum(
        1 for item in items if item.get("slaStatus") == "OVERDUE"
    )
    escalated = sum(
        1 for item in items if item.get("escalated") is True
    )
    response_counts = {
        status: sum(
            1
            for item in items
            if item.get("responseStatus") == status
        )
        for status in (
            "MONITORING",
            "ESCALATION_PENDING",
            "ASSIGNMENT_REQUIRED",
            "IN_RESPONSE",
            "COMPLETED",
        )
    }
    closure_counts = {
        status: sum(
            1
            for item in items
            if item.get("closureStatus") == status
        )
        for status in valid_closures
    }
    expected = (
        ("connectedIncidents", connected),
        ("overdueWorkOrders", overdue),
        ("escalatedIncidents", escalated),
        ("monitoringWorkOrders", response_counts["MONITORING"]),
        (
            "escalationPendingIncidents",
            response_counts["ESCALATION_PENDING"],
        ),
        (
            "assignmentRequiredIncidents",
            response_counts["ASSIGNMENT_REQUIRED"],
        ),
        ("inResponseIncidents", response_counts["IN_RESPONSE"]),
        ("completedResponses", response_counts["COMPLETED"]),
        (
            "pendingWorkOrderClosures",
            closure_counts["WORK_ORDER_PENDING"],
        ),
        (
            "returnToServiceConfirmed",
            closure_counts["RETURN_TO_SERVICE_CONFIRMED"],
        ),
        (
            "groundedClosures",
            closure_counts["GROUNDED_CONFIRMED"],
        ),
        (
            "closureConsistencyAlerts",
            closure_counts["REVIEW_REQUIRED"],
        ),
    )
    for key, count in expected:
        if value[key] != count:
            raise AssertionError(
                f"{key} 집계 불일치: {value[key]} != {count}"
            )
    if sum(response_counts.values()) != len(items):
        raise AssertionError(
            "운영자 대응 상태가 없는 정비 작업이 있습니다."
        )
    return (
        f"{len(items)} work orders; {connected} linked; "
        f"{overdue} overdue; {escalated} escalated; "
        f"{response_counts['ASSIGNMENT_REQUIRED']} unassigned; "
        f"{closure_counts['WORK_ORDER_PENDING']} closure pending; "
        f"{closure_counts['REVIEW_REQUIRED']} consistency alerts"
    )


def write_reports(
    root: Path,
    status: str,
    checks: list[CheckResult],
    generated_at: str,
) -> tuple[Path, Path]:
    output_dir = (
        root
        / "artifacts"
        / "maintenance-sla-tracking-acceptance"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / (
        f"visionflow-maintenance-sla-tracking-{stamp}.json"
    )
    html_path = output_dir / (
        f"visionflow-maintenance-sla-tracking-{stamp}.html"
    )
    payload = {
        "schemaVersion": 1,
        "project": "visionflow",
        "operation": "MAINTENANCE_SLA_INCIDENT_TRACKING",
        "generatedAt": generated_at,
        "status": status,
        "checks": [asdict(check) for check in checks],
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(check.status)}</td>"
        f"<td>{html.escape(check.title)}</td>"
        f"<td>{check.duration_ms}</td>"
        f"<td>{html.escape(check.detail)}</td>"
        "</tr>"
        for check in checks
    )
    html_path.write_text(
        "<!doctype html><html lang=\"ko\"><meta charset=\"utf-8\">"
        "<title>VisionFlow Maintenance SLA Tracking</title>"
        "<style>"
        "body{font-family:Arial,sans-serif;margin:32px;color:#0f172a}"
        "table{border-collapse:collapse;width:100%}"
        "th,td{border:1px solid #cbd5e1;padding:10px;text-align:left}"
        "th{background:#f1f5f9}"
        "</style>"
        "<h1>VisionFlow Maintenance SLA Incident Tracking</h1>"
        f"<p>Status: <strong>{html.escape(status)}</strong></p>"
        "<table><thead><tr><th>Status</th><th>Check</th>"
        "<th>ms</th><th>Detail</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></html>",
        encoding="utf-8",
    )
    return json_path, html_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--backend-url",
        default="http://localhost:8080",
    )
    parser.add_argument(
        "--frontend-url",
        default="http://localhost:3000",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    backend = args.backend_url.rstrip("/")
    frontend = args.frontend_url.rstrip("/")
    backend_value: dict[str, Any] | None = None

    def backend_tracking() -> str:
        nonlocal backend_value
        status, body, _ = request(
            f"{backend}/api/maintenance/sla/incidents?windowDays=30"
        )
        if status != 200:
            raise AssertionError(f"Unexpected HTTP {status}")
        backend_value = decode_json(body)
        return validate_tracking(backend_value)

    def invalid_window() -> str:
        status, _, _ = request(
            f"{backend}/api/maintenance/sla/incidents?windowDays=0"
        )
        if status != 400:
            raise AssertionError(
                f"Expected HTTP 400, received {status}"
            )
        return "HTTP 400"

    def frontend_proxy() -> str:
        status, body, _ = request(
            f"{frontend}/api/maintenance/sla/incidents?windowDays=30"
        )
        if status != 200:
            raise AssertionError(f"Unexpected HTTP {status}")
        frontend_value = decode_json(body)
        detail = validate_tracking(frontend_value)
        if backend_value is not None:
            keys = (
                "windowDays",
                "totalWorkOrders",
                "connectedIncidents",
                "overdueWorkOrders",
                "escalatedIncidents",
                "monitoringWorkOrders",
                "escalationPendingIncidents",
                "assignmentRequiredIncidents",
                "inResponseIncidents",
                "completedResponses",
                "pendingWorkOrderClosures",
                "returnToServiceConfirmed",
                "groundedClosures",
                "closureConsistencyAlerts",
            )
            if any(
                frontend_value[key] != backend_value[key]
                for key in keys
            ):
                raise AssertionError(
                    "Backend와 Next 프록시 집계가 다릅니다."
                )
        return detail

    def frontend_marker() -> str:
        status, body, _ = request(f"{frontend}/maintenance")
        if status != 200:
            raise AssertionError(f"Unexpected HTTP {status}")
        page = body.decode("utf-8", errors="replace")
        if "data-maintenance-sla-incident-tracking" not in page:
            raise AssertionError(
                "정비 화면에 SLA Incident 추적 패널이 없습니다."
            )
        if "data-maintenance-sla-response-queue" not in page:
            raise AssertionError(
                "정비 화면에 운영자 대응 큐가 없습니다."
            )
        if "data-maintenance-sla-inline-action" not in page:
            raise AssertionError(
                "정비 화면에 인라인 대응 시작 기능이 없습니다."
            )
        if "data-maintenance-sla-inline-resolution" not in page:
            raise AssertionError(
                "정비 화면에 인라인 조치 완료 기능이 없습니다."
            )
        if "data-maintenance-sla-workorder-closure" not in page:
            raise AssertionError(
                "정비 화면에 작업 마감·비행 허가 기능이 없습니다."
            )
        if "data-maintenance-sla-closure-consistency" not in page:
            raise AssertionError(
                "정비 화면에 마감 정합성 현황이 없습니다."
            )
        return (
            "Tracking, response queue, response start and "
            "resolution/work-order closure/consistency markers present"
        )

    def operator_mutation_routes() -> str:
        paths = (
            "/api/incidents/1/assignee",
            "/api/incidents/1/status",
            "/api/maintenance/work-orders/1/complete",
        )
        for path in paths:
            status, _, _ = request(f"{frontend}{path}")
            if status not in {401, 403, 405}:
                raise AssertionError(
                    f"{path} route unavailable: HTTP {status}"
                )
        return "Incident and maintenance mutation routes present"

    print("VisionFlow maintenance SLA Incident tracking acceptance")
    print(f"Frontend: {frontend}")
    print(f"Backend : {backend}")
    print()

    checks = [
        run_check("Backend SLA Incident tracking", backend_tracking),
        run_check("Backend window validation", invalid_window),
        run_check("Next SLA Incident tracking proxy", frontend_proxy),
        run_check("Frontend tracking panel", frontend_marker),
        run_check(
            "Frontend operator mutation routes",
            operator_mutation_routes,
        ),
    ]
    ready = all(check.status == "PASS" for check in checks)
    result = (
        "MAINTENANCE_SLA_TRACKING_READY"
        if ready
        else "MAINTENANCE_SLA_TRACKING_BLOCKED"
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    json_path, html_path = write_reports(
        root,
        result,
        checks,
        generated_at,
    )
    print()
    print(f"VisionFlow maintenance SLA tracking: {result}")
    print(
        f"Checks: {sum(c.status == 'PASS' for c in checks)}/"
        f"{len(checks)} passed"
    )
    print(f"JSON report: {json_path}")
    print(f"HTML report: {html_path}")
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
