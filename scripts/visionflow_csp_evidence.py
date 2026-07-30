#!/usr/bin/env python3
"""Collect a bounded VisionFlow CSP Report-Only snapshot as release evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import sys
import tempfile
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_URL = "http://localhost:3000/api/security/csp-report"
DEFAULT_OUTPUT_DIRECTORY = Path("artifacts/csp-observability")
URL_FIELDS = ("documentUri", "blockedUri", "sourceFile")
TEXT_FIELDS = (
    "documentUri",
    "blockedUri",
    "effectiveDirective",
    "violatedDirective",
    "disposition",
    "sourceFile",
    "receivedAt",
)
NUMBER_FIELDS = ("lineNumber", "columnNumber", "statusCode")


class EvidenceError(RuntimeError):
    """Raised when CSP evidence cannot be trusted."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def read_status(url: str, timeout_seconds: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "User-Agent": "VisionFlow-CSP-Evidence/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status_code = getattr(response, "status", 200)
            body = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise EvidenceError(f"CSP 관찰 API에 연결할 수 없습니다: {error}") from error
    if status_code != 200:
        raise EvidenceError(f"CSP 관찰 API가 HTTP {status_code}를 반환했습니다.")
    try:
        value = json.loads(body)
    except json.JSONDecodeError as error:
        raise EvidenceError("CSP 관찰 API 응답이 올바른 JSON이 아닙니다.") from error
    if not isinstance(value, dict):
        raise EvidenceError("CSP 관찰 API 응답 루트는 JSON 객체여야 합니다.")
    return value


def read_input_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvidenceError(f"입력 JSON을 읽을 수 없습니다: {path}") from error
    if not isinstance(value, dict):
        raise EvidenceError("입력 JSON 루트는 객체여야 합니다.")
    return value


