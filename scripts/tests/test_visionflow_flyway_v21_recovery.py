from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import visionflow_flyway_v21_recovery as recovery


def healthy_state() -> dict:
    return {
        "backendStatus": "exited",
        "history": [
            {
                "installedRank": 21,
                "version": "21",
                "description": "restrict drone history delete",
                "type": "SQL",
                "script": "V21__restrict_drone_history_delete.sql",
                "checksum": -439926118,
                "installedBy": "visionflow",
                "installedOn": "2026-08-02 16:06:00.000000",
                "executionTime": 30,
                "success": 0,
            }
        ],
        "constraints": {
            name: {"table": table, "deleteRule": delete_rule}
            for name, (table, delete_rule) in recovery.EXPECTED_CONSTRAINTS.items()
        },
        "databaseFindingCounts": {"sample": 0},
    }


class FlywayV21RecoveryTest(unittest.TestCase):
    def test_exact_failed_profile_is_ready(self) -> None:
        self.assertEqual(recovery.evaluate_state(healthy_state()), [])

    def test_partial_constraint_change_is_blocked(self) -> None:
        state = healthy_state()
        state["constraints"]["fk_flight_session_drone"][
            "deleteRule"
        ] = "RESTRICT"
        failures = recovery.evaluate_state(state)
        self.assertTrue(any("fk_flight_session_drone drift" in row for row in failures))

    def test_running_backend_is_blocked(self) -> None:
        state = healthy_state()
        state["backendStatus"] = "running"
        failures = recovery.evaluate_state(state)
        self.assertTrue(any("must be stopped" in row for row in failures))

    def test_repair_sql_changes_only_failed_flyway_metadata(self) -> None:
        sql = recovery.build_repair_sql().upper()
        self.assertIn("DELETE FROM FLYWAY_SCHEMA_HISTORY", sql)
        for table in (
            "DRONE ",
            "FLIGHT_SESSION ",
            "AI_INFERENCE_EVENT ",
            "AI_ALERT ",
            "INCIDENT ",
        ):
            self.assertNotIn(f"DELETE FROM {table}", sql)
        self.assertNotIn("ALTER TABLE", sql)
        self.assertNotIn("DROP TABLE", sql)


if __name__ == "__main__":
    unittest.main()
