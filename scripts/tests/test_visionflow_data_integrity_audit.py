from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import visionflow_data_integrity_audit as audit


class DataIntegrityAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = json.loads(
            (SCRIPT_DIR / "visionflow_data_integrity_policy.json").read_text(
                encoding="utf-8"
            )
        )

    def test_sql_guard_accepts_select_and_blocks_mutation(self) -> None:
        self.assertEqual(audit.validate_select("SELECT 1;"), "SELECT 1")
        with self.assertRaises(audit.AuditError):
            audit.validate_select("UPDATE drone SET name='x'")
        with self.assertRaises(audit.AuditError):
            audit.validate_select("SELECT 1; SELECT 2")

    @mock.patch.object(audit, "run_command")
    def test_mysql_query_forces_read_only_transaction(self, run_command: mock.Mock) -> None:
        run_command.return_value = "7"
        rows = audit.mysql_query("visionflow-mysql", "SELECT COUNT(*) FROM drone")
        self.assertEqual(rows, [["7"]])
        arguments = run_command.call_args.args[0]
        audit_sql = next(
            value for value in arguments if value.startswith("VISIONFLOW_AUDIT_SQL=")
        )
        self.assertIn("SET SESSION TRANSACTION READ ONLY", audit_sql)
        self.assertIn("START TRANSACTION READ ONLY", audit_sql)
        self.assertIn("SELECT COUNT(*) FROM drone", audit_sql)

    def test_database_collection_and_healthy_evaluation(self) -> None:
        def query(sql: str) -> list[list[str]]:
            if sql == "SELECT DATABASE(), VERSION()":
                return [["visionflow", "8.4.0"]]
            if "information_schema.TABLES" in sql:
                return [[name] for name in sorted(audit.EXPECTED_TABLES)]
            if "UNION ALL" in sql:
                return [[key, "0"] for key in audit.DATABASE_RULES]
            if "snapshot_file_name" in sql:
                return []
            raise AssertionError(sql)

        database, counts, references = audit.collect_database(query)
        self.assertEqual(database["missingRequiredTables"], [])
        self.assertEqual(references, [])
        with tempfile.TemporaryDirectory() as directory:
            snapshots, snapshot_counts = audit.inspect_snapshots(
                Path(directory), [], "artifacts/backend-data/ai-snapshots"
            )
        status, rules = audit.evaluate(
            self.policy,
            database,
            {**counts, **snapshot_counts},
            snapshots,
        )
        self.assertEqual(status, "DATA_INTEGRITY_HEALTHY")
        self.assertTrue(all(row["status"] == "PASS" for row in rules))

    def test_critical_relationship_finding_blocks(self) -> None:
        counts = {key: 0 for key in audit.DATABASE_RULES}
        counts["session-orphan-ai-event"] = 1
        counts.update(
            {
                "snapshot-invalid-reference": 0,
                "snapshot-missing-file": 0,
                "snapshot-size-mismatch": 0,
                "snapshot-duplicate-reference": 0,
                "snapshot-unreferenced-file": 0,
            }
        )
        status, _ = audit.evaluate(
            self.policy,
            {"missingRequiredTables": []},
            counts,
            {},
        )
        self.assertEqual(status, "DATA_INTEGRITY_BLOCKED")

    def test_multiple_active_sessions_for_one_drone_blocks(self) -> None:
        counts = {key: 0 for key in audit.DATABASE_RULES}
        counts["flight-session-multiple-active-per-drone"] = 1
        counts.update(
            {
                "snapshot-invalid-reference": 0,
                "snapshot-missing-file": 0,
                "snapshot-size-mismatch": 0,
                "snapshot-duplicate-reference": 0,
                "snapshot-unreferenced-file": 0,
            }
        )
        status, rules = audit.evaluate(
            self.policy,
            {"missingRequiredTables": []},
            counts,
            {},
        )
        self.assertEqual(status, "DATA_INTEGRITY_BLOCKED")
        active_rule = next(
            row
            for row in rules
            if row["key"] == "flight-session-multiple-active-per-drone"
        )
        self.assertEqual(active_rule["status"], "CRITICAL")

    def test_unreferenced_snapshot_is_advisory(self) -> None:
        counts = {key: 0 for key in audit.DATABASE_RULES}
        counts.update(
            {
                "snapshot-invalid-reference": 0,
                "snapshot-missing-file": 0,
                "snapshot-size-mismatch": 0,
                "snapshot-duplicate-reference": 0,
                "snapshot-unreferenced-file": 1,
            }
        )
        status, _ = audit.evaluate(
            self.policy,
            {"missingRequiredTables": []},
            counts,
            {},
        )
        self.assertEqual(status, "DATA_INTEGRITY_ADVISORY")

    def test_snapshot_reconciliation_does_not_collect_plain_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshots = root / "artifacts/backend-data/ai-snapshots"
            snapshots.mkdir(parents=True)
            (snapshots / "unreferenced.jpg").write_bytes(b"abc")
            details, counts = audit.inspect_snapshots(
                root,
                [
                    {
                        "eventId": 7,
                        "fileName": "missing.jpg",
                        "expectedSizeBytes": 10,
                    }
                ],
                "artifacts/backend-data/ai-snapshots",
            )
        self.assertEqual(counts["snapshot-missing-file"], 1)
        self.assertEqual(counts["snapshot-unreferenced-file"], 1)
        self.assertFalse(details["fileNamesCollected"])
        serialized = json.dumps(details)
        self.assertNotIn("missing.jpg", serialized)
        self.assertNotIn("unreferenced.jpg", serialized)


if __name__ == "__main__":
    unittest.main()
