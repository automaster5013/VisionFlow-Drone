from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from scripts.visionflow_project_closeout import (
    CLOSEOUT_STATUS,
    ProjectCloseoutError,
    create_closeout,
    sha256_file,
    verify_closeout_file,
    write_sidecar,
)


NOW = datetime(2026, 7, 23, 7, 0, tzinfo=timezone.utc)


def package_manifest(
    *,
    generated_at: datetime = NOW - timedelta(hours=1),
    status: str = "TRANSFER_PACKAGE_READY_WITH_DEFERRED",
) -> dict:
    return {
        "schemaVersion": 1,
        "project": "visionflow",
        "scope": "SECOND_PROJECT_DIGITAL_TWIN",
        "operation": "TRANSFER_PACKAGE",
        "packageId": "11111111-1111-4111-8111-111111111111",
        "generatedAt": generated_at.isoformat(),
        "status": status,
        "handoff": {
            "releaseReadinessStatus": "READY_WITH_DEFERRED",
            "baselineStatus": "BASELINE_READY_WITH_DEFERRED",
        },
        "transferReadiness": {
            "status": "TRANSFER_READY_WITH_DEFERRED",
        },
        "databaseBackup": {
            "internalStatus": "VALID",
            "fileCount": 3,
        },
        "deferred": [
            {"key": "hp-omen-runtime-restore", "status": "DEFERRED"},
            {"key": "gpu-best-model", "status": "DEFERRED"},
            {
                "key": "hp-target-smartphone-https-revalidation",
                "status": "DEFERRED",
            },
            {"key": "dji-mini4-pro", "status": "OUT_OF_SCOPE"},
        ],
        "safety": {
            "containsOperationalDatabaseBackup": True,
            "containsEnvironmentFiles": False,
            "containsOperatorKeys": False,
            "containsPrivateKeys": False,
            "containsModelWeights": False,
            "originalInputsModified": False,
            "externalTransferPerformed": False,
        },
    }


class ProjectCloseoutTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.package_dir = self.root / "artifacts/transfer-package"
        self.output = self.root / "artifacts/project-closeout"
        self.package_dir.mkdir(parents=True)
        self.output.mkdir(parents=True)
        self.package = (
            self.package_dir
            / "visionflow-transfer-package-20260723T060000Z.zip"
        )
        self.package.write_bytes(b"verified-transfer-package")
        self.manifest = package_manifest()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def verifier(self, root: Path, value: str):
        self.assertEqual(self.root, root)
        self.assertEqual(self.package, Path(value))
        return self.package, self.manifest

    def create(self):
        with mock.patch(
            "scripts.visionflow_project_closeout.verify_transfer_package_file",
            side_effect=self.verifier,
        ):
            return create_closeout(
                self.root,
                self.package,
                output_root=self.output,
                max_package_age_hours=24,
                now=NOW,
            )

    def verify(self, report: Path):
        with mock.patch(
            "scripts.visionflow_project_closeout.verify_transfer_package_file",
            side_effect=self.verifier,
        ):
            return verify_closeout_file(self.root, str(report))

    def resign(self, report: Path) -> None:
        write_sidecar(
            report.with_suffix(".sha256"),
            [
                report,
                report.with_suffix(".html"),
                report.with_suffix(".md"),
            ],
        )

    def test_create_and_verify_closeout_report(self) -> None:
        report, html, markdown, sidecar, value = self.create()
        self.assertTrue(report.is_file())
        self.assertTrue(html.is_file())
        self.assertTrue(markdown.is_file())
        self.assertTrue(sidecar.is_file())
        self.assertEqual(CLOSEOUT_STATUS, value["status"])
        self.assertEqual(0, value["summary"]["blocking"])
        self.assertEqual(8, value["summary"]["completedCapabilities"])
        self.assertEqual(3, value["summary"]["deferred"])
        self.assertEqual(1, value["summary"]["outOfScope"])
        verified_path, verified = self.verify(report)
        self.assertEqual(report, verified_path)
        self.assertEqual(value, verified)

    def test_report_is_non_sensitive_index_only(self) -> None:
        report, html, markdown, _, value = self.create()
        rendered = (
            report.read_text(encoding="utf-8-sig")
            + html.read_text(encoding="utf-8")
            + markdown.read_text(encoding="utf-8")
        )
        self.assertFalse(value["safety"]["containsDatabaseBackup"])
        self.assertNotIn("CREATE TABLE", rendered)
        self.assertNotIn("OPERATOR_", rendered)
        self.assertNotIn("rootCA-key.pem", rendered)
        self.assertIn("best.pt", rendered)
        self.assertNotIn("serialized-model-weight-bytes", rendered)
        self.assertEqual(sha256_file(self.package), value["sourceArtifact"]["sha256"])

    def test_stale_package_is_rejected(self) -> None:
        self.manifest = package_manifest(generated_at=NOW - timedelta(hours=25))
        with self.assertRaisesRegex(ProjectCloseoutError, "유효 범위"):
            self.create()

    def test_blocked_package_is_rejected(self) -> None:
        self.manifest = package_manifest(status="BLOCKED")
        with self.assertRaisesRegex(ProjectCloseoutError, "종결 조건"):
            self.create()

    def test_unknown_deferred_item_is_rejected(self) -> None:
        self.manifest["deferred"].append(
            {"key": "unexpected-work", "status": "DEFERRED"}
        )
        with self.assertRaisesRegex(ProjectCloseoutError, "알 수 없는"):
            self.create()

    def test_legacy_smartphone_deferred_key_is_normalized(self) -> None:
        smartphone = next(
            item
            for item in self.manifest["deferred"]
            if item["key"] == "hp-target-smartphone-https-revalidation"
        )
        smartphone["key"] = "smartphone-real-sensor-https"

        _, _, _, _, report = self.create()

        self.assertFalse(
            any(
                item["key"] == "smartphone-real-sensor-https"
                for item in report["deferred"]
            )
        )
        target_mobile = next(
            item
            for item in report["deferred"]
            if item["key"] == "hp-target-smartphone-https-revalidation"
        )
        self.assertIn("새 LAN IP", target_mobile["reason"])

    def test_output_outside_artifacts_is_rejected(self) -> None:
        with self.assertRaisesRegex(ProjectCloseoutError, "출력 폴더"):
            with mock.patch(
                "scripts.visionflow_project_closeout.verify_transfer_package_file",
                side_effect=self.verifier,
            ):
                create_closeout(
                    self.root,
                    self.package,
                    output_root=self.root / "outside",
                    max_package_age_hours=24,
                    now=NOW,
                )

    def test_sidecar_tamper_is_rejected(self) -> None:
        report, _, markdown, _, _ = self.create()
        markdown.write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ProjectCloseoutError, "SHA-256"):
            self.verify(report)

    def test_executable_html_is_rejected_after_resigning(self) -> None:
        report, html, _, _, _ = self.create()
        html.write_text("<script>alert(1)</script>", encoding="utf-8")
        self.resign(report)
        with self.assertRaisesRegex(ProjectCloseoutError, "실행 가능한"):
            self.verify(report)

    def test_json_html_mismatch_is_rejected_after_resigning(self) -> None:
        report, html, _, _, _ = self.create()
        html.write_text(
            html.read_text(encoding="utf-8").replace("최종 증빙", "변조된 증빙"),
            encoding="utf-8",
        )
        self.resign(report)
        with self.assertRaisesRegex(ProjectCloseoutError, "내용이 일치"):
            self.verify(report)

    def test_source_package_tamper_is_rejected(self) -> None:
        report, _, _, _, _ = self.create()
        self.package.write_bytes(b"changed")
        with self.assertRaisesRegex(ProjectCloseoutError, "동일성이 다릅니다"):
            self.verify(report)

    def test_summary_tamper_is_rejected_after_resigning(self) -> None:
        report, _, _, _, _ = self.create()
        value = json.loads(report.read_text(encoding="utf-8-sig"))
        value["summary"]["deferred"] = 99
        report.write_text(
            json.dumps(value, ensure_ascii=False, indent=2),
            encoding="utf-8-sig",
        )
        self.resign(report)
        with self.assertRaisesRegex(ProjectCloseoutError, "집계"):
            self.verify(report)


if __name__ == "__main__":
    unittest.main()
