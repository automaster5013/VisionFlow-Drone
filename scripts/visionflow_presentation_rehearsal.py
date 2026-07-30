"""Run and independently verify repeated VisionFlow presentation demos."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

try:
    from visionflow_presentation_gate import (
        PresentationGateError,
        READY_STATUS as PRESENTATION_GATE_READY_STATUS,
        verify_gate_report,
    )
except ModuleNotFoundError:  # pragma: no cover - package import during tests
    from scripts.visionflow_presentation_gate import (
        PresentationGateError,
        READY_STATUS as PRESENTATION_GATE_READY_STATUS,
        verify_gate_report,
    )


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
SCOPE = "SECOND_PROJECT_DIGITAL_TWIN"
OPERATION = "PRESENTATION_STABILITY_REHEARSAL"
REPORT_ROOT = Path("artifacts/presentation-rehearsal")
ACCEPTANCE_ROOT = Path("artifacts/visionflow-acceptance")
PRESENTATION_GATE_ROOT = Path("artifacts/presentation-gate")
READY_STATUS = "PRESENTATION_REHEARSAL_READY_WITH_DEFERRED"
BLOCKED_STATUS = "PRESENTATION_REHEARSAL_BLOCKED"
CONFIRMATION = "RUN_PRESENTATION_REHEARSAL"
REQUIRED_DEMO_RESULTS = (
    "Demo operator session login",
    "Demo start",
    "Demo AI detection",
    "Demo SLA escalation",
    "Demo incident resolve",
    "Demo flight complete",
    "Persisted demo scenario",
    "AI detection snapshot",
    "Incident report API",
    "Demo operator session logout",
)
MAX_JSON_BYTES = 5 * 1024 * 1024


class PresentationRehearsalError(RuntimeError):
    """Raised when a repeated presentation rehearsal cannot be trusted."""


Runner = Callable[[int], int]


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
        raise PresentationRehearsalError(
            "프로젝트 내부 증적을 상대경로로 기록할 수 없습니다."
        ) from error


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
        raise PresentationRehearsalError(f"{title} 파일을 찾을 수 없습니다.")
    if path.stat().st_size > MAX_JSON_BYTES:
        raise PresentationRehearsalError(f"{title} JSON 크기가 너무 큽니다.")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PresentationRehearsalError(
            f"{title} JSON 형식이 올바르지 않습니다."
        ) from error
    if not isinstance(value, dict):
        raise PresentationRehearsalError(
            f"{title} JSON 최상위 값은 객체여야 합니다."
        )
    return value


def write_text_atomic(path: Path, value: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    try:
        temporary.write_text(value, encoding=encoding)
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


def resolve_project_file(
    root: Path,
    value: str | None,
    *,
    directory: Path,
    pattern: str,
    title: str,
) -> Path:
    allowed = (root / directory).resolve()
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
            for item in allowed.glob(pattern)
            if item.is_file() and not item.is_symlink()
        ] if allowed.is_dir() else []
        if not candidates:
            raise PresentationRehearsalError(
                f"{title} 파일이 없습니다: {directory.as_posix()}"
            )
        path = max(
            candidates,
            key=lambda item: (item.stat().st_mtime_ns, item.name),
        )
    if (
        not is_within(path, allowed)
        or not path.is_file()
        or path.is_symlink()
    ):
        raise PresentationRehearsalError(
            f"{title} 경로가 허용 영역을 벗어났습니다."
        )
    return path


def acceptance_snapshot(root: Path) -> dict[Path, tuple[int, int, str]]:
    directory = (root / ACCEPTANCE_ROOT).resolve()
    if not directory.is_dir():
        return {}
    return {
        path.resolve(): (
            path.stat().st_mtime_ns,
            path.stat().st_size,
            sha256_file(path),
        )
        for path in directory.glob("visionflow-acceptance-*.json")
        if path.is_file() and not path.is_symlink()
    }


def newest_changed_acceptance(
    before: Mapping[Path, tuple[int, int, str]],
    after: Mapping[Path, tuple[int, int, str]],
) -> Path:
    changed = [
        path
        for path, fingerprint in after.items()
        if before.get(path) != fingerprint
    ]
    if not changed:
        raise PresentationRehearsalError(
            "실행 후 새 인수 테스트 JSON이 생성되지 않았습니다."
        )
    return max(
        changed,
        key=lambda path: (path.stat().st_mtime_ns, path.name),
    )


def numeric_duration(value: Any, title: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PresentationRehearsalError(
            f"{title} DurationMs가 올바르지 않습니다."
        )
    return value


def validate_acceptance_run(
    root: Path,
    path: Path,
    *,
    iteration: int,
    process_exit_code: int,
    elapsed_seconds: float,
    max_run_seconds: float,
    max_step_ms: int,
) -> dict[str, Any]:
    report = read_json(path, f"{iteration}회차 인수 테스트")
    configuration = report.get("configuration")
    summary = report.get("summary")
    scenario = report.get("scenario")
    results = report.get("results")
    issues: list[str] = []
    if process_exit_code != 0:
        issues.append(f"인수 실행 종료코드 {process_exit_code}")
    if not isinstance(configuration, Mapping):
        issues.append("configuration 없음")
    else:
        if configuration.get("runDemo") is not True:
            issues.append("runDemo=true 아님")
        if configuration.get("skipAi") is not False:
            issues.append("AI 검증 제외")
    if not isinstance(summary, Mapping):
        issues.append("summary 없음")
        total = passed = failed = 0
    else:
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
            issues.append("인수 결과 실패")
    if not isinstance(scenario, Mapping) or scenario.get("stage") != "COMPLETED":
        issues.append("영속 데모 미완료")
    by_name: dict[str, Mapping[str, Any]] = {}
    if not isinstance(results, list):
        issues.append("results 없음")
    else:
        for item in results:
            if not isinstance(item, Mapping):
                continue
            name = str(item.get("Name") or item.get("name") or "")
            if name:
                by_name[name] = item
    stages = []
    for name in REQUIRED_DEMO_RESULTS:
        item = by_name.get(name)
        if item is None:
            issues.append(f"필수 단계 누락: {name}")
            continue
        passed_value = item.get("Passed")
        if passed_value is None:
            passed_value = item.get("passed")
        duration_value = item.get("DurationMs")
        if duration_value is None:
            duration_value = item.get("durationMs")
        try:
            duration_ms = numeric_duration(duration_value, name)
        except PresentationRehearsalError as error:
            issues.append(str(error))
            continue
        stage_status = "PASS" if passed_value is True else "FAILED"
        if stage_status != "PASS":
            issues.append(f"필수 단계 실패: {name}")
        if duration_ms > max_step_ms:
            issues.append(
                f"단계 시간 초과: {name} {duration_ms}ms > {max_step_ms}ms"
            )
        stages.append(
            {
                "name": name,
                "status": stage_status,
                "durationMs": duration_ms,
            }
        )
    if elapsed_seconds > max_run_seconds:
        issues.append(
            f"전체 실행시간 초과: {elapsed_seconds:.3f}s > {max_run_seconds:g}s"
        )
    return {
        "iteration": iteration,
        "status": "PASS" if not issues else "FAILED",
        "processExitCode": process_exit_code,
        "elapsedSeconds": round(elapsed_seconds, 3),
        "acceptance": artifact_entry(root, path),
        "summary": {
            "total": total if isinstance(total, int) else 0,
            "passed": passed if isinstance(passed, int) else 0,
            "failed": failed if isinstance(failed, int) else 0,
        },
        "stages": stages,
        "issues": issues,
    }


def percentile_nearest_rank(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[min(rank - 1, len(ordered) - 1)]


def aggregate_metrics(runs: list[Mapping[str, Any]]) -> dict[str, Any]:
    elapsed = [float(item["elapsedSeconds"]) for item in runs]
    stage_durations: dict[str, list[int]] = {
        name: [] for name in REQUIRED_DEMO_RESULTS
    }
    for run in runs:
        for stage in run.get("stages", []):
            if (
                isinstance(stage, Mapping)
                and stage.get("name") in stage_durations
                and isinstance(stage.get("durationMs"), int)
            ):
                stage_durations[str(stage["name"])].append(
                    int(stage["durationMs"])
                )
    stage_metrics = [
        {
            "name": name,
            "samples": len(values),
            "averageMs": (
                round(sum(values) / len(values), 3)
                if values
                else 0.0
            ),
            "maximumMs": max(values, default=0),
            "p95Ms": int(percentile_nearest_rank(
                [float(value) for value in values],
                0.95,
            )),
        }
        for name, values in stage_durations.items()
    ]
    return {
        "attemptedRuns": len(runs),
        "passedRuns": sum(item.get("status") == "PASS" for item in runs),
        "successRatePercent": (
            round(
                100
                * sum(item.get("status") == "PASS" for item in runs)
                / len(runs),
                3,
            )
            if runs
            else 0.0
        ),
        "averageRunSeconds": (
            round(sum(elapsed) / len(elapsed), 3)
            if elapsed
            else 0.0
        ),
        "maximumRunSeconds": max(elapsed, default=0.0),
        "p95RunSeconds": round(
            percentile_nearest_rank(elapsed, 0.95),
            3,
        ),
        "stages": stage_metrics,
    }


def build_report(
    *,
    gate: dict[str, Any],
    runs: list[dict[str, Any]],
    requested_runs: int,
    max_run_seconds: float,
    max_step_ms: int,
    fail_fast: bool,
    now: datetime,
) -> dict[str, Any]:
    aggregate = aggregate_metrics(runs)
    ready = (
        len(runs) == requested_runs
        and aggregate["passedRuns"] == requested_runs
    )
    deferred = [
        {
            "key": str(item.get("key")),
            "status": str(item.get("status")),
            "scope": str(item.get("scope")),
            "reason": str(item.get("reason")),
        }
        for item in gate.get("deferred", [])
        if isinstance(item, Mapping)
    ]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "scope": SCOPE,
        "operation": OPERATION,
        "rehearsalId": str(uuid.uuid4()),
        "generatedAt": now.astimezone(timezone.utc).isoformat(),
        "status": READY_STATUS if ready else BLOCKED_STATUS,
        "policy": {
            "requestedRuns": requested_runs,
            "maxRunSeconds": max_run_seconds,
            "maxStepMs": max_step_ms,
            "failFast": fail_fast,
            "requiredDemoResults": list(REQUIRED_DEMO_RESULTS),
        },
        "sourcePresentationGate": gate["artifact"],
        "runs": runs,
        "metrics": aggregate,
        "deferred": deferred,
        "summary": {
            "requestedRuns": requested_runs,
            "attemptedRuns": len(runs),
            "passedRuns": aggregate["passedRuns"],
            "blocking": 0 if ready else 1,
            "deferred": sum(
                item["status"] == "DEFERRED" for item in deferred
            ),
            "outOfScope": sum(
                item["status"] == "OUT_OF_SCOPE" for item in deferred
            ),
        },
        "safety": {
            "persistentDemoDataCreated": True,
            "databaseMutation": True,
            "sourceEvidenceModified": False,
            "environmentValuesRecorded": False,
            "operatorKeysRecorded": False,
            "privateKeysRecorded": False,
            "absolutePathsRecorded": False,
            "gpuModelChanged": False,
            "smartphoneSensorValidationExecuted": False,
            "djiIntegrationExecuted": False,
        },
    }


def render_html(report: Mapping[str, Any]) -> str:
    ready = report["status"] == READY_STATUS

    def acceptance_label(item: Mapping[str, Any]) -> str:
        acceptance = item.get("acceptance")
        if not isinstance(acceptance, Mapping):
            return "보고서 없음"
        return str(acceptance.get("path") or "보고서 없음")

    run_rows = "".join(
        "<tr>"
        f"<td>{item['iteration']}</td>"
        f"<td class='{str(item['status']).lower()}'>{html.escape(str(item['status']))}</td>"
        f"<td>{item['elapsedSeconds']}</td>"
        f"<td>{html.escape(', '.join(str(issue) for issue in item['issues']) or '-')}</td>"
        f"<td><code>{html.escape(acceptance_label(item))}</code></td>"
        "</tr>"
        for item in report["runs"]
    )
    stage_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['name']))}</td>"
        f"<td>{item['samples']}</td>"
        f"<td>{item['averageMs']}</td>"
        f"<td>{item['p95Ms']}</td>"
        f"<td>{item['maximumMs']}</td>"
        "</tr>"
        for item in report["metrics"]["stages"]
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
<title>VisionFlow 발표 시연 반복 안정성 리허설</title><style>
body {{ margin:0; background:#eef3f8; color:#0f172a; font-family:Arial,'Noto Sans KR',sans-serif; }}
main {{ max-width:1180px; margin:32px auto; padding:0 20px; }}
section {{ background:#fff; border:1px solid #dbe4ee; border-radius:16px; padding:24px; margin:16px 0; }}
h1,h2 {{ margin-top:0; }} .status {{ color:{'#047857' if ready else '#b91c1c'}; font-size:1.35rem; font-weight:800; }}
table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:10px; border-bottom:1px solid #e2e8f0; text-align:left; vertical-align:top; }}
.pass {{ color:#047857; font-weight:700; }} .failed {{ color:#b91c1c; font-weight:700; }}
code {{ word-break:break-all; }}
</style></head><body><main>
<section><h1>VisionFlow 발표 시연 반복 안정성 리허설</h1>
<p class="status">{html.escape(str(report['status']))}</p>
<p>연속 성공 {report['summary']['passedRuns']}/{report['summary']['requestedRuns']} ·
성공률 {report['metrics']['successRatePercent']}% ·
평균 {report['metrics']['averageRunSeconds']}초 · 최대 {report['metrics']['maximumRunSeconds']}초</p></section>
<section><h2>회차별 결과</h2><table><thead><tr><th>회차</th><th>상태</th><th>전체 초</th><th>문제</th><th>인수 증적</th></tr></thead>
<tbody>{run_rows}</tbody></table></section>
<section><h2>단계별 시간</h2><table><thead><tr><th>단계</th><th>표본</th><th>평균 ms</th><th>P95 ms</th><th>최대 ms</th></tr></thead>
<tbody>{stage_rows}</tbody></table></section>
<section><h2>보류·범위 외</h2><table><thead><tr><th>항목</th><th>상태</th><th>사유</th></tr></thead>
<tbody>{deferred_rows}</tbody></table></section>
<section><p>각 회차는 MySQL에 비행·AI·인시던트 데모 증적을 생성합니다. 운영자 키,
환경변수 값, 개인키, GPS 원본 좌표와 절대경로는 이 보고서에 기록하지 않습니다.</p></section>
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
        raise PresentationRehearsalError(
            "출력 폴더는 artifacts/presentation-rehearsal 내부여야 합니다."
        )
    output.mkdir(parents=True, exist_ok=True)
    timestamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = output / f"visionflow-presentation-rehearsal-{timestamp}"
    if base.with_suffix(".json").exists() or base.with_suffix(".html").exists():
        base = output / (
            f"visionflow-presentation-rehearsal-{timestamp}-{uuid.uuid4().hex[:8]}"
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


def default_runner(
    root: Path,
    *,
    drone_id: int,
) -> Runner:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    script = (root / "scripts/visionflow-acceptance.ps1").resolve()
    if not powershell:
        raise PresentationRehearsalError("powershell.exe를 찾을 수 없습니다.")
    if not script.is_file() or script.is_symlink():
        raise PresentationRehearsalError(
            "visionflow-acceptance.ps1을 찾을 수 없습니다."
        )

    def run(_: int) -> int:
        result = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "-RunDemo",
                "-DroneId",
                str(drone_id),
            ],
            cwd=root,
            check=False,
        )
        return result.returncode

    return run


def run_rehearsal(
    root: Path,
    *,
    gate_value: str | None,
    runner: Runner,
    runs: int,
    max_run_seconds: float,
    max_step_ms: int,
    fail_fast: bool,
    output_root: Path,
    now: datetime,
) -> tuple[Path, Path, Path, dict[str, Any], int]:
    if not 1 <= runs <= 10:
        raise PresentationRehearsalError("반복 횟수는 1~10이어야 합니다.")
    if max_run_seconds <= 0 or max_step_ms <= 0:
        raise PresentationRehearsalError("시간 제한은 양수여야 합니다.")
    gate_path = resolve_project_file(
        root,
        gate_value,
        directory=PRESENTATION_GATE_ROOT,
        pattern="visionflow-presentation-gate-*.json",
        title="발표 운영 게이트",
    )
    try:
        verified_gate_path, gate_report = verify_gate_report(
            root,
            relative_path(root, gate_path),
        )
    except PresentationGateError as error:
        raise PresentationRehearsalError(str(error)) from error
    if gate_report.get("status") != PRESENTATION_GATE_READY_STATUS:
        raise PresentationRehearsalError(
            f"발표 운영 게이트가 READY가 아닙니다: {gate_report.get('status')}"
        )
    gate = dict(gate_report)
    gate["artifact"] = artifact_entry(root, verified_gate_path)
    run_results: list[dict[str, Any]] = []
    for iteration in range(1, runs + 1):
        before = acceptance_snapshot(root)
        started = time.monotonic()
        process_exit_code = 1
        try:
            process_exit_code = runner(iteration)
            elapsed = time.monotonic() - started
            after = acceptance_snapshot(root)
            acceptance_path = newest_changed_acceptance(before, after)
            result = validate_acceptance_run(
                root,
                acceptance_path,
                iteration=iteration,
                process_exit_code=process_exit_code,
                elapsed_seconds=elapsed,
                max_run_seconds=max_run_seconds,
                max_step_ms=max_step_ms,
            )
        except (
            PresentationRehearsalError,
            FileNotFoundError,
            OSError,
            subprocess.SubprocessError,
        ) as error:
            elapsed = time.monotonic() - started
            result = {
                "iteration": iteration,
                "status": "FAILED",
                "processExitCode": process_exit_code,
                "elapsedSeconds": round(elapsed, 3),
                "acceptance": None,
                "summary": {"total": 0, "passed": 0, "failed": 1},
                "stages": [],
                "issues": [sanitize_error(error, root)],
            }
        run_results.append(result)
        if fail_fast and result["status"] != "PASS":
            break
    report = build_report(
        gate=gate,
        runs=run_results,
        requested_runs=runs,
        max_run_seconds=max_run_seconds,
        max_step_ms=max_step_ms,
        fail_fast=fail_fast,
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
        raise PresentationRehearsalError(
            "발표 리허설 보고서 경로가 올바르지 않습니다."
        )
    return path


def verify_sidecar(json_path: Path, html_path: Path) -> None:
    sidecar = json_path.with_suffix(".sha256")
    if not sidecar.is_file() or sidecar.is_symlink():
        raise PresentationRehearsalError("발표 리허설 sidecar가 없습니다.")
    try:
        lines = [
            line.strip().split()
            for line in sidecar.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
    except UnicodeDecodeError as error:
        raise PresentationRehearsalError(
            "발표 리허설 sidecar가 UTF-8이 아닙니다."
        ) from error
    if len(lines) != 2 or any(len(parts) != 2 for parts in lines):
        raise PresentationRehearsalError(
            "발표 리허설 sidecar 형식이 올바르지 않습니다."
        )
    recorded = {parts[1]: parts[0].lower() for parts in lines}
    if set(recorded) != {json_path.name, html_path.name}:
        raise PresentationRehearsalError(
            "발표 리허설 sidecar 파일 목록이 다릅니다."
        )
    for path in (json_path, html_path):
        checksum = recorded[path.name]
        if (
            not is_checksum(checksum)
            or not path.is_file()
            or path.is_symlink()
            or checksum != sha256_file(path)
        ):
            raise PresentationRehearsalError(
                f"발표 리허설 SHA-256이 다릅니다: {path.name}"
            )


def verify_artifact(root: Path, value: Any, directory: Path) -> Path:
    if not isinstance(value, Mapping):
        raise PresentationRehearsalError("증적 메타데이터가 없습니다.")
    relative = value.get("path")
    if not isinstance(relative, str):
        raise PresentationRehearsalError("증적 상대경로가 없습니다.")
    allowed = (root / directory).resolve()
    path = (root / relative).resolve()
    if (
        not is_within(path, allowed)
        or not path.is_file()
        or path.is_symlink()
        or value.get("fileName") != path.name
        or value.get("sizeBytes") != path.stat().st_size
        or value.get("sha256") != sha256_file(path)
    ):
        raise PresentationRehearsalError("증적 파일 동일성이 다릅니다.")
    return path


def validate_report_shape(report: Mapping[str, Any]) -> None:
    policy = report.get("policy")
    runs = report.get("runs")
    metrics = report.get("metrics")
    summary = report.get("summary")
    safety = report.get("safety")
    deferred = report.get("deferred")
    if (
        report.get("schemaVersion") != SCHEMA_VERSION
        or report.get("project") != PROJECT_NAME
        or report.get("scope") != SCOPE
        or report.get("operation") != OPERATION
        or report.get("status") not in {READY_STATUS, BLOCKED_STATUS}
        or not isinstance(report.get("rehearsalId"), str)
        or not isinstance(policy, Mapping)
        or not isinstance(runs, list)
        or not isinstance(metrics, Mapping)
        or not isinstance(summary, Mapping)
        or not isinstance(safety, Mapping)
        or not isinstance(deferred, list)
    ):
        raise PresentationRehearsalError(
            "발표 리허설 보고서 형식이 올바르지 않습니다."
        )
    requested = policy.get("requestedRuns")
    if (
        not isinstance(requested, int)
        or isinstance(requested, bool)
        or not 1 <= requested <= 10
        or policy.get("requiredDemoResults") != list(REQUIRED_DEMO_RESULTS)
        or not isinstance(policy.get("maxRunSeconds"), (int, float))
        or isinstance(policy.get("maxRunSeconds"), bool)
        or policy.get("maxRunSeconds") <= 0
        or not isinstance(policy.get("maxStepMs"), int)
        or isinstance(policy.get("maxStepMs"), bool)
        or policy.get("maxStepMs") <= 0
        or not isinstance(policy.get("failFast"), bool)
    ):
        raise PresentationRehearsalError(
            "발표 리허설 실행 정책이 올바르지 않습니다."
        )
    expected_iteration = 1
    failed_seen = False
    for run in runs:
        if (
            not isinstance(run, Mapping)
            or run.get("iteration") != expected_iteration
            or run.get("status") not in {"PASS", "FAILED"}
            or not isinstance(run.get("processExitCode"), int)
            or isinstance(run.get("processExitCode"), bool)
            or not isinstance(run.get("elapsedSeconds"), (int, float))
            or isinstance(run.get("elapsedSeconds"), bool)
            or run.get("elapsedSeconds") < 0
            or not isinstance(run.get("summary"), Mapping)
            or not isinstance(run.get("stages"), list)
            or not isinstance(run.get("issues"), list)
            or any(not isinstance(item, str) for item in run.get("issues", []))
            or (
                run.get("status") == "PASS"
                and (
                    run.get("acceptance") is None
                    or run.get("issues")
                )
            )
            or (
                run.get("status") == "FAILED"
                and not run.get("issues")
            )
        ):
            raise PresentationRehearsalError(
                "발표 리허설 회차 형식이 올바르지 않습니다."
            )
        if policy.get("failFast") is True and failed_seen:
            raise PresentationRehearsalError(
                "fail-fast 보고서에 실패 이후 회차가 있습니다."
            )
        failed_seen = run.get("status") == "FAILED"
        expected_iteration += 1
    if len(runs) > requested:
        raise PresentationRehearsalError(
            "발표 리허설 실행 회차가 요청 횟수를 초과했습니다."
        )
    expected_metrics = aggregate_metrics(runs)
    if metrics != expected_metrics:
        raise PresentationRehearsalError(
            "발표 리허설 성능 집계가 상세 결과와 다릅니다."
        )
    ready = (
        len(runs) == requested
        and metrics.get("passedRuns") == requested
    )
    expected_summary = {
        "requestedRuns": requested,
        "attemptedRuns": len(runs),
        "passedRuns": metrics.get("passedRuns"),
        "blocking": 0 if ready else 1,
        "deferred": sum(
            isinstance(item, Mapping) and item.get("status") == "DEFERRED"
            for item in deferred
        ),
        "outOfScope": sum(
            isinstance(item, Mapping) and item.get("status") == "OUT_OF_SCOPE"
            for item in deferred
        ),
    }
    if (
        summary != expected_summary
        or report.get("status") != (READY_STATUS if ready else BLOCKED_STATUS)
    ):
        raise PresentationRehearsalError(
            "발표 리허설 최종 판정이 상세 결과와 다릅니다."
        )
    if (
        safety.get("persistentDemoDataCreated") is not True
        or safety.get("databaseMutation") is not True
        or safety.get("sourceEvidenceModified") is not False
        or safety.get("environmentValuesRecorded") is not False
        or safety.get("operatorKeysRecorded") is not False
        or safety.get("privateKeysRecorded") is not False
        or safety.get("absolutePathsRecorded") is not False
        or safety.get("gpuModelChanged") is not False
        or safety.get("smartphoneSensorValidationExecuted") is not False
        or safety.get("djiIntegrationExecuted") is not False
    ):
        raise PresentationRehearsalError(
            "발표 리허설 안전 메타데이터가 올바르지 않습니다."
        )


def verify_rehearsal_report(
    root: Path,
    value: str,
) -> tuple[Path, dict[str, Any]]:
    json_path = resolve_report(root, value)
    html_path = json_path.with_suffix(".html")
    verify_sidecar(json_path, html_path)
    report = read_json(json_path, "발표 리허설")
    validate_report_shape(report)
    try:
        html_value = html_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise PresentationRehearsalError(
            "발표 리허설 HTML이 UTF-8이 아닙니다."
        ) from error
    lowered = html_value.lower()
    if any(
        token in lowered
        for token in ("<script", "<iframe", "<object", "<embed", "javascript:")
    ):
        raise PresentationRehearsalError(
            "발표 리허설 HTML에 실행 가능한 콘텐츠가 있습니다."
        )
    if html_value != render_html(report):
        raise PresentationRehearsalError(
            "발표 리허설 JSON과 HTML 내용이 일치하지 않습니다."
        )
    gate_path = verify_artifact(
        root,
        report.get("sourcePresentationGate"),
        PRESENTATION_GATE_ROOT,
    )
    try:
        _, gate = verify_gate_report(
            root,
            relative_path(root, gate_path),
        )
    except PresentationGateError as error:
        raise PresentationRehearsalError(str(error)) from error
    if gate.get("status") != PRESENTATION_GATE_READY_STATUS:
        raise PresentationRehearsalError(
            "원본 발표 운영 게이트가 READY가 아닙니다."
        )
    policy = report["policy"]
    verified_runs = []
    for run in report["runs"]:
        if run.get("acceptance") is None:
            if run.get("status") != "FAILED" or not run.get("issues"):
                raise PresentationRehearsalError(
                    "원본 인수 증적이 없는 회차의 실패 정보가 올바르지 않습니다."
                )
            verified_runs.append(dict(run))
            continue
        acceptance_path = verify_artifact(
            root,
            run.get("acceptance"),
            ACCEPTANCE_ROOT,
        )
        rebuilt = validate_acceptance_run(
            root,
            acceptance_path,
            iteration=int(run.get("iteration")),
            process_exit_code=int(run.get("processExitCode")),
            elapsed_seconds=float(run.get("elapsedSeconds")),
            max_run_seconds=float(policy["maxRunSeconds"]),
            max_step_ms=int(policy["maxStepMs"]),
        )
        if rebuilt != run:
            raise PresentationRehearsalError(
                f"{run.get('iteration')}회차 재검증 결과가 다릅니다."
            )
        verified_runs.append(rebuilt)
    if report["status"] == READY_STATUS and (
        len(verified_runs) != policy["requestedRuns"]
        or any(item["status"] != "PASS" for item in verified_runs)
    ):
        raise PresentationRehearsalError(
            "READY 보고서에 통과하지 않은 회차가 있습니다."
        )
    return json_path, report


def build_plan(runs: int) -> list[dict[str, str]]:
    return [
        {
            "order": "01",
            "mode": "READ_ONLY",
            "detail": "최신 PRESENTATION_READY_WITH_DEFERRED 게이트 독립 검증",
        },
        {
            "order": "02",
            "mode": "CONFIRMATION",
            "detail": f"영속 데모 {runs}회 반복 실행 동의 확인",
        },
        {
            "order": "03",
            "mode": "DATABASE_MUTATION",
            "detail": "각 회차 비행·AI 탐지·인시던트·해결 증적 생성",
        },
        {
            "order": "04",
            "mode": "VERIFY",
            "detail": "필수 단계 성공률과 전체·단계별 시간 제한 판정",
        },
        {
            "order": "05",
            "mode": "EVIDENCE",
            "detail": "JSON·HTML·SHA-256 리허설 증적 생성 및 독립 재검증",
        },
    ]


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="VisionFlow repeated presentation rehearsal"
    )
    parser.add_argument("--root", default=str(default_root))
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan", help="변경 없는 실행 계획 출력")
    plan.add_argument("--runs", type=int, default=3)
    execute = subparsers.add_parser("run", help="영속 데모 반복 리허설 실행")
    execute.add_argument("--confirm", required=True)
    execute.add_argument("--gate")
    execute.add_argument("--runs", type=int, default=3)
    execute.add_argument("--drone-id", type=int, default=1)
    execute.add_argument("--max-run-seconds", type=float, default=30.0)
    execute.add_argument("--max-step-ms", type=int, default=10000)
    execute.add_argument("--no-fail-fast", action="store_true")
    execute.add_argument("--output", default=REPORT_ROOT.as_posix())
    verify = subparsers.add_parser("verify", help="리허설 증적 독립 재검증")
    verify.add_argument("--report", required=True)
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    args = build_parser(default_root).parse_args(arguments)
    root = Path(args.root).resolve()
    try:
        if not root.is_dir():
            raise PresentationRehearsalError("프로젝트 루트를 찾을 수 없습니다.")
        if args.command == "plan":
            if not 1 <= args.runs <= 10:
                raise PresentationRehearsalError(
                    "반복 횟수는 1~10이어야 합니다."
                )
            print("VisionFlow presentation stability rehearsal: PLAN")
            for item in build_plan(args.runs):
                print(f"{item['order']}. [{item['mode']}] {item['detail']}")
            print("No database, service, GPU, smartphone, or DJI action was executed.")
            return 0
        if args.command == "verify":
            path, report = verify_rehearsal_report(root, args.report)
            print("VisionFlow presentation stability rehearsal: VERIFIED")
            print(f"Status: {report['status']}")
            print(f"Report: {path}")
            return 0
        if args.confirm != CONFIRMATION:
            raise PresentationRehearsalError(
                f"실행하려면 --confirm {CONFIRMATION}가 필요합니다."
            )
        if args.drone_id <= 0:
            raise PresentationRehearsalError("드론 ID는 양수여야 합니다.")
        output_value = Path(args.output)
        output = (
            output_value.resolve()
            if output_value.is_absolute()
            else (root / output_value).resolve()
        )
        runner = default_runner(root, drone_id=args.drone_id)
        json_path, html_path, sidecar, report, exit_code = run_rehearsal(
            root,
            gate_value=args.gate,
            runner=runner,
            runs=args.runs,
            max_run_seconds=args.max_run_seconds,
            max_step_ms=args.max_step_ms,
            fail_fast=not args.no_fail_fast,
            output_root=output,
            now=datetime.now(timezone.utc),
        )
        print(f"VisionFlow presentation stability rehearsal: {report['status']}")
        print(
            "Runs: "
            f"{report['summary']['passedRuns']}/"
            f"{report['summary']['requestedRuns']} passed"
        )
        print(f"JSON report: {json_path}")
        print(f"HTML report: {html_path}")
        print(f"SHA-256: {sidecar}")
        return exit_code
    except (
        PresentationRehearsalError,
        PresentationGateError,
        FileNotFoundError,
        OSError,
        subprocess.SubprocessError,
    ) as error:
        print(f"[FAIL] {sanitize_error(error, root)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
