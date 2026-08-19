#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def run_id():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run_stream(label, command, cwd, log_path=None, interactive=False):
    print(f"\n=== {label} ===")
    print("[CMD] " + subprocess.list2cmdline(command))
    if interactive:
        code = subprocess.run(command, cwd=cwd).returncode
        print(f"[{'PASS' if code == 0 else 'FAIL'}] {label} - exit={code}")
        return code

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8", newline="\n") as log:
        p = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert p.stdout is not None
        for line in p.stdout:
            print(line, end="")
            log.write(line)
        code = p.wait()
    print(f"[{'PASS' if code == 0 else 'FAIL'}] {label} - exit={code}")
    return code


def docker_health():
    names = [
        "visionflow-frontend",
        "visionflow-backend",
        "visionflow-ai",
        "visionflow-mobile-https",
        "visionflow-mysql",
    ]
    result = subprocess.run(
        ["docker", "inspect", *names],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    payload = json.loads(result.stdout)
    summary = {}
    for item in payload:
        name = str(item.get("Name", "")).lstrip("/")
        state = item.get("State") or {}
        status = str(state.get("Status", ""))
        health = str((state.get("Health") or {}).get("Status", ""))
        if status != "running":
            raise RuntimeError(f"{name}: status={status}")
        if health and health != "healthy":
            raise RuntimeError(f"{name}: health={health}")
        summary[name] = {"status": status, "health": health or None}
        print(f"[PASS] {name} - status={status} health={health or 'n/a'}")
    return summary


def cmd(*parts):
    if os.name == "nt":
        return ["cmd.exe", "/d", "/c", *parts]
    return list(parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--skip-backend-tests", action="store_true")
    parser.add_argument("--skip-frontend-build", action="store_true")
    parser.add_argument("--skip-android-build", action="store_true")
    parser.add_argument("--skip-auth-gate", action="store_true")
    parser.add_argument("--skip-dji-software-gate", action="store_true")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    backend = root / "02_backend" / "visionflow-api"
    frontend = root / "01_frontend" / "visionflow-web"
    android = root / "04_android" / "visionflow-dji-bridge"
    auth = root / "scripts" / "phase3-auth-e2e" / "phase3_auth_e2e.py"
    software = root / "scripts" / "phase3-dji-simulator" / "phase3_software_gate.py"

    required = [backend / "gradlew.bat", frontend / "package.json", android / "gradlew.bat", auth, software]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        print("[FAIL] Missing prerequisites: " + ", ".join(missing), file=sys.stderr)
        return 2

    print("=== VISIONFLOW PHASE 3 LOCAL ACCEPTANCE ===")
    print(f"root={root}")
    print("physicalDJI=SKIPPED")
    print("aws=SKIPPED")
    print("\n=== Docker 5-service baseline ===")
    try:
        docker_state = docker_health()
    except Exception as exc:
        print(f"[FAIL] Docker baseline: {exc}", file=sys.stderr)
        return 2

    run_dir = root / "artifacts" / "phase3-local-acceptance" / run_id()
    run_dir.mkdir(parents=True, exist_ok=True)

    steps = [
        ("Git whitespace check", ["git", "-C", str(root), "diff", "--check"], root, False),
        ("Backend test suite", None if args.skip_backend_tests else cmd("gradlew.bat", "test"), backend, False),
        ("Frontend lint", cmd("npm", "run", "lint"), frontend, False),
        ("Frontend production build", None if args.skip_frontend_build else cmd("npm", "run", "build"), frontend, False),
        ("Android DJI Bridge assembleDebug", None if args.skip_android_build else cmd("gradlew.bat", ":app:assembleDebug"), android, False),
        ("Auth / RBAC runtime E2E", None if args.skip_auth_gate else [sys.executable, str(auth)], root, True),
        ("DJI software-only integration gate", None if args.skip_dji_software_gate else [sys.executable, str(software), "--repo-root", str(root)], root, False),
    ]

    results = []
    failed = False
    for index, (label, command, cwd, interactive) in enumerate(steps, start=1):
        if command is None or failed:
            results.append({"name": label, "status": "SKIPPED"})
            continue
        log_path = run_dir / f"{index:02d}.log"
        code = run_stream(label, command, cwd, log_path, interactive)
        status = "PASS" if code == 0 else "FAIL"
        results.append({"name": label, "status": status, "exitCode": code, "log": None if interactive else str(log_path)})
        if code != 0:
            failed = True

    overall = "FAIL" if failed else "PASS"
    summary = {
        "gate": "phase3-local-acceptance",
        "status": overall,
        "completedAt": utc_now(),
        "physicalDjiRuntime": "SKIPPED",
        "aws": "SKIPPED",
        "dockerBaseline": docker_state,
        "steps": results,
    }
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("\n=== PHASE 3 LOCAL ACCEPTANCE RESULT ===")
    for item in results:
        print(f"{item['status']:7} {item['name']}")
    print(f"evidence={summary_path}")
    print(f"RESULT={overall}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
