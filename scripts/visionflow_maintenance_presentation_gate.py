#!/usr/bin/env python3
"""Combine VisionFlow presentation and maintenance read-only checks."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence


READY_STATUS = "MAINTENANCE_PRESENTATION_GATE_READY_WITH_DEFERRED"
BLOCKED_STATUS = "MAINTENANCE_PRESENTATION_GATE_BLOCKED"
REPORT_ROOT = Path("artifacts/maintenance-presentation-gate")
Runner = Callable[[str, Sequence[str], Path], tuple[int, str, int]]


@dataclass(frozen=True)
class Stage:
    key: str
    title: str
    status: str
    exit_code: int
    duration_ms: int
    detail: str
    output_tail: list[str]


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def sanitized_lines(value: str, root: Path, limit: int = 12) -> list[str]:
    sanitized = value
    variants = {
        str(root.resolve()),
        str(root.resolve()).replace("\\", "/"),
        str(root.resolve()).replace("/", "\\"),
    }
    for variant in variants:
        sanitized = sanitized.replace(variant, "<PROJECT_ROOT>")
    sanitized = re.sub(
        r"\b(?:VIEWER|OPERATOR|ADMIN)_[A-Za-z0-9_-]{12,}\b",
        "<REDACTED_OPERATOR_KEY>",
        sanitized,
    )
    lines = [line.strip() for line in sanitized.splitlines() if line.strip()]
    return lines[-limit:]


def default_runner(
    script: str,
    arguments: Sequence[str],
    root: Path,
) -> tuple[int, str, int]:
    path = (root / "scripts" / script).resolve()
    scripts_root = (root / "scripts").resolve()
    if (
        not is_within(path, scripts_root)
        or not path.is_file()
        or path.is_symlink()
    ):
        return 2, f"Required script is missing: scripts/{script}", 0

    command = [sys.executable, str(path), *arguments]
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            check=False,
        )
        output = "\n".join(
            part for part in (completed.stdout, completed.stderr) if part
        )
        return (
            completed.returncode,
            output,
            round((time.perf_counter() - started) * 1000),
        )
    except subprocess.TimeoutExpired as error:
        output = "\n".join(
            str(part)
            for part in (error.stdout, error.stderr)
            if part
        )
        return (
            124,
            output + "\nValidation timed out after 600 seconds.",
            round((time.perf_counter() - started) * 1000),
        )
    except OSError as error:
        return (
            2,
            str(error),
            round((time.perf_counter() - started) * 1000),
        )


def run_stage(
    *,
    key: str,
    title: str,
    script: str,
    arguments: Sequence[str],
    root: Path,
    runner: Runner,
) -> Stage:
    exit_code, output, duration_ms = runner(script, arguments, root)
    passed = exit_code == 0
    lines = sanitized_lines(output, root)
    detail = (
        "Completed successfully"
        if passed
        else lines[-1] if lines else f"Exited with code {exit_code}"
    )
    return Stage(
        key=key,
        title=title,
        status="PASS" if passed else "FAILED",
        exit_code=exit_code,
        duration_ms=duration_ms,
        detail=detail,
        output_tail=lines,
    )


def diagnosis(stages: Sequence[Stage]) -> dict[str, object]:
    failed = {stage.key for stage in stages if stage.status != "PASS"}
    if not failed:
        return {
            "code": "PRESENTATION_PATHS_AND_MAINTENANCE_HEALTHY",
            "actions": [
                "브라우저에서 /demo-scenario를 열고 발표를 시작합니다.",
                "정비 게이트 설정과 컨테이너를 발표 중 변경하지 않습니다.",
            ],
        }
    if failed == {"presentation-quick-check"}:
        return {
            "code": "PRESENTATION_QUICK_CHECK_FAILED",
            "actions": [
                "발표 퀵체크 하위 출력의 실패 서비스부터 복구합니다.",
                "기존 발표 퀵체크를 단독 실행해 상세 보고서를 확인합니다.",
            ],
        }
    if failed == {"maintenance-flight-gate"}:
        return {
            "code": "MAINTENANCE_FLIGHT_GATE_FAILED",
            "actions": [
                "선택한 드론 ID와 현재 정비 게이트 모드를 확인합니다.",
                "정비 게이트 인수 테스트 HTML의 실패 항목을 확인합니다.",
            ],
        }
    return {
        "code": "MULTIPLE_VALIDATION_FAILURES",
        "actions": [
            "발표 퀵체크와 정비 게이트 인수 테스트를 각각 단독 실행합니다.",
            "서비스 연결 문제를 먼저 해결한 뒤 통합 게이트를 재실행합니다.",
        ],
    }


def html_report(report: dict[str, object]) -> str:
    rows: list[str] = []
    for stage in report["stages"]:  # type: ignore[index]
        color = "#047857" if stage["status"] == "PASS" else "#b91c1c"
        rows.append(
            "<tr>"
            f"<td>{html.escape(stage['title'])}</td>"
            f"<td style=\"font-weight:700;color:{color}\">"
            f"{html.escape(stage['status'])}</td>"
            f"<td>{stage['exit_code']}</td>"
            f"<td>{stage['duration_ms']} ms</td>"
            f"<td>{html.escape(stage['detail'])}</td>"
            "</tr>"
        )
    diagnosis_value = report["diagnosis"]  # type: ignore[assignment]
    actions = "".join(
        f"<li>{html.escape(action)}</li>"
        for action in diagnosis_value["actions"]
    )
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VisionFlow Maintenance Presentation Gate</title>
  <style>
    body {{ font-family: Segoe UI, sans-serif; margin: 32px; color: #0f172a; }}
    .card {{ border: 1px solid #cbd5e1; border-radius: 14px; padding: 20px; margin-bottom: 18px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #e2e8f0; padding: 10px; text-align: left; }}
    th {{ background: #f8fafc; }}
  </style>
</head>
<body>
  <h1>VisionFlow 정비·발표 통합 게이트</h1>
  <div class="card">
    <p><strong>결과:</strong> {html.escape(report['status'])}</p>
    <p><strong>드론:</strong> #{report['inputs']['droneId']}</p>
    <p><strong>진단:</strong> {html.escape(diagnosis_value['code'])}</p>
    <p><strong>안전:</strong> 읽기 전용 검증, 운영 데이터 변경 없음</p>
    <ul>{actions}</ul>
  </div>
  <table>
    <thead><tr><th>단계</th><th>상태</th><th>종료 코드</th><th>시간</th><th>상세</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</body>
</html>
"""


