from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import ANY, patch

from scripts.visionflow_release_evidence import (
    EvidenceBundleError,
    create_bundle,
    main,
    newest_readiness_report,
    resolve_report,
)


class VisionFlowReleaseEvidenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.now = datetime.now(timezone.utc)
        self.sources = {
            "acceptance-demo": self.write_json(
                "artifacts/visionflow-acceptance/visionflow-acceptance-test.json",
                {"summary": {"total": 12, "passed": 12, "failed": 0}},
            ),
            "maintenance-operations": self.write_json(
                (
                    "artifacts/maintenance-acceptance/"
                    "visionflow-maintenance-acceptance-test.json"
                ),
                {
                    "operation": "MAINTENANCE_FLIGHT_GATE_ACCEPTANCE",
                    "status": "MAINTENANCE_GATE_READY",
                },
            ),
            "verified-backup": self.write_bytes(
                "backups/visionflow-backup-test.zip",
                b"verified-backup-placeholder",
            ),
            "storage-audit": self.write_json(
                "artifacts/storage-audit/run/storage-audit.json",
                {"status": "HEALTHY"},
            ),
            "retention-recovery-drill": self.write_json(
                "artifacts/retention-drill/run/retention-recovery-drill.json",
                {"status": "PASSED"},
            ),
            "ai-cpu-baseline": self.write_json(
                "artifacts/ai-benchmark/visionflow-ai-benchmark-test.json",
                {"modelName": "yolo26n.pt", "device": "cpu"},
            ),
            "csp-report-only-observation": self.write_json(
                "artifacts/csp-observability/visionflow-csp-observation-test.json",
                {
                    "operation": "CSP_REPORT_ONLY_OBSERVATION",
                    "status": "CSP_OBSERVATION_CLEAN",
                },
            ),
            "smartphone-real-sensor-https": self.write_json(
                (
                    "artifacts/mobile-readiness/"
                    "visionflow-smartphone-e2e-test.json"
                ),
                {
                    "operation": "SMARTPHONE_E2E_VERIFICATION",
                    "status": "SMARTPHONE_E2E_PASS",
                },
            ),
        }
        self.report = self.create_readiness_report()

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

    def evidence(self, path: Path) -> dict[str, object]:
        return {
            "path": path.relative_to(self.root).as_posix(),
            "sizeBytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    def write_sidecar(self, path: Path, *, checksum: str | None = None) -> None:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        path.with_suffix(".sha256").write_text(
            f"{checksum or actual}  {path.name}\n",
            encoding="utf-8",
        )

    def create_supplemental_reports(self) -> dict[str, Path]:
        machine = self.write_json(
            "artifacts/machine-readiness/visionflow-machine-baseline-test.json",
            {
                "schemaVersion": 1,
                "project": "visionflow",
                "operation": "MACHINE_READINESS_PROFILE",
                "generatedAt": self.now.isoformat(),
                "role": "baseline",
                "status": "BASELINE_READY_WITH_DEFERRED",
                "sourceIdentity": {"status": "PASS"},
                "summary": {"blocking": 0},
            },
        )
        cold_start = self.write_json(
            (
                "artifacts/cold-start-rehearsal/"
                "visionflow-cold-start-rehearsal-test.json"
            ),
            {
                "schemaVersion": 1,
                "project": "visionflow",
                "operation": "COLD_START_REHEARSAL",
                "generatedAt": self.now.isoformat(),
                "status": "COLD_START_READY_WITH_DEFERRED",
                "summary": {"blocking": 0},
                "safety": {
                    "databaseMutation": False,
                    "dockerStarted": False,
                    "originalHandoffModified": False,
                },
            },
        )
        transfer = self.write_json(
            (
                "artifacts/transfer-readiness/"
                "visionflow-transfer-readiness-test.json"
            ),
            {
                "schemaVersion": 1,
                "project": "visionflow",
                "operation": "TRANSFER_READINESS_GATE",
                "generatedAt": self.now.isoformat(),
                "status": "TRANSFER_READY_WITH_DEFERRED",
                "summary": {"blocking": 0},
                "safety": {
                    "databaseMutation": False,
                    "externalTransferPerformed": False,
                },
            },
        )
        reports = {
            "machine-readiness": machine,
            "cold-start-rehearsal": cold_start,
            "transfer-readiness": transfer,
        }
        for path in reports.values():
            self.write_sidecar(path)
        return reports

    def create_transfer_rehearsal_report(self) -> tuple[Path, dict[str, object]]:
        report: dict[str, object] = {
            "schemaVersion": 1,
            "project": "visionflow",
            "operation": "OFFLINE_TRANSFER_REHEARSAL",
            "generatedAt": self.now.isoformat(),
            "status": "OFFLINE_TRANSFER_REHEARSAL_READY_WITH_DEFERRED",
            "safety": {
                "databaseMutation": False,
                "dockerStarted": False,
                "gpuExecuted": False,
                "externalTransferPerformed": False,
                "temporaryWorkspaceRemoved": True,
                "sourceFilesModified": False,
            },
        }
        path = self.write_json(
            (
                "artifacts/transfer-rehearsal/"
                "visionflow-transfer-rehearsal-test.json"
            ),
            report,
        )
        return path, report

    def create_transfer_day_report(self) -> tuple[Path, dict[str, object]]:
        report: dict[str, object] = {
            "schemaVersion": 1,
            "project": "visionflow",
            "operation": "HP_OMEN_TRANSFER_DAY",
            "generatedAt": self.now.isoformat(),
            "status": "TRANSFER_DAY_READY_WITH_DEFERRED",
            "activationReport": {
                "key": "hp-runtime-activation",
                "path": (
                    "artifacts/hp-omen-restore/activation-test/"
                    "visionflow-hp-omen-activation.json"
                ),
                "sizeBytes": 100,
                "sha256": "a" * 64,
            },
            "safety": {
                "permanentDelete": False,
                "environmentValuesRecorded": False,
                "operatorKeysRecorded": False,
                "modelWeightsIncluded": False,
                "absolutePathsRecorded": False,
                "activationRequiresExplicitConfirmation": True,
            },
        }
        path = self.write_json(
            (
                "artifacts/hp-omen-transfer-day/checkpoint-test/"
                "visionflow-hp-omen-transfer-day.json"
            ),
            report,
        )
        return path, report

    def create_readiness_report(
        self,
        *,
        status: str = "READY_WITH_DEFERRED",
        name: str = "visionflow-release-readiness-20260722T120000Z.json",
    ) -> Path:
        checks = []
        for key, path in self.sources.items():
            checks.append(
                {
                    "key": key,
                    "title": key,
                    "requirement": "REQUIRED",
                    "status": "PASS",
                    "detail": "verified",
                    "evidence": self.evidence(path),
                    "metrics": {},
                }
            )
        report = {
            "schemaVersion": 1,
            "project": "visionflow",
            "scope": "SECOND_PROJECT_DIGITAL_TWIN",
            "generatedAt": self.now.isoformat(),
            "status": status,
            "summary": {
                "totalRequired": len(checks),
                "passedRequired": len(checks),
                "warnings": 0,
                "blocked": 0 if status != "BLOCKED" else 1,
                "deferred": 2,
                "outOfScope": 1,
            },
            "checks": checks,
            "deferred": [
                {
                    "key": "hp-omen-gpu-best-model",
                    "title": "HP OMEN GPU 모델 검증",
                    "status": "DEFERRED",
                    "scope": "SECOND_PROJECT_FOLLOW_UP",
                    "reason": "HP OMEN 이관 후 검증",
                }
            ],
            "safety": {
                "readOnly": True,
                "permanentDelete": False,
                "databaseMutation": False,
            },
        }
        path = self.write_json(f"artifacts/release-readiness/{name}", report)
        path.with_suffix(".html").write_text(
            "<!doctype html><html><body>READY_WITH_DEFERRED</body></html>",
            encoding="utf-8",
        )
        return path

    def build(self):
        return create_bundle(
            self.root,
            self.report,
            output_root=self.root / "artifacts/release-evidence",
            now=self.now,
        )

    def test_bundle_contains_only_minimal_safe_evidence(self) -> None:
        bundle, sidecar, manifest = self.build()

        self.assertTrue(bundle.is_file())
        self.assertTrue(sidecar.is_file())
        with zipfile.ZipFile(bundle) as archive:
            names = set(archive.namelist())
        self.assertEqual(
            names,
            {
                "README.md",
                "evidence-manifest.json",
                "release-readiness/report.json",
                "release-readiness/report.html",
                "evidence/acceptance-demo.json",
                "evidence/maintenance-operations.json",
                "evidence/storage-audit.json",
                "evidence/retention-recovery-drill.json",
                "evidence/ai-cpu-baseline.json",
                "evidence/csp-report-only-observation.json",
                "evidence/smartphone-real-sensor-https.json",
            },
        )
        backup = next(
            item for item in manifest["evidence"]
            if item["key"] == "verified-backup"
        )
        self.assertFalse(backup["included"])
        self.assertIsNone(backup["archivePath"])
        self.assertTrue(
            all(
                item["status"] == "DEFERRED"
                for item in manifest["supplementalEvidence"]
            )
        )

    def test_legacy_readiness_without_mobile_evidence_remains_supported(self) -> None:
        report = json.loads(self.report.read_text(encoding="utf-8"))
        report["checks"] = [
            item
            for item in report["checks"]
            if item["key"] != "smartphone-real-sensor-https"
        ]
        report["summary"]["totalRequired"] = len(report["checks"])
        report["summary"]["passedRequired"] = len(report["checks"])
        report["deferred"] = [
            {
                "key": "smartphone-real-sensor-https",
                "title": "스마트폰 실센서·카메라 HTTPS E2E 검증",
                "status": "DEFERRED",
                "scope": "SECOND_PROJECT_FOLLOW_UP",
                "reason": "아직 증적이 없음",
            }
        ]
        self.report.write_text(json.dumps(report), encoding="utf-8")

        bundle, _, manifest = self.build()

        with zipfile.ZipFile(bundle) as archive:
            self.assertNotIn(
                "evidence/smartphone-real-sensor-https.json",
                archive.namelist(),
            )
        self.assertFalse(
            any(
                item["key"] == "smartphone-real-sensor-https"
                for item in manifest["evidence"]
            )
        )

    def test_bundle_includes_verified_supplemental_readiness_chain(self) -> None:
        self.create_supplemental_reports()

        bundle, _, manifest = self.build()

        with zipfile.ZipFile(bundle) as archive:
            names = set(archive.namelist())
        self.assertIn("supplemental/machine-readiness.json", names)
        self.assertIn("supplemental/cold-start-rehearsal.json", names)
        self.assertIn("supplemental/transfer-readiness.json", names)
        by_key = {
            item["key"]: item
            for item in manifest["supplementalEvidence"]
        }
        self.assertTrue(
            all(
                by_key[key]["status"] == "PASS"
                and by_key[key]["included"]
                for key in (
                    "machine-readiness",
                    "cold-start-rehearsal",
                    "transfer-readiness",
                )
            )
        )
        self.assertEqual(
            by_key["offline-transfer-rehearsal"]["status"],
            "DEFERRED",
        )
        self.assertEqual(
            by_key["hp-omen-transfer-day"]["status"],
            "DEFERRED",
        )

    def test_bundle_includes_verified_offline_transfer_rehearsal(self) -> None:
        path, report = self.create_transfer_rehearsal_report()

        with patch(
            "scripts.visionflow_release_evidence."
            "verify_transfer_rehearsal_report",
            return_value=(path, report),
        ) as verifier:
            bundle, _, manifest = self.build()

        verifier.assert_called_once_with(
            self.root,
            path.relative_to(self.root).as_posix(),
        )
        with zipfile.ZipFile(bundle) as archive:
            self.assertIn(
                "supplemental/offline-transfer-rehearsal.json",
                archive.namelist(),
            )
        entry = next(
            item
            for item in manifest["supplementalEvidence"]
            if item["key"] == "offline-transfer-rehearsal"
        )
        self.assertEqual(entry["status"], "PASS")
        self.assertTrue(entry["included"])

    def test_bundle_includes_verified_hp_transfer_day_checkpoint(self) -> None:
        path, report = self.create_transfer_day_report()

        with patch(
            "scripts.visionflow_release_evidence."
            "verify_transfer_day_checkpoint",
            return_value=(path, report),
        ) as verifier:
            bundle, _, manifest = self.build()

        verifier.assert_called_once_with(
            self.root,
            path.relative_to(self.root).as_posix(),
            environment={},
            platform_name=ANY,
        )
        with zipfile.ZipFile(bundle) as archive:
            self.assertIn(
                "supplemental/hp-omen-transfer-day.json",
                archive.namelist(),
            )
        entry = next(
            item
            for item in manifest["supplementalEvidence"]
            if item["key"] == "hp-omen-transfer-day"
        )
        self.assertEqual(entry["status"], "PASS")
        self.assertTrue(entry["included"])

    def test_tampered_supplemental_sidecar_is_rejected(self) -> None:
        reports = self.create_supplemental_reports()
        self.write_sidecar(
            reports["machine-readiness"],
            checksum="f" * 64,
        )

        with self.assertRaisesRegex(EvidenceBundleError, "sidecar"):
            self.build()

    def test_sidecar_checksum_matches_bundle(self) -> None:
        bundle, sidecar, _ = self.build()

        expected = hashlib.sha256(bundle.read_bytes()).hexdigest()
        self.assertEqual(sidecar.read_text(encoding="utf-8"), f"{expected}  {bundle.name}\n")

    def test_changed_evidence_is_rejected(self) -> None:
        self.sources["storage-audit"].write_text(
            json.dumps({"status": "CHANGED"}),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(EvidenceBundleError, "크기가 변경|SHA-256"):
            self.build()

    def test_blocked_readiness_report_is_rejected(self) -> None:
        self.report = self.create_readiness_report(
            status="BLOCKED",
            name="visionflow-release-readiness-blocked.json",
        )

        with self.assertRaisesRegex(EvidenceBundleError, "번들 생성 조건"):
            self.build()

    def test_missing_readiness_html_is_rejected(self) -> None:
        self.report.with_suffix(".html").unlink()

        with self.assertRaisesRegex(EvidenceBundleError, "HTML"):
            self.build()

    def test_executable_content_in_readiness_html_is_rejected(self) -> None:
        self.report.with_suffix(".html").write_text(
            "<html><body>READY_WITH_DEFERRED<script>alert(1)</script></body></html>",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(EvidenceBundleError, "실행 가능한"):
            self.build()

    def test_path_traversal_in_evidence_is_rejected(self) -> None:
        report = json.loads(self.report.read_text(encoding="utf-8"))
        report["checks"][0]["evidence"]["path"] = "../outside.json"
        self.report.write_text(json.dumps(report), encoding="utf-8")

        with self.assertRaisesRegex(EvidenceBundleError, "안전하지 않은"):
            self.build()

    def test_output_outside_release_evidence_root_is_rejected(self) -> None:
        with self.assertRaisesRegex(EvidenceBundleError, "출력 폴더"):
            create_bundle(
                self.root,
                self.report,
                output_root=self.root / "outside",
                now=self.now,
            )

    def test_report_override_outside_readiness_root_is_rejected(self) -> None:
        outside = self.root / "outside.json"
        outside.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(EvidenceBundleError, "허용 경로"):
            resolve_report(self.root, str(outside))

    def test_newest_report_selection_does_not_fall_back_to_older_ready(self) -> None:
        older = self.report
        newest = self.create_readiness_report(
            status="BLOCKED",
            name="visionflow-release-readiness-20260722T130000Z.json",
        )
        newer_time = self.now.timestamp() + 10
        os.utime(newest, (newer_time, newer_time))

        selected = newest_readiness_report(self.root)

        self.assertNotEqual(selected, older.resolve())
        self.assertEqual(selected, newest.resolve())

    def test_cli_auto_discovers_and_creates_bundle(self) -> None:
        exit_code = main(["--root", str(self.root)])

        self.assertEqual(exit_code, 0)
        bundles = list(
            (self.root / "artifacts/release-evidence").glob(
                "visionflow-release-evidence-*.zip"
            )
        )
        self.assertEqual(len(bundles), 1)


if __name__ == "__main__":
    unittest.main()
