#!/usr/bin/env python3
"""Read-only acceptance checks for the VisionFlow maintenance flight gate."""

from __future__ import annotations

import argparse
import html
import json
import math
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class HttpResult:
    status_code: int
    body: str
    duration_ms: int
    error: str | None


@dataclass(frozen=True)
class Check:
    key: str
    title: str
    status: str
    detail: str
    status_code: int
    duration_ms: int


def request(uri: str, timeout_seconds: int) -> HttpResult:
    started = time.perf_counter()
    request_object = urllib.request.Request(
        uri,
        method="GET",
        headers={
            "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
            "User-Agent": "VisionFlow-Maintenance-Acceptance/1.0",
        },
    )
    try:
        with urllib.request.urlopen(
            request_object,
            timeout=timeout_seconds,
        ) as response:
            body = response.read().decode("utf-8", errors="replace")
            return HttpResult(
                int(response.status),
                body,
                round((time.perf_counter() - started) * 1000),
                None,
            )
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        return HttpResult(
            int(error.code),
            body,
            round((time.perf_counter() - started) * 1000),
            str(error),
        )
    except Exception as error:  # noqa: BLE001 - CLI boundary
        return HttpResult(
            0,
            "",
            round((time.perf_counter() - started) * 1000),
            str(error),
        )


def parse_json(result: HttpResult) -> Any | None:
    if not result.body.strip():
        return None
    try:
        return json.loads(result.body)
    except json.JSONDecodeError:
        return None


def unwrap(value: Any) -> Any:
    if isinstance(value, dict) and "data" in value:
        return value["data"]
    return value


def integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def nullable_non_negative_integer(value: Any) -> bool:
    return value is None or (integer(value) and value >= 0)


def valid_clearance(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and integer(value.get("droneId"))
        and value.get("mode") in {"OFF", "ADVISORY", "ENFORCED"}
        and isinstance(value.get("enforced"), bool)
        and isinstance(value.get("flightAllowed"), bool)
        and isinstance(value.get("attentionRequired"), bool)
        and (
            value.get("workOrderId") is None
            or integer(value.get("workOrderId"))
        )
        and isinstance(value.get("reason"), str)
    )


