from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
GATE_PATH = (
    ROOT
    / "scripts"
    / "phase3-dji-simulator"
    / "phase3_dji_physical_stream_gate.py"
)
SPEC = importlib.util.spec_from_file_location(
    "phase3_dji_physical_stream_gate",
    GATE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


def valid_log() -> str:
    return "\n".join(
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


def status_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "running": True,
        "inputMode": "ANDROID_BRIDGE",
        "activeStream": True,
        "codec": "H264",
        "sourceId": "private-source",
        "sessionId": "private-session",
        "droneId": 1,
        "connections": 3,
        "encodedChunks": 20,
        "encodedBytes": 9000,
        "decodedFrames": 25,
        "decoderFailures": 0,
    }
    payload.update(overrides)
    return payload


class Phase3DjiPhysicalStreamGateTest(unittest.TestCase):
    def test_device_parser_keeps_transport_state_without_daemon_noise(self) -> None:
        output = (
            "* daemon started successfully *\n"
            "List of devices attached\n"
            "ABC123 device product:x model:Phone transport_id:1\n"
            "XYZ987 unauthorized usb:1-2 transport_id:2\n"
        )

        self.assertEqual(
            gate.parse_devices(output),
            [
                {"serial": "ABC123", "state": "device"},
                {"serial": "XYZ987", "state": "unauthorized"},
            ],
        )

    def test_complete_ordered_android_marker_sequence_passes(self) -> None:
        result = gate.evaluate_android_log(valid_log())

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["failureMarkers"], [])
        self.assertEqual(result["missingMarkers"], [])

    def test_missing_marker_stays_pending(self) -> None:
        result = gate.evaluate_android_log(
            valid_log().replace("MSDK_ENCODED_STREAM_PROGRESS", "STREAM_NOT_READY")
        )

        self.assertEqual(result["status"], "PENDING")
        self.assertIn("MSDK_ENCODED_STREAM_PROGRESS", result["missingMarkers"])

    def test_each_failure_marker_fails_closed(self) -> None:
        for marker in gate.FAILURE_MARKERS:
            with self.subTest(marker=marker):
                result = gate.evaluate_android_log(valid_log() + f"\n{marker}")
                self.assertEqual(result["status"], "FAIL")
                self.assertIn(marker, result["failureMarkers"])

    def test_registration_and_stream_order_fail_closed(self) -> None:
        registration_out_of_order = valid_log().replace(
            "MSDK_INITIALIZE_COMPLETE\nMSDK_REGISTER_APP_REQUESTED",
            "MSDK_REGISTER_APP_REQUESTED\nMSDK_INITIALIZE_COMPLETE",
        )
        stream_out_of_order = valid_log().replace(
            "MSDK_CAMERA_AVAILABLE camera=LEFT_OR_MAIN count=1\n"
            "MSDK_STREAM_LISTENER_ATTACHED camera=LEFT_OR_MAIN",
            "MSDK_STREAM_LISTENER_ATTACHED camera=LEFT_OR_MAIN\n"
            "MSDK_CAMERA_AVAILABLE camera=LEFT_OR_MAIN count=1",
        )

        self.assertEqual(
            gate.evaluate_android_log(registration_out_of_order)["status"],
            "FAIL",
        )
        self.assertEqual(
            gate.evaluate_android_log(stream_out_of_order)["status"],
            "FAIL",
        )

    def test_status_snapshot_keeps_only_public_runtime_evidence(self) -> None:
        snapshot = gate.status_snapshot(status_payload())

        self.assertEqual(snapshot["inputMode"], "ANDROID_BRIDGE")
        self.assertEqual(snapshot["codec"], "H264")
        self.assertNotIn("sourceId", snapshot)
        self.assertNotIn("sessionId", snapshot)
        self.assertNotIn("droneId", snapshot)
        self.assertNotIn("lastDecoderLog", snapshot)

    def test_status_snapshot_rejects_wrong_mode_state_and_codec(self) -> None:
        invalid_payloads = (
            status_payload(inputMode="SMARTPHONE_UPLOAD"),
            status_payload(running=False),
            status_payload(activeStream="true"),
            status_payload(codec="VP9"),
            status_payload(decodedFrames=-1),
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(gate.GateError):
                    gate.status_snapshot(payload)

    def test_ai_progress_requires_ingress_decode_active_codec_and_no_failure(self) -> None:
        before = gate.status_snapshot(
            status_payload(
                activeStream=False,
                codec=None,
                connections=2,
                encodedChunks=10,
                encodedBytes=1000,
                decodedFrames=20,
            )
        )
        current = gate.status_snapshot(status_payload())

        passed, deltas = gate.ai_progress(
            before,
            current,
            minimum_encoded_bytes=4096,
            minimum_decoded_frames=3,
            active_observed=True,
            codec_observed=True,
        )

        self.assertTrue(passed)
        self.assertEqual(deltas["connectionDelta"], 1)
        self.assertGreaterEqual(deltas["encodedByteDelta"], 4096)
        self.assertGreaterEqual(deltas["decodedFrameDelta"], 3)
        self.assertEqual(deltas["decoderFailureDelta"], 0)

        failure_cases = (
            {"active_observed": False, "codec_observed": True},
            {"active_observed": True, "codec_observed": False},
        )
        for case in failure_cases:
            with self.subTest(case=case):
                failed, _ = gate.ai_progress(
                    before,
                    current,
                    minimum_encoded_bytes=4096,
                    minimum_decoded_frames=3,
                    **case,
                )
                self.assertFalse(failed)

        decoder_failed = dict(current, decoderFailures=1)
        failed, _ = gate.ai_progress(
            before,
            decoder_failed,
            minimum_encoded_bytes=4096,
            minimum_decoded_frames=3,
            active_observed=True,
            codec_observed=True,
        )
        self.assertFalse(failed)

        insufficient_cases = (
            dict(current, encodedBytes=5095),
            dict(current, decodedFrames=22),
            dict(current, connections=2),
            dict(current, encodedChunks=10),
        )
        for insufficient in insufficient_cases:
            with self.subTest(insufficient=insufficient):
                failed, _ = gate.ai_progress(
                    before,
                    insufficient,
                    minimum_encoded_bytes=4096,
                    minimum_decoded_frames=3,
                    active_observed=True,
                    codec_observed=True,
                )
                self.assertFalse(failed)

    def test_safe_marker_log_excludes_unrelated_log_lines(self) -> None:
        output = (
            "UNRELATED sourceId=private-source sessionId=private-session\n"
            + valid_log()
            + "\nUNRELATED VISIONFLOW_DJI_BRIDGE_KEY=private-key"
        )

        evidence = gate.safe_marker_log(output)

        self.assertIn("MSDK_REGISTER_SUCCESS", evidence)
        self.assertIn("MSDK_ENCODED_STREAM_PROGRESS", evidence)
        self.assertNotIn("private-source", evidence)
        self.assertNotIn("private-session", evidence)
        self.assertNotIn("private-key", evidence)

    def test_default_mode_waits_without_adb_secret_or_network_access(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            completed = subprocess.CompletedProcess(
                args=["git"],
                returncode=0,
                stdout="",
            )
            argv = [str(GATE_PATH), "--repo-root", str(root)]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(gate, "capture", return_value=completed) as capture,
                mock.patch.object(
                    gate,
                    "resolve_bridge_key",
                    side_effect=AssertionError("bridge key must not be resolved"),
                ),
                mock.patch.object(
                    gate,
                    "read_dji_status",
                    side_effect=AssertionError("network must not be accessed"),
                ),
                mock.patch.object(
                    gate.shutil,
                    "which",
                    side_effect=AssertionError("ADB must not be resolved"),
                ),
            ):
                result = gate.main()

            self.assertEqual(result, 0)
            self.assertEqual(capture.call_count, 1)
            self.assertEqual(capture.call_args.args[0][0], "git")
            summaries = list(
                (root / "artifacts" / "phase3-dji-physical-stream").glob(
                    "*/summary.json"
                )
            )
            self.assertEqual(len(summaries), 1)
            summary_text = summaries[0].read_text(encoding="utf-8")
            summary = json.loads(summary_text)
            self.assertEqual(summary["status"], "WAIT")
            self.assertEqual(summary["ai"]["bridgeKeySource"], "NOT_RESOLVED")
            self.assertFalse(summary["ai"]["bridgeKeyValueRecorded"])
            self.assertNotIn("private-source", summary_text)
            self.assertNotIn("private-session", summary_text)


if __name__ == "__main__":
    unittest.main()
