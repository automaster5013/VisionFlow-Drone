from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.visionflow_migration_handoff import create_handoff, sha256_file
from scripts.visionflow_transfer_package import (
    CONFIRMATION,
    ARCHIVE_ROOT,
    TransferPackageError,
    create_transfer_package,
    ensure_backup_manifest_safe,
    verify_transfer_package_file,
)


NOW = datetime(2026, 7, 23, 6, 0, tzinfo=timezone.utc)


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_sidecar(path: Path) -> Path:
    sidecar = path.with_suffix(".sha256")
    sidecar.write_text(f"{sha256_file(path)}  {path.name}\n", encoding="utf-8")
    return sidecar


def create_backup(path: Path) -> None:
    sql = b"CREATE TABLE drone(id BIGINT);\n"
    manifest = {
        "schemaVersion": 1,
        "project": "visionflow",
        "createdAt": (NOW - timedelta(hours=3)).isoformat(),
        "database": {
            "name": "visionflow",
            "dumpPath": "database/visionflow.sql",
        },
        "files": [
            {
                "path": "database/visionflow.sql",
                "sizeBytes": len(sql),
                "sha256": sha(sql),
            }
        ],
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("database/visionflow.sql", sql)
        archive.writestr(
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )


def create_source(path: Path) -> tuple[str, str]:
    source = b"services:\n  mysql:\n    image: mysql:8.4\n"
    manifest = {
        "schemaVersion": 1,
        "project": "visionflow",
        "operation": "PORTABLE_SOURCE_RELEASE",
        "summary": {"includedFiles": 1, "includedBytes": len(source)},
        "files": [
            {
                "path": "compose.yaml",
                "sizeBytes": len(source),
                "sha256": sha(source),
            }
        ],
        "excluded": [],
        "safety": {},
    }
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("VisionFlow-Drone/compose.yaml", source)
        archive.writestr("VisionFlow-Drone/README-MIGRATION.md", "migration")
        archive.writestr("VisionFlow-Drone/SOURCE_MANIFEST.json", manifest_bytes)
    write_sidecar(path)
    return sha256_file(path), sha(manifest_bytes)


def create_evidence(path: Path, backup: Path) -> None:
    readme = b"release evidence"
    mobile = b'{"status":"SMARTPHONE_E2E_PASS"}'
    manifest = {
        "schemaVersion": 1,
        "project": "visionflow",
        "scope": "SECOND_PROJECT_DIGITAL_TWIN",
        "operation": "RELEASE_EVIDENCE_BUNDLE",
        "readiness": {"status": "READY_WITH_DEFERRED"},
        "evidence": [
            {
                "key": "verified-backup",
                "sourcePath": backup.relative_to(path.parents[2]).as_posix(),
                "sourceSizeBytes": backup.stat().st_size,
                "sourceSha256": sha256_file(backup),
                "included": False,
                "archivePath": None,
            },
            {
                "key": "smartphone-real-sensor-https",
                "sourcePath": "artifacts/mobile-readiness/mobile.json",
                "sourceSizeBytes": len(mobile),
                "sourceSha256": sha(mobile),
                "included": True,
                "archivePath": "evidence/smartphone-real-sensor-https.json",
            },
        ],
        "includedFiles": [
            {
                "archivePath": "README.md",
                "sizeBytes": len(readme),
                "sha256": sha(readme),
            },
            {
                "archivePath": "evidence/smartphone-real-sensor-https.json",
                "sizeBytes": len(mobile),
                "sha256": sha(mobile),
            },
        ],
        "excludedContent": [],
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("README.md", readme)
        archive.writestr("evidence/smartphone-real-sensor-https.json", mobile)
        archive.writestr(
            "evidence-manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )
    write_sidecar(path)


def create_baseline(path: Path, source_sha: str, manifest_sha: str) -> None:
    profile = {
        "schemaVersion": 1,
        "project": "visionflow",
        "operation": "MACHINE_READINESS_PROFILE",
        "profileId": "11111111-1111-4111-8111-111111111111",
        "role": "baseline",
        "status": "BASELINE_READY_WITH_DEFERRED",
        "summary": {"blocking": 0},
        "sourceIdentity": {
            "status": "PASS",
            "mode": "ARCHIVE",
            "archiveSha256": source_sha,
            "manifestSha256": manifest_sha,
            "fileCount": 1,
        },
    }
    path.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    path.with_suffix(".html").write_text(
        "<html><body>BASELINE_READY_WITH_DEFERRED</body></html>",
        encoding="utf-8",
    )
    write_sidecar(path)


def create_readiness(path: Path, handoff: Path, *, generated_at: datetime) -> None:
    status = "TRANSFER_READY_WITH_DEFERRED"
    report = {
        "schemaVersion": 1,
        "project": "visionflow",
        "scope": "SECOND_PROJECT_DIGITAL_TWIN",
        "operation": "TRANSFER_READINESS_GATE",
        "generatedAt": generated_at.isoformat(),
        "status": status,
        "handoff": {
            "path": handoff.relative_to(path.parents[2]).as_posix(),
            "sha256": sha256_file(handoff),
            "smartphoneE2eStatus": "PASS",
        },
        "checks": [{"key": "handoff-identity", "status": "PASS"}],
        "summary": {"checks": 1, "passed": 1, "blocking": 0},
        "safety": {
            "readOnlyInputs": True,
            "databaseMutation": False,
            "dockerStarted": False,
            "externalTransferPerformed": False,
        },
    }
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    path.with_suffix(".html").write_text(
        f"<html><body>{status}</body></html>",
        encoding="utf-8",
    )
    write_sidecar(path)


class TransferPackageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        for relative in (
            "artifacts/source-release",
            "artifacts/release-evidence",
            "artifacts/machine-readiness",
            "artifacts/migration-handoff",
            "artifacts/transfer-readiness",
            "artifacts/transfer-package",
            "backups",
        ):
            (self.root / relative).mkdir(parents=True)
        self.backup = self.root / "backups/visionflow-backup-20260723T010000Z.zip"
        create_backup(self.backup)
        source = self.root / "artifacts/source-release/visionflow-source-release-20260723T020000Z.zip"
        source_sha, manifest_sha = create_source(source)
        evidence = self.root / "artifacts/release-evidence/visionflow-release-evidence-20260723T030000Z.zip"
        create_evidence(evidence, self.backup)
        baseline = self.root / "artifacts/machine-readiness/visionflow-machine-baseline-20260723T040000Z.json"
        create_baseline(baseline, source_sha, manifest_sha)
        self.handoff, _, _ = create_handoff(
            self.root,
            output_root=self.root / "artifacts/migration-handoff",
            now=NOW - timedelta(hours=2),
        )
        self.readiness = (
            self.root
            / "artifacts/transfer-readiness/visionflow-transfer-readiness-20260723T050000Z.json"
        )
        create_readiness(
            self.readiness,
            self.handoff,
            generated_at=NOW - timedelta(hours=1),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def create(self):
        return create_transfer_package(
            self.root,
            readiness_value=None,
            handoff_value=None,
            backup_value=None,
            output_root=self.root / "artifacts/transfer-package",
            max_readiness_age_hours=24,
            confirmation=CONFIRMATION,
            now=NOW,
        )

    def test_create_and_verify_transfer_package(self) -> None:
        bundle, sidecar, manifest = self.create()
        self.assertTrue(bundle.is_file())
        self.assertTrue(sidecar.is_file())
        self.assertEqual("TRANSFER_PACKAGE_READY_WITH_DEFERRED", manifest["status"])
        verified_path, verified = verify_transfer_package_file(self.root, str(bundle))
        self.assertEqual(bundle, verified_path)
        self.assertEqual(manifest, verified)
        self.assertTrue(verified["safety"]["containsOperationalDatabaseBackup"])
        self.assertEqual("PASS", verified["handoff"]["smartphoneE2eStatus"])
        self.assertEqual(
            "PASS",
            verified["transferReadiness"]["smartphoneE2eStatus"],
        )

    def test_package_contains_only_expected_categories(self) -> None:
        bundle, _, _ = self.create()
        with zipfile.ZipFile(bundle) as archive:
            names = set(archive.namelist())
        self.assertIn(f"{ARCHIVE_ROOT}/TRANSFER_PACKAGE_MANIFEST.json", names)
        self.assertTrue(any("/database/visionflow-backup-" in name for name in names))
        self.assertFalse(
            any(
                Path(name).name.lower().startswith(".env")
                or Path(name).suffix.lower() in {".pt", ".pem", ".key"}
                for name in names
            )
        )

    def test_create_requires_explicit_backup_confirmation(self) -> None:
        with self.assertRaisesRegex(TransferPackageError, CONFIRMATION):
            create_transfer_package(
                self.root,
                readiness_value=None,
                handoff_value=None,
                backup_value=None,
                output_root=self.root / "artifacts/transfer-package",
                max_readiness_age_hours=24,
                confirmation="",
                now=NOW,
            )

    def test_stale_readiness_is_rejected(self) -> None:
        create_readiness(
            self.readiness,
            self.handoff,
            generated_at=NOW - timedelta(hours=25),
        )
        with self.assertRaisesRegex(TransferPackageError, "유효 범위"):
            self.create()

    def test_blocked_readiness_is_rejected(self) -> None:
        report = json.loads(self.readiness.read_text(encoding="utf-8-sig"))
        report["status"] = "BLOCKED"
        report["summary"]["blocking"] = 1
        self.readiness.write_text(json.dumps(report), encoding="utf-8-sig")
        self.readiness.with_suffix(".html").write_text(
            "<html><body>BLOCKED</body></html>",
            encoding="utf-8",
        )
        write_sidecar(self.readiness)
        with self.assertRaisesRegex(TransferPackageError, "패키징 조건"):
            self.create()

    def test_changed_backup_is_rejected(self) -> None:
        with self.backup.open("ab") as stream:
            stream.write(b"changed")
        with self.assertRaisesRegex(TransferPackageError, "크기|SHA-256"):
            self.create()

    def test_sensitive_backup_manifest_path_is_rejected(self) -> None:
        with self.assertRaisesRegex(TransferPackageError, "이관 금지"):
            ensure_backup_manifest_safe(
                {"files": [{"path": "files/backend-data/rootCA-key.pem"}]}
            )

    def test_tampered_outer_package_is_rejected(self) -> None:
        bundle, _, _ = self.create()
        with bundle.open("ab") as stream:
            stream.write(b"tampered")
        with self.assertRaisesRegex(TransferPackageError, "sidecar와 다릅니다"):
            verify_transfer_package_file(self.root, str(bundle))

    def test_tampered_inner_file_is_rejected_with_new_outer_sidecar(self) -> None:
        bundle, _, _ = self.create()
        replacement = bundle.with_suffix(".replacement.zip")
        with zipfile.ZipFile(bundle, "r") as source, zipfile.ZipFile(
            replacement,
            "w",
            zipfile.ZIP_DEFLATED,
        ) as target:
            for info in source.infolist():
                value = source.read(info.filename)
                if info.filename == f"{ARCHIVE_ROOT}/README.md":
                    value = b"changed"
                target.writestr(info.filename, value)
        os.replace(replacement, bundle)
        write_sidecar(bundle)
        with self.assertRaisesRegex(TransferPackageError, "크기|SHA-256"):
            verify_transfer_package_file(self.root, str(bundle))

    def test_output_outside_artifacts_is_rejected(self) -> None:
        with self.assertRaisesRegex(TransferPackageError, "출력 폴더"):
            create_transfer_package(
                self.root,
                readiness_value=None,
                handoff_value=None,
                backup_value=None,
                output_root=self.root / "outside",
                max_readiness_age_hours=24,
                confirmation=CONFIRMATION,
                now=NOW,
            )

    def test_newest_invalid_readiness_does_not_fall_back(self) -> None:
        invalid = (
            self.root
            / "artifacts/transfer-readiness/visionflow-transfer-readiness-20260723T055900Z.json"
        )
        invalid.write_text("not-json", encoding="utf-8")
        invalid.with_suffix(".html").write_text("not-json", encoding="utf-8")
        write_sidecar(invalid)
        newer = self.readiness.stat().st_mtime_ns + 2_000_000_000
        os.utime(invalid, ns=(newer, newer))
        with self.assertRaisesRegex(TransferPackageError, "JSON 형식"):
            self.create()


if __name__ == "__main__":
    unittest.main()
