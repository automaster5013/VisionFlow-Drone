from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "visionflow_maintenance_presentation_gate.py"
)
SPEC = importlib.util.spec_from_file_location(
    "visionflow_maintenance_presentation_gate",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

NOW = datetime(2026, 7, 26, 0, 0, tzinfo=timezone.utc)


class MaintenancePresentationGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.output = (
            self.root / "artifacts/maintenance-presentation-gate"
        )
        self.failures: set[str] = set()

    def runner(self, script, arguments, root):
        self.assertEqual(self.root, root)
        if script in self.failures:
            return 1, f"{script} failed", 20
        return 0, f"{script} passed", 10

    def run_gate(self):
        return MODULE.run_gate(
            self.root,
            drone_id=1,
            required_mode="ADVISORY",
            output_root=self.output,
            runner=self.runner,
            now=NOW,
        )

    def test_ready_gate_writes_utf8_json_and_html(self):
        report, json_path, html_path, exit_code = self.run_gate()

        self.assertEqual(0, exit_code)
        self.assertEqual(MODULE.READY_STATUS, report["status"])
        self.assertTrue(json_path.is_file())
        self.assertTrue(html_path.is_file())
        loaded = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual("ADVISORY", loaded["inputs"]["requiredMode"])
        self.assertFalse(loaded["safety"]["ownSha256SidecarCreated"])
        self.assertTrue(
            loaded["safety"]["childQuickCheckMayCreateSha256Sidecar"]
        )

    def test_maintenance_failure_is_classified(self):
        self.failures = {"visionflow_maintenance_acceptance.py"}

        report, _, _, exit_code = self.run_gate()

        self.assertEqual(1, exit_code)
        self.assertEqual(MODULE.BLOCKED_STATUS, report["status"])
        self.assertEqual(
            "MAINTENANCE_FLIGHT_GATE_FAILED",
            report["diagnosis"]["code"],
        )

    def test_presentation_failure_is_classified(self):
        self.failures = {"visionflow_presentation_quick_check.py"}

        report, _, _, _ = self.run_gate()

        self.assertEqual(
            "PRESENTATION_QUICK_CHECK_FAILED",
            report["diagnosis"]["code"],
        )

    def test_output_redacts_project_path_and_operator_key(self):
        def secret_runner(script, arguments, root):
            return (
                1,
                f"{root}\\log OPERATOR_1234567890abcdef1234567890",
                5,
            )

        report, json_path, _, _ = MODULE.run_gate(
            self.root,
            drone_id=1,
            required_mode=None,
            output_root=self.output,
            runner=secret_runner,
            now=NOW,
        )
        value = json_path.read_text(encoding="utf-8")

        self.assertNotIn(str(self.root), value)
        self.assertNotIn("OPERATOR_1234567890", value)
        self.assertIn("<REDACTED_OPERATOR_KEY>", value)
        self.assertFalse(report["safety"]["operatorKeysRecorded"])

    def test_output_outside_allowed_directory_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "OutputDirectory"):
            MODULE.run_gate(
                self.root,
                drone_id=1,
                required_mode=None,
                output_root=self.root / "outside",
                runner=self.runner,
                now=NOW,
            )


if __name__ == "__main__":
    unittest.main()