def valid_fleet(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    counts = (
        value.get("totalDrones"),
        value.get("allowedDrones"),
        value.get("attentionDrones"),
        value.get("blockedDrones"),
    )
    clearances = value.get("clearances")
    return (
        value.get("mode") in {"OFF", "ADVISORY", "ENFORCED"}
        and isinstance(value.get("enforced"), bool)
        and all(integer(count) and count >= 0 for count in counts)
        and isinstance(value.get("evaluatedAt"), str)
        and isinstance(clearances, list)
        and all(valid_clearance(item) for item in clearances)
        and len(clearances) == value["totalDrones"]
        and value["allowedDrones"] + value["blockedDrones"]
        == value["totalDrones"]
        and sum(item["flightAllowed"] for item in clearances)
        == value["allowedDrones"]
        and sum(not item["flightAllowed"] for item in clearances)
        == value["blockedDrones"]
        and sum(item["attentionRequired"] for item in clearances)
        == value["attentionDrones"]
        and all(
            item["mode"] == value["mode"]
            and item["enforced"] == value["enforced"]
            for item in clearances
        )
        and len({item["droneId"] for item in clearances})
        == len(clearances)
    )


def valid_metrics(value: Any, expected_window_days: int) -> bool:
    if not isinstance(value, dict):
        return False
    work_order_counts = (
        value.get("totalWorkOrders"),
        value.get("openWorkOrders"),
        value.get("inProgressWorkOrders"),
        value.get("completedWorkOrders"),
        value.get("groundedWorkOrders"),
        value.get("resolvedWorkOrders"),
    )
    fleet_counts = (
        value.get("totalDrones"),
        value.get("allowedDrones"),
        value.get("attentionDrones"),
        value.get("blockedDrones"),
    )
    return (
        value.get("windowDays") == expected_window_days
        and isinstance(value.get("windowStartedAt"), str)
        and isinstance(value.get("generatedAt"), str)
        and all(
            integer(count) and count >= 0
            for count in (*work_order_counts, *fleet_counts)
        )
        and value["openWorkOrders"]
        + value["inProgressWorkOrders"]
        + value["completedWorkOrders"]
        + value["groundedWorkOrders"]
        == value["totalWorkOrders"]
        and value["completedWorkOrders"] + value["groundedWorkOrders"]
        == value["resolvedWorkOrders"]
        and number(value.get("resolutionRatePercent"))
        and 0 <= value["resolutionRatePercent"] <= 100
        and nullable_non_negative_integer(
            value.get("averageStartDelayMinutes")
        )
        and nullable_non_negative_integer(
            value.get("averageResolutionMinutes")
        )
        and value.get("gateMode") in {"OFF", "ADVISORY", "ENFORCED"}
        and isinstance(value.get("gateEnforced"), bool)
        and value["gateEnforced"] == (value["gateMode"] == "ENFORCED")
        and value["allowedDrones"] + value["blockedDrones"]
        == value["totalDrones"]
        and value["attentionDrones"] <= value["totalDrones"]
    )


def metrics_signature(value: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "windowDays",
        "totalWorkOrders",
        "openWorkOrders",
        "inProgressWorkOrders",
        "completedWorkOrders",
        "groundedWorkOrders",
        "resolvedWorkOrders",
        "resolutionRatePercent",
        "averageStartDelayMinutes",
        "averageResolutionMinutes",
        "gateMode",
        "gateEnforced",
        "totalDrones",
        "allowedDrones",
        "attentionDrones",
        "blockedDrones",
    )
    return {field: value[field] for field in fields}


def metrics_matches_fleet(
    metrics: dict[str, Any],
    fleet: dict[str, Any],
) -> bool:
    return all(
        metrics[metrics_field] == fleet[fleet_field]
        for metrics_field, fleet_field in (
            ("gateMode", "mode"),
            ("gateEnforced", "enforced"),
            ("totalDrones", "totalDrones"),
            ("allowedDrones", "allowedDrones"),
            ("attentionDrones", "attentionDrones"),
            ("blockedDrones", "blockedDrones"),
        )
    )


def valid_priority_item(value: Any) -> bool:
    valid = (
        isinstance(value, dict)
        and integer(value.get("droneId"))
        and value["droneId"] > 0
        and value.get("priority")
        in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
        and integer(value.get("riskScore"))
        and 0 <= value["riskScore"] <= 100
        and isinstance(value.get("flightAllowed"), bool)
        and isinstance(value.get("attentionRequired"), bool)
        and (
            value.get("workOrderId") is None
            or (
                integer(value.get("workOrderId"))
                and value["workOrderId"] > 0
            )
        )
        and (
            value.get("waitingMinutes") is None
            or (
                integer(value.get("waitingMinutes"))
                and value["waitingMinutes"] >= 0
            )
        )
        and isinstance(value.get("recommendedAction"), str)
        and bool(value["recommendedAction"].strip())
        and isinstance(value.get("reason"), str)
    )
    if not valid:
        return False
    sla_status = value.get("slaStatus")
    if sla_status not in {
        "ON_TRACK",
        "DUE_SOON",
        "OVERDUE",
        "NOT_APPLICABLE",
    }:
        return False
    if sla_status == "NOT_APPLICABLE":
        return (
            value.get("slaDueAt") is None
            and value.get("slaRemainingMinutes") is None
            and value.get("slaOverdueMinutes") is None
        )
    return (
        isinstance(value.get("slaDueAt"), str)
        and integer(value.get("slaRemainingMinutes"))
        and value["slaRemainingMinutes"] >= 0
        and integer(value.get("slaOverdueMinutes"))
        and value["slaOverdueMinutes"] >= 0
    )


def valid_priority_queue(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    priorities = value.get("priorities")
    counts = (
        value.get("totalDrones"),
        value.get("urgentDrones"),
        value.get("attentionDrones"),
        value.get("normalDrones"),
        value.get("overdueDrones"),
        value.get("dueSoonDrones"),
    )
    return (
        value.get("mode") in {"OFF", "ADVISORY", "ENFORCED"}
        and isinstance(value.get("enforced"), bool)
        and value["enforced"] == (value["mode"] == "ENFORCED")
        and isinstance(value.get("evaluatedAt"), str)
        and all(integer(count) and count >= 0 for count in counts)
        and isinstance(priorities, list)
        and all(valid_priority_item(item) for item in priorities)
        and len(priorities) == value["totalDrones"]
        and value["urgentDrones"]
        + value["attentionDrones"]
        + value["normalDrones"]
        == value["totalDrones"]
        and value["overdueDrones"] <= value["totalDrones"]
        and value["dueSoonDrones"] <= value["totalDrones"]
        and len({item["droneId"] for item in priorities})
        == len(priorities)
        and all(
            priorities[index]["riskScore"]
            >= priorities[index + 1]["riskScore"]
            for index in range(len(priorities) - 1)
        )
        and sum(
            item["priority"] in {"CRITICAL", "HIGH"}
            for item in priorities
        )
        == value["urgentDrones"]
        and sum(
            item["priority"] == "MEDIUM"
            for item in priorities
        )
        == value["attentionDrones"]
        and sum(
            item["priority"] == "LOW"
            for item in priorities
        )
        == value["normalDrones"]
        and sum(
            item["slaStatus"] == "OVERDUE"
            for item in priorities
        )
        == value["overdueDrones"]
        and sum(
            item["slaStatus"] == "DUE_SOON"
            for item in priorities
        )
        == value["dueSoonDrones"]
    )


def priority_signature(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": value["mode"],
        "enforced": value["enforced"],
        "totalDrones": value["totalDrones"],
        "urgentDrones": value["urgentDrones"],
        "attentionDrones": value["attentionDrones"],
        "normalDrones": value["normalDrones"],
        "overdueDrones": value["overdueDrones"],
        "dueSoonDrones": value["dueSoonDrones"],
        "priorities": [
            {
                key: item.get(key)
                for key in (
                    "droneId",
                    "priority",
                    "riskScore",
                    "flightAllowed",
                    "attentionRequired",
                    "workOrderId",
                    "workOrderStatus",
                    "clearanceStatus",
                    "openedAt",
                    "slaStatus",
                    "slaDueAt",
                    "slaRemainingMinutes",
                    "slaOverdueMinutes",
                    "recommendedAction",
                    "reason",
                )
            }
            for item in value["priorities"]
        ],
    }


def priority_matches_fleet(
    priority_queue: dict[str, Any],
    fleet: dict[str, Any],
) -> bool:
    return (
        priority_queue["mode"] == fleet["mode"]
        and priority_queue["enforced"] == fleet["enforced"]
        and priority_queue["totalDrones"] == fleet["totalDrones"]
        and {
            item["droneId"]
            for item in priority_queue["priorities"]
        }
        == {
            item["droneId"]
            for item in fleet["clearances"]
        }
    )


def valid_sla_automation(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    positive_fields = (
        value.get("openSlaMinutes"),
        value.get("inProgressSlaMinutes"),
        value.get("dueSoonMinutes"),
        value.get("initialDelayMs"),
        value.get("scanDelayMs"),
    )
    return (
        value.get("automationEnabled") is True
        and all(
            integer(item) and item > 0
            for item in positive_fields
        )
        and value["dueSoonMinutes"] <= value["openSlaMinutes"]
        and value["dueSoonMinutes"]
        <= value["inProgressSlaMinutes"]
    )


def sla_automation_signature(
    value: dict[str, Any],
) -> dict[str, Any]:
    return {
        key: value[key]
        for key in (
            "automationEnabled",
            "openSlaMinutes",
            "inProgressSlaMinutes",
            "dueSoonMinutes",
            "initialDelayMs",
            "scanDelayMs",
        )
    }


def has_maintenance_kpi_content(body: str) -> bool:
    return any(
        marker in body
        for marker in (
            "정비 운영 KPI를 집계하고 있습니다.",
            "정비 운영 현황",
            "Maintenance KPI",
            'data-visionflow-maintenance-kpi="ready"',
        )
    )


def has_maintenance_priority_content(body: str) -> bool:
    return any(
        marker in body
        for marker in (
            "드론별 정비 우선순위를 계산하고 있습니다.",
            "정비 우선조치 큐",
            "Maintenance Priority Queue",
        )
    )


def has_team_copyright(body: str) -> bool:
    return (
        "© 2026 Team PyvaOps." in body
        and "All rights reserved." in body
    )


def has_sla_automation_content(body: str) -> bool:
    return (
        "SLA 자동 Incident 상향" in body
        or "data-maintenance-sla-automation" in body
    )


def fleet_signature(value: dict[str, Any]) -> dict[str, Any]:
    clearances = sorted(
        (
            {
                "droneId": item["droneId"],
                "mode": item["mode"],
                "enforced": item["enforced"],
                "flightAllowed": item["flightAllowed"],
                "attentionRequired": item["attentionRequired"],
                "workOrderId": item.get("workOrderId"),
                "clearanceStatus": item.get("clearanceStatus"),
            }
            for item in value["clearances"]
        ),
        key=lambda item: item["droneId"],
    )
    return {
        "mode": value["mode"],
        "enforced": value["enforced"],
        "totalDrones": value["totalDrones"],
        "allowedDrones": value["allowedDrones"],
        "attentionDrones": value["attentionDrones"],
        "blockedDrones": value["blockedDrones"],
        "clearances": clearances,
    }


def clearance_signature(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "droneId": value["droneId"],
        "mode": value["mode"],
        "enforced": value["enforced"],
        "flightAllowed": value["flightAllowed"],
        "attentionRequired": value["attentionRequired"],
        "workOrderId": value.get("workOrderId"),
        "clearanceStatus": value.get("clearanceStatus"),
    }


def add_http_check(
    checks: list[Check],
    key: str,
    title: str,
    result: HttpResult,
    expected_status: int = 200,
) -> bool:
    passed = result.status_code == expected_status
    detail = (
        f"HTTP {result.status_code}"
        if passed
        else result.error or f"Unexpected HTTP {result.status_code}"
    )
    checks.append(
        Check(
            key,
            title,
            "PASS" if passed else "FAILED",
            detail,
            result.status_code,
            result.duration_ms,
        )
    )
    return passed


def add_schema_check(
    checks: list[Check],
    key: str,
    title: str,
    result: HttpResult,
    passed: bool,
    success_detail: str,
    failure_detail: str,
) -> None:
    checks.append(
        Check(
            key,
            title,
            "PASS" if passed else "FAILED",
            success_detail if passed else failure_detail,
            result.status_code,
            result.duration_ms,
        )
    )


def valid_detail(
    value: Any,
    expected_order_id: int,
    expected_drone_id: int,
) -> bool:
    if not isinstance(value, dict):
        return False
    work_order = value.get("workOrder")
    history = value.get("history")
    if (
        not isinstance(work_order, dict)
        or work_order.get("id") != expected_order_id
        or work_order.get("droneId") != expected_drone_id
        or not isinstance(history, list)
    ):
        return False
    actions = {
        "CREATED",
        "RISK_SYNCHRONIZED",
        "REOPENED",
        "INSPECTION_STARTED",
        "RETURNED_TO_SERVICE",
        "GROUNDED",
    }
    return all(
        isinstance(item, dict)
        and integer(item.get("id"))
        and item.get("actionType") in actions
        and isinstance(item.get("actor"), str)
        and isinstance(item.get("createdAt"), str)
        for item in history
    )


def html_report(report: dict[str, Any]) -> str:
    rows = []
    for check in report["checks"]:
        color = "#047857" if check["status"] == "PASS" else "#b91c1c"
        rows.append(
            "<tr>"
            f"<td>{html.escape(check['title'])}</td>"
            f"<td style=\"font-weight:700;color:{color}\">"
            f"{html.escape(check['status'])}</td>"
            f"<td>{check['status_code']}</td>"
            f"<td>{check['duration_ms']} ms</td>"
            f"<td>{html.escape(check['detail'])}</td>"
            "</tr>"
        )
    summary = report["summary"]
    evidence = report["evidence"]
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VisionFlow Maintenance Acceptance</title>
  <style>
    body {{ font-family: Segoe UI, sans-serif; margin: 32px; color: #0f172a; }}
    .card {{ border: 1px solid #cbd5e1; border-radius: 14px; padding: 20px; margin-bottom: 18px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #e2e8f0; padding: 10px; text-align: left; vertical-align: top; }}
    th {{ background: #f8fafc; }}
    code {{ background: #f1f5f9; padding: 2px 5px; border-radius: 4px; }}
  </style>
</head>
<body>
  <h1>VisionFlow 정비 비행 게이트 인수 테스트</h1>
  <div class="card">
    <p><strong>결과:</strong> {html.escape(report['status'])}</p>
    <p><strong>검사:</strong> {summary['passed']}/{summary['total']} PASS</p>
    <p><strong>드론:</strong> #{evidence['droneId']}</p>
    <p><strong>게이트 모드:</strong> {html.escape(str(evidence.get('mode') or '-'))}</p>
    <p><strong>연결 작업:</strong> {html.escape(str(evidence.get('workOrderId') or '-'))}</p>
    <p><strong>KPI 기간:</strong> {html.escape(str(evidence.get('metricsWindowDays') or '-'))}일</p>
    <p><strong>KPI 작업:</strong> {html.escape(str(evidence.get('metricsTotalWorkOrders') or 0))}건</p>
    <p><strong>KPI 처리율:</strong> {html.escape(str(evidence.get('metricsResolutionRatePercent') or 0))}%</p>
    <p><strong>정비 긴급·높음:</strong> {html.escape(str(evidence.get('priorityUrgentDrones') or 0))}대</p>
    <p><strong>정비 주의:</strong> {html.escape(str(evidence.get('priorityAttentionDrones') or 0))}대</p>
    <p><strong>SLA 초과:</strong> {html.escape(str(evidence.get('priorityOverdueDrones') or 0))}대</p>
    <p><strong>SLA 임박:</strong> {html.escape(str(evidence.get('priorityDueSoonDrones') or 0))}대</p>
    <p><strong>SLA 자동 에스컬레이션:</strong> {html.escape(str(evidence.get('slaAutomationEnabled')))}</p>
    <p><strong>SLA 검색 간격:</strong> {html.escape(str(evidence.get('slaScanDelayMs') or 0))}ms</p>
    <p><strong>안전:</strong> 읽기 전용, DB 변경 없음</p>
  </div>
  <table>
    <thead><tr><th>검사</th><th>상태</th><th>HTTP</th><th>시간</th><th>상세</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</body>
</html>
"""


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="VisionFlow maintenance flight-gate acceptance",
    )
    result.add_argument(
        "-FrontendUrl",
        "--frontend-url",
        default="http://localhost:3000",
    )
    result.add_argument(
        "-BackendUrl",
        "--backend-url",
        default="http://localhost:8080",
    )
    result.add_argument("-DroneId", "--drone-id", type=int, default=1)
    result.add_argument(
        "-MetricsWindowDays",
        "--metrics-window-days",
        type=int,
        default=30,
    )
    result.add_argument(
        "-TimeoutSeconds",
        "--timeout-seconds",
        type=int,
        default=10,
    )
    result.add_argument(
        "-RequireMode",
        "--require-mode",
        choices=("OFF", "ADVISORY", "ENFORCED"),
    )
    result.add_argument(
        "-OutputDirectory",
        "--output-directory",
        default="artifacts/maintenance-acceptance",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    if args.drone_id < 1:
        raise SystemExit("DroneId must be at least 1.")
    if not 1 <= args.metrics_window_days <= 365:
        raise SystemExit("MetricsWindowDays must be between 1 and 365.")
    if not 1 <= args.timeout_seconds <= 120:
        raise SystemExit("TimeoutSeconds must be between 1 and 120.")

    frontend = args.frontend_url.rstrip("/")
    backend = args.backend_url.rstrip("/")
    checks: list[Check] = []
    evidence: dict[str, Any] = {
        "droneId": args.drone_id,
        "mode": None,
        "flightAllowed": None,
        "attentionRequired": None,
        "workOrderId": None,
        "historyCount": None,
        "metricsWindowDays": args.metrics_window_days,
        "metricsTotalWorkOrders": None,
        "metricsResolutionRatePercent": None,
        "priorityUrgentDrones": None,
        "priorityAttentionDrones": None,
        "priorityOverdueDrones": None,
        "priorityDueSoonDrones": None,
        "slaAutomationEnabled": None,
        "slaScanDelayMs": None,
    }

    print("VisionFlow maintenance flight-gate acceptance")
    print(f"Frontend: {frontend}")
    print(f"Backend : {backend}")
    print(f"Drone   : {args.drone_id}")
    print("")

    health = request(f"{backend}/api/health", args.timeout_seconds)
    add_http_check(checks, "backend-health", "Backend health", health)

    backend_fleet_result = request(
        f"{backend}/api/maintenance/flight-clearance",
        args.timeout_seconds,
    )
    backend_fleet = unwrap(parse_json(backend_fleet_result))
    backend_fleet_valid = (
        backend_fleet_result.status_code == 200 and valid_fleet(backend_fleet)
    )
    add_schema_check(
        checks,
        "backend-fleet-clearance",
        "Backend fleet clearance",
        backend_fleet_result,
        backend_fleet_valid,
        (
            f"{backend_fleet['totalDrones']} drones; "
            f"{backend_fleet['allowedDrones']} allowed; "
            f"{backend_fleet['blockedDrones']} blocked"
            if backend_fleet_valid
            else ""
        ),
        "Expected a valid fleet clearance response",
    )

    frontend_fleet_result = request(
        f"{frontend}/api/maintenance/flight-clearance",
        args.timeout_seconds,
    )
    frontend_fleet = unwrap(parse_json(frontend_fleet_result))
    frontend_fleet_valid = (
        frontend_fleet_result.status_code == 200
        and valid_fleet(frontend_fleet)
    )
    fleet_consistent = (
        backend_fleet_valid
        and frontend_fleet_valid
        and fleet_signature(backend_fleet) == fleet_signature(frontend_fleet)
    )
    add_schema_check(
        checks,
        "frontend-fleet-proxy",
        "Next fleet clearance proxy",
        frontend_fleet_result,
        fleet_consistent,
        "Backend and Next proxy fleet state are consistent",
        "Fleet response is invalid or differs from backend",
    )

    priority_path = "/api/maintenance/priorities"
    backend_priority_result = request(
        f"{backend}{priority_path}",
        args.timeout_seconds,
    )
    backend_priority = unwrap(parse_json(backend_priority_result))
    backend_priority_valid = (
        backend_priority_result.status_code == 200
        and valid_priority_queue(backend_priority)
        and backend_fleet_valid
        and priority_matches_fleet(backend_priority, backend_fleet)
    )
    if backend_priority_valid:
        evidence.update(
            {
                "priorityUrgentDrones":
                    backend_priority["urgentDrones"],
                "priorityAttentionDrones":
                    backend_priority["attentionDrones"],
                "priorityOverdueDrones":
                    backend_priority["overdueDrones"],
                "priorityDueSoonDrones":
                    backend_priority["dueSoonDrones"],
            }
        )
    add_schema_check(
        checks,
        "backend-maintenance-priorities",
        "Backend maintenance priority queue",
        backend_priority_result,
        backend_priority_valid,
        (
            f"{backend_priority['totalDrones']} drones; "
            f"{backend_priority['urgentDrones']} urgent; "
            f"{backend_priority['attentionDrones']} attention; "
            f"{backend_priority['overdueDrones']} SLA overdue"
            if backend_priority_valid
            else ""
        ),
        "Expected a sorted priority queue consistent with fleet clearance",
    )

    frontend_priority_result = request(
        f"{frontend}{priority_path}",
        args.timeout_seconds,
    )
    frontend_priority = unwrap(parse_json(frontend_priority_result))
    frontend_priority_valid = (
        frontend_priority_result.status_code == 200
        and valid_priority_queue(frontend_priority)
        and backend_priority_valid
        and priority_signature(frontend_priority)
        == priority_signature(backend_priority)
    )
    add_schema_check(
        checks,
        "frontend-maintenance-priorities-proxy",
        "Next maintenance priority queue proxy",
        frontend_priority_result,
        frontend_priority_valid,
        "Backend and Next proxy priority queues are consistent",
        "Priority proxy response is invalid or differs from backend",
    )

    sla_path = "/api/maintenance/sla"
    backend_sla_result = request(
        f"{backend}{sla_path}",
        args.timeout_seconds,
    )
    backend_sla = unwrap(parse_json(backend_sla_result))
    backend_sla_valid = (
        backend_sla_result.status_code == 200
        and valid_sla_automation(backend_sla)
    )
    if backend_sla_valid:
        evidence.update(
            {
                "slaAutomationEnabled":
                    backend_sla["automationEnabled"],
                "slaScanDelayMs": backend_sla["scanDelayMs"],
            }
        )
    add_schema_check(
        checks,
        "backend-maintenance-sla-automation",
        "Backend maintenance SLA automation",
        backend_sla_result,
        backend_sla_valid,
        (
            "Automation "
            + ("ON" if backend_sla["automationEnabled"] else "OFF")
            + f"; scan {backend_sla['scanDelayMs']} ms"
            if backend_sla_valid
            else ""
        ),
        "Expected a valid maintenance SLA automation status",
    )

    frontend_sla_result = request(
        f"{frontend}{sla_path}",
        args.timeout_seconds,
    )
    frontend_sla = unwrap(parse_json(frontend_sla_result))
    frontend_sla_valid = (
        frontend_sla_result.status_code == 200
        and valid_sla_automation(frontend_sla)
        and backend_sla_valid
        and sla_automation_signature(frontend_sla)
        == sla_automation_signature(backend_sla)
    )
    add_schema_check(
        checks,
        "frontend-maintenance-sla-automation-proxy",
        "Next maintenance SLA automation proxy",
        frontend_sla_result,
        frontend_sla_valid,
        "Backend and Next proxy SLA settings are consistent",
        "SLA automation proxy response is invalid or differs from backend",
    )

    metrics_path = (
        "/api/maintenance/metrics"
        f"?windowDays={args.metrics_window_days}"
    )
    backend_metrics_result = request(
        f"{backend}{metrics_path}",
        args.timeout_seconds,
    )
    backend_metrics = unwrap(parse_json(backend_metrics_result))
    backend_metrics_valid = (
        backend_metrics_result.status_code == 200
        and valid_metrics(backend_metrics, args.metrics_window_days)
        and backend_fleet_valid
        and metrics_matches_fleet(backend_metrics, backend_fleet)
    )
    if backend_metrics_valid:
        evidence.update(
            {
                "metricsTotalWorkOrders":
                    backend_metrics["totalWorkOrders"],
                "metricsResolutionRatePercent":
                    backend_metrics["resolutionRatePercent"],
            }
        )
    add_schema_check(
        checks,
        "backend-maintenance-metrics",
        "Backend maintenance KPI",
        backend_metrics_result,
        backend_metrics_valid,
        (
            f"{backend_metrics['totalWorkOrders']} work orders; "
            f"{backend_metrics['resolutionRatePercent']}% resolved"
            if backend_metrics_valid
            else ""
        ),
        "Expected valid KPI totals consistent with fleet clearance",
    )

    frontend_metrics_result = request(
        f"{frontend}{metrics_path}",
        args.timeout_seconds,
    )
    frontend_metrics = unwrap(parse_json(frontend_metrics_result))
    frontend_metrics_valid = (
        frontend_metrics_result.status_code == 200
        and valid_metrics(frontend_metrics, args.metrics_window_days)
        and backend_metrics_valid
        and metrics_signature(frontend_metrics)
        == metrics_signature(backend_metrics)
    )
    add_schema_check(
        checks,
        "frontend-maintenance-metrics-proxy",
        "Next maintenance KPI proxy",
        frontend_metrics_result,
        frontend_metrics_valid,
        "Backend and Next proxy KPI values are consistent",
        "KPI proxy response is invalid or differs from backend",
    )

    backend_invalid_metrics_result = request(
        f"{backend}/api/maintenance/metrics?windowDays=0",
        args.timeout_seconds,
    )
    add_http_check(
        checks,
        "backend-maintenance-metrics-window-validation",
        "Backend maintenance KPI window validation",
        backend_invalid_metrics_result,
        expected_status=400,
    )

    frontend_invalid_metrics_result = request(
        f"{frontend}/api/maintenance/metrics?windowDays=0",
        args.timeout_seconds,
    )
    add_http_check(
        checks,
        "frontend-maintenance-metrics-window-validation",
        "Next maintenance KPI window validation",
        frontend_invalid_metrics_result,
        expected_status=400,
    )

    frontend_pages: dict[str, HttpResult] = {}
    for key, title, path in (
        ("frontend-drones", "Frontend drone control", "/drones"),
        ("frontend-maintenance", "Frontend maintenance", "/maintenance"),
        ("frontend-demo", "Frontend demo console", "/demo-scenario"),
    ):
        result = request(f"{frontend}{path}", args.timeout_seconds)
        frontend_pages[path] = result
        add_http_check(checks, key, title, result)

    maintenance_page = frontend_pages["/maintenance"]
    add_schema_check(
        checks,
        "frontend-maintenance-kpi-content",
        "Frontend maintenance KPI content",
        maintenance_page,
        (
            maintenance_page.status_code == 200
            and has_maintenance_kpi_content(maintenance_page.body)
        ),
        "Maintenance KPI component is present in the server render",
        "Maintenance page is missing the KPI component marker",
    )
    add_schema_check(
        checks,
        "frontend-maintenance-priority-content",
        "Frontend maintenance priority content",
        maintenance_page,
        (
            maintenance_page.status_code == 200
            and has_maintenance_priority_content(maintenance_page.body)
        ),
        "Maintenance priority component is present in the server render",
        "Maintenance page is missing the priority component marker",
    )
    add_schema_check(
        checks,
        "frontend-team-copyright",
        "Frontend Team PyvaOps copyright",
        maintenance_page,
        (
            maintenance_page.status_code == 200
            and has_team_copyright(maintenance_page.body)
        ),
        "Team PyvaOps copyright is present in the shared layout",
        "Shared layout is missing the Team PyvaOps copyright",
    )
    add_schema_check(
        checks,
        "frontend-maintenance-sla-automation-content",
        "Frontend maintenance SLA automation content",
        maintenance_page,
        (
            maintenance_page.status_code == 200
            and has_sla_automation_content(maintenance_page.body)
        ),
        "Maintenance SLA automation marker is present",
        "Maintenance page is missing the SLA automation marker",
    )

    backend_single_result = request(
        f"{backend}/api/maintenance/flight-clearance/{args.drone_id}",
        args.timeout_seconds,
    )
    backend_single = unwrap(parse_json(backend_single_result))
    backend_single_valid = (
        backend_single_result.status_code == 200
        and valid_clearance(backend_single)
        and backend_single["droneId"] == args.drone_id
    )
    if backend_single_valid:
        evidence.update(
            {
                "mode": backend_single["mode"],
                "flightAllowed": backend_single["flightAllowed"],
                "attentionRequired": backend_single["attentionRequired"],
                "workOrderId": backend_single.get("workOrderId"),
            }
        )
    fleet_item = None
    if backend_fleet_valid:
        fleet_item = next(
            (
                item
                for item in backend_fleet["clearances"]
                if item["droneId"] == args.drone_id
            ),
            None,
        )
    single_matches_fleet = (
        backend_single_valid
        and fleet_item is not None
        and clearance_signature(backend_single)
        == clearance_signature(fleet_item)
    )
    add_schema_check(
        checks,
        "backend-drone-clearance",
        "Backend selected drone clearance",
        backend_single_result,
        single_matches_fleet,
        (
            f"Mode {backend_single['mode']}; "
            f"allowed={backend_single['flightAllowed']}; "
            f"attention={backend_single['attentionRequired']}"
            if backend_single_valid
            else ""
        ),
        "Selected drone clearance is invalid or absent from fleet response",
    )

    frontend_single_result = request(
        f"{frontend}/api/maintenance/flight-clearance/{args.drone_id}",
        args.timeout_seconds,
    )
    frontend_single = unwrap(parse_json(frontend_single_result))
    frontend_single_valid = (
        frontend_single_result.status_code == 200
        and valid_clearance(frontend_single)
        and backend_single_valid
        and clearance_signature(frontend_single)
        == clearance_signature(backend_single)
    )
    add_schema_check(
        checks,
        "frontend-drone-proxy",
        "Next selected drone clearance proxy",
        frontend_single_result,
        frontend_single_valid,
        "Backend and Next proxy selected-drone state are consistent",
        "Selected-drone proxy response is invalid or differs from backend",
    )

    mode_matches = (
        args.require_mode is None
        or (
            backend_single_valid
            and backend_single["mode"] == args.require_mode
        )
    )
    checks.append(
        Check(
            "required-mode",
            "Required flight-gate mode",
            "PASS" if mode_matches else "FAILED",
            (
                f"Mode {evidence['mode']}"
                if args.require_mode is None
                else f"Expected and received {args.require_mode}"
                if mode_matches
                else f"Expected {args.require_mode}; received {evidence['mode']}"
            ),
            200 if backend_single_valid else backend_single_result.status_code,
            0,
        )
    )

    work_order_id = evidence["workOrderId"]
    if integer(work_order_id):
        backend_detail_result = request(
            f"{backend}/api/maintenance/work-orders/{work_order_id}",
            args.timeout_seconds,
        )
        backend_detail = unwrap(parse_json(backend_detail_result))
        backend_detail_valid = (
            backend_detail_result.status_code == 200
            and valid_detail(
                backend_detail,
                work_order_id,
                args.drone_id,
            )
        )
        if backend_detail_valid:
            evidence["historyCount"] = len(backend_detail["history"])
        add_schema_check(
            checks,
            "backend-work-order-evidence",
            "Backend work-order evidence",
            backend_detail_result,
            backend_detail_valid,
            f"Work order #{work_order_id}; {evidence['historyCount']} history entries",
            "Expected a valid work order and processing history",
        )

        frontend_detail_result = request(
            f"{frontend}/api/maintenance/work-orders/{work_order_id}",
            args.timeout_seconds,
        )
        frontend_detail = unwrap(parse_json(frontend_detail_result))
        frontend_detail_valid = (
            frontend_detail_result.status_code == 200
            and valid_detail(
                frontend_detail,
                work_order_id,
                args.drone_id,
            )
            and backend_detail_valid
            and frontend_detail == backend_detail
        )
        add_schema_check(
            checks,
            "frontend-work-order-evidence",
            "Next work-order evidence proxy",
            frontend_detail_result,
            frontend_detail_valid,
            "Backend and Next proxy work-order evidence are consistent",
            "Work-order proxy response is invalid or differs from backend",
        )
    else:
        for key, title in (
            (
                "backend-work-order-evidence",
                "Backend work-order evidence",
            ),
            (
                "frontend-work-order-evidence",
                "Next work-order evidence proxy",
            ),
        ):
            checks.append(
                Check(
                    key,
                    title,
                    "PASS",
                    "No linked work order; evidence detail is not applicable",
                    200,
                    0,
                )
            )

    for check in checks:
        color = "\033[32m" if check.status == "PASS" else "\033[31m"
        reset = "\033[0m"
        print(
            f"{color}[{check.status}]{reset} {check.title} "
            f"({check.duration_ms} ms) - {check.detail}"
        )

    failed = [check for check in checks if check.status != "PASS"]
    status = (
        "MAINTENANCE_GATE_READY"
        if not failed
        else "MAINTENANCE_GATE_BLOCKED"
    )
    generated_at = datetime.now(timezone.utc)
    report = {
        "schemaVersion": 1,
        "project": "visionflow",
        "operation": "MAINTENANCE_FLIGHT_GATE_ACCEPTANCE",
        "generatedAt": generated_at.isoformat(),
        "status": status,
        "inputs": {
            "frontendUrl": frontend,
            "backendUrl": backend,
            "droneId": args.drone_id,
            "metricsWindowDays": args.metrics_window_days,
            "requiredMode": args.require_mode,
            "timeoutSeconds": args.timeout_seconds,
        },
        "summary": {
            "total": len(checks),
            "passed": len(checks) - len(failed),
            "failed": len(failed),
        },
        "evidence": evidence,
        "checks": [asdict(check) for check in checks],
        "safety": {
            "readOnly": True,
            "httpMethods": ["GET"],
            "databaseMutation": False,
            "operatorKeysRecorded": False,
        },
    }

    output_directory = Path(args.output_directory).resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    stamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
    json_path = output_directory / (
        f"visionflow-maintenance-acceptance-{stamp}.json"
    )
    html_path = output_directory / (
        f"visionflow-maintenance-acceptance-{stamp}.html"
    )
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    html_path.write_text(html_report(report), encoding="utf-8")

    print("")
    print(f"VisionFlow maintenance acceptance: {status}")
    print(f"Checks: {report['summary']['passed']}/{report['summary']['total']} passed")
    print(f"JSON report: {json_path}")
    print(f"HTML report: {html_path}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
