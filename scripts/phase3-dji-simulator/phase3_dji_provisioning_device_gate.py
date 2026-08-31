#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


APP_ID = "com.visionflow.dji.bridge"
SELF_TEST_ACTIVITY = (
    "com.visionflow.dji.bridge/"
    ".DjiProvisioningSelfTestActivity"
)
LOG_TAG = "VisionFlowProvisioning"


class GateError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


def make_run_id() -> str:
    return datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )


def windows_command(*parts: str) -> list[str]:
    if os.name == "nt":
        return ["cmd.exe", "/d", "/c", *parts]
    return list(parts)


def run_step(
    *,
    label: str,
    command: list[str],
    cwd: Path,
) -> dict[str, object]:
    print("")
    print(f"=== {label} ===")
    print("[CMD] " + subprocess.list2cmdline(command))

    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    status = "PASS" if result.returncode == 0 else "FAIL"
    print(f"[{status}] {label} - exit={result.returncode}")

    if result.returncode != 0:
        raise GateError(
            f"{label} failed with exit={result.returncode}"
        )

    return {
        "name": label,
        "status": status,
        "exitCode": result.returncode,
    }


def capture(
    command: list[str],
    *,
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def parse_devices(output: str) -> list[dict[str, str]]:
    devices: list[dict[str, str]] = []
    in_device_list = False
    valid_states = {
        "device",
        "offline",
        "unauthorized",
        "recovery",
        "sideload",
        "bootloader",
    }

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("List of devices attached"):
            in_device_list = True
            continue

        if not in_device_list or "\t" not in raw_line:
            continue

        serial, details = raw_line.split("\t", 1)
        serial = serial.strip()
        fields = details.strip().split()
        if not serial or not fields:
            continue

        state = fields[0]
        if state not in valid_states:
            continue

        devices.append(
            {
                "serial": serial,
                "state": state,
            }
        )

    return devices


def wait_result(
    *,
    reason: str,
    require_device: bool,
) -> tuple[str, int]:
    if require_device:
        print(f"[FAIL] {reason}", file=sys.stderr)
        return "FAIL", 1

    print("")
    print("=== PHASE 3 DJI PROVISIONING DEVICE GATE: WAIT ===")
    print(f"reason={reason}")
    print("physicalDJI=SKIPPED")
    return "WAIT", 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "VisionFlow Phase 3 Android provisioning / "
            "Keystore ADB gate."
        )
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--serial")
    parser.add_argument(
        "--run-device",
        action="store_true",
        help=(
            "Explicitly allow APK install and Android Keystore "
            "self-test execution."
        ),
    )
    parser.add_argument(
        "--require-device",
        action="store_true",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
    )
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    android_root = (
        root
        / "04_android"
        / "visionflow-dji-bridge"
    )
    run_id = make_run_id()
    evidence_dir = (
        root
        / "artifacts"
        / "phase3-dji-provisioning-device"
        / run_id
    )
    evidence_dir.mkdir(
        parents=True,
        exist_ok=True,
    )
    summary_path = evidence_dir / "summary.json"
    selftest_log_path = evidence_dir / "selftest-log.txt"

    steps: list[dict[str, object]] = []
    status = "FAIL"
    device_summary: dict[str, object] = {}
    reason: str | None = None
    selected_serial: str | None = None

    try:
        steps.append(
            run_step(
                label="Git whitespace check",
                command=[
                    "git",
                    "-C",
                    str(root),
                    "diff",
                    "--check",
                ],
                cwd=root,
            )
        )

        if not args.skip_build:
            steps.append(
                run_step(
                    label=(
                        "Android provisioning unit tests "
                        "and debug APK"
                    ),
                    command=windows_command(
                        "gradlew.bat",
                        ":app:testDebugUnitTest",
                        ":app:assembleDebug",
                    ),
                    cwd=android_root,
                )
            )

        if not args.run_device:
            reason = (
                "device execution not requested; "
                "rerun with --run-device when hardware validation is intended"
            )
            status, rc = wait_result(
                reason=reason,
                require_device=False,
            )
            return rc

        adb = shutil.which("adb")
        if adb is None:
            reason = "adb executable not found"
            status, rc = wait_result(
                reason=reason,
                require_device=args.require_device,
            )
            return rc

        devices_result = capture(
            [adb, "devices"],
            cwd=root,
        )
        if devices_result.returncode != 0:
            raise GateError(
                "adb devices failed with "
                f"exit={devices_result.returncode}"
            )

        discovered = parse_devices(devices_result.stdout)
        device_summary["discovered"] = discovered

        online = [
            item["serial"]
            for item in discovered
            if item["state"] == "device"
        ]

        if args.serial:
            if args.serial not in online:
                reason = (
                    f"requested device is not online: "
                    f"{args.serial}"
                )
                status, rc = wait_result(
                    reason=reason,
                    require_device=args.require_device,
                )
                return rc
            selected_serial = args.serial
        elif len(online) == 1:
            selected_serial = online[0]
        elif not online:
            states = ", ".join(
                f"{item['serial']}={item['state']}"
                for item in discovered
            )
            reason = (
                "no authorized Android device connected"
                + (f" ({states})" if states else "")
            )
            status, rc = wait_result(
                reason=reason,
                require_device=args.require_device,
            )
            return rc
        else:
            reason = (
                "multiple Android devices are online; "
                "use --serial"
            )
            status, rc = wait_result(
                reason=reason,
                require_device=args.require_device,
            )
            return rc

        device_summary["selectedSerial"] = selected_serial

        abi_result = capture(
            [
                adb,
                "-s",
                selected_serial,
                "shell",
                "getprop",
                "ro.product.cpu.abi",
            ],
            cwd=root,
        )
        if abi_result.returncode != 0:
            raise GateError("could not read Android device ABI")

        abi = abi_result.stdout.strip()
        device_summary["abi"] = abi

        if not abi.startswith("arm64"):
            reason = (
                "connected device is not arm64; "
                f"abi={abi or 'unknown'}"
            )
            status, rc = wait_result(
                reason=reason,
                require_device=args.require_device,
            )
            return rc

        apk_path = (
            android_root
            / "app"
            / "build"
            / "outputs"
            / "apk"
            / "debug"
            / "app-debug.apk"
        )
        if not apk_path.is_file():
            raise GateError(
                f"debug APK not found: {apk_path}"
            )

        if not args.skip_install:
            steps.append(
                run_step(
                    label="Install Android debug APK",
                    command=[
                        adb,
                        "-s",
                        selected_serial,
                        "install",
                        "-r",
                        str(apk_path),
                    ],
                    cwd=root,
                )
            )

        capture(
            [
                adb,
                "-s",
                selected_serial,
                "shell",
                "am",
                "force-stop",
                APP_ID,
            ],
            cwd=root,
        )

        steps.append(
            run_step(
                label="Launch isolated provisioning self-test",
                command=[
                    adb,
                    "-s",
                    selected_serial,
                    "shell",
                    "am",
                    "start",
                    "-W",
                    "-n",
                    SELF_TEST_ACTIVITY,
                    "--es",
                    "runId",
                    run_id,
                ],
                cwd=root,
            )
        )

        log_result = capture(
            [
                adb,
                "-s",
                selected_serial,
                "logcat",
                "-d",
                "-s",
                f"{LOG_TAG}:I",
                "*:S",
            ],
            cwd=root,
        )
        selftest_log_path.write_text(
            log_result.stdout,
            encoding="utf-8",
        )

        pass_marker = (
            "DJI_PROVISIONING_SELF_TEST_PASS "
            f"runId={run_id}"
        )
        fail_marker = (
            "DJI_PROVISIONING_SELF_TEST_FAIL "
            f"runId={run_id}"
        )

        if fail_marker in log_result.stdout:
            raise GateError(
                "Android provisioning self-test reported FAIL"
            )
        if pass_marker not in log_result.stdout:
            raise GateError(
                "Android provisioning self-test PASS marker "
                "was not found"
            )

        steps.append(
            {
                "name": (
                    "Android Keystore provisioning round-trip"
                ),
                "status": "PASS",
                "exitCode": 0,
            }
        )
        print(
            "[PASS] Android Keystore provisioning "
            "round-trip"
        )

        status = "PASS"
        print("")
        print(
            "=== PHASE 3 DJI PROVISIONING "
            "DEVICE GATE: PASS ==="
        )
        print("keystoreRoundTrip=PASS")
        print("isolatedDiagnosticsStorage=PASS")
        print("physicalDJI=SKIPPED")
        print(f"evidence={summary_path}")
        return 0

    except (GateError, FileNotFoundError) as error:
        reason = str(error)
        print(f"[FAIL] {error}", file=sys.stderr)
        status = "FAIL"
        return 1

    finally:
        if selected_serial:
            adb = shutil.which("adb")
            if adb:
                capture(
                    [
                        adb,
                        "-s",
                        selected_serial,
                        "shell",
                        "am",
                        "force-stop",
                        APP_ID,
                    ],
                    cwd=root,
                )

        summary = {
            "gate": "phase3-dji-provisioning-device",
            "status": status,
            "completedAt": utc_now(),
            "reason": reason,
            "device": device_summary,
            "keystoreRoundTrip": (
                "PASS" if status == "PASS" else status
            ),
            "isolatedDiagnosticsStorage": True,
            "physicalDjiRuntime": "SKIPPED",
            "steps": steps,
        }
        summary_path.write_text(
            json.dumps(
                summary,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    raise SystemExit(main())
