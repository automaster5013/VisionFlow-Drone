from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from scripts.visionflow_retention import (
    RetentionError,
    load_audit_report,
    quarantine_candidates,
    restore_quarantine,
)


class VisionFlowRetentionTest(unittest.TestCase):
    def create_backup(self, root: Path, now: datetime) -> Path:
        backup = root / "backups" / "visionflow-backup.zip"
        backup.parent.mkdir(parents=True, exist_ok=True)
        sql = b"CREATE TABLE drone(id BIGINT);\n"
        manifest = {
            "schemaVersion": 1,
            "project": "visionflow",
            "createdAt": now.isoformat(),
            "database": {
                "name": "visionflow",
                "dumpPath": "database/visionflow.sql",
            },
            "files": [
                {
                    "path": "database/visionflow.sql",
                    "sizeBytes": len(sql),
                    "sha256": hashlib.sha256(sql).hexdigest(),
                }
            ],
        }
        with zipfile.ZipFile(backup, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr("database/visionflow.sql", sql)
        return backup

    def create_candidate(self, root: Path, now: datetime, age_days: int = 20) -> Path:
        candidate = root / "artifacts" / "ai-output" / "old.mp4"
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_bytes(b"old-video")
        modified = (now - timedelta(days=age_days)).timestamp()
        os.utime(candidate, (modified, modified))
        return candidate

    def create_audit(
        self,
        root: Path,
        now: datetime,
        candidate: Path,
        *,
        status: str = "HEALTHY",
        expected_size: int | None = None,
    ) -> Path:
        audit = root / "artifacts" / "storage-audit" / "run" / "storage-audit.json"
        audit.parent.mkdir(parents=True, exist_ok=True)
        size = candidate.stat().st_size if expected_size is None else expected_size
        report = {
            "schemaVersion": 1,
            "project": "visionflow",
            "generatedAt": now.isoformat(),
            "status": status,
            "disk": {"root": str(root)},
            "retention": {
                "dryRunOnly": True,
                "policy": {
                    "aiOutputDays": 14,
                    "backupDays": 30,
                    "reportDays": 30,
                    "minimumBackups": 1,
                },
                "candidateCount": 1,
                "candidates": [
                    {
                        "category": "ai-output",
                        "path": candidate.relative_to(root).as_posix(),
                        "sizeBytes": size,
                        "ageDays": 20,
                        "reason": "AI 출력 보존기간 초과",
                    }
                ],
            },
        }
        audit.write_text(json.dumps(report), encoding="utf-8")
        return audit

    def test_dry_run_verifies_everything_without_moving_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            now = datetime.now(timezone.utc)
            candidate = self.create_candidate(root, now)
            audit = self.create_audit(root, now, candidate)
            backup = self.create_backup(root, now)

            result_path, result = quarantine_candidates(
                root,
                audit,
                backup,
                max_audit_age_hours=24,
                max_backup_age_days=7,
                apply=False,
                confirmation="",
                output_root=root / "artifacts/retention-quarantine",
                now=now,
            )

            self.assertEqual(result["status"], "DRY_RUN_COMPLETE")
            self.assertTrue(result_path.is_file())
            self.assertTrue(candidate.is_file())

    def test_apply_moves_to_quarantine_and_restore_returns_original(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            now = datetime.now(timezone.utc)
            candidate = self.create_candidate(root, now)
            audit = self.create_audit(root, now, candidate)
            backup = self.create_backup(root, now)

            manifest_path, manifest = quarantine_candidates(
                root,
                audit,
                backup,
                max_audit_age_hours=24,
                max_backup_age_days=7,
                apply=True,
                confirmation="QUARANTINE",
                output_root=root / "artifacts/retention-quarantine",
                now=now,
            )

            self.assertEqual(manifest["status"], "COMPLETED")
            self.assertFalse(candidate.exists())
            quarantine_file = manifest_path.parent / manifest["files"][0]["quarantinePath"]
            self.assertTrue(quarantine_file.is_file())

            result_path = restore_quarantine(root, manifest_path, "RESTORE_FILES")

            self.assertTrue(result_path.is_file())
            self.assertTrue(candidate.is_file())
            self.assertFalse(quarantine_file.exists())
            self.assertEqual(candidate.read_bytes(), b"old-video")

    def test_apply_requires_confirmation_before_move(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            now = datetime.now(timezone.utc)
            candidate = self.create_candidate(root, now)
            audit = self.create_audit(root, now, candidate)
            backup = self.create_backup(root, now)

            with self.assertRaisesRegex(RetentionError, "--confirm QUARANTINE"):
                quarantine_candidates(
                    root,
                    audit,
                    backup,
                    max_audit_age_hours=24,
                    max_backup_age_days=7,
                    apply=True,
                    confirmation="",
                    output_root=root / "artifacts/retention-quarantine",
                    now=now,
                )
            self.assertTrue(candidate.exists())

    def test_changed_candidate_blocks_entire_operation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            now = datetime.now(timezone.utc)
            candidate = self.create_candidate(root, now)
            audit = self.create_audit(
                root,
                now,
                candidate,
                expected_size=candidate.stat().st_size + 1,
            )
            backup = self.create_backup(root, now)

            with self.assertRaisesRegex(RetentionError, "재검증을 통과하지 못한"):
                quarantine_candidates(
                    root,
                    audit,
                    backup,
                    max_audit_age_hours=24,
                    max_backup_age_days=7,
                    apply=True,
                    confirmation="QUARANTINE",
                    output_root=root / "artifacts/retention-quarantine",
                    now=now,
                )
            self.assertTrue(candidate.exists())

    def test_partial_move_failure_rolls_back_already_moved_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            now = datetime.now(timezone.utc)
            first = self.create_candidate(root, now)
            second = root / "artifacts" / "ai-output" / "second.mp4"
            second.write_bytes(b"second-video")
            modified = (now - timedelta(days=20)).timestamp()
            os.utime(second, (modified, modified))
            audit = self.create_audit(root, now, first)
            report = json.loads(audit.read_text(encoding="utf-8"))
            report["retention"]["candidates"].append(
                {
                    "category": "ai-output",
                    "path": second.relative_to(root).as_posix(),
                    "sizeBytes": second.stat().st_size,
                    "ageDays": 20,
                    "reason": "AI 출력 보존기간 초과",
                }
            )
            report["retention"]["candidateCount"] = 2
            audit.write_text(json.dumps(report), encoding="utf-8")
            backup = self.create_backup(root, now)
            real_move = __import__("shutil").move
            forward_moves = 0

            def flaky_move(source: str, destination: str) -> str:
                nonlocal forward_moves
                source_path = Path(source)
                destination_path = Path(destination)
                is_forward = "ai-output" in source_path.parts and "files" in destination_path.parts
                if is_forward:
                    forward_moves += 1
                    if forward_moves == 2:
                        raise OSError("simulated move failure")
                return real_move(source, destination)

            with mock.patch("scripts.visionflow_retention.shutil.move", side_effect=flaky_move):
                with self.assertRaisesRegex(RetentionError, "격리 이동 실패"):
                    quarantine_candidates(
                        root,
                        audit,
                        backup,
                        max_audit_age_hours=24,
                        max_backup_age_days=7,
                        apply=True,
                        confirmation="QUARANTINE",
                        output_root=root / "artifacts/retention-quarantine",
                        now=now,
                    )
            self.assertTrue(first.is_file())
            self.assertTrue(second.is_file())

    def test_critical_audit_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            now = datetime.now(timezone.utc)
            candidate = self.create_candidate(root, now)
            audit = self.create_audit(root, now, candidate, status="CRITICAL")

            with self.assertRaisesRegex(RetentionError, "CRITICAL"):
                load_audit_report(
                    audit,
                    root,
                    max_age_hours=24,
                    now=now,
                )


if __name__ == "__main__":
    unittest.main()
