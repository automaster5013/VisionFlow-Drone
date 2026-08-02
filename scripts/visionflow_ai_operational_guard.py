#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT_DEFAULT = r"C:\VisionFlow-Drone"
EXPECTED_CONTAINERS = (
    "visionflow-ai",
    "visionflow-backend",
    "visionflow-frontend",
    "visionflow-mysql",
)
EXPECTED_AI_ENV = {
    "AI_MODEL_PROFILE": "best-gpu",
    "AI_MODEL_PATH": "/app/models/best.pt",
    "AI_REQUIRE_LOCAL_MODEL": "true",
    "AI_DEVICE": "0",
    "AI_REQUIRE_CUDA": "true",
    "AI_EVENT_MIN_CONSECUTIVE_FRAMES": "5",
    "AI_EVENT_COOLDOWN_SECONDS": "10",
}
PURGED_OPERATION = (
    "artifacts/ai-event-cleanup/"
    "cleanup-20260730-091108/operation.json"
)


@dataclass
class CheckResult:
    name: str
    status: str
    message: str
    details: dict[str, Any]


def run(args: list[str], timeout: int = 300, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        args,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )
    if check and completed.returncode != 0:
        raise RuntimeError(
            f"명령 실패({completed.returncode}): {' '.join(args)}\n"
            f"{completed.stderr.strip()}"
        )
    return completed


def mysql_scalar(sql: str) -> str:
    command = (
        'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" '
        '-D "$MYSQL_DATABASE" --batch --raw --skip-column-names '
        f'-e "{sql}"'
    )
    return run([
        "docker", "exec", "visionflow-mysql", "sh", "-lc", command
    ]).stdout.strip()


def container_health(name: str) -> str:
    completed = run([
        "docker", "inspect", "-f",
        "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
        name,
    ], timeout=60, check=False)
    if completed.returncode != 0:
        return "missing"
    return completed.stdout.strip() or "unknown"


def check_containers() -> CheckResult:
    states = {name: container_health(name) for name in EXPECTED_CONTAINERS}
    bad = {name: state for name, state in states.items() if state != "healthy"}
    return CheckResult(
        "containers",
        "CRITICAL" if bad else "HEALTHY",
        "핵심 컨테이너 상태를 확인했습니다." if not bad else "healthy가 아닌 컨테이너가 있습니다.",
        states,
    )


def check_ai_environment() -> CheckResult:
    output = run([
        "docker", "inspect", "visionflow-ai", "--format",
        "{{range .Config.Env}}{{println .}}{{end}}",
    ], timeout=60).stdout
    env: dict[str, str] = {}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            env[key] = value
    actual = {key: env.get(key) for key in EXPECTED_AI_ENV}
    mismatch = {
        key: {"expected": expected, "actual": actual.get(key)}
        for key, expected in EXPECTED_AI_ENV.items()
        if actual.get(key) != expected
    }
    mismatch_names = ", ".join(sorted(mismatch))
    return CheckResult(
        "ai_environment",
        "CRITICAL" if mismatch else "HEALTHY",
        (
            "AI 모델·GPU·이벤트 게이트 환경값이 정상입니다."
            if not mismatch
            else f"AI 환경값이 예상과 다릅니다: {mismatch_names}"
        ),
        {"actual": actual, "mismatch": mismatch},
    )


