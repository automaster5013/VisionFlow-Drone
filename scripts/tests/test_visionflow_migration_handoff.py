from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from scripts.visionflow_migration_handoff import (
    ARCHIVE_ROOT,
    HandoffError,
    create_handoff,
    sha256_file,
    verify_handoff_file,
)


NOW = datetime(2026, 7, 22, 6, 0, tzinfo=timezone.utc)


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_sidecar(path: Path) -> Path:
    sidecar = path.with_suffix(".sha256")
    sidecar.write_text(f"{sha256_file(path)}  {path.name}\n", encoding="utf-8")
    return sidecar


def create_source(path: Path) -> tuple[str, str]:
    source = b"services:\n  mysql:\n    image: mysql:8\n"
    manifest = {
        "schemaVersion": 1,
        "project": "visionflow",
        "operation": "PORTABLE_SOURCE_RELEASE",
        "summary": {"includedFiles": 1, "includedBytes": len(source)},
        "files": [
            {"path": "compose.yaml", "sizeBytes": len(source), "sha256": sha(source)}
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


def create_evidence(
    path: Path,
    *,
    readiness: str = "READY_WITH_DEFERRED",
    include_mobile: bool = True,
) -> None:
    readme = b"release evidence"
    mobile = b'{"status":"SMARTPHONE_E2E_PASS"}'
    evidence = [
        {
            "key": "verified-backup",
            "sourcePath": "backups/visionflow-backup.zip",
            "sourceSizeBytes": 1234,
            "sourceSha256": "a" * 64,
            "included": False,
            "archivePath": None,
        }
    ]
    included_files = [
        {"archivePath": "README.md", "sizeBytes": len(readme), "sha256": sha(readme)}
    ]
    if include_mobile:
        evidence.append(
            {
                "key": "smartphone-real-sensor-https",
                "sourcePath": "artifacts/mobile-readiness/mobile.json",
                "sourceSizeBytes": len(mobile),
                "sourceSha256": sha(mobile),
                "included": True,
                "archivePath": "evidence/smartphone-real-sensor-https.json",
            }
        )
        included_files.append(
            {
                "archivePath": "evidence/smartphone-real-sensor-https.json",
                "sizeBytes": len(mobile),
                "sha256": sha(mobile),
            }
        )
    manifest = {
        "schemaVersion": 1,
        "project": "visionflow",
        "scope": "SECOND_PROJECT_DIGITAL_TWIN",
        "operation": "RELEASE_EVIDENCE_BUNDLE",
        "readiness": {"status": readiness},
        "evidence": evidence,
        "includedFiles": included_files,
        "excludedContent": [],
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("README.md", readme)
        if include_mobile:
            archive.writestr(
                "evidence/smartphone-real-sensor-https.json",
                mobile,
            )
        archive.writestr(
            "evidence-manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2).encode(),
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
    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    path.with_suffix(".html").write_text(
        "<html><body>BASELINE_READY_WITH_DEFERRED</body></html>", encoding="utf-8"
    )
    write_sidecar(path)


class MigrationHandoffTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        for relative in (
            "artifacts/source-release",
            "artifacts/release-evidence",
            "artifacts/machine-readiness",
            "artifacts/migration-handoff",
        ):
            (self.root / relative).mkdir(parents=True)
        self.source = self.root / "artifacts/source-release/visionflow-source-release-20260722T050000Z.zip"
        source_sha, manifest_sha = create_source(self.source)
        self.evidence = self.root / "artifacts/release-evidence/visionflow-release-evidence-20260722T051000Z.zip"
        create_evidence(self.evidence)
        self.baseline = self.root / "artifacts/machine-readiness/visionflow-machine-baseline-20260722T052000Z.json"
        create_baseline(self.baseline, source_sha, manifest_sha)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def create(self):
        return create_handoff(
            self.root,
            output_root=self.root / "artifacts/migration-handoff",
            now=NOW,
        )

    def test_create_and_verify_safe_handoff(self) -> None:
        bundle, sidecar, manifest = self.create()
        self.assertTrue(bundle.is_file())
        self.assertTrue(sidecar.is_file())
        verified_bundle, verified = verify_handoff_file(self.root, str(bundle))
        self.assertEqual(bundle, verified_bundle)
        self.assertEqual(manifest, verified)
        self.assertFalse(manifest["verifiedMySqlBackup"]["included"])
        self.assertEqual("PASS", manifest["evidence"]["smartphoneE2eStatus"])
        with zipfile.ZipFile(bundle) as archive:
            names = set(archive.namelist())
        self.assertIn(f"{ARCHIVE_ROOT}/HANDOFF_MANIFEST.json", names)
        self.assertFalse(any(name.endswith((".sql", ".pt", ".env")) for name in names))

    def test_legacy_evidence_without_mobile_is_carried_as_deferred(self) -> None:
        create_evidence(self.evidence, include_mobile=False)
        _, _, manifest = self.create()
        self.assertEqual("DEFERRED", manifest["evidence"]["smartphoneE2eStatus"])

    def test_source_sidecar_mismatch_is_rejected(self) -> None:
        self.source.with_suffix(".sha256").write_text(f"{'0' * 64}  {self.source.name}\n")
        with self.assertRaisesRegex(HandoffError, "소스 ZIP SHA-256"):
            self.create()

    def test_evidence_sidecar_mismatch_is_rejected(self) -> None:
        self.evidence.with_suffix(".sha256").write_text(f"{'0' * 64}  {self.evidence.name}\n")
        with self.assertRaisesRegex(HandoffError, "증빙 ZIP SHA-256"):
            self.create()

    def test_baseline_sidecar_mismatch_is_rejected(self) -> None:
        self.baseline.with_suffix(".sha256").write_text(f"{'0' * 64}  {self.baseline.name}\n")
        with self.assertRaisesRegex(HandoffError, "baseline 프로필 SHA-256"):
            self.create()

    def test_baseline_source_identity_mismatch_is_rejected(self) -> None:
        profile = json.loads(self.baseline.read_text(encoding="utf-8-sig"))
        profile["sourceIdentity"]["manifestSha256"] = "f" * 64
        self.baseline.write_text(json.dumps(profile), encoding="utf-8-sig")
        write_sidecar(self.baseline)
        with self.assertRaisesRegex(HandoffError, "SOURCE_MANIFEST"):
            self.create()

    def test_blocked_release_evidence_is_rejected(self) -> None:
        create_evidence(self.evidence, readiness="BLOCKED")
        with self.assertRaisesRegex(HandoffError, "준비 상태"):
            self.create()

    def test_missing_baseline_html_is_rejected(self) -> None:
        self.baseline.with_suffix(".html").unlink()
        with self.assertRaisesRegex(HandoffError, "baseline HTML"):
            self.create()

    def test_newest_invalid_source_does_not_fall_back(self) -> None:
        invalid = self.source.parent / "visionflow-source-release-20260722T060000Z.zip"
        invalid.write_bytes(b"not-a-zip")
        write_sidecar(invalid)
        newer = self.source.stat().st_mtime_ns + 2_000_000_000
        os.utime(invalid, ns=(newer, newer))
        with self.assertRaisesRegex(HandoffError, "손상"):
            self.create()

    def test_tampered_outer_bundle_is_rejected(self) -> None:
        bundle, _, _ = self.create()
        with bundle.open("ab") as stream:
            stream.write(b"tamper")
        with self.assertRaisesRegex(HandoffError, "sidecar"):
            verify_handoff_file(self.root, str(bundle))

    def test_tampered_inner_file_is_rejected_even_with_new_outer_sidecar(self) -> None:
        bundle, _, _ = self.create()
        with zipfile.ZipFile(bundle, "r") as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        entries[f"{ARCHIVE_ROOT}/README.md"] = b"changed"
        temporary = bundle.with_suffix(".tmp.zip")
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, value in entries.items():
                archive.writestr(name, value)
        temporary.replace(bundle)
        write_sidecar(bundle)
        with self.assertRaisesRegex(HandoffError, "내부 파일 무결성"):
            verify_handoff_file(self.root, str(bundle))

    def test_output_outside_artifacts_is_rejected(self) -> None:
        with self.assertRaisesRegex(HandoffError, "출력 폴더"):
            create_handoff(self.root, output_root=self.root / "outside", now=NOW)


if __name__ == "__main__":
    unittest.main()
