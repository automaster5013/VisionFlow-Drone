from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE_PATH = ROOT / "scripts" / "phase3-dji-simulator" / "phase3_dji_msdk_registration_gate.py"
SPEC = importlib.util.spec_from_file_location("phase3_dji_msdk_registration_gate", GATE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)

class Phase3DjiMsdkRegistrationGateTests(unittest.TestCase):
    def test_parse_devices_ignores_adb_daemon_noise(self) -> None:
        output = """* daemon not running; starting now at tcp:5037
* daemon started successfully
List of devices attached
R3CN8062SCX\tdevice product:c2qksw model:SM_N986N
192.168.45.197:5555\tdevice product:c2qksw model:SM_N986N
"""
        self.assertEqual(gate.parse_devices(output), [
            {"serial": "R3CN8062SCX", "state": "device"},
            {"serial": "192.168.45.197:5555", "state": "device"},
        ])

    def test_parse_devices_accepts_space_aligned_long_listing(self) -> None:
        output = """List of devices attached
R3CN8062SCX            device product:c2qksw model:SM_N986N device:c2q transport_id:2
192.168.45.197:5555    device product:c2qksw model:SM_N986N device:c2q transport_id:3
"""
        self.assertEqual(gate.parse_devices(output), [
            {"serial": "R3CN8062SCX", "state": "device"},
            {"serial": "192.168.45.197:5555", "state": "device"},
        ])

    def test_registration_log_passes_in_required_order(self) -> None:
        output = """
I/VisionFlowDJI: MSDK_INIT_START
I/VisionFlowDJI: MSDK_INIT_PROCESS event=START_TO_INITIALIZE progress=0
I/VisionFlowDJI: MSDK_INITIALIZE_COMPLETE
I/VisionFlowDJI: MSDK_REGISTER_APP_REQUESTED
I/VisionFlowDJI: MSDK_REGISTER_SUCCESS
"""
        result = gate.evaluate_registration_log(output)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["missingMarkers"], [])

    def test_registration_failure_marker_fails(self) -> None:
        result = gate.evaluate_registration_log("MSDK_INIT_START\nMSDK_REGISTER_FAILURE error=test\n")
        self.assertEqual(result["status"], "FAIL")

    def test_registration_log_reports_missing_markers(self) -> None:
        result = gate.evaluate_registration_log("MSDK_INIT_START\n")
        self.assertEqual(result["status"], "PENDING")
        self.assertIn("MSDK_REGISTER_SUCCESS", result["missingMarkers"])

    def test_registration_log_rejects_out_of_order_markers(self) -> None:
        output = """
MSDK_REGISTER_SUCCESS
MSDK_INIT_START
MSDK_INITIALIZE_COMPLETE
MSDK_REGISTER_APP_REQUESTED
"""
        result = gate.evaluate_registration_log(output)
        self.assertEqual(result["status"], "FAIL")

if __name__ == "__main__":
    unittest.main()