def check_gpu_model(run_inference: bool) -> CheckResult:
    code = """
import json
from pathlib import Path
import torch
from ultralytics import YOLO
p=Path('/app/models/best.pt')
r={'modelExists':p.is_file(),'modelBytes':p.stat().st_size if p.is_file() else 0,'cudaAvailable':torch.cuda.is_available(),'cudaBuild':torch.version.cuda,'device':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}
m=YOLO(str(p)) if p.is_file() else None
r['task']=m.task if m else None
r['classes']=m.names if m else None
r['scale']=m.model.yaml.get('scale') if m else None
image=Path('/app/data/dummy/test-input.jpg')
r['fixtureExists']=image.is_file()
if RUN_INFERENCE and image.is_file() and m:
    pred=m.predict(source=str(image),device=0,imgsz=640,conf=0.35,verbose=False)[0]
    r['detections']=len(pred.boxes) if pred.boxes is not None else 0
    r['speedMs']=pred.speed
print(json.dumps(r,ensure_ascii=False))
""".replace("RUN_INFERENCE", "True" if run_inference else "False")
    completed = run([
        "docker", "exec", "visionflow-ai", "python", "-c", code
    ], timeout=300, check=False)
    if completed.returncode != 0:
        return CheckResult("gpu_model", "CRITICAL", "GPU·모델 점검 명령이 실패했습니다.", {"stderr": completed.stderr.strip()})
    try:
        data = json.loads(completed.stdout.strip().splitlines()[-1])
    except Exception as exc:
        return CheckResult("gpu_model", "CRITICAL", "GPU·모델 점검 결과 해석에 실패했습니다.", {"error": str(exc), "stdout": completed.stdout})
    classes = data.get("classes") or {}
    valid = (
        data.get("modelExists") is True
        and data.get("modelBytes", 0) > 0
        and data.get("cudaAvailable") is True
        and data.get("device") == "NVIDIA GeForce RTX 5060 Laptop GPU"
        and data.get("task") == "detect"
        and data.get("scale") == "m"
        and str(classes.get("0", classes.get(0))) == "Hardhat"
        and str(classes.get("1", classes.get(1))) == "NO-Hardhat"
    )
    status = "HEALTHY" if valid else "CRITICAL"
    if valid and run_inference and not data.get("fixtureExists"):
        status = "WARNING"
    return CheckResult(
        "gpu_model",
        status,
        "RTX 5060에서 YOLO26m best.pt가 정상입니다." if status == "HEALTHY" else "GPU·모델 정보 또는 추론 fixture를 확인해야 합니다.",
        data,
    )


def check_event_gate(root: Path) -> CheckResult:
    bat = root / "scripts" / "run-event-gate-test.bat"
    if not bat.is_file():
        return CheckResult("event_gate", "WARNING", "이벤트 게이트 테스트 BAT가 없습니다.", {"path": str(bat)})
    completed = run([str(bat)], timeout=180, check=False)
    output = (completed.stdout + "\n" + completed.stderr).strip()
    passed = completed.returncode == 0 and "EVENT_GATE_TEST=PASS" in output and "reported_frames= [5, 25]" in output
    return CheckResult(
        "event_gate",
        "HEALTHY" if passed else "CRITICAL",
        "5프레임 확인·10초 쿨다운 테스트가 통과했습니다." if passed else "이벤트 게이트 테스트가 실패했습니다.",
        {"exitCode": completed.returncode, "output": output},
    )


def check_recent_growth(warning: int, critical: int) -> CheckResult:
    values = mysql_scalar(
        "SELECT COUNT(*),COALESCE(SUM(detection_count),0),COUNT(snapshot_file_name),COALESCE(SUM(snapshot_size_bytes),0) "
        "FROM ai_inference_event WHERE received_at >= UTC_TIMESTAMP(6)-INTERVAL 10 MINUTE;"
    ).split("\t")
    if len(values) != 4:
        return CheckResult("recent_growth", "CRITICAL", "최근 이벤트 집계 형식이 잘못됐습니다.", {"raw": values})
    events, detections, snapshots, bytes_ = map(int, values)
    status = "CRITICAL" if events >= critical else "WARNING" if events >= warning else "HEALTHY"
    return CheckResult(
        "recent_growth", status,
        "최근 10분 이벤트 증가량이 정상입니다." if status == "HEALTHY" else "최근 10분 이벤트 증가량이 임계값을 넘었습니다.",
        {"windowMinutes": 10, "events": events, "detections": detections, "snapshots": snapshots, "snapshotBytes": bytes_, "eventsPerMinute": round(events / 10, 3), "warningThreshold": warning, "criticalThreshold": critical},
    )


def check_snapshot_consistency(root: Path) -> CheckResult:
    active = root / "artifacts" / "backend-data" / "ai-snapshots"
    files = list(active.glob("*.jpg"))
    actual_count = len(files)
    actual_bytes = sum(path.stat().st_size for path in files)
    values = mysql_scalar(
        "SELECT COUNT(snapshot_file_name),COALESCE(SUM(snapshot_size_bytes),0) FROM ai_inference_event;"
    ).split("\t")
    if len(values) != 2:
        return CheckResult("snapshot_consistency", "CRITICAL", "DB 스냅샷 집계 형식이 잘못됐습니다.", {"raw": values})
    db_count, db_bytes = map(int, values)
    ok = actual_count == db_count and actual_bytes == db_bytes
    return CheckResult(
        "snapshot_consistency", "HEALTHY" if ok else "CRITICAL",
        "DB 참조와 실제 JPG 수·용량이 일치합니다." if ok else "DB 참조와 실제 JPG가 일치하지 않습니다.",
        {"databaseReferences": db_count, "databaseBytes": db_bytes, "actualFiles": actual_count, "actualBytes": actual_bytes},
    )


