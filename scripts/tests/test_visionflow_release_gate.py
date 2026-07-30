from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIRECTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIRECTORY))

from visionflow_release_gate import (
    ReleaseGateError,
    main,
    newest_demo_acceptance,
    resolve_override,
    run_release_gate,
)


class VisionFlowReleaseGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.now = datetime.now(timezone.utc)
        self.acceptance = self.create_acceptance(run_demo=True)
        self.maintenance = self.create_maintenance_acceptance()
        self.backup = self.create_backup()
        self.audit = self.create_audit()
        self.drill = self.create_drill()
        self.benchmark = self.create_benchmark()
        self.csp = self.create_csp_observation()
        self.mobile = None

    def write_json(self, path: Path, value: dict[str, object]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def create_acceptance(
        self,
        *,
        run_demo: bool,
        run_rbac: bool = True,
        run_session: bool = True,
        generated_at: datetime | None = None,
        name: str = "visionflow-acceptance-20260722-120000.json",
    ) -> Path:
        return self.write_json(
            self.root / "artifacts/visionflow-acceptance" / name,
            {
                "generatedAt": (generated_at or self.now).isoformat(),
                "configuration": {
                    "runDemo": run_demo,
                    "runRbac": run_rbac,
                    "runSession": run_session,
                    "skipAi": False,
                },
                "summary": {"total": 9, "passed": 9, "failed": 0},
                "scenario": {"stage": "COMPLETED"} if run_demo else None,
                "results": [
                    {"Name": name, "Passed": True}
                    for name in (
                        "Backend health",
                        "Frontend dashboard",
                        "AI ingest status",
                        "AI stream status",
                        "Frontend security headers",
                        "Frontend CSP report observability",
                        "RBAC enabled mode",
                        "Operator browser session mode",
                        "Demo flight complete",
                    )
                ],
            },
        )

    def create_backup(self, *, corrupted: bool = False) -> Path:
        path = self.root / "backups/visionflow-backup-20260722T120000Z.zip"
        path.parent.mkdir(parents=True, exist_ok=True)
        if corrupted:
            path.write_bytes(b"not-a-zip")
            return path
        sql = b"CREATE TABLE drone(id BIGINT);\n"
        manifest = {
            "schemaVersion": 1,
            "project": "visionflow",
            "createdAt": self.now.isoformat(),
            "files": [
                {
                    "path": "database/visionflow.sql",
                    "sizeBytes": len(sql),
                    "sha256": hashlib.sha256(sql).hexdigest(),
                }
            ],
        }
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr("database/visionflow.sql", sql)
        return path

    def create_maintenance_acceptance(
        self,
        *,
        status: str = "MAINTENANCE_GATE_READY",
        generated_at: datetime | None = None,
    ) -> Path:
        required = (
            "backend-maintenance-metrics",
            "frontend-maintenance-metrics-proxy",
            "backend-maintenance-metrics-window-validation",
            "frontend-maintenance-metrics-window-validation",
            "frontend-maintenance-kpi-content",
        )
        return self.write_json(
            (
                self.root
                / "artifacts/maintenance-acceptance"
                / "visionflow-maintenance-acceptance-test.json"
            ),
            {
                "schemaVersion": 1,
                "project": "visionflow",
                "operation": "MAINTENANCE_FLIGHT_GATE_ACCEPTANCE",
                "generatedAt": (generated_at or self.now).isoformat(),
                "status": status,
                "summary": {
                    "total": len(required),
                    "passed": (
                        len(required)
                        if status == "MAINTENANCE_GATE_READY"
                        else 0
                    ),
                    "failed": (
                        0
                        if status == "MAINTENANCE_GATE_READY"
                        else len(required)
                    ),
                },
                "evidence": {
                    "metricsWindowDays": 30,
                    "metricsTotalWorkOrders": 4,
                    "metricsResolutionRatePercent": 50.0,
                },
                "checks": [
                    {
                        "key": key,
                        "status": (
                            "PASS"
                            if status == "MAINTENANCE_GATE_READY"
                            else "FAILED"
                        ),
                    }
                    for key in required
                ],
                "safety": {
                    "readOnly": True,
                    "httpMethods": ["GET"],
                    "databaseMutation": False,
                },
            },
        )

    def create_audit(
        self,
        *,
        status: str = "HEALTHY",
        generated_at: datetime | None = None,
    ) -> Path:
        return self.write_json(
            self.root / "artifacts/storage-audit/run/storage-audit.json",
            {
                "schemaVersion": 1,
                "project": "visionflow",
                "generatedAt": (generated_at or self.now).isoformat(),
                "status": status,
                "disk": {"root": str(self.root)},
                "retention": {
                    "dryRunOnly": True,
                    "policy": {
                        "aiOutputDays": 14,
                        "backupDays": 30,
                        "reportDays": 30,
                        "minimumBackups": 1,
                    },
                    "candidateCount": 0,
                    "candidates": [],
                },
            },
        )

    def create_drill(
        self,
        *,
        status: str = "PASSED",
        completed_at: datetime | None = None,
    ) -> Path:
        return self.write_json(
            self.root
            / "artifacts/retention-drill/drill/retention-recovery-drill.json",
            {
                "schemaVersion": 1,
                "project": "visionflow",
                "operation": "RETENTION_RECOVERY_DRILL",
                "startedAt": self.now.isoformat(),
                "completedAt": (completed_at or self.now).isoformat(),
                "status": status,
                "stages": [],
            },
        )

    def create_benchmark(
        self,
        *,
        generated_at: datetime | None = None,
    ) -> Path:
        return self.write_json(
            self.root
            / "artifacts/ai-benchmark/visionflow-ai-benchmark-20260722-120000.json",
            {
                "generatedAt": (generated_at or self.now).isoformat(),
                "sampleCount": 59,
                "processedFrameDelta": 59,
                "averageInferenceMs": 106.69,
                "modelName": "yolo26n.pt",
                "device": "cpu",
            },
        )

    def create_mobile_evidence(
        self,
        *,
        generated_at: datetime | None = None,
        status: str = "SMARTPHONE_E2E_PASS",
        valid_checksum: bool = True,
    ) -> Path:
        required_checks = (
            "trusted-https-endpoint",
            "browser-permission-policy",
            "completed-flight-session",
            "mobile-source-identity",
            "telemetry-minimum",
            "mobile-sensor-source",
            "gps-values",
            "orientation-values",
            "ai-events",
            "ai-detections",
        )
        path = self.write_json(
            (
                self.root
                / "artifacts/mobile-readiness"
                / "visionflow-smartphone-e2e-20260727T072641Z.json"
            ),
            {
                "schemaVersion": 1,
                "project": "visionflow",
                "operation": "SMARTPHONE_E2E_VERIFICATION",
                "generatedAt": (generated_at or self.now).isoformat(),
                "status": status,
                "checks": [
                    {"key": key, "status": "PASS"}
                    for key in required_checks
                ],
                "evidence": {
                    "sessionId": "mobile-session",
                    "droneId": 3,
                    "telemetryCount": 371,
                    "mobileSensorCount": 371,
                    "aiEventCount": 1,
                    "detectionCount": 1,
                },
                "privacy": {
                    "exactCoordinatesRecorded": False,
                    "operatorKeyRecorded": False,
                    "sessionTokenRecorded": False,
                    "rawImageRecorded": False,
                    "rawVideoRecorded": False,
                },
                "safety": {
                    "readOnly": True,
                    "databaseMutation": False,
                    "externalMessagesSent": False,
                },
            },
        )
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if not valid_checksum:
            digest = "0" * 64
        path.with_suffix(".sha256").write_text(
            f"{digest}  {path.name}\n",
            encoding="utf-8",
        )
        return path

    def create_csp_observation(
        self,
        *,
        status: str = "CSP_OBSERVATION_CLEAN",
        generated_at: datetime | None = None,
        corrupt_sidecar: bool = False,
    ) -> Path:
        directory = self.root / "artifacts/csp-observability"
        path = directory / "visionflow-csp-observation-20260723T010000000000Z.json"
        total = 1 if status == "CSP_OBSERVATION_REVIEW_REQUIRED" else 0
        reports = []
        if total:
            reports.append(
                {
                    "documentUri": "http://localhost:3000/dashboard",
                    "blockedUri": "https://example.invalid/test.js",
                    "sourceFile": "http://localhost:3000/_next/app.js",
                    "effectiveDirective": "script-src-elem",
                    "receivedAt": self.now.isoformat(),
                }
            )
        self.write_json(
            path,
            {
                "schemaVersion": 1,
                "project": "visionflow",
                "operation": "CSP_REPORT_ONLY_OBSERVATION",
                "generatedAt": (generated_at or self.now).isoformat(),
                "status": status,
                "summary": {
                    "totalReports": total,
                    "retainedReports": total,
                },
                "observation": {
                    "mode": "REPORT_ONLY",
                    "persisted": False,
                    "storage": "BOUNDED_PROCESS_MEMORY",
                    "totalReports": total,
                    "retainedReports": total,
                    "reports": reports,
                },
            },
        )
        csv_path = path.with_suffix(".csv")
        html_path = path.with_suffix(".html")
        csv_path.write_text("receivedAt,effectiveDirective\n", encoding="utf-8")
        html_path.write_text("<html><body>CSP evidence</body></html>", encoding="utf-8")
        paths = (path, csv_path, html_path)
        lines = [
            f"{hashlib.sha256(item.read_bytes()).hexdigest()}  {item.name}"
            for item in paths
        ]
        if corrupt_sidecar:
            lines[0] = f"{'0' * 64}  {path.name}"
        path.with_suffix(".sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def run_gate(self):
        return run_release_gate(
            self.root,
            acceptance=self.acceptance,
            backup=self.backup,
            audit=self.audit,
            drill=self.drill,
            benchmark=self.benchmark,
            csp=self.csp,
            maintenance=self.maintenance,
            mobile=self.mobile,
            output_root=self.root / "artifacts/release-readiness",
            now=self.now,
            acceptance_max_age_hours=48,
            backup_max_age_days=7,
            audit_max_age_hours=24,
            drill_max_age_hours=24,
            benchmark_max_age_days=30,
            csp_max_age_hours=24,
            maintenance_max_age_hours=24,
            mobile_max_age_days=30,
        )

    def test_all_required_evidence_is_ready_with_agreed_deferred_items(self) -> None:
        json_path, html_path, report, exit_code = self.run_gate()

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "READY_WITH_DEFERRED")
        self.assertEqual(report["summary"]["passedRequired"], 7)
        self.assertEqual(report["summary"]["blocked"], 0)
        self.assertEqual(report["summary"]["deferred"], 3)
        self.assertEqual(report["summary"]["outOfScope"], 1)
        smartphone = next(
            item
            for item in report["deferred"]
            if item["key"] == "smartphone-real-sensor-https"
        )
        self.assertIn("SMARTPHONE_E2E_PASS 증적이 없어", smartphone["reason"])
        self.assertTrue(json_path.is_file())
        self.assertTrue(html_path.is_file())
        self.assertIn("VisionFlow 2차 프로젝트", html_path.read_text(encoding="utf-8"))

    def test_valid_smartphone_evidence_is_promoted_to_required_pass(self) -> None:
        self.mobile = self.create_mobile_evidence()

        _, _, report, exit_code = self.run_gate()

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["summary"]["passedRequired"], 8)
        self.assertEqual(report["summary"]["deferred"], 2)
        mobile = next(
            item
            for item in report["checks"]
            if item["key"] == "smartphone-real-sensor-https"
        )
        self.assertEqual(mobile["status"], "PASS")
        self.assertEqual(mobile["metrics"]["droneId"], 3)
        self.assertTrue(mobile["metrics"]["sidecarVerified"])
        self.assertFalse(
            any(
                item["key"] == "smartphone-real-sensor-https"
                for item in report["deferred"]
            )
        )

    def test_invalid_smartphone_checksum_remains_deferred(self) -> None:
        self.mobile = self.create_mobile_evidence(valid_checksum=False)

        _, _, report, exit_code = self.run_gate()

        self.assertEqual(exit_code, 0)
        self.assertFalse(
            any(
                item["key"] == "smartphone-real-sensor-https"
                for item in report["checks"]
            )
        )
        mobile = next(
            item
            for item in report["deferred"]
            if item["key"] == "smartphone-real-sensor-https"
        )
        self.assertIn("SHA-256", mobile["reason"])

    def test_non_demo_acceptance_blocks_release(self) -> None:
        self.acceptance = self.create_acceptance(
            run_demo=False,
            name="visionflow-acceptance-20260722-120100.json",
        )

        _, _, report, exit_code = self.run_gate()

        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], "BLOCKED")
        check = next(item for item in report["checks"] if item["key"] == "acceptance-demo")
        self.assertEqual(check["status"], "FAILED")

    def test_failed_maintenance_acceptance_blocks_release(self) -> None:
        self.maintenance = self.create_maintenance_acceptance(
            status="MAINTENANCE_GATE_BLOCKED"
        )

        _, _, report, exit_code = self.run_gate()

        self.assertEqual(exit_code, 1)
        check = next(
            item
            for item in report["checks"]
            if item["key"] == "maintenance-operations"
        )
        self.assertEqual(check["status"], "FAILED")

    def test_stale_maintenance_acceptance_blocks_release(self) -> None:
        self.maintenance = self.create_maintenance_acceptance(
            generated_at=self.now - timedelta(hours=25)
        )

        _, _, report, exit_code = self.run_gate()

        self.assertEqual(exit_code, 1)
        check = next(
            item
            for item in report["checks"]
            if item["key"] == "maintenance-operations"
        )
        self.assertEqual(check["status"], "FAILED")

    def test_missing_session_mode_blocks_release(self) -> None:
        self.acceptance = self.create_acceptance(
            run_demo=True,
            run_session=False,
            name="visionflow-acceptance-20260722-120101.json",
        )

        _, _, report, exit_code = self.run_gate()

        self.assertEqual(exit_code, 1)
        check = next(item for item in report["checks"] if item["key"] == "acceptance-demo")
        self.assertEqual(check["status"], "FAILED")
        self.assertIn("runSession", check["detail"])

    def test_stale_storage_audit_blocks_release(self) -> None:
        self.audit = self.create_audit(generated_at=self.now - timedelta(hours=25))

        _, _, report, exit_code = self.run_gate()

        self.assertEqual(exit_code, 1)
        check = next(item for item in report["checks"] if item["key"] == "storage-audit")
        self.assertEqual(check["status"], "FAILED")

    def test_storage_warning_is_visible_but_not_blocking(self) -> None:
        self.audit = self.create_audit(status="WARNING")

        _, _, report, exit_code = self.run_gate()

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["summary"]["warnings"], 1)
        check = next(item for item in report["checks"] if item["key"] == "storage-audit")
        self.assertEqual(check["status"], "WARNING")

    def test_failed_recovery_drill_blocks_release(self) -> None:
        self.drill = self.create_drill(status="RESTORE_FAILED")

        _, _, report, exit_code = self.run_gate()

        self.assertEqual(exit_code, 1)
        check = next(
            item for item in report["checks"]
            if item["key"] == "retention-recovery-drill"
        )
        self.assertEqual(check["status"], "FAILED")

    def test_corrupt_backup_blocks_release(self) -> None:
        self.backup = self.create_backup(corrupted=True)

        _, _, report, exit_code = self.run_gate()

        self.assertEqual(exit_code, 1)
        check = next(item for item in report["checks"] if item["key"] == "verified-backup")
        self.assertEqual(check["status"], "FAILED")

    def test_stale_benchmark_blocks_release(self) -> None:
        self.benchmark = self.create_benchmark(
            generated_at=self.now - timedelta(days=31)
        )

        _, _, report, exit_code = self.run_gate()

        self.assertEqual(exit_code, 1)
        check = next(item for item in report["checks"] if item["key"] == "ai-cpu-baseline")
        self.assertEqual(check["status"], "FAILED")

    def test_csp_review_required_is_visible_warning(self) -> None:
        self.csp = self.create_csp_observation(
            status="CSP_OBSERVATION_REVIEW_REQUIRED"
        )

        _, _, report, exit_code = self.run_gate()

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "READY_WITH_DEFERRED")
        self.assertEqual(report["summary"]["warnings"], 1)
        check = next(
            item
            for item in report["checks"]
            if item["key"] == "csp-report-only-observation"
        )
        self.assertEqual(check["status"], "WARNING")

    def test_corrupt_csp_sidecar_blocks_release(self) -> None:
        self.csp = self.create_csp_observation(corrupt_sidecar=True)

        _, _, report, exit_code = self.run_gate()

        self.assertEqual(exit_code, 1)
        check = next(
            item
            for item in report["checks"]
            if item["key"] == "csp-report-only-observation"
        )
        self.assertEqual(check["status"], "FAILED")

    def test_override_outside_evidence_root_is_rejected(self) -> None:
        outside = self.root / "outside.json"
        outside.write_text("{}", encoding="utf-8")

        with self.assertRaises(ReleaseGateError):
            resolve_override(self.root, str(outside), "acceptance")

    def test_auto_selection_prefers_integrated_report_over_newer_basic_report(self) -> None:
        demo = self.acceptance
        basic = self.create_acceptance(
            run_demo=False,
            name="visionflow-acceptance-20260722-120500.json",
        )
        newer = self.now.timestamp() + 10
        os.utime(basic, (newer, newer))

        selected = newest_demo_acceptance(self.root)

        self.assertEqual(selected, demo.resolve())

    def test_cli_auto_discovers_latest_evidence(self) -> None:
        exit_code = main(["--root", str(self.root)])

        self.assertEqual(exit_code, 0)
        reports = list(
            (self.root / "artifacts/release-readiness").glob(
                "visionflow-release-readiness-*.json"
            )
        )
        self.assertEqual(len(reports), 1)
        report = json.loads(reports[0].read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "READY_WITH_DEFERRED")


if __name__ == "__main__":
    unittest.main()
