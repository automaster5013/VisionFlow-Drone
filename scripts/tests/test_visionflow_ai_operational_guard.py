from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import visionflow_ai_operational_guard as guard


class OperationalGuardDataIntegrityTest(unittest.TestCase):
    def make_report(self, status: str, *, read_only: bool = True) -> dict[str, object]:
        return {
            "status": status,
            "readOnly": read_only,
            "summary": {
                "databaseRules": 39,
                "snapshotRules": 5,
                "findings": 0 if status == "DATA_INTEGRITY_HEALTHY" else 1,
                "criticalRules": 1 if status == "DATA_INTEGRITY_BLOCKED" else 0,
                "advisoryRules": 1 if status == "DATA_INTEGRITY_ADVISORY" else 0,
            },
            "safety": {
                "databaseMutation": False,
                "containerMutation": False,
                "serviceRestart": False,
                "credentialValueCollection": False,
                "snapshotFileContentRead": False,
                "writesOnlyReports": True,
            },
        }

    def run_check(
        self,
        audit_status: str,
        exit_code: int,
        *,
        read_only: bool = True,
    ) -> guard.CheckResult:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / "scripts"
            scripts.mkdir()
            (scripts / "visionflow_data_integrity_audit.py").write_text(
                "# test fixture\n", encoding="utf-8"
            )
            guard_dir = root / "artifacts" / "operational-guard" / "guard-test"
            guard_dir.mkdir(parents=True)

            def fake_run(arguments: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                output = Path(arguments[arguments.index("--output") + 1])
                output.mkdir(parents=True)
                (output / "visionflow-data-integrity-audit.json").write_text(
                    json.dumps(
                        self.make_report(audit_status, read_only=read_only),
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(arguments, exit_code, "", "")

            with mock.patch.object(guard, "run", side_effect=fake_run):
                result = guard.check_data_integrity(root, guard_dir)
        return result

    def test_healthy_audit_maps_to_healthy(self) -> None:
        result = self.run_check("DATA_INTEGRITY_HEALTHY", 0)
        self.assertEqual(result.status, "HEALTHY")
        self.assertTrue(result.details["readOnlySafetyVerified"])
        self.assertEqual(result.details["databaseRules"], 39)
        self.assertEqual(result.details["snapshotRules"], 5)

    def test_advisory_audit_maps_to_warning(self) -> None:
        result = self.run_check("DATA_INTEGRITY_ADVISORY", 0)
        self.assertEqual(result.status, "WARNING")

    def test_blocked_audit_maps_to_critical(self) -> None:
        result = self.run_check("DATA_INTEGRITY_BLOCKED", 1)
        self.assertEqual(result.status, "CRITICAL")

    def test_non_read_only_report_is_critical(self) -> None:
        result = self.run_check("DATA_INTEGRITY_HEALTHY", 0, read_only=False)
        self.assertEqual(result.status, "CRITICAL")
        self.assertFalse(result.details["readOnlySafetyVerified"])

    def test_status_exit_code_mismatch_is_critical(self) -> None:
        result = self.run_check("DATA_INTEGRITY_HEALTHY", 1)
        self.assertEqual(result.status, "CRITICAL")

    def test_missing_audit_script_is_critical(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_dir = root / "artifacts" / "operational-guard" / "guard-test"
            report_dir.mkdir(parents=True)
            result = guard.check_data_integrity(root, report_dir)
        self.assertEqual(result.status, "CRITICAL")

    def test_guard_has_no_repair_execution_path(self) -> None:
        source = Path(guard.__file__).read_text(encoding="utf-8")
        self.assertNotIn("visionflow_data_integrity_repair", source)


if __name__ == "__main__":
    unittest.main()
