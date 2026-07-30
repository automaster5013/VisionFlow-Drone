from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from scripts.visionflow_presentation_gate import (
    AGREED_DEFERRED,
    BLOCKED_STATUS,
    PresentationGateError,
    READY_STATUS,
    run_gate,
    verify_gate_report,
)


NOW = datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc)


class VisionFlowPresentationGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.output = self.root / "artifacts/presentation-gate"
        self.acceptance = self.write_json(
            "artifacts/visionflow-acceptance/"
            "visionflow-acceptance-20260724-075000.json",
            self.acceptance_report(),
        )
        self.readiness = self.write_json(
            "artifacts/release-readiness/"
            "visionflow-release-readiness-20260724T075500Z.json",
            self.readiness_report(),
        )
        self.release = self.write_bytes(
            "artifacts/release-evidence/"
            "visionflow-release-evidence-20260724T075600Z.zip",
            b"verified-release-evidence",
        )
        self.release.with_suffix(".sha256").write_text(
            f"{self.sha(self.release)}  {self.release.name}\n",
            encoding="utf-8",
        )
        self.closeout = self.write_json(
            "artifacts/project-closeout/"
            "visionflow-project-closeout-20260724T070000Z.json",
            {
                "status": "SECOND_PROJECT_CLOSED_WITH_DEFERRED",
                "summary": {"blocking": 0},
            },
        )
        self.release_manifest = self.manifest()
        self.closeout_report = {
            "status": "SECOND_PROJECT_CLOSED_WITH_DEFERRED",
            "summary": {"blocking": 0},
        }

    def write_json(self, relative: str, value: dict) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def write_bytes(self, relative: str, value: bytes) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
        return path

    @staticmethod
    def sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def artifact(self, path: Path) -> dict:
        return {
            "path": path.relative_to(self.root).as_posix(),
            "sizeBytes": path.stat().st_size,
            "sha256": self.sha(path),
        }

    def acceptance_report(
        self,
        *,
        generated_at: datetime = NOW - timedelta(minutes=10),
    ) -> dict:
        names = (
            "Backend health",
            "Backend drone list",
            "Frontend dashboard",
            "Frontend security headers",
            "AI ingest status",
            "AI stream status",
            "RBAC enabled mode",
            "Operator browser session mode",
            "Demo flight complete",
        )
        return {
            "generatedAt": generated_at.isoformat(),
            "configuration": {
                "runDemo": True,
                "runRbac": True,
                "runSession": True,
                "skipAi": False,
            },
            "summary": {
                "total": len(names),
                "passed": len(names),
                "failed": 0,
            },
            "scenario": {"stage": "COMPLETED"},
            "results": [
                {"Name": name, "Passed": True}
                for name in names
            ],
        }

    def readiness_report(self) -> dict:
        acceptance = self.artifact(self.acceptance)
        return {
            "schemaVersion": 1,
            "project": "visionflow",
            "scope": "SECOND_PROJECT_DIGITAL_TWIN",
            "generatedAt": (NOW - timedelta(minutes=5)).isoformat(),
            "status": "READY_WITH_DEFERRED",
            "summary": {"blocked": 0},
            "safety": {
                "readOnly": True,
                "permanentDelete": False,
                "databaseMutation": False,
            },
            "checks": [
                {
                    "key": "acceptance-demo",
                    "evidence": acceptance,
                }
            ],
            "deferred": [dict(item) for item in AGREED_DEFERRED],
        }

    def manifest(self) -> dict:
        readiness = self.artifact(self.readiness)
        acceptance = self.artifact(self.acceptance)
        return {
            "schemaVersion": 1,
            "project": "visionflow",
            "operation": "RELEASE_EVIDENCE_BUNDLE",
            "createdAt": (NOW - timedelta(minutes=4)).isoformat(),
            "readiness": {
                "status": "READY_WITH_DEFERRED",
                "sourcePath": readiness["path"],
                "sourceSha256": readiness["sha256"],
            },
            "evidence": [
                {
                    "key": "acceptance-demo",
                    "sourcePath": acceptance["path"],
                    "sourceSizeBytes": acceptance["sizeBytes"],
                    "sourceSha256": acceptance["sha256"],
                }
            ],
            "supplementalEvidence": [],
            "includedFiles": [{"archivePath": "README.md"}],
        }

    def patched_dependencies(self) -> ExitStack:
        stack = ExitStack()
        stack.enter_context(
            patch(
                "scripts.visionflow_presentation_gate."
                "validate_readiness_report",
                return_value=None,
            )
        )
        stack.enter_context(
            patch(
                "scripts.visionflow_presentation_gate."
                "verify_release_evidence_bundle",
                return_value=(self.release, self.release_manifest),
            )
        )
        stack.enter_context(
            patch(
                "scripts.visionflow_presentation_gate."
                "verify_closeout_file",
                return_value=(self.closeout, self.closeout_report),
            )
        )
        return stack

    def run_presentation_gate(self):
        with self.patched_dependencies():
            return run_gate(
                self.root,
                acceptance=None,
                readiness=None,
                release_evidence=None,
                closeout=None,
                output_root=self.output,
                now=NOW,
                acceptance_max_age_hours=2,
                readiness_max_age_hours=2,
                release_evidence_max_age_hours=2,
            )

    def verify(self, report: Path):
        with self.patched_dependencies():
            return verify_gate_report(
                self.root,
                report.relative_to(self.root).as_posix(),
            )

    def test_ready_report_is_created_and_independently_verified(self) -> None:
        json_path, html_path, sidecar, report, exit_code = (
            self.run_presentation_gate()
        )

        self.assertEqual(0, exit_code)
        self.assertEqual(READY_STATUS, report["status"])
        self.assertEqual(5, report["summary"]["passed"])
        self.assertEqual(0, report["summary"]["blocking"])
        self.assertEqual(2, report["summary"]["deferred"])
        self.assertFalse(
            any(
                item["key"] == "smartphone-real-sensor-https"
                for item in report["deferred"]
            )
        )
        self.assertTrue(json_path.is_file())
        self.assertTrue(html_path.is_file())
        self.assertTrue(sidecar.is_file())
        verified_path, verified = self.verify(json_path)
        self.assertEqual(json_path, verified_path)
        self.assertEqual(report, verified)

    def test_report_does_not_record_absolute_root_or_secrets(self) -> None:
        json_path, html_path, _, report, _ = self.run_presentation_gate()
        rendered = (
            json_path.read_text(encoding="utf-8-sig")
            + html_path.read_text(encoding="utf-8")
        )

        self.assertNotIn(str(self.root), rendered)
        self.assertNotIn("OPERATOR_", rendered)
        self.assertNotIn("rootCA-key.pem", rendered)
        self.assertFalse(report["safety"]["absolutePathsRecorded"])
        self.assertFalse(report["safety"]["environmentValuesRecorded"])

    def test_stale_acceptance_blocks_presentation(self) -> None:
        self.write_json(
            self.acceptance.relative_to(self.root).as_posix(),
            self.acceptance_report(generated_at=NOW - timedelta(hours=3)),
        )
        self.readiness = self.write_json(
            self.readiness.relative_to(self.root).as_posix(),
            self.readiness_report(),
        )
        self.release_manifest = self.manifest()

        _, _, _, report, exit_code = self.run_presentation_gate()

        self.assertEqual(1, exit_code)
        self.assertEqual(BLOCKED_STATUS, report["status"])
        acceptance = report["checks"][0]
        self.assertEqual("FAILED", acceptance["status"])
        self.assertIn("오래됐습니다", acceptance["detail"])

    def test_readiness_acceptance_lineage_mismatch_blocks(self) -> None:
        readiness = json.loads(self.readiness.read_text(encoding="utf-8"))
        readiness["checks"][0]["evidence"]["sha256"] = "f" * 64
        self.readiness.write_text(json.dumps(readiness), encoding="utf-8")
        self.release_manifest = self.manifest()

        _, _, _, report, exit_code = self.run_presentation_gate()

        self.assertEqual(1, exit_code)
        self.assertEqual("FAILED", report["checks"][1]["status"])
        self.assertIn("동일성이 다릅니다", report["checks"][1]["detail"])

    def test_missing_closeout_blocks_with_clear_result(self) -> None:
        self.closeout.unlink()

        _, _, _, report, exit_code = self.run_presentation_gate()

        self.assertEqual(1, exit_code)
        closeout = next(
            item
            for item in report["checks"]
            if item["key"] == "project-closeout"
        )
        self.assertEqual("MISSING", closeout["status"])

    def test_explicit_artifact_outside_allowed_root_is_rejected(self) -> None:
        outside = self.write_json("outside.json", {})

        with self.assertRaisesRegex(PresentationGateError, "허용 영역"):
            run_gate(
                self.root,
                acceptance=str(outside),
                readiness=None,
                release_evidence=None,
                closeout=None,
                output_root=self.output,
                now=NOW,
                acceptance_max_age_hours=2,
                readiness_max_age_hours=2,
                release_evidence_max_age_hours=2,
            )

    def test_report_sidecar_tamper_is_rejected(self) -> None:
        json_path, html_path, _, _, _ = self.run_presentation_gate()
        html_path.write_text("changed", encoding="utf-8")

        with self.assertRaisesRegex(PresentationGateError, "SHA-256"):
            self.verify(json_path)

    def test_source_artifact_tamper_is_rejected(self) -> None:
        json_path, _, _, _, _ = self.run_presentation_gate()
        self.acceptance.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(
            PresentationGateError,
            "증적 동일성이 다릅니다",
        ):
            self.verify(json_path)


if __name__ == "__main__":
    unittest.main()
