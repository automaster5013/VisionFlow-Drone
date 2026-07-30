from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from scripts.visionflow_storage_audit import (
    build_parser,
    collect_database_audit,
    determine_status,
    generate_report,
    reconcile_snapshots,
    retention_candidates,
    scan_files,
    summarize_categories,
)


class VisionFlowStorageAuditTest(unittest.TestCase):
    def create_file(self, root: Path, relative: str, content: bytes, age_days: int) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        modified = (datetime.now(timezone.utc) - timedelta(days=age_days)).timestamp()
        os.utime(path, (modified, modified))
        return path

    def test_scan_and_category_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.create_file(root, "artifacts/ai-output/old.mp4", b"video", 20)
            self.create_file(root, "artifacts/backend-data/ai-snapshots/1.jpg", b"jpg", 1)

            records, warnings = scan_files(root, datetime.now(timezone.utc))
            categories = {row["category"]: row for row in summarize_categories(records)}

            self.assertEqual(warnings, [])
            self.assertEqual(len(records), 2)
            self.assertEqual(categories["ai-output"]["fileCount"], 1)
            self.assertEqual(categories["backend-data"]["totalBytes"], 3)

    @mock.patch("scripts.visionflow_storage_audit.mysql_query")
    def test_database_audit_parses_table_sizes_and_snapshot_references(
        self,
        query_mock: mock.Mock,
    ) -> None:
        query_mock.side_effect = [
            [["visionflow", "8.4.0"]],
            [["ai_inference_event", "12", "4096", "2048"]],
            [["1"]],
            [["7", "event-7.jpg", "1234"]],
        ]

        result = collect_database_audit("mysql-id", Path("."))

        self.assertTrue(result["available"])
        self.assertTrue(result["snapshotMetadataAvailable"])
        self.assertEqual(result["tables"][0]["totalBytes"], 6144)
        self.assertEqual(result["snapshotReferences"][0]["eventId"], 7)

    def test_retention_dry_run_protects_latest_backups(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.create_file(root, "backups/new-1.zip", b"1", 1)
            self.create_file(root, "backups/new-2.zip", b"2", 2)
            self.create_file(root, "backups/new-3.zip", b"3", 3)
            old_backup = self.create_file(root, "backups/old.zip", b"old", 60)
            old_video = self.create_file(root, "artifacts/ai-output/old.mp4", b"v", 20)
            records, _ = scan_files(root, datetime.now(timezone.utc))

            candidates = retention_candidates(
                records,
                ai_output_days=14,
                backup_days=30,
                report_days=30,
                minimum_backups=3,
            )
            paths = {candidate["path"] for candidate in candidates}

            self.assertIn(old_backup.relative_to(root).as_posix(), paths)
            self.assertIn(old_video.relative_to(root).as_posix(), paths)
            self.assertNotIn("backups/new-3.zip", paths)
            self.assertTrue(old_backup.exists())
            self.assertTrue(old_video.exists())

    def test_snapshot_reconciliation_finds_missing_orphan_and_size_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.create_file(
                root,
                "artifacts/backend-data/ai-snapshots/event-1.jpg",
                b"1234",
                1,
            )
            self.create_file(
                root,
                "artifacts/backend-data/ai-snapshots/orphan.jpg",
                b"orphan",
                1,
            )
            references = [
                {"eventId": 1, "fileName": "event-1.jpg", "expectedSizeBytes": 3},
                {"eventId": 2, "fileName": "event-2.jpg", "expectedSizeBytes": 5},
            ]

            result = reconcile_snapshots(root, references)

            self.assertEqual(len(result["missingFiles"]), 1)
            self.assertEqual(len(result["unreferencedFiles"]), 1)
            self.assertEqual(len(result["sizeMismatches"]), 1)

    def test_missing_snapshot_causes_critical_status(self) -> None:
        snapshots = {
            "missingFiles": [{"eventId": 1}],
            "invalidReferences": [],
            "sizeMismatches": [],
            "unreferencedFiles": [],
            "duplicateFileNames": [],
        }
        status, issues = determine_status(
            80.0,
            100,
            snapshots,
            warning_free_percent=20.0,
            critical_free_percent=10.0,
            warning_managed_bytes=1024,
        )
        self.assertEqual(status, "CRITICAL")
        self.assertTrue(any("없는 스냅샷" in issue for issue in issues))

    def test_filesystem_only_report_does_not_delete_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_video = self.create_file(root, "artifacts/ai-output/old.mp4", b"video", 20)
            parser = build_parser(root)
            args = parser.parse_args(
                [
                    "--root",
                    str(root),
                    "--filesystem-only",
                    "--output",
                    "reports",
                ]
            )

            output, report = generate_report(args)

            self.assertTrue(old_video.exists())
            self.assertTrue((output / "storage-audit.json").is_file())
            self.assertTrue((output / "storage-audit.html").is_file())
            self.assertTrue((output / "retention-candidates.csv").is_file())
            loaded = json.loads((output / "storage-audit.json").read_text(encoding="utf-8"))
            self.assertTrue(loaded["retention"]["dryRunOnly"])
            self.assertEqual(report["database"]["available"], False)


if __name__ == "__main__":
    unittest.main()