def check_data_integrity(root: Path, report_dir: Path) -> CheckResult:
    script = root / "scripts" / "visionflow_data_integrity_audit.py"
    if not script.is_file():
        return CheckResult(
            "data_integrity",
            "CRITICAL",
            "읽기 전용 데이터 정합성 감사 스크립트가 없습니다.",
            {"path": str(script)},
        )

    audit_dir = report_dir / "data-integrity"
    completed = run(
        [
            sys.executable,
            str(script),
            "--root",
            str(root),
            "--output",
            str(audit_dir),
        ],
        timeout=600,
        check=False,
    )
    report_path = audit_dir / "visionflow-data-integrity-audit.json"
    if not report_path.is_file():
        return CheckResult(
            "data_integrity",
            "CRITICAL",
            "데이터 정합성 감사 보고서가 생성되지 않았습니다.",
            {
                "exitCode": completed.returncode,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
            },
        )

    try:
        report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return CheckResult(
            "data_integrity",
            "CRITICAL",
            "데이터 정합성 감사 보고서를 해석하지 못했습니다.",
            {"error": str(exc), "report": str(report_path)},
        )

    audit_status = str(report.get("status", "UNKNOWN"))
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    safety = report.get("safety") if isinstance(report.get("safety"), dict) else {}
    read_only = (
        report.get("readOnly") is True
        and safety.get("databaseMutation") is False
        and safety.get("containerMutation") is False
        and safety.get("serviceRestart") is False
        and safety.get("credentialValueCollection") is False
        and safety.get("snapshotFileContentRead") is False
        and safety.get("writesOnlyReports") is True
    )
    expected_exit_codes = {
        "DATA_INTEGRITY_HEALTHY": {0},
        "DATA_INTEGRITY_ADVISORY": {0},
        "DATA_INTEGRITY_BLOCKED": {1},
    }
    exit_code_valid = completed.returncode in expected_exit_codes.get(audit_status, set())
    status_map = {
        "DATA_INTEGRITY_HEALTHY": "HEALTHY",
        "DATA_INTEGRITY_ADVISORY": "WARNING",
        "DATA_INTEGRITY_BLOCKED": "CRITICAL",
    }
    status = status_map.get(audit_status, "CRITICAL")
    if not read_only or not exit_code_valid:
        status = "CRITICAL"

    if not read_only:
        message = "데이터 정합성 감사의 읽기 전용 안전 증명이 유효하지 않습니다."
    elif not exit_code_valid:
        message = "데이터 정합성 감사 상태와 종료 코드가 일치하지 않습니다."
    elif status == "HEALTHY":
        message = "39개 DB 관계와 5개 snapshot 규칙이 정상입니다."
    elif status == "WARNING":
        message = "데이터 정합성 감사에 검토할 advisory가 있습니다."
    else:
        message = "데이터 정합성 감사에서 차단 수준 문제가 발견됐습니다."

    return CheckResult(
        "data_integrity",
        status,
        message,
        {
            "auditStatus": audit_status,
            "exitCode": completed.returncode,
            "readOnlySafetyVerified": read_only,
            "databaseRules": summary.get("databaseRules"),
            "snapshotRules": summary.get("snapshotRules"),
            "findings": summary.get("findings"),
            "criticalRules": summary.get("criticalRules"),
            "advisoryRules": summary.get("advisoryRules"),
            "report": str(report_path),
        },
    )


def check_disk(root: Path, warning_percent: float) -> CheckResult:
    usage = shutil.disk_usage(root)
    free_percent = usage.free / usage.total * 100
    status = "WARNING" if free_percent < warning_percent else "HEALTHY"
    return CheckResult(
        "disk", status,
        "C 드라이브 여유 공간이 정상입니다." if status == "HEALTHY" else "C 드라이브 여유 비율이 낮습니다.",
        {"totalGB": round(usage.total / 1024**3, 2), "usedGB": round(usage.used / 1024**3, 2), "freeGB": round(usage.free / 1024**3, 2), "freePercent": round(free_percent, 1), "warningThresholdPercent": warning_percent},
    )


