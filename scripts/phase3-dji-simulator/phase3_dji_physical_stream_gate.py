#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any


APP_ID = "com.visionflow.dji.bridge"
MAIN_ACTIVITY = f"{APP_ID}/.MainActivity"
LOG_TAG = "VisionFlowDJI"
DJI_KEY_HEADER = "X-VisionFlow-DJI-Key"

REGISTRATION_MARKERS = (
    "MSDK_INIT_START",
    "MSDK_INITIALIZE_COMPLETE",
    "MSDK_REGISTER_APP_REQUESTED",
    "MSDK_REGISTER_SUCCESS",
)
STREAM_MARKERS = (
    "MSDK_CAMERA_LISTENER_READY",
    "MSDK_PRODUCT_CONNECT",
    "MSDK_CAMERA_AVAILABLE",
    "MSDK_STREAM_LISTENER_ATTACHED",
    "DJI_BRIDGE_UPLOAD_START",
    "MSDK_ENCODED_STREAM_FIRST",
    "MSDK_ENCODED_STREAM_PROGRESS",
)
FAILURE_MARKERS = (
    "MSDK_REGISTER_FAILURE",
    "DJI_BRIDGE_WAIT_PROVISIONING",
    "DJI_BRIDGE_UPLOAD_START_ERROR",
    "MSDK_ENCODED_STREAM_UNSUPPORTED",
    "MSDK_ENCODED_STREAM_RANGE_ERROR",
    "MSDK_ENCODED_STREAM_UPLOAD_REJECTED",
    "DJI_BRIDGE_UPLOAD_OVERFLOW",
    "DJI_BRIDGE_UPLOAD_ERROR",
    "FATAL EXCEPTION",
    "AbstractMethodError",
)
EVIDENCE_MARKERS = tuple(
    dict.fromkeys((*REGISTRATION_MARKERS, *STREAM_MARKERS, *FAILURE_MARKERS))
)


class GateError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


