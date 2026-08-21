#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

APP_ID = "com.visionflow.dji.bridge"
MAIN_ACTIVITY = f"{APP_ID}/.MainActivity"
LOG_TAG = "VisionFlowDJI"
REQUIRED_MARKERS = (
    "MSDK_INIT_START",
    "MSDK_INITIALIZE_COMPLETE",
    "MSDK_REGISTER_APP_REQUESTED",
    "MSDK_REGISTER_SUCCESS",
)
FAILURE_MARKER = "MSDK_REGISTER_FAILURE"
POST_REGISTRATION_CRASH_MARKERS = (
    "FATAL EXCEPTION",
    "AbstractMethodError",
)

class GateError(RuntimeError):
    pass

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def make_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def windows_command(*parts: str) -> list[str]:
    if os.name == "nt":
        return ["cmd.exe", "/d", "/c", *parts]
    return list(parts)

def run_step(*, label: str, command: list[str], cwd: Path) -> dict[str, object]:
    print("")
    print(f"=== {label} ===")
    print("[CMD] " + subprocess.list2cmdline(command))
    result = subprocess.run(command, cwd=cwd, text=True, encoding="utf-8", errors="replace")
    status = "PASS" if result.returncode == 0 else "FAIL"
    print(f"[{status}] {label} - exit={result.returncode}")
    if result.returncode != 0:
        raise GateError(f"{label} failed with exit={result.returncode}")
    return {"name": label, "status": status, "exitCode": result.returncode}

