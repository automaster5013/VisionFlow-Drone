from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import visionflow_system_traceability_audit as traceability


class SystemTraceabilityDeletePolicyTest(unittest.TestCase):
    def test_alter_table_replaces_create_table_delete_rule(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            migrations = (
                root
                / "02_backend"
                / "visionflow-api"
                / "src"
                / "main"
                / "resources"
                / "db"
                / "migration"
            )
            migrations.mkdir(parents=True)
            (migrations / "V1__create_tables.sql").write_text(
                """
                CREATE TABLE drone (id BIGINT PRIMARY KEY);
                CREATE TABLE flight_session (
                    session_id VARCHAR(36) PRIMARY KEY,
                    drone_id BIGINT NOT NULL,
                    CONSTRAINT fk_flight_session_drone
                        FOREIGN KEY (drone_id) REFERENCES drone (id)
                        ON DELETE CASCADE
                );
                """,
                encoding="utf-8",
            )
            (migrations / "V2__restrict_delete.sql").write_text(
                """
                ALTER TABLE flight_session
                    DROP FOREIGN KEY fk_flight_session_drone,
                    ADD CONSTRAINT fk_flight_session_drone
                        FOREIGN KEY (drone_id) REFERENCES drone (id)
                        ON DELETE RESTRICT;
                """,
                encoding="utf-8",
            )

            _, foreign_keys = traceability.parse_migrations(root)

        self.assertEqual(len(foreign_keys), 1)
        self.assertEqual(foreign_keys[0]["fromTable"], "flight_session")
        self.assertEqual(foreign_keys[0]["deleteRule"], "RESTRICT")
        self.assertEqual(foreign_keys[0]["source"], "V2__restrict_delete.sql")

    def test_current_drone_history_foreign_keys_are_restrict(self) -> None:
        root = SCRIPT_DIR.parent
        _, foreign_keys = traceability.parse_migrations(root)
        relations = {
            (item["fromTable"], item["fromColumn"]): item
            for item in foreign_keys
            if item["toTable"] == "drone" and item["toColumn"] == "id"
        }
        expected_sources = {
            ("drone_telemetry_history", "drone_id"): (
                "V21__restrict_drone_history_delete.sql"
            ),
            ("flight_session", "drone_id"): (
                "V21__restrict_drone_history_delete.sql"
            ),
            ("flight_quality_assessment", "drone_id"): (
                "V21__restrict_drone_history_delete.sql"
            ),
            ("maintenance_work_order", "drone_id"): (
                "V19__create_maintenance_work_order.sql"
            ),
        }

        self.assertEqual(set(relations), set(expected_sources))
        for relation, expected_source in expected_sources.items():
            with self.subTest(relation=relation):
                self.assertEqual(relations[relation]["deleteRule"], "RESTRICT")
                self.assertEqual(relations[relation]["source"], expected_source)


if __name__ == "__main__":
    unittest.main()
