from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import visionflow_data_integrity_audit as audit
import visionflow_data_integrity_repair as repair


class DataIntegrityRepairTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = json.loads(
            (SCRIPT_DIR / "visionflow_data_integrity_repair_policy.json").read_text(
                encoding="utf-8"
            )
        )

    def make_ready_state(self) -> dict:
        expected = self.policy["expected"]
        missing = []
        for index, item in enumerate(expected["recoverableSessions"], start=1):
            missing.append(
                {
                    "sessionId": str(uuid.UUID(int=index)),
                    "hash": item["hash"],
                    "eventRows": item["rows"],
                    "alertRows": item["rows"],
                    "incidentRows": item["rows"],
                    "currentDroneReferences": 0,
                    "distinctDrones": 1,
                    "minDroneId": item["droneId"],
                    "maxDroneId": item["droneId"],
                    "firstObservedAt": "2026-07-24 00:00:00",
                    "lastObservedAt": "2026-07-24 01:00:00",
                    "droneStatus": None,
                }
            )
        stale = expected["staleDronePointer"]
        missing.append(
            {
                "sessionId": str(uuid.UUID(int=100)),
                "hash": stale["hash"],
                "eventRows": 0,
                "alertRows": 0,
                "incidentRows": 0,
                "currentDroneReferences": stale["currentReferences"],
                "distinctDrones": 1,
                "minDroneId": stale["droneId"],
                "maxDroneId": stale["droneId"],
                "firstObservedAt": None,
                "lastObservedAt": None,
                "droneStatus": stale["droneStatus"],
            }
        )
        existing = [
            {
                "sessionId": str(uuid.UUID(int=200 + index)),
                "hash": item["hash"],
                "droneId": item["droneId"],
                "status": item["status"],
                "startedAt": "2026-07-24 00:00:00",
                "endedAt": "2026-07-24 00:01:00",
                "aiEvents": item["aiEvents"],
            }
            for index, item in enumerate(expected["existingSessions"])
        ]
        return {
            "database": {"missingRequiredTables": []},
            "databaseCounts": repair.expected_finding_counts(self.policy),
            "totals": {
                key: expected[key]
                for key in (
                    "flightSessionRows",
                    "droneRows",
                    "aiEventRows",
                    "aiAlertRows",
                    "incidentRows",
                )
            },
            "missingSessions": missing,
            "existingSessions": existing,
        }

    def test_ready_profile_is_accepted(self) -> None:
        self.assertEqual(
            repair.evaluate_profile(self.policy, self.make_ready_state()), []
        )

    def test_profile_drift_is_blocked(self) -> None:
        state = self.make_ready_state()
        state["missingSessions"][0]["eventRows"] += 1
        failures = repair.evaluate_profile(self.policy, state)
        self.assertTrue(any("content drift" in item for item in failures))

    def test_apply_sql_is_transactional_and_has_no_delete(self) -> None:
        sql = repair.build_apply_sql(self.policy, self.make_ready_state())
        self.assertIn("TRANSACTION ISOLATION LEVEL SERIALIZABLE", sql)
        self.assertIn("START TRANSACTION", sql)
        self.assertIn("INSERT INTO flight_session", sql)
        self.assertIn("UPDATE drone SET flight_session_id = NULL", sql)
        self.assertIn("COMMIT", sql)
        self.assertNotRegex(sql.upper(), r"\bDELETE\b")
        self.assertGreaterEqual(sql.count("visionflow_repair_guard_failed"), 10)

    def test_uuid_validation_blocks_non_uuid_identifier(self) -> None:
        self.assertEqual(
            repair.require_uuid("00000000-0000-0000-0000-000000000001"),
            "00000000-0000-0000-0000-000000000001",
        )
        with self.assertRaises(repair.RepairError):
            repair.require_uuid("not-a-session-id")

    def test_backup_contains_manual_rollback_but_no_credentials(self) -> None:
        state = self.make_ready_state()
        with tempfile.TemporaryDirectory() as directory:
            output = repair.create_backup(Path(directory), self.policy, state)
            before = (output / "before-state.json").read_text(encoding="utf-8")
            rollback = (output / "rollback.sql").read_text(encoding="utf-8")
        self.assertIn('"containsCredentials": false', before)
        self.assertNotIn("MYSQL_PASSWORD", before)
        self.assertIn("MANUAL ROLLBACK ONLY", rollback)
        self.assertIn("DELETE FROM flight_session", rollback)

    @mock.patch.object(subprocess, "run")
    def test_execute_apply_uses_container_credentials_without_values(
        self, run: mock.Mock
    ) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="1\nVISIONFLOW_RESULT:13:1\n1\n",
            stderr="",
        )
        inserted, updated = repair.execute_apply(
            "visionflow-mysql", "START TRANSACTION; COMMIT;"
        )
        self.assertEqual((inserted, updated), (13, 1))
        arguments = run.call_args.args[0]
        joined = " ".join(arguments)
        self.assertIn('MYSQL_PWD="$MYSQL_PASSWORD"', joined)
        self.assertNotRegex(joined, r"MYSQL_PWD=[^\"$]")

    def test_post_state_requires_zero_database_findings(self) -> None:
        expected = self.policy["expected"]
        state = {
            "missingSessions": [],
            "databaseCounts": {key: 0 for key in audit.DATABASE_RULES},
            "totals": {
                "flightSessionRows": 15,
                "droneRows": expected["droneRows"],
                "aiEventRows": expected["aiEventRows"],
                "aiAlertRows": expected["aiAlertRows"],
                "incidentRows": expected["incidentRows"],
            },
        }
        self.assertEqual(repair.verify_post_state(self.policy, state), [])
        state["databaseCounts"]["session-orphan-drone"] = 1
        self.assertTrue(repair.verify_post_state(self.policy, state))


if __name__ == "__main__":
    unittest.main()