def write_report(
    root: Path,
    output_root: Path,
    report: dict[str, object],
    generated_at: datetime,
) -> tuple[Path, Path]:
    allowed = (root / REPORT_ROOT).resolve()
    resolved_output = output_root.resolve()
    if not is_within(resolved_output, allowed):
        raise ValueError(
            "OutputDirectory must be inside "
            "artifacts/maintenance-presentation-gate."
        )
    resolved_output.mkdir(parents=True, exist_ok=True)
    stamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
    base = f"visionflow-maintenance-presentation-gate-{stamp}"
    json_path = resolved_output / f"{base}.json"
    html_path = resolved_output / f"{base}.html"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    html_path.write_text(html_report(report), encoding="utf-8")
    return json_path, html_path


def run_gate(
    root: Path,
    *,
    drone_id: int,
    required_mode: str | None,
    output_root: Path,
    runner: Runner = default_runner,
    now: datetime | None = None,
) -> tuple[dict[str, object], Path, Path, int]:
    stages = [
        run_stage(
            key="presentation-quick-check",
            title="Presentation quick check",
            script="visionflow_presentation_quick_check.py",
            arguments=("--root", str(root), "check"),
            root=root,
            runner=runner,
        )
    ]
    maintenance_arguments = [
        "-FrontendUrl",
        "http://localhost:3000",
        "-BackendUrl",
        "http://localhost:8080",
        "-DroneId",
        str(drone_id),
    ]
    if required_mode:
        maintenance_arguments.extend(("-RequireMode", required_mode))
    stages.append(
        run_stage(
            key="maintenance-flight-gate",
            title="Maintenance flight-gate acceptance",
            script="visionflow_maintenance_acceptance.py",
            arguments=maintenance_arguments,
            root=root,
            runner=runner,
        )
    )

    failed = [stage for stage in stages if stage.status != "PASS"]
    status = READY_STATUS if not failed else BLOCKED_STATUS
    generated_at = now or datetime.now(timezone.utc)
    report: dict[str, object] = {
        "schemaVersion": 1,
        "project": "visionflow",
        "scope": "SECOND_PROJECT_DIGITAL_TWIN",
        "operation": "MAINTENANCE_PRESENTATION_GATE",
        "generatedAt": generated_at.isoformat(),
        "status": status,
        "inputs": {
            "droneId": drone_id,
            "requiredMode": required_mode,
        },
        "summary": {
            "total": len(stages),
            "passed": len(stages) - len(failed),
            "failed": len(failed),
        },
        "stages": [asdict(stage) for stage in stages],
        "diagnosis": diagnosis(stages),
        "deferred": [
            "hp-target-smartphone-https-revalidation",
            "hp-omen-gpu-best-model",
            "dji-mini4-pro-integration",
        ],
        "safety": {
            "readOnly": True,
            "databaseMutation": False,
            "operatorKeysRecorded": False,
            "automaticRestart": False,
            "ownSha256SidecarCreated": False,
            "childQuickCheckMayCreateSha256Sidecar": True,
        },
    }
    json_path, html_path = write_report(
        root,
        output_root,
        report,
        generated_at,
    )
    return report, json_path, html_path, 0 if not failed else 1


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="VisionFlow maintenance and presentation integrated gate",
    )
    value.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parents[1]),
    )
    value.add_argument("-DroneId", "--drone-id", type=int, default=1)
    value.add_argument(
        "-RequireMode",
        "--require-mode",
        choices=("OFF", "ADVISORY", "ENFORCED"),
    )
    value.add_argument(
        "-OutputDirectory",
        "--output-directory",
        default=str(REPORT_ROOT),
    )
    return value


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    if args.drone_id < 1:
        raise SystemExit("DroneId must be at least 1.")

    root = Path(args.root).resolve()
    output_value = Path(args.output_directory)
    output_root = (
        output_value.resolve()
        if output_value.is_absolute()
        else (root / output_value).resolve()
    )

    print("VisionFlow maintenance presentation gate")
    print(f"Project: {root}")
    print(f"Drone  : {args.drone_id}")
    print("")
    try:
        report, json_path, html_path, exit_code = run_gate(
            root,
            drone_id=args.drone_id,
            required_mode=args.require_mode,
            output_root=output_root,
        )
    except ValueError as error:
        print(f"[FAIL] {error}")
        return 2

    for stage in report["stages"]:
        print(
            f"[{stage['status']}] {stage['title']} "
            f"({stage['duration_ms']} ms) - {stage['detail']}"
        )
    print("")
    print(f"VisionFlow maintenance presentation gate: {report['status']}")
    print(
        f"Stages: {report['summary']['passed']}/"
        f"{report['summary']['total']} passed"
    )
    print(f"Diagnosis: {report['diagnosis']['code']}")
    print(f"JSON report: {json_path}")
    print(f"HTML report: {html_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