def require_int(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise EvidenceError(f"{name} 값이 올바른 정수가 아닙니다.")
    return value


def optional_text(value: Any, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise EvidenceError(f"{name} 값은 문자열 또는 null이어야 합니다.")
    if len(value) > 512:
        raise EvidenceError(f"{name} 값이 512자를 초과했습니다.")
    return value


def optional_number(value: Any, name: str) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError(f"{name} 값은 숫자 또는 null이어야 합니다.")
    return value


def validate_url_privacy(value: str | None, name: str) -> None:
    if value is not None and ("?" in value or "#" in value):
        raise EvidenceError(f"{name}에 제거되지 않은 쿼리 또는 fragment가 있습니다.")


def normalize_report(value: Any, index: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(f"reports[{index}]는 객체여야 합니다.")
    report: dict[str, Any] = {}
    for field in TEXT_FIELDS:
        report[field] = optional_text(value.get(field), f"reports[{index}].{field}")
    for field in NUMBER_FIELDS:
        report[field] = optional_number(value.get(field), f"reports[{index}].{field}")
    if not report["receivedAt"]:
        raise EvidenceError(f"reports[{index}].receivedAt이 비어 있습니다.")
    for field in URL_FIELDS:
        validate_url_privacy(report[field], f"reports[{index}].{field}")
    return report


def normalize_status(value: dict[str, Any]) -> dict[str, Any]:
    if value.get("enabled") is not True:
        raise EvidenceError("CSP Report-Only 수신기가 활성화되어 있지 않습니다.")
    if value.get("mode") != "REPORT_ONLY":
        raise EvidenceError("CSP 모드가 REPORT_ONLY가 아닙니다.")
    if value.get("persisted") is not False:
        raise EvidenceError("CSP 보고서가 비영속 모드가 아닙니다.")
    if value.get("storage") != "BOUNDED_PROCESS_MEMORY":
        raise EvidenceError("CSP 저장 방식이 제한된 프로세스 메모리가 아닙니다.")

    max_retained = require_int(value.get("maxRetainedReports"), "maxRetainedReports", minimum=1)
    total = require_int(value.get("totalReports"), "totalReports")
    retained = require_int(value.get("retainedReports"), "retainedReports")
    raw_reports = value.get("reports")
    if not isinstance(raw_reports, list):
        raise EvidenceError("reports 값은 배열이어야 합니다.")
    reports = [normalize_report(report, index) for index, report in enumerate(raw_reports)]
    if retained != len(reports):
        raise EvidenceError("retainedReports와 실제 reports 배열 길이가 다릅니다.")
    if retained > max_retained:
        raise EvidenceError("보관 보고서 수가 설정된 최대 한도를 초과했습니다.")
    if total < retained:
        raise EvidenceError("전체 수신 건수가 현재 보관 건수보다 작습니다.")

    started_at = optional_text(value.get("startedAt"), "startedAt")
    last_received_at = optional_text(value.get("lastReceivedAt"), "lastReceivedAt")
    max_report_bytes = require_int(value.get("maxReportBytes"), "maxReportBytes", minimum=1)
    directive_counts = Counter(
        report["effectiveDirective"] or "unknown" for report in reports
    )
    return {
        "enabled": True,
        "mode": "REPORT_ONLY",
        "persisted": False,
        "storage": "BOUNDED_PROCESS_MEMORY",
        "maxReportBytes": max_report_bytes,
        "maxRetainedReports": max_retained,
        "startedAt": started_at,
        "totalReports": total,
        "retainedReports": retained,
        "lastReceivedAt": last_received_at,
        "byDirective": [
            {"directive": directive, "count": count}
            for directive, count in sorted(
                directive_counts.items(), key=lambda item: (-item[1], item[0])
            )
        ],
        "reports": reports,
    }


def csv_safe(value: Any) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@")):
        return f"'{text}"
    return text


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        delete=False,
    ) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def render_csv(reports: list[dict[str, Any]]) -> str:
    from io import StringIO

    output = StringIO(newline="")
    fields = [*TEXT_FIELDS, *NUMBER_FIELDS]
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for report in reports:
        writer.writerow({field: csv_safe(report.get(field)) for field in fields})
    return output.getvalue()


def render_html(evidence: dict[str, Any]) -> str:
    summary = evidence["summary"]
    rows = []
    for report in evidence["observation"]["reports"]:
        rows.append(
            "<tr>"
            f"<td>{html.escape(report['receivedAt'] or '')}</td>"
            f"<td>{html.escape(report['effectiveDirective'] or 'unknown')}</td>"
            f"<td>{html.escape(report['blockedUri'] or '')}</td>"
            f"<td>{html.escape(report['sourceFile'] or report['documentUri'] or '')}</td>"
            "</tr>"
        )
    table_body = "".join(rows) or '<tr><td colspan="4">수신된 위반이 없습니다.</td></tr>'
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VisionFlow CSP 관찰 증적</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #0f172a; }}
    .status {{ display: inline-block; padding: 8px 12px; border-radius: 999px; background: #fef3c7; font-weight: 700; }}
    .grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 20px 0; }}
    .card {{ border: 1px solid #cbd5e1; border-radius: 12px; padding: 16px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
    th, td {{ border: 1px solid #cbd5e1; padding: 8px; text-align: left; font-size: 13px; word-break: break-all; }}
    th {{ background: #f1f5f9; }}
    .note {{ margin-top: 20px; color: #475569; }}
  </style>
</head>
<body>
  <p>VISIONFLOW SECURITY EVIDENCE</p>
  <h1>CSP Report-Only 관찰 증적</h1>
  <span class="status">{html.escape(evidence['status'])}</span>
  <div class="grid">
    <div class="card"><strong>전체 수신</strong><br>{summary['totalReports']}건</div>
    <div class="card"><strong>현재 보관</strong><br>{summary['retainedReports']}건</div>
    <div class="card"><strong>마지막 수신</strong><br>{html.escape(summary['lastReceivedAt'] or '없음')}</div>
  </div>
  <table>
    <thead><tr><th>수신 시각</th><th>지시문</th><th>차단 후보</th><th>발생 위치</th></tr></thead>
    <tbody>{table_body}</tbody>
  </table>
  <p class="note">Report-Only 결과이므로 위반 건수는 기능 차단을 뜻하지 않습니다. URL 쿼리 문자열과 인증정보는 포함하지 않습니다.</p>
</body>
</html>
"""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_evidence(
    observation: dict[str, Any], output_directory: Path, source: str, generated_at: datetime
) -> dict[str, Path]:
    status = (
        "CSP_OBSERVATION_CLEAN"
        if observation["totalReports"] == 0
        else "CSP_OBSERVATION_REVIEW_REQUIRED"
    )
    evidence = {
        "schemaVersion": 1,
        "project": "visionflow",
        "operation": "CSP_REPORT_ONLY_OBSERVATION",
        "generatedAt": generated_at.isoformat(),
        "status": status,
        "source": source,
        "summary": {
            "totalReports": observation["totalReports"],
            "retainedReports": observation["retainedReports"],
            "maxRetainedReports": observation["maxRetainedReports"],
            "lastReceivedAt": observation["lastReceivedAt"],
            "directiveCount": len(observation["byDirective"]),
        },
        "deferred": [
            "Enforced Content-Security-Policy until final HTTPS and AI addresses",
            "Strict-Transport-Security until HTTPS deployment",
            "Smartphone real-sensor HTTPS validation",
            "HP OMEN RTX 5060 and fine-tuned best.pt validation",
            "DJI Mini 4 Pro integration (third-project scope)",
        ],
        "observation": observation,
    }
    timestamp = generated_at.strftime("%Y%m%dT%H%M%S%fZ")
    stem = f"visionflow-csp-observation-{timestamp}"
    json_path = output_directory / f"{stem}.json"
    csv_path = output_directory / f"{stem}.csv"
    html_path = output_directory / f"{stem}.html"
    checksum_path = output_directory / f"{stem}.sha256"
    atomic_write_text(json_path, json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    atomic_write_text(csv_path, render_csv(observation["reports"]))
    atomic_write_text(html_path, render_html(evidence))
    checksums = "\n".join(
        f"{sha256_file(path)}  {path.name}" for path in (json_path, csv_path, html_path)
    )
    atomic_write_text(checksum_path, checksums + "\n")
    return {
        "json": json_path.resolve(),
        "csv": csv_path.resolve(),
        "html": html_path.resolve(),
        "sha256": checksum_path.resolve(),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    parser.add_argument("--timeout-seconds", type=int, default=10)
    parser.add_argument("--input-json", type=Path)
    parser.add_argument("--fail-on-violation", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        raw_status = (
            read_input_file(args.input_json)
            if args.input_json is not None
            else read_status(args.url, args.timeout_seconds)
        )
        observation = normalize_status(raw_status)
        generated_at = utc_now()
        source = str(args.input_json.resolve()) if args.input_json else args.url
        paths = write_evidence(observation, args.output_directory, source, generated_at)
    except EvidenceError as error:
        print(f"VisionFlow CSP observation evidence: BLOCKED\n{error}", file=sys.stderr)
        return 1

    status = (
        "CSP_OBSERVATION_CLEAN"
        if observation["totalReports"] == 0
        else "CSP_OBSERVATION_REVIEW_REQUIRED"
    )
    print(f"VisionFlow CSP observation evidence: {status}")
    print(f"Total reports   : {observation['totalReports']}")
    print(f"Retained reports: {observation['retainedReports']}")
    print(f"JSON report     : {paths['json']}")
    print(f"CSV report      : {paths['csv']}")
    print(f"HTML report     : {paths['html']}")
    print(f"SHA-256         : {paths['sha256']}")
    if args.fail_on_violation and observation["totalReports"] > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
