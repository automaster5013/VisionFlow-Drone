from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.visionflow_transfer_readiness import (
    TransferReadinessError,
    resolve_input,
    run_gate,
    sha256_file,
)


NOW = datetime(2026, 7, 22, 8, 0, tzinfo=timezone.utc)
SOURCE_SHA = "1" * 64
MANIFEST_SHA = "2" * 64


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_sidecar(path: Path) -> None:
    path.with_suffix(".sha256").write_text(
        f"{sha256_file(path)}  {path.name}\n", encoding="utf-8"
    )


def create_handoff(
    path: Path,
    *,
    baseline_status: str = "BASELINE_READY_WITH_DEFERRED",
    release_status: str = "READY_WITH_DEFERRED",
    smartphone_status: str | None = "PASS",
) -> None:
    readme = b"handoff"
    readme_path = "VisionFlow-Handoff/README.md"
    manifest = {
        "schemaVersion": 1,
        "project": "visionflow",
        "operation": "MIGRATION_HANDOFF",
        "source": {"sha256": SOURCE_SHA, "manifestSha256": MANIFEST_SHA},
        "evidence": {"readinessStatus": release_status},
        "baseline": {"status": baseline_status},
        "verifiedMySqlBackup": {
            "included": False,
            "sourcePath": "backups/verified.zip",
            "sizeBytes": 100,
            "sha256": "a" * 64,
        },
        "files": [
            {"archivePath": readme_path, "sizeBytes": len(readme), "sha256": sha(readme)}
        ],
    }
    if smartphone_status is not None:
        manifest["evidence"]["smartphoneE2eStatus"] = smartphone_status
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(readme_path, readme)
        archive.writestr(
            "VisionFlow-Handoff/HANDOFF_MANIFEST.json",
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )
    write_sidecar(path)


def create_cold_start(
    path: Path,
    handoff: Path,
    *,
    status: str = "COLD_START_READY_WITH_DEFERRED",
    blocking: int = 0,
    generated_at: datetime = NOW - timedelta(hours=1),
    handoff_sha: str | None = None,
    source_sha: str = SOURCE_SHA,
    manifest_sha: str = MANIFEST_SHA,
) -> None:
    report = {
        "schemaVersion": 1,
        "project": "visionflow",
        "operation": "COLD_START_REHEARSAL",
        "generatedAt": generated_at.isoformat(),
        "status": status,
        "handoff": {
            "path": f"artifacts/migration-handoff/{handoff.name}",
            "sha256": handoff_sha or sha256_file(handoff),
        },
        "source": {"sha256": source_sha, "manifestSha256": manifest_sha},
        "summary": {"blocking": blocking},
        "safety": {
            "databaseMutation": False,
            "dockerStarted": False,
            "originalHandoffModified": False,
        },
    }
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    path.with_suffix(".html").write_text(
        f"<html><body>{status}</body></html>", encoding="utf-8"
    )
    write_sidecar(path)


class TransferReadinessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.handoff_root = self.root / "artifacts/migration-handoff"
        self.cold_root = self.root / "artifacts/cold-start-rehearsal"
        self.output = self.root / "artifacts/transfer-readiness"
        self.handoff_root.mkdir(parents=True)
        self.cold_root.mkdir(parents=True)
        self.output.mkdir(parents=True)
        self.handoff = self.handoff_root / "visionflow-migration-handoff-20260722T060000Z.zip"
        self.cold = self.cold_root / "visionflow-cold-start-rehearsal-20260722T070000Z.json"
        create_handoff(self.handoff)
        create_cold_start(self.cold, self.handoff)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def execute(self):
        return run_gate(
            self.root,
            self.handoff,
            self.cold,
            output_root=self.output,
            max_age_hours=24,
            now=NOW,
        )

    def test_ready_gate_creates_three_reports(self) -> None:
        json_path, html_path, sidecar, report, exit_code = self.execute()
        self.assertEqual(0, exit_code)
        self.assertEqual("TRANSFER_READY_WITH_DEFERRED", report["status"])
        self.assertTrue(json_path.is_file())
        self.assertTrue(html_path.is_file())
        self.assertTrue(sidecar.is_file())
        self.assertEqual(11, report["summary"]["passed"])
        self.assertEqual("PASS", report["handoff"]["smartphoneE2eStatus"])

    def test_missing_smartphone_lineage_blocks(self) -> None:
        create_handoff(self.handoff, smartphone_status=None)
        create_cold_start(self.cold, self.handoff)
        _, _, _, report, exit_code = self.execute()
        self.assertEqual(1, exit_code)
        mobile = next(
            item
            for item in report["checks"]
            if item["key"] == "smartphone-e2e-lineage"
        )
        self.assertEqual("BLOCKED", mobile["status"])

    def test_blocked_cold_start_produces_blocked_gate(self) -> None:
        create_cold_start(self.cold, self.handoff, status="BLOCKED", blocking=1)
        _, _, _, report, exit_code = self.execute()
        self.assertEqual(1, exit_code)
        self.assertEqual("BLOCKED", report["status"])
        self.assertEqual("BLOCKED", next(item for item in report["checks"] if item["key"] == "cold-start-status")["status"])

    def test_handoff_identity_mismatch_blocks(self) -> None:
        create_cold_start(self.cold, self.handoff, handoff_sha="f" * 64)
        _, _, _, report, exit_code = self.execute()
        self.assertEqual(1, exit_code)
        self.assertEqual("BLOCKED", next(item for item in report["checks"] if item["key"] == "handoff-identity")["status"])

    def test_source_manifest_mismatch_blocks(self) -> None:
        create_cold_start(self.cold, self.handoff, manifest_sha="f" * 64)
        _, _, _, report, exit_code = self.execute()
        self.assertEqual(1, exit_code)
        self.assertEqual("BLOCKED", next(item for item in report["checks"] if item["key"] == "source-manifest-identity")["status"])

    def test_stale_cold_start_blocks(self) -> None:
        create_cold_start(self.cold, self.handoff, generated_at=NOW - timedelta(hours=25))
        _, _, _, report, exit_code = self.execute()
        self.assertEqual(1, exit_code)
        self.assertEqual("BLOCKED", next(item for item in report["checks"] if item["key"] == "cold-start-age")["status"])

    def test_future_cold_start_blocks(self) -> None:
        create_cold_start(self.cold, self.handoff, generated_at=NOW + timedelta(minutes=11))
        _, _, _, report, exit_code = self.execute()
        self.assertEqual(1, exit_code)
        self.assertEqual("BLOCKED", next(item for item in report["checks"] if item["key"] == "cold-start-age")["status"])

    def test_blocked_baseline_status_blocks(self) -> None:
        create_handoff(self.handoff, baseline_status="BLOCKED")
        create_cold_start(self.cold, self.handoff)
        _, _, _, report, exit_code = self.execute()
        self.assertEqual(1, exit_code)
        self.assertEqual("BLOCKED", next(item for item in report["checks"] if item["key"] == "baseline-status")["status"])

    def test_blocked_release_status_blocks(self) -> None:
        create_handoff(self.handoff, release_status="BLOCKED")
        create_cold_start(self.cold, self.handoff)
        _, _, _, report, exit_code = self.execute()
        self.assertEqual(1, exit_code)
        self.assertEqual("BLOCKED", next(item for item in report["checks"] if item["key"] == "release-evidence-status")["status"])

    def test_tampered_handoff_is_rejected(self) -> None:
        with self.handoff.open("ab") as stream:
            stream.write(b"tampered")
        with self.assertRaisesRegex(TransferReadinessError, "sidecar와 다릅니다"):
            self.execute()

    def test_tampered_cold_start_sidecar_is_rejected(self) -> None:
        self.cold.with_suffix(".sha256").write_text(
            f"{'0' * 64}  {self.cold.name}\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(TransferReadinessError, "sidecar와 다릅니다"):
            self.execute()

    def test_output_outside_artifacts_is_rejected(self) -> None:
        with self.assertRaisesRegex(TransferReadinessError, "출력 폴더"):
            run_gate(
                self.root,
                self.handoff,
                self.cold,
                output_root=self.root / "outside",
                max_age_hours=24,
                now=NOW,
            )

    def test_newest_invalid_input_does_not_fall_back(self) -> None:
        invalid = self.cold_root / "visionflow-cold-start-rehearsal-20260722T080000Z.json"
        invalid.write_text("invalid", encoding="utf-8")
        write_sidecar(invalid)
        invalid.with_suffix(".html").write_text("invalid", encoding="utf-8")
        newer = self.cold.stat().st_mtime_ns + 2_000_000_000
        os.utime(invalid, ns=(newer, newer))
        selected = resolve_input(
            self.root,
            None,
            self.cold_root,
            "visionflow-cold-start-rehearsal-*.json",
            "콜드 스타트 보고서",
        )
        self.assertEqual(invalid, selected)
        with self.assertRaisesRegex(TransferReadinessError, "JSON 형식"):
            run_gate(
                self.root,
                self.handoff,
                selected,
                output_root=self.output,
                max_age_hours=24,
                now=NOW,
            )


if __name__ == "__main__":
    unittest.main()
