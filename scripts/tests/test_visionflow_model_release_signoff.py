from __future__ import annotations

import json
import unittest
import zipfile
from datetime import timedelta

from scripts.tests import test_visionflow_model_soak_decision as decision_test
from scripts.visionflow_model_release_signoff import (
    BLOCKED_STATUS,
    MANIFEST_NAME,
    REJECTED_STATUS,
    SIGNED_OFF_STATUS,
    ModelReleaseSignoffError,
    build_plan,
    build_report,
    output_path,
    verify_signoff_report,
    write_signoff,
)
from scripts.visionflow_model_soak_decision import ROLLBACK_CONFIRMATION


NOW = decision_test.NOW + timedelta(hours=1)


class ModelReleaseSignoffTest(unittest.TestCase):
    def setUp(self) -> None:
        fixture = decision_test.ModelSoakDecisionTest(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.root = fixture.root
        self.output = self.root / "artifacts/model-release-signoff"

    def decision(
        self,
        *,
        blocked: bool = False,
        fail_key: str | None = None,
    ):
        runner = decision_test.FakeDecisionRunner(fail_key=fail_key)
        soak_path = (
            self.fixture.blocked_soak()
            if blocked
            else self.fixture.passed_soak_path
        )
        return self.fixture.execute(
            soak_path,
            runner,
            ROLLBACK_CONFIRMATION if blocked else "",
        )[0]

    def create(self, decision_path):
        report, chain = build_report(
            root=self.root,
            decision_path=decision_path,
            now=NOW,
        )
        paths = write_signoff(
            output_directory=self.output,
            report=report,
            chain=chain,
        )
        return report, paths

    def test_stabilized_release_creates_verified_signoff_bundle(self) -> None:
        report, paths = self.create(self.decision())
        report_path, _, bundle_path, _ = paths

        self.assertEqual(SIGNED_OFF_STATUS, report["status"])
        self.assertTrue(report["summary"]["approved"])
        self.assertTrue(bundle_path.is_file())
        verified_path, verified = verify_signoff_report(
            root=self.root,
            report_path=report_path,
        )
        self.assertEqual(report_path, verified_path)
        self.assertEqual(report, verified)

    def test_safe_rollback_creates_rejected_evidence(self) -> None:
        report, paths = self.create(self.decision(blocked=True))

        self.assertEqual(REJECTED_STATUS, report["status"])
        self.assertTrue(report["summary"]["safeRollback"])
        verify_signoff_report(
            root=self.root,
            report_path=paths[0],
        )

    def test_failed_rollback_blocks_signoff(self) -> None:
        report, paths = self.create(
            self.decision(blocked=True, fail_key="rollback-start")
        )

        self.assertEqual(BLOCKED_STATUS, report["status"])
        self.assertTrue(report["summary"]["blocking"])
        verify_signoff_report(
            root=self.root,
            report_path=paths[0],
        )

    def test_bundle_contains_only_fixed_safe_evidence(self) -> None:
        _, paths = self.create(self.decision())
        bundle_path = paths[2]

        with zipfile.ZipFile(bundle_path) as archive:
            names = archive.namelist()

        self.assertIn(MANIFEST_NAME, names)
        self.assertIn(
            "signoff/visionflow-model-release-signoff.json",
            names,
        )
        self.assertFalse(
            any(
                name.lower().endswith(
                    (".pt", ".env", ".pem", ".key", ".mp4")
                )
                for name in names
            )
        )
        self.assertFalse(any(".." in name.split("/") for name in names))

    def test_bundle_manifest_matches_every_payload(self) -> None:
        _, paths = self.create(self.decision())

        with zipfile.ZipFile(paths[2]) as archive:
            manifest = json.loads(
                archive.read(MANIFEST_NAME).decode("utf-8")
            )
            payload_names = {
                name for name in archive.namelist() if name != MANIFEST_NAME
            }

        self.assertEqual(
            payload_names,
            {item["path"] for item in manifest["files"]},
        )
        self.assertFalse(
            manifest["safety"]["modelWeightsIncluded"],
        )

    def test_changed_decision_invalidates_signoff(self) -> None:
        decision_path = self.decision()
        _, paths = self.create(decision_path)
        decision_path.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "동일성"):
            verify_signoff_report(
                root=self.root,
                report_path=paths[0],
            )

    def test_tampered_report_is_rejected_by_sidecar(self) -> None:
        _, paths = self.create(self.decision())
        paths[0].write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "SHA-256"):
            verify_signoff_report(
                root=self.root,
                report_path=paths[0],
            )

    def test_tampered_bundle_is_rejected_by_sidecar(self) -> None:
        _, paths = self.create(self.decision())
        paths[2].write_bytes(b"changed")

        with self.assertRaisesRegex(RuntimeError, "SHA-256"):
            verify_signoff_report(
                root=self.root,
                report_path=paths[0],
            )

    def test_output_outside_signoff_root_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            ModelReleaseSignoffError,
            "artifacts/model-release-signoff",
        ):
            output_path(self.root, "artifacts/other")

    def test_plan_is_read_only_and_covers_safe_bundle(self) -> None:
        plan = build_plan()

        self.assertEqual(6, len(plan))
        self.assertIn("MODEL_RELEASE_STABILIZED", plan[2])
        self.assertIn("최소 증빙 ZIP", plan[4])


if __name__ == "__main__":
    unittest.main()