def make_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def capture(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
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
        if not in_device_list:
            continue
        fields = line.split()
        if len(fields) < 2 or fields[1] not in valid_states:
            continue
        devices.append({"serial": fields[0], "state": fields[1]})
    return devices


def marker_position(output: str, marker: str) -> int:
    return output.find(marker)


def evaluate_android_log(output: str) -> dict[str, Any]:
    failures = [marker for marker in FAILURE_MARKERS if marker in output]
    if failures:
        return {
            "status": "FAIL",
            "reason": "Android/MSDK stream failure marker detected",
            "failureMarkers": failures,
            "missingMarkers": [],
        }

    required = (*REGISTRATION_MARKERS, *STREAM_MARKERS)
    missing = [marker for marker in required if marker not in output]
    if missing:
        return {
            "status": "PENDING",
            "reason": "physical stream marker sequence is incomplete",
            "failureMarkers": [],
            "missingMarkers": missing,
        }

    registration_positions = [
        marker_position(output, marker) for marker in REGISTRATION_MARKERS
    ]
    if registration_positions != sorted(registration_positions):
        return {
            "status": "FAIL",
            "reason": "MSDK registration markers are out of order",
            "failureMarkers": [],
            "missingMarkers": [],
        }

    register_success = marker_position(output, "MSDK_REGISTER_SUCCESS")
    listener_ready = marker_position(output, "MSDK_CAMERA_LISTENER_READY")
    product_connect = marker_position(output, "MSDK_PRODUCT_CONNECT")
    camera_available = marker_position(output, "MSDK_CAMERA_AVAILABLE")
    listener_attached = marker_position(output, "MSDK_STREAM_LISTENER_ATTACHED")
    upload_start = marker_position(output, "DJI_BRIDGE_UPLOAD_START")
    first_packet = marker_position(output, "MSDK_ENCODED_STREAM_FIRST")
    progress = marker_position(output, "MSDK_ENCODED_STREAM_PROGRESS")

    if listener_ready < register_success or product_connect < register_success:
        return {
            "status": "FAIL",
            "reason": "product/listener marker occurred before MSDK registration",
            "failureMarkers": [],
            "missingMarkers": [],
        }
    stream_order = (
        listener_ready,
        camera_available,
        listener_attached,
        upload_start,
        first_packet,
        progress,
    )
    if list(stream_order) != sorted(stream_order):
        return {
            "status": "FAIL",
            "reason": "camera/encoded-stream markers are out of order",
            "failureMarkers": [],
            "missingMarkers": [],
        }
    return {
        "status": "PASS",
        "reason": None,
        "failureMarkers": [],
        "missingMarkers": [],
    }


def safe_marker_log(output: str) -> str:
    lines: list[str] = []
    for raw in output.splitlines():
        if any(marker in raw for marker in EVIDENCE_MARKERS):
            lines.append(raw.replace("\r", " ")[:800])
    return "\n".join(lines) + ("\n" if lines else "")


def parse_env_value(path: Path, name: str) -> str | None:
    if not path.is_file():
        return None
    matches: list[str] = []
    for raw in path.read_text(encoding="utf-8-sig", errors="strict").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() != name:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        matches.append(value)
    if len(matches) > 1:
        raise GateError(f"{name} is duplicated in the runtime env file")
    return matches[0] if matches else None


def resolve_bridge_key(*, root: Path, env_file: str, env_name: str) -> tuple[str, str]:
    value = os.environ.get(env_name, "").strip()
    source = "PROCESS_ENV"
    if not value:
        candidate = Path(env_file)
        if not candidate.is_absolute():
            candidate = root / candidate
        try:
            value = (parse_env_value(candidate.resolve(), env_name) or "").strip()
        except (OSError, UnicodeError) as error:
            raise GateError("DJI bridge key env file could not be read") from error
        source = "RUNTIME_ENV_FILE"
    if len(value) < 32:
        raise GateError(f"{env_name} must be configured with at least 32 characters")
    if any(character in value for character in ("\r", "\n", "\0")):
        raise GateError(f"{env_name} contains an unsupported control character")
    if value.startswith("${") or value.startswith("<"):
        raise GateError(f"{env_name} is still a placeholder")
    return value, source


def resolve_ca_file(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise GateError("explicit CA file was not found")
        return path
    result = capture(["mkcert", "-CAROOT"], cwd=Path.cwd())
    if result.returncode != 0 or not result.stdout.strip():
        raise GateError("mkcert Root CA could not be resolved; pass --ca-file")
    path = Path(result.stdout.strip()) / "rootCA.pem"
    if not path.is_file():
        raise GateError("mkcert rootCA.pem was not found")
    return path.resolve()


def validate_host_ip(value: str) -> str:
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError as error:
        raise GateError("--host-ip must be a valid IPv4 address") from error
    if not isinstance(address, ipaddress.IPv4Address):
        raise GateError("--host-ip must be IPv4")
    if address.is_loopback or address.is_unspecified or address.is_multicast:
        raise GateError("--host-ip must be the Edge PC LAN IPv4 address")
    return str(address)


def read_dji_status(*, host_ip: str, ca_file: Path, bridge_key: str) -> dict[str, Any]:
    try:
        context = ssl.create_default_context(cafile=str(ca_file))
    except Exception as error:
        raise GateError("trusted CA context could not be created") from error
    request = urllib.request.Request(
        f"https://{host_ip}:3443/api/ingest/dji/status",
        headers={
            "User-Agent": "VisionFlow-Physical-Stream-Gate/1.0",
            DJI_KEY_HEADER: bridge_key,
        },
        method="GET",
    )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=context),
    )
    try:
        with opener.open(request, timeout=5.0) as response:
            status = int(response.status)
            body = response.read()
    except urllib.error.HTTPError as error:
        raise GateError(f"authenticated DJI status probe returned HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise GateError("authenticated DJI status HTTPS probe failed") from error
    if status != 200:
        raise GateError(f"authenticated DJI status probe returned HTTP {status}")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GateError("DJI status response was not valid UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise GateError("DJI status response must be a JSON object")
    return payload


def metric_int(payload: dict[str, Any], name: str) -> int:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GateError(f"DJI status metric {name} is missing or invalid")
    return value


def status_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("inputMode") != "ANDROID_BRIDGE":
        raise GateError("running AI inputMode is not ANDROID_BRIDGE")
    if payload.get("running") is not True:
        raise GateError("running AI DJI source is not open")
    active = payload.get("activeStream")
    if not isinstance(active, bool):
        raise GateError("DJI status activeStream is missing or invalid")
    codec = payload.get("codec")
    if codec is not None and codec not in {"H264", "H265"}:
        raise GateError("DJI status codec is invalid")
    return {
        "running": True,
        "inputMode": "ANDROID_BRIDGE",
        "activeStream": active,
        "codec": codec,
        "connections": metric_int(payload, "connections"),
        "encodedChunks": metric_int(payload, "encodedChunks"),
        "encodedBytes": metric_int(payload, "encodedBytes"),
        "decodedFrames": metric_int(payload, "decodedFrames"),
        "decoderFailures": metric_int(payload, "decoderFailures"),
    }


def ai_progress(
    before: dict[str, Any],
    current: dict[str, Any],
    *,
    minimum_encoded_bytes: int,
    minimum_decoded_frames: int,
    active_observed: bool,
    codec_observed: bool,
) -> tuple[bool, dict[str, int | bool]]:
    deltas: dict[str, int | bool] = {
        "connectionDelta": int(current["connections"]) - int(before["connections"]),
        "encodedChunkDelta": int(current["encodedChunks"]) - int(before["encodedChunks"]),
        "encodedByteDelta": int(current["encodedBytes"]) - int(before["encodedBytes"]),
        "decodedFrameDelta": int(current["decodedFrames"]) - int(before["decodedFrames"]),
        "decoderFailureDelta": int(current["decoderFailures"]) - int(before["decoderFailures"]),
        "activeStreamObserved": active_observed,
        "supportedCodecObservedWhileActive": codec_observed,
    }
    passed = (
        int(deltas["connectionDelta"]) >= 1
        and int(deltas["encodedChunkDelta"]) >= 1
        and int(deltas["encodedByteDelta"]) >= minimum_encoded_bytes
        and int(deltas["decodedFrameDelta"]) >= minimum_decoded_frames
        and int(deltas["decoderFailureDelta"]) == 0
        and bool(deltas["activeStreamObserved"])
        and bool(deltas["supportedCodecObservedWhileActive"])
    )
    return passed, deltas


def wait_result(*, reason: str, require_device: bool) -> tuple[str, int]:
    if require_device:
        print(f"[FAIL] {reason}", file=sys.stderr)
        return "FAIL", 1
    print("")
    print("=== PHASE 3 DJI PHYSICAL STREAM GATE: WAIT ===")
    print(f"reason={reason}")
    print("adbExecuted=FALSE")
    print("physicalDJI=SKIPPED")
    return "WAIT", 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="VisionFlow Phase 3 controlled DJI physical encoded-stream gate."
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--run-device", action="store_true")
    parser.add_argument("--require-device", action="store_true")
    parser.add_argument("--serial")
    parser.add_argument("--host-ip")
    parser.add_argument("--ca-file")
    parser.add_argument("--env-file", default=".env.docker")
    parser.add_argument("--bridge-key-env", default="VISIONFLOW_DJI_BRIDGE_KEY")
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--poll-interval", type=float, default=0.5)
    parser.add_argument("--minimum-encoded-bytes", type=int, default=4096)
    parser.add_argument("--minimum-decoded-frames", type=int, default=3)
    args = parser.parse_args()
    if args.require_device and not args.run_device:
        parser.error("--require-device requires --run-device")
    if args.timeout_seconds <= 0 or args.poll_interval <= 0:
        parser.error("timeout and poll interval must be positive")
    if args.minimum_encoded_bytes <= 0 or args.minimum_decoded_frames <= 0:
        parser.error("minimum encoded bytes and decoded frames must be positive")

    root = Path(args.repo_root).resolve()
    run = make_run_id()
    evidence_dir = root / "artifacts" / "phase3-dji-physical-stream" / run
    evidence_dir.mkdir(parents=True, exist_ok=True)
    summary_path = evidence_dir / "summary.json"
    marker_log_path = evidence_dir / "android-marker-log.txt"
    status = "FAIL"
    reason: str | None = None
    selected_serial: str | None = None
    adb: str | None = None
    latest_log = ""
    before: dict[str, Any] | None = None
    current: dict[str, Any] | None = None
    deltas: dict[str, int | bool] = {}
    active_observed = False
    codec_observed = False
    bridge_key_source = "NOT_RESOLVED"
    device_summary: dict[str, Any] = {}

    try:
        print("=== VISIONFLOW PHASE 3 DJI PHYSICAL STREAM GATE ===")
        print(f"root={root}")
        print("flightControl=PROHIBITED")
        print("telemetrySubmission=PROHIBITED")
        print("eventSubmission=PROHIBITED")
        whitespace = capture(["git", "-C", str(root), "diff", "--check"], cwd=root)
        if whitespace.returncode != 0:
            raise GateError("Git whitespace check failed")
        if not args.run_device:
            reason = "device execution not requested; rerun with --run-device only at the controlled home hardware gate"
            status, rc = wait_result(reason=reason, require_device=False)
            return rc
        if not args.host_ip:
            raise GateError("--host-ip is required with --run-device")

        host_ip = validate_host_ip(args.host_ip)
        bridge_key, bridge_key_source = resolve_bridge_key(
            root=root,
            env_file=args.env_file,
            env_name=args.bridge_key_env,
        )
        ca_file = resolve_ca_file(args.ca_file)
        before = status_snapshot(
            read_dji_status(host_ip=host_ip, ca_file=ca_file, bridge_key=bridge_key)
        )
        if before["activeStream"]:
            raise GateError("AI already has an active DJI stream; stop the previous client first")
        print("[PASS] Authenticated HTTPS DJI AI baseline")
        print(f"bridgeKeySource={bridge_key_source}")
        print("bridgeKeyValuePrinted=FALSE")

        adb = shutil.which("adb")
        if adb is None:
            reason = "adb executable not found"
            status, rc = wait_result(reason=reason, require_device=args.require_device)
            return rc
        devices_result = capture([adb, "devices", "-l"], cwd=root)
        if devices_result.returncode != 0:
            raise GateError("adb devices -l failed")
        discovered = parse_devices(devices_result.stdout)
        online = [item["serial"] for item in discovered if item["state"] == "device"]
        if args.serial:
            if args.serial not in online:
                reason = "requested Android transport is not online/authorized"
                status, rc = wait_result(reason=reason, require_device=args.require_device)
                return rc
            selected_serial = args.serial
        elif len(online) == 1:
            selected_serial = online[0]
        elif not online:
            reason = "no authorized Android device is connected"
            status, rc = wait_result(reason=reason, require_device=args.require_device)
            return rc
        else:
            reason = "multiple Android transports are online; use --serial"
            status, rc = wait_result(reason=reason, require_device=args.require_device)
            return rc

        model_result = capture(
            [adb, "-s", selected_serial, "shell", "getprop", "ro.product.model"],
            cwd=root,
        )
        abi_result = capture(
            [adb, "-s", selected_serial, "shell", "getprop", "ro.product.cpu.abi"],
            cwd=root,
        )
        if model_result.returncode != 0 or abi_result.returncode != 0:
            raise GateError("Android model/ABI could not be read")
        model = model_result.stdout.strip()
        abi = abi_result.stdout.strip()
        if not abi.startswith("arm64"):
            raise GateError("selected Android device is not arm64")
        device_summary = {
            "serialSha256Prefix": hashlib.sha256(selected_serial.encode("utf-8")).hexdigest()[:12],
            "model": model,
            "abi": abi,
        }

        if capture([adb, "-s", selected_serial, "logcat", "-c"], cwd=root).returncode != 0:
            raise GateError("adb logcat -c failed")
        capture([adb, "-s", selected_serial, "shell", "am", "force-stop", APP_ID], cwd=root)
        launch = capture(
            [adb, "-s", selected_serial, "shell", "am", "start", "-W", "-n", MAIN_ACTIVITY],
            cwd=root,
        )
        if launch.returncode != 0:
            raise GateError("VisionFlow DJI Bridge launch failed")
        print("[PASS] VisionFlow DJI Bridge controlled cold launch")

        deadline = time.monotonic() + args.timeout_seconds
        log_evaluation: dict[str, Any] = {"status": "PENDING", "missingMarkers": []}
        ai_pass = False
        last_status_error: str | None = None
        while time.monotonic() < deadline:
            log_result = capture(
                [
                    adb,
                    "-s",
                    selected_serial,
                    "logcat",
                    "-d",
                    "-v",
                    "time",
                    "-s",
                    f"{LOG_TAG}:V",
                    "AndroidRuntime:E",
                    "*:S",
                ],
                cwd=root,
            )
            if log_result.returncode != 0:
                raise GateError("VisionFlowDJI logcat could not be read")
            latest_log = log_result.stdout
            log_evaluation = evaluate_android_log(latest_log)
            if log_evaluation["status"] == "FAIL":
                failures = ",".join(log_evaluation.get("failureMarkers") or [])
                raise GateError(f"Android physical stream log failed: {failures or log_evaluation['reason']}")

            try:
                current = status_snapshot(
                    read_dji_status(host_ip=host_ip, ca_file=ca_file, bridge_key=bridge_key)
                )
                active_observed = active_observed or bool(current["activeStream"])
                codec_observed = codec_observed or (
                    bool(current["activeStream"])
                    and current["codec"] in {"H264", "H265"}
                )
                ai_pass, deltas = ai_progress(
                    before,
                    current,
                    minimum_encoded_bytes=args.minimum_encoded_bytes,
                    minimum_decoded_frames=args.minimum_decoded_frames,
                    active_observed=active_observed,
                    codec_observed=codec_observed,
                )
                last_status_error = None
            except GateError as error:
                last_status_error = str(error)

            if log_evaluation["status"] == "PASS" and ai_pass:
                break
            time.sleep(args.poll_interval)

        marker_log_path.write_text(safe_marker_log(latest_log), encoding="utf-8")
        if log_evaluation["status"] != "PASS" or not ai_pass:
            missing = ",".join(log_evaluation.get("missingMarkers") or [])
            detail = f"missingMarkers={missing or 'NONE'} aiProgress={ai_pass}"
            if last_status_error:
                detail += f" statusProbe={last_status_error}"
            raise GateError(f"physical encoded-stream gate timed out: {detail}")

        pid = capture([adb, "-s", selected_serial, "shell", "pidof", APP_ID], cwd=root)
        if pid.returncode != 0 or not pid.stdout.strip():
            raise GateError("VisionFlow DJI Bridge process is not alive after stream proof")

        status = "PASS"
        print("[PASS] MSDK product/camera/encoded-stream marker sequence")
        print("[PASS] Edge AI authenticated active stream observed")
        print("[PASS] Edge AI encoded bytes and decoded frames increased")
        print("")
        print("=== PHASE 3 DJI PHYSICAL STREAM GATE: PASS ===")
        print("msdkRegistration=PASS")
        print("djiProductConnection=PASS")
        print("cameraAvailability=PASS")
        print("encodedStreamProgress=PASS")
        print("edgeAiEncodedIngress=PASS")
        print("edgeAiFfmpegDecode=PASS")
        print("flightControl=NOT_PERFORMED")
        print("telemetrySubmission=NOT_PERFORMED")
        print("eventSubmission=NOT_PERFORMED")
        print("bridgeKeyValuePrinted=FALSE")
        print(f"evidence={summary_path}")
        return 0
    except (GateError, OSError, UnicodeError) as error:
        reason = str(error)
        if latest_log:
            marker_log_path.write_text(safe_marker_log(latest_log), encoding="utf-8")
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1
    finally:
        if selected_serial and adb:
            capture([adb, "-s", selected_serial, "shell", "am", "force-stop", APP_ID], cwd=root)
        public_before = before or {}
        public_current = current or {}
        summary = {
            "gate": "phase3-dji-physical-stream",
            "status": status,
            "completedAt": utc_now(),
            "reason": reason,
            "device": device_summary,
            "android": {
                "requiredMarkers": list((*REGISTRATION_MARKERS, *STREAM_MARKERS)),
                "markerEvidence": str(marker_log_path),
                "applicationStoppedAfterGate": selected_serial is not None,
            },
            "ai": {
                "before": public_before,
                "observed": public_current,
                "deltas": deltas,
                "bridgeKeySource": bridge_key_source,
                "bridgeKeyValueRecorded": False,
            },
            "flightControl": "NOT_PERFORMED",
            "telemetrySubmission": "NOT_PERFORMED",
            "eventSubmission": "NOT_PERFORMED",
            "databaseMutation": "NOT_PERFORMED",
            "aws": "NOT_PERFORMED",
        }
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def self_test() -> int:
    devices = parse_devices(
        "List of devices attached\nABC123 device product:x model:Phone\nXYZ unauthorized\n"
    )
    if devices != [
        {"serial": "ABC123", "state": "device"},
        {"serial": "XYZ", "state": "unauthorized"},
    ]:
        raise GateError("device parser self-test failed")
    log = "\n".join(
        (
            "MSDK_INIT_START",
            "MSDK_INITIALIZE_COMPLETE",
            "MSDK_REGISTER_APP_REQUESTED",
            "MSDK_REGISTER_SUCCESS",
            "MSDK_CAMERA_LISTENER_READY",
            "MSDK_PRODUCT_CONNECT id=1",
            "MSDK_CAMERA_AVAILABLE camera=LEFT_OR_MAIN count=1",
            "MSDK_STREAM_LISTENER_ATTACHED camera=LEFT_OR_MAIN",
            "DJI_BRIDGE_UPLOAD_START camera=LEFT_OR_MAIN codec=H264",
            "MSDK_ENCODED_STREAM_FIRST camera=LEFT_OR_MAIN codec=H264",
            "MSDK_ENCODED_STREAM_PROGRESS camera=LEFT_OR_MAIN codec=H264 packets=120 bytes=65536",
        )
    )
    if evaluate_android_log(log)["status"] != "PASS":
        raise GateError("Android marker evaluator self-test failed")
    if evaluate_android_log(log + "\nDJI_BRIDGE_UPLOAD_ERROR")["status"] != "FAIL":
        raise GateError("Android failure marker self-test failed")
    before = {
        "connections": 2,
        "encodedChunks": 10,
        "encodedBytes": 1000,
        "decodedFrames": 20,
        "decoderFailures": 0,
    }
    current = {
        "connections": 3,
        "encodedChunks": 20,
        "encodedBytes": 9000,
        "decodedFrames": 25,
        "decoderFailures": 0,
    }
    passed, deltas = ai_progress(
        before,
        current,
        minimum_encoded_bytes=4096,
        minimum_decoded_frames=3,
        active_observed=True,
        codec_observed=True,
    )
    if not passed or deltas["decodedFrameDelta"] != 5:
        raise GateError("AI progress evaluator self-test failed")
    print("SELF_TEST=PASS")
    print("ADB_EXECUTED=FALSE")
    print("PHYSICAL_DJI_EXECUTED=FALSE")
    print("NETWORK_REQUEST_EXECUTED=FALSE")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(self_test())
    raise SystemExit(main())
