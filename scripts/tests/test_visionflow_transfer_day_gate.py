from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts.visionflow_transfer_day_gate import (
    SOURCE_BLOCKED_STATUS,
    SOURCE_READY_STATUS,
    TARGET_BLOCKED_STATUS,
    TARGET_READY_STATUS,
    TransferDayGateError,
    build_plan,
    resolve_project_file,
    run_source_gate,
    run_target_gate,
    verify_gate_report,
    verify_release_evidence_bundle,
)
from scripts.visionflow_transfer_media import (
    MANIFEST_NAME as TRANSFER_MEDIA_MANIFEST_NAME,
)

class VisionFlowTransferDayGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.now = datetime(2026, 7, 24, 5, 0, tzinfo=timezone.utc)

        self.package = self.write_bytes(
            "artifacts/transfer-package/"
            "visionflow-transfer-package-20260724T050000Z.zip",
            b"verified-transfer-package",
        )
        self.package_sha = self.sha(self.package)
        self.media = self.root.parent / f"{self.root.name}-external-media"
        self.addCleanup(lambda: self.remove_media())
        self.media.mkdir()
        self.write_external_json(
            self.media / TRANSFER_MEDIA_MANIFEST_NAME,
            {"status": "TRANSFER_MEDIA_READY_WITH_DEFERRED"},
        )
        (self.media / "evidence").mkdir()
        self.source_release = self.media / "evidence" / (
            "visionflow-release-evidence-source.zip"
        )
        self.source_release.write_bytes(b"source-release-evidence")
        self.rehearsal_report = {
            "status": "OFFLINE_TRANSFER_REHEARSAL_READY_WITH_DEFERRED",
            "package": {"sha256": self.package_sha},
        }
        self.rehearsal = self.write_json(
            "artifacts/transfer-rehearsal/"
            "visionflow-transfer-rehearsal-20260724T050000Z.json",
            self.rehearsal_report,
        )
        self.checkpoint_report = {
            "status": "TRANSFER_DAY_READY_WITH_DEFERRED",
        }
        self.checkpoint = self.write_json(
            "artifacts/hp-omen-transfer-day/checkpoint-20260724T050000Z/"
            "visionflow-hp-omen-transfer-day.json",
            self.checkpoint_report,
        )
        self.release = self.write_bytes(
            "artifacts/release-evidence/"
            "visionflow-release-evidence-20260724T050000Z.zip",
            b"verified-release-evidence",
        )

    def remove_media(self) -> None:
        if not self.media.exists():
            return
        for path in sorted(self.media.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            else:
                path.rmdir()
        self.media.rmdir()

    def write_bytes(self, relative: str, value: bytes) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
        return path

    def write_json(self, relative: str, value: dict[str, object]) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    @staticmethod
    def write_external_json(path: Path, value: dict[str, object]) -> None:
        path.write_text(json.dumps(value), encoding="utf-8")

    @staticmethod
    def sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def source_release_manifest(self) -> dict[str, object]:
        return {
            "supplementalEvidence": [
                {
                    "key": "offline-transfer-rehearsal",
                    "status": "PASS",
                    "included": True,
                    "archivePath": (
                        "supplemental/offline-transfer-rehearsal.json"
                    ),
                    "sourceSha256": self.sha(self.rehearsal),
                }
            ]
        }

    def target_release_manifest(self) -> dict[str, object]:
        manifest = self.source_release_manifest()
        manifest["supplementalEvidence"].append(
            {
                "key": "hp-omen-transfer-day",
                "status": "PASS",
                "included": True,
                "archivePath": "supplemental/hp-omen-transfer-day.json",
                "sourceSha256": self.sha(self.checkpoint),
            }
        )
        return manifest

    def source_patches(self, release_manifest: dict[str, object]):
        return (
            patch(
                "scripts.visionflow_transfer_day_gate."
                "verify_transfer_package_file",
                return_value=(
                    self.package,
                    {"status": "TRANSFER_PACKAGE_READY_WITH_DEFERRED"},
                ),
            ),
            patch(
                "scripts.visionflow_transfer_day_gate.verify_media",
                return_value=(
                    self.media,
                    {
                        "package": {"sha256": self.package_sha},
                        "releaseEvidence": {
                            "sha256": self.sha(self.release),
                        },
                    },
                ),
            ),
            patch(
                "scripts.visionflow_transfer_day_gate."
                "verify_rehearsal_report",
                return_value=(self.rehearsal, self.rehearsal_report),
            ),
            patch(
                "scripts.visionflow_transfer_day_gate."
                "verify_release_evidence_bundle",
                return_value=(self.release, release_manifest),
            ),
        )

    def test_source_gate_is_ready_when_all_lineage_matches(self) -> None:
        patches = self.source_patches(self.source_release_manifest())
        with patches[0], patches[1], patches[2], patches[3]:
            report_path, report, exit_code = run_source_gate(
                self.root,
                media_value=str(self.media),
                package_value=None,
                rehearsal_value=None,
                release_evidence_value=None,
                now=self.now,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], SOURCE_READY_STATUS)
        self.assertEqual(report["summary"], {
            "total": 5,
            "passed": 5,
            "blocking": 0,
        })
        _, verified = verify_gate_report(
            self.root,
            report_path.relative_to(self.root).as_posix(),
        )
        self.assertEqual(verified, report)
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn(str(self.media), serialized)

    def test_source_lineage_mismatch_is_blocked(self) -> None:
        manifest = self.source_release_manifest()
        manifest["supplementalEvidence"][0]["sourceSha256"] = "f" * 64
        patches = self.source_patches(manifest)
        with patches[0], patches[1], patches[2], patches[3]:
            report_path, report, exit_code = run_source_gate(
                self.root,
                media_value=str(self.media),
                package_value=None,
                rehearsal_value=None,
                release_evidence_value=None,
                now=self.now,
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], SOURCE_BLOCKED_STATUS)
        self.assertEqual(report["checks"][-1]["key"], "source-lineage")
        _, verified = verify_gate_report(
            self.root,
            report_path.relative_to(self.root).as_posix(),
        )
        self.assertEqual(verified["summary"]["blocking"], 1)

    def test_target_gate_is_ready_when_checkpoint_is_in_release_bundle(self) -> None:
        with (
            patch(
                "scripts.visionflow_transfer_day_gate.latest_checkpoint",
                return_value=self.checkpoint,
            ),
            patch(
                "scripts.visionflow_transfer_day_gate.verify_checkpoint",
                return_value=(self.checkpoint, self.checkpoint_report),
            ),
            patch(
                "scripts.visionflow_transfer_day_gate."
                "verify_release_evidence_bundle",
                return_value=(self.release, self.target_release_manifest()),
            ),
            patch(
                "scripts.visionflow_transfer_day_gate."
                "verify_release_evidence_file",
                return_value=(
                    self.source_release,
                    self.source_release_manifest(),
                ),
            ),
        ):
            report_path, report, exit_code = run_target_gate(
                self.root,
                checkpoint_value=None,
                source_release_evidence_value=str(self.source_release),
                release_evidence_value=None,
                now=self.now,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], TARGET_READY_STATUS)
        self.assertEqual(report["summary"]["passed"], 3)
        verify_gate_report(
            self.root,
            report_path.relative_to(self.root).as_posix(),
        )

    def test_target_gate_blocks_release_without_hp_checkpoint_entry(self) -> None:
        with (
            patch(
                "scripts.visionflow_transfer_day_gate.latest_checkpoint",
                return_value=self.checkpoint,
            ),
            patch(
                "scripts.visionflow_transfer_day_gate.verify_checkpoint",
                return_value=(self.checkpoint, self.checkpoint_report),
            ),
            patch(
                "scripts.visionflow_transfer_day_gate."
                "verify_release_evidence_bundle",
                return_value=(self.release, self.source_release_manifest()),
            ),
            patch(
                "scripts.visionflow_transfer_day_gate."
                "verify_release_evidence_file",
                return_value=(
                    self.source_release,
                    self.source_release_manifest(),
                ),
            ),
        ):
            _, report, exit_code = run_target_gate(
                self.root,
                checkpoint_value=None,
                source_release_evidence_value=str(self.source_release),
                release_evidence_value=None,
                now=self.now,
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], TARGET_BLOCKED_STATUS)
        self.assertEqual(report["checks"][-1]["key"], "target-lineage")

    def test_tampered_gate_html_is_rejected(self) -> None:
        patches = self.source_patches(self.source_release_manifest())
        with patches[0], patches[1], patches[2], patches[3]:
            report_path, _, _ = run_source_gate(
                self.root,
                media_value=str(self.media),
                package_value=None,
                rehearsal_value=None,
                release_evidence_value=None,
                now=self.now,
            )
        report_path.with_suffix(".html").write_text(
            "tampered",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(TransferDayGateError, "SHA-256"):
            verify_gate_report(
                self.root,
                report_path.relative_to(self.root).as_posix(),
            )

    def test_latest_file_selection_does_not_fall_back(self) -> None:
        older = self.release
        newer = self.write_bytes(
            "artifacts/release-evidence/"
            "visionflow-release-evidence-20260724T060000Z.zip",
            b"broken-newer-release",
        )
        newer_time = older.stat().st_mtime + 10
        os.utime(newer, (newer_time, newer_time))

        selected = resolve_project_file(
            self.root,
            None,
            directory=Path("artifacts/release-evidence"),
            pattern="visionflow-release-evidence-*.zip",
            title="릴리스 증빙",
        )

        self.assertEqual(selected, newer.resolve())

    def test_release_bundle_sidecar_mismatch_is_rejected(self) -> None:
        with zipfile.ZipFile(self.release, "w") as archive:
            archive.writestr(
                "evidence-manifest.json",
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "project": "visionflow",
                        "operation": "RELEASE_EVIDENCE_BUNDLE",
                    }
                ),
            )
        self.release.with_suffix(".sha256").write_text(
            f"{'0' * 64}  {self.release.name}\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(TransferDayGateError, "SHA-256"):
            verify_release_evidence_bundle(self.root, None)

    def test_source_and_target_plans_are_read_only(self) -> None:
        source = build_plan("SOURCE")
        target = build_plan("TARGET")

        self.assertEqual(len(source), 5)
        self.assertEqual(len(target), 3)
        self.assertTrue(all(item["mode"] == "READ_ONLY" for item in source + target))


if __name__ == "__main__":
    unittest.main()