def capture(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

def parse_devices(output: str) -> list[dict[str, str]]:
    devices: list[dict[str, str]] = []
    in_device_list = False
    valid_states = {"device", "offline", "unauthorized", "recovery", "sideload", "bootloader"}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("List of devices attached"):
            in_device_list = True
            continue
        if not in_device_list:
            continue
        fields = line.split()
        if len(fields) < 2:
            continue
        serial = fields[0]
        state = fields[1]
        if state not in valid_states:
            continue
        devices.append({"serial": serial, "state": state})
    return devices

def evaluate_registration_log(output: str) -> dict[str, object]:
    if FAILURE_MARKER in output:
        return {"status": "FAIL", "reason": "DJI MSDK registerApp reported failure", "missingMarkers": []}
    positions: list[int] = []
    missing: list[str] = []
    for marker in REQUIRED_MARKERS:
        position = output.find(marker)
        if position < 0:
            missing.append(marker)
        else:
            positions.append(position)
    if missing:
        return {"status": "PENDING", "reason": "registration sequence is incomplete", "missingMarkers": missing}
    if positions != sorted(positions):
        return {"status": "FAIL", "reason": "DJI MSDK registration markers are out of order", "missingMarkers": []}
    return {"status": "PASS", "reason": None, "missingMarkers": []}

def evaluate_post_registration_stability(
    output: str,
    *,
    app_id: str = APP_ID,
) -> dict[str, object]:
    if app_id not in output:
        return {"status": "PASS", "reason": None}

    for marker in POST_REGISTRATION_CRASH_MARKERS:
        if marker in output:
            return {
                "status": "FAIL",
                "reason": (
                    "VisionFlow DJI Bridge crashed after MSDK registration: "
                    + marker
                ),
            }

    return {"status": "PASS", "reason": None}


def wait_result(*, reason: str, require_device: bool) -> tuple[str, int]:
    if require_device:
        print(f"[FAIL] {reason}", file=sys.stderr)
        return "FAIL", 1
    print("")
    print("=== PHASE 3 DJI MSDK REGISTRATION GATE: WAIT ===")
    print(f"reason={reason}")
    print("physicalDJI=SKIPPED")
    return "WAIT", 0

def main() -> int:
    parser = argparse.ArgumentParser(description="VisionFlow Phase 3 DJI MSDK Android registration gate.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--serial")
    parser.add_argument("--run-device", action="store_true", help="Explicitly allow debug APK installation and MSDK registration execution on Android.")
    parser.add_argument("--require-device", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--skip-install", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--poll-interval", type=float, default=0.5)
    parser.add_argument(
        "--stability-seconds",
        type=float,
        default=3.0,
        help=(
            "Seconds to observe the Android process after "
            "MSDK_REGISTER_SUCCESS before declaring PASS."
        ),
    )
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    if args.poll_interval <= 0:
        parser.error("--poll-interval must be positive")
    if args.stability_seconds <= 0:
        parser.error("--stability-seconds must be positive")

    root = Path(args.repo_root).resolve()
    android_root = root / "04_android" / "visionflow-dji-bridge"
    run_id = make_run_id()
    evidence_dir = root / "artifacts" / "phase3-dji-msdk-registration" / run_id
    evidence_dir.mkdir(parents=True, exist_ok=True)
    summary_path = evidence_dir / "summary.json"
    log_path = evidence_dir / "msdk-log.txt"
    steps: list[dict[str, object]] = []
    status = "FAIL"
    reason: str | None = None
    selected_serial: str | None = None
    device_summary: dict[str, object] = {}
    registration: dict[str, object] = {"status": "NOT_RUN"}
    latest_log = ""
    try:
        steps.append(run_step(label="Git whitespace check", command=["git", "-C", str(root), "diff", "--check"], cwd=root))
        if not args.skip_build:
            steps.append(run_step(label="Android MSDK debug APK", command=windows_command("gradlew.bat", ":app:testDebugUnitTest", ":app:assembleDebug"), cwd=android_root))
        if not args.run_device:
            reason = "device execution not requested; rerun with --run-device when Android MSDK validation is intended"
            status, rc = wait_result(reason=reason, require_device=False)
            registration = {"status": status}
            return rc
        adb = shutil.which("adb")
        if adb is None:
            reason = "adb executable not found"
            status, rc = wait_result(reason=reason, require_device=args.require_device)
            registration = {"status": status}
            return rc
        devices_result = capture([adb, "devices", "-l"], cwd=root)
        if devices_result.returncode != 0:
            raise GateError(f"adb devices -l failed with exit={devices_result.returncode}")
        discovered = parse_devices(devices_result.stdout)
        device_summary["discovered"] = discovered
        online = [item["serial"] for item in discovered if item["state"] == "device"]
        if args.serial:
            if args.serial not in online:
                reason = f"requested Android device is not online: {args.serial}"
                status, rc = wait_result(reason=reason, require_device=args.require_device)
                registration = {"status": status}
                return rc
            selected_serial = args.serial
        elif len(online) == 1:
            selected_serial = online[0]
        elif not online:
            states = ", ".join(f"{item['serial']}={item['state']}" for item in discovered)
            reason = "no authorized Android device connected" + (f" ({states})" if states else "")
            status, rc = wait_result(reason=reason, require_device=args.require_device)
            registration = {"status": status}
            return rc
        else:
            reason = "multiple Android transports are online; use --serial to select one"
            status, rc = wait_result(reason=reason, require_device=args.require_device)
            registration = {"status": status}
            return rc
        device_summary["selectedSerial"] = selected_serial
        model_result = capture([adb, "-s", selected_serial, "shell", "getprop", "ro.product.model"], cwd=root)
        abi_result = capture([adb, "-s", selected_serial, "shell", "getprop", "ro.product.cpu.abi"], cwd=root)
        if model_result.returncode != 0 or abi_result.returncode != 0:
            raise GateError("could not read Android device model/ABI")
        model = model_result.stdout.strip(); abi = abi_result.stdout.strip()
        device_summary["model"] = model; device_summary["abi"] = abi
        if not abi.startswith("arm64"):
            reason = f"connected Android device is not arm64; abi={abi or 'unknown'}"
            status, rc = wait_result(reason=reason, require_device=args.require_device)
            registration = {"status": status}
            return rc
        apk_path = android_root / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
        if not apk_path.is_file():
            raise GateError(f"debug APK not found: {apk_path}")
        if not args.skip_install:
            steps.append(run_step(label="Install Android debug APK", command=[adb, "-s", selected_serial, "install", "-r", str(apk_path)], cwd=root))
        if capture([adb, "-s", selected_serial, "logcat", "-c"], cwd=root).returncode != 0:
            raise GateError("adb logcat -c failed")
        capture([adb, "-s", selected_serial, "shell", "am", "force-stop", APP_ID], cwd=root)
        steps.append(run_step(label="Launch VisionFlow DJI Bridge", command=[adb, "-s", selected_serial, "shell", "am", "start", "-W", "-n", MAIN_ACTIVITY], cwd=root))
        deadline = time.monotonic() + args.timeout_seconds
        evaluation: dict[str, object] = {"status": "PENDING"}
        while time.monotonic() < deadline:
            log_result = capture([adb, "-s", selected_serial, "logcat", "-d", "-v", "time", "-s", f"{LOG_TAG}:I", "*:S"], cwd=root)
            if log_result.returncode != 0:
                raise GateError("could not read VisionFlowDJI logcat")
            latest_log = log_result.stdout
            evaluation = evaluate_registration_log(latest_log)
            if evaluation["status"] == "PASS":
                break
            if evaluation["status"] == "FAIL":
                raise GateError(str(evaluation.get("reason")))
            time.sleep(args.poll_interval)
        log_path.write_text(latest_log, encoding="utf-8")
        if evaluation["status"] != "PASS":
            missing = evaluation.get("missingMarkers") or []
            raise GateError("DJI MSDK registration timed out; missing=" + ",".join(str(item) for item in missing))
        steps.append({"name": "DJI MSDK application registration", "status": "PASS", "exitCode": 0})
        print("[PASS] DJI MSDK application registration")

        time.sleep(args.stability_seconds)
        runtime_result = capture(
            [
                adb,
                "-s",
                selected_serial,
                "logcat",
                "-d",
                "-v",
                "time",
                "AndroidRuntime:E",
                "*:S",
            ],
            cwd=root,
        )
        if runtime_result.returncode != 0:
            raise GateError(
                "could not read AndroidRuntime logcat after registration"
            )

        stability = evaluate_post_registration_stability(
            runtime_result.stdout,
        )
        if stability["status"] != "PASS":
            raise GateError(str(stability.get("reason")))

        pid_result = capture(
            [
                adb,
                "-s",
                selected_serial,
                "shell",
                "pidof",
                APP_ID,
            ],
            cwd=root,
        )
        pids = pid_result.stdout.strip()
        if pid_result.returncode != 0 or not pids:
            raise GateError(
                "VisionFlow DJI Bridge process is not alive after registration"
            )

        steps.append(
            {
                "name": "DJI MSDK post-registration stability",
                "status": "PASS",
                "exitCode": 0,
            }
        )
        registration = {
            "status": "PASS",
            "requiredMarkers": list(REQUIRED_MARKERS),
            "timeoutSeconds": args.timeout_seconds,
            "stabilitySeconds": args.stability_seconds,
            "postRegistrationStability": "PASS",
            "processPids": pids.split(),
        }
        status = "PASS"
        print(
            "[PASS] DJI MSDK post-registration stability "
            f"- {args.stability_seconds:.1f}s"
        )
        print("")
        print("=== PHASE 3 DJI MSDK REGISTRATION GATE: PASS ===")
        print(f"device={selected_serial}")
        print(f"model={model or 'unknown'}")
        print("msdkRegistration=PASS")
        print("postRegistrationStability=PASS")
        print("djiProductConnection=SKIPPED")
        print("physicalDJI=SKIPPED")
        print(f"evidence={summary_path}")
        return 0
    except (GateError, FileNotFoundError) as error:
        reason = str(error); status = "FAIL"
        registration = {"status": "FAIL", "reason": reason}
        if latest_log:
            log_path.write_text(latest_log, encoding="utf-8")
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1
    finally:
        if selected_serial:
            adb = shutil.which("adb")
            if adb:
                capture([adb, "-s", selected_serial, "shell", "am", "force-stop", APP_ID], cwd=root)
        summary = {
            "gate": "phase3-dji-msdk-registration",
            "status": status,
            "completedAt": utc_now(),
            "reason": reason,
            "device": device_summary,
            "registration": registration,
            "djiProductConnection": "SKIPPED",
            "physicalDjiRuntime": "SKIPPED",
            "steps": steps,
        }
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    raise SystemExit(main())