def check_cleanup_record(root: Path) -> CheckResult:
    path = root / PURGED_OPERATION
    if not path.is_file():
        return CheckResult("cleanup_record", "WARNING", "PURGED 작업 기록을 찾지 못했습니다.", {"path": str(path)})
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    ok = data.get("status") == "PURGED" and data.get("purgedSnapshotCount") == 133306 and data.get("purgedSnapshotBytes") == 15413065831
    return CheckResult(
        "cleanup_record", "HEALTHY" if ok else "WARNING",
        "과거 폭증 데이터 PURGED 이력이 정상입니다." if ok else "PURGED 이력이 예상과 다릅니다.",
        {"status": data.get("status"), "purgedAt": data.get("purgedAt"), "purgedSnapshotCount": data.get("purgedSnapshotCount"), "purgedSnapshotBytes": data.get("purgedSnapshotBytes")},
    )


def check_deep_audit(root: Path) -> CheckResult:
    bat = root / "scripts" / "run-visionflow-storage-audit.bat"
    if not bat.is_file():
        return CheckResult("storage_audit", "WARNING", "storage audit BAT가 없습니다.", {"path": str(bat)})
    completed = run([str(bat)], timeout=600, check=False)
    output = (completed.stdout + "\n" + completed.stderr).strip()
    ok = completed.returncode == 0 and "VisionFlow storage audit: HEALTHY" in output
    return CheckResult(
        "storage_audit", "HEALTHY" if ok else "CRITICAL",
        "전체 저장소 감사가 HEALTHY입니다." if ok else "전체 저장소 감사가 HEALTHY가 아닙니다.",
        {"exitCode": completed.returncode, "output": output},
    )


def overall(results: list[CheckResult]) -> str:
    statuses = {result.status for result in results}
    return "CRITICAL" if "CRITICAL" in statuses else "WARNING" if "WARNING" in statuses else "HEALTHY"


def create_report_dir(root: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_dir = root / "artifacts" / "operational-guard" / f"guard-{stamp}"
    report_dir.mkdir(parents=True, exist_ok=False)
    return report_dir


def write_report(report_dir: Path, results: list[CheckResult]) -> Path:
    payload = {"schemaVersion": 2, "generatedAt": datetime.now(timezone.utc).isoformat(), "status": overall(results), "checks": [asdict(result) for result in results]}
    path = report_dir / "operational-guard.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    text = [f"VisionFlow AI Operational Guard: {payload['status']}", f"Generated: {payload['generatedAt']}", ""]
    text.extend(f"[{item.status}] {item.name}: {item.message}" for item in results)
    (report_dir / "operational-guard.txt").write_text("\n".join(text) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="VisionFlow AI 운영 상태 자동 점검")
    parser.add_argument("--root", default=ROOT_DEFAULT)
    parser.add_argument("--warning-events-10m", type=int, default=120)
    parser.add_argument("--critical-events-10m", type=int, default=600)
    parser.add_argument("--disk-warning-percent", type=float, default=20.0)
    parser.add_argument("--skip-inference", action="store_true")
    parser.add_argument("--deep", action="store_true")
    args = parser.parse_args()
    if shutil.which("docker") is None:
        raise RuntimeError("docker 명령을 찾을 수 없습니다.")
    root = Path(args.root).resolve()
    report_dir = create_report_dir(root)
    checks: list[tuple[str, Callable[[], CheckResult]]] = [
        ("containers", check_containers),
        ("ai_environment", check_ai_environment),
        ("gpu_model", lambda: check_gpu_model(not args.skip_inference)),
        ("event_gate", lambda: check_event_gate(root)),
        ("recent_growth", lambda: check_recent_growth(args.warning_events_10m, args.critical_events_10m)),
        ("snapshot_consistency", lambda: check_snapshot_consistency(root)),
        ("data_integrity", lambda: check_data_integrity(root, report_dir)),
        ("disk", lambda: check_disk(root, args.disk_warning_percent)),
        ("cleanup_record", lambda: check_cleanup_record(root)),
    ]
    if args.deep:
        checks.append(("storage_audit", lambda: check_deep_audit(root)))
    results: list[CheckResult] = []
    for name, function in checks:
        try:
            result = function()
        except Exception as exc:
            result = CheckResult(name, "CRITICAL", "점검 중 예외가 발생했습니다.", {"error": str(exc)})
        results.append(result)
        print(f"[{result.status}] {result.name}: {result.message}")
    report = write_report(report_dir, results)
    status = overall(results)
    print("")
    print(f"VisionFlow AI Operational Guard: {status}")
    print(f"Report: {report}")
    return {"HEALTHY": 0, "WARNING": 1, "CRITICAL": 2}[status]


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n사용자 중단", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"\n오류: {exc}", file=sys.stderr)
        raise SystemExit(2)
