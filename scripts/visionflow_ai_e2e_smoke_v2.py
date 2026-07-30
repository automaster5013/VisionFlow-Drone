#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DEFAULT = r"C:\VisionFlow-Drone"
AI_CONTAINER = "visionflow-ai"
MYSQL_CONTAINER = "visionflow-mysql"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(
    args: list[str],
    *,
    timeout: int = 300,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
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
            f"Command failed ({completed.returncode}): {' '.join(args)}\n"
            f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return completed


def container_health(name: str) -> str:
    completed = run(
        [
            "docker",
            "inspect",
            "-f",
            "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
            name,
        ],
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        return "missing"
    return completed.stdout.strip()


def mysql_query(sql: str) -> str:
    command = (
        'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" '
        '-D "$MYSQL_DATABASE" '
        '--batch --raw --skip-column-names '
        f"-e {shlex.quote(sql)}"
    )
    return run(
        ["docker", "exec", MYSQL_CONTAINER, "sh", "-lc", command],
        timeout=180,
    ).stdout.strip()


def sql_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def session_stats(source_id: str, session_id: str) -> dict[str, Any]:
    source = sql_string(source_id)
    session = sql_string(session_id)
    sql = (
        "SELECT "
        "COUNT(*),"
        "COALESCE(SUM(e.detection_count),0),"
        "COUNT(e.snapshot_file_name),"
        "COALESCE(SUM(e.snapshot_size_bytes),0),"
        "COALESCE(MIN(e.id),0),"
        "COALESCE(MAX(e.id),0),"
        "COALESCE(MIN(e.frame_index),0),"
        "COALESCE(MAX(e.frame_index),0),"
        "(SELECT COUNT(*) FROM ai_detection d "
        "JOIN ai_inference_event ie ON ie.id=d.event_id "
        f"WHERE ie.source_id={source} AND ie.session_id={session}),"
        "(SELECT COUNT(*) FROM ai_alert a "
        "JOIN ai_inference_event ie ON ie.id=a.event_id "
        f"WHERE ie.source_id={source} AND ie.session_id={session}) "
        "FROM ai_inference_event e "
        f"WHERE e.source_id={source} AND e.session_id={session};"
    )
    values = mysql_query(sql).split("\t")
    if len(values) != 10:
        raise RuntimeError(f"Unexpected DB stats: {values}")
    keys = (
        "events",
        "recordedDetections",
        "snapshots",
        "snapshotBytes",
        "minEventId",
        "maxEventId",
        "minFrameIndex",
        "maxFrameIndex",
        "actualDetections",
        "alerts",
    )
    return {key: int(value) for key, value in zip(keys, values)}


def snapshot_rows(source_id: str, session_id: str) -> list[dict[str, Any]]:
    source = sql_string(source_id)
    session = sql_string(session_id)
    output = mysql_query(
        "SELECT id,frame_index,snapshot_file_name,snapshot_size_bytes "
        "FROM ai_inference_event "
        f"WHERE source_id={source} AND session_id={session} "
        "ORDER BY id;"
    )
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        event_id, frame_index, file_name, size_bytes = line.split("\t")
        rows.append(
            {
                "eventId": int(event_id),
                "frameIndex": int(frame_index),
                "fileName": file_name,
                "sizeBytes": int(size_bytes),
            }
        )
    return rows


def parse_feeder_result(output: str) -> dict[str, Any]:
    for line in reversed(output.splitlines()):
        if line.startswith("E2E_FEEDER_RESULT="):
            return json.loads(line.split("=", 1)[1])
    raise RuntimeError(f"Feeder result was not found:\n{output}")


def run_storage_audit(root: Path) -> dict[str, Any]:
    audit = root / "scripts" / "run-visionflow-storage-audit.bat"
    if not audit.is_file():
        return {"status": "SKIPPED", "reason": f"Not found: {audit}"}
    completed = run([str(audit)], timeout=600, check=False)
    output = (completed.stdout + "\n" + completed.stderr).strip()
    status = "HEALTHY" if "VisionFlow storage audit: HEALTHY" in output else "FAILED"
    return {
        "status": status,
        "exitCode": completed.returncode,
        "output": output,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="VisionFlow deterministic end-to-end frame ingest smoke test"
    )
    parser.add_argument("--root", default=ROOT_DEFAULT)
    parser.add_argument("--frames", type=int, default=30)
    parser.add_argument("--fps", type=float, default=5.0)
    parser.add_argument("--drone-id", type=int, default=1)
    parser.add_argument("--wait-seconds", type=int, default=30)
    parser.add_argument("--skip-audit", action="store_true")
    args = parser.parse_args()

    if shutil.which("docker") is None:
        raise RuntimeError("docker command was not found.")

    root = Path(args.root).resolve()
    feeder_host = root / "scripts" / "visionflow_e2e_frame_feeder.py"
    if not feeder_host.is_file():
        raise RuntimeError(f"Feeder script was not found: {feeder_host}")

    health = {
        name: container_health(name)
        for name in (
            "visionflow-ai",
            "visionflow-backend",
            "visionflow-mysql",
        )
    }
    bad = {name: state for name, state in health.items() if state != "healthy"}
    if bad:
        raise RuntimeError(f"Core containers are not healthy: {bad}")

    container_feeder = "/tmp/visionflow_e2e_frame_feeder.py"
    run(["docker", "cp", str(feeder_host), f"{AI_CONTAINER}:{container_feeder}"])

    command = [
        "docker",
        "exec",
        AI_CONTAINER,
        "python",
        container_feeder,
        "--frames",
        str(args.frames),
        "--fps",
        str(args.fps),
        "--drone-id",
        str(args.drone_id),
    ]
    print("Submitting deterministic frames through the FastAPI ingest endpoint...")
    completed = run(command, timeout=max(300, int(args.frames / args.fps) + 120))
    print(completed.stdout, end="")
    feeder_result = parse_feeder_result(completed.stdout)

    source_id = str(feeder_result["sourceId"])
    session_id = str(feeder_result["sessionId"])
    deadline = time.time() + args.wait_seconds
    stats: dict[str, Any] = {}

    while time.time() < deadline:
        stats = session_stats(source_id, session_id)
        if stats["events"] >= 1 and stats["snapshots"] >= 1:
            break
        time.sleep(1)

    rows = snapshot_rows(source_id, session_id)
    active_dir = root / "artifacts" / "backend-data" / "ai-snapshots"
    file_checks: list[dict[str, Any]] = []
    for row in rows:
        path = active_dir / str(row["fileName"])
        exists = path.is_file()
        actual_size = path.stat().st_size if exists else None
        file_checks.append(
            {
                **row,
                "path": str(path),
                "exists": exists,
                "actualSizeBytes": actual_size,
                "sizeMatches": exists and actual_size == row["sizeBytes"],
            }
        )

    problems: list[str] = []
    if stats.get("events") != 1:
        problems.append(
            f"Expected exactly 1 event, actual={stats.get('events')}. "
            "A value greater than 1 indicates gate/cooldown regression."
        )
    if stats.get("alerts") != 1:
        problems.append(f"Expected exactly 1 alert, actual={stats.get('alerts')}.")
    if stats.get("snapshots") != 1:
        problems.append(f"Expected exactly 1 snapshot, actual={stats.get('snapshots')}.")
    if stats.get("actualDetections", 0) < 1:
        problems.append("No ai_detection row was stored.")
    if stats.get("recordedDetections") != stats.get("actualDetections"):
        problems.append(
            "ai_inference_event.detection_count and ai_detection rows differ."
        )
    if len(file_checks) != 1 or not all(
        check["exists"] and check["sizeMatches"] for check in file_checks
    ):
        problems.append("Snapshot file existence/size validation failed.")
    # Browser ingest assigns frame indexes internally from zero.
    # With a 5-frame gate, the first eligible index is therefore 4.
    expected_first_eligible_frame_index = 4
    if stats.get("minFrameIndex", -1) < expected_first_eligible_frame_index:
        problems.append(
            "Event was reported before the fifth processed frame: "
            f"frameIndex={stats.get('minFrameIndex')}, "
            f"expectedAtLeast={expected_first_eligible_frame_index} "
            "(zero-based frame index)"
        )

    audit_result = (
        {"status": "SKIPPED"}
        if args.skip_audit
        else run_storage_audit(root)
    )
    if audit_result.get("status") == "FAILED":
        problems.append("Storage audit did not return HEALTHY.")

    status = "HEALTHY" if not problems else "CRITICAL"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_dir = root / "artifacts" / "e2e-smoke" / f"e2e-{stamp}"
    report_dir.mkdir(parents=True, exist_ok=False)
    report = {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "status": status,
        "test": {
            "type": "DETERMINISTIC_FRAME_INGEST_GATE",
            "expectedEvents": 1,
            "expectedAlerts": 1,
            "expectedSnapshots": 1,
            "frames": args.frames,
            "fps": args.fps,
            "durationSeconds": args.frames / args.fps,
            "cooldownSeconds": 10,
            "frameIndexBase": 0,
            "expectedFirstEligibleFrameIndex": 4,
        },
        "containers": health,
        "feeder": feeder_result,
        "database": stats,
        "snapshotFiles": file_checks,
        "storageAudit": audit_result,
        "problems": problems,
    }
    report_path = report_dir / "e2e-smoke.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("")
    print(f"VisionFlow E2E Smoke Test: {status}")
    print(f"Source ID: {source_id}")
    print(f"Session ID: {session_id}")
    print("Database:")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    if problems:
        print("Problems:")
        for problem in problems:
            print(f"- {problem}")
    print(f"Report: {report_path}")
    print("")
    print(
        "The generated event is intentionally retained for dashboard verification."
    )
    return 0 if status == "HEALTHY" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nUser interrupted.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as error:
        print(f"\nE2E_SMOKE_ERROR={error}", file=sys.stderr)
        raise SystemExit(2)
