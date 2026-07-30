from __future__ import annotations

import json
import shutil
import tempfile
import unittest
import zipfile
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts.visionflow_presentation_gate import (
    READY_STATUS as GATE_READY_STATUS,
)
from scripts.visionflow_presentation_performance import (
    READY_STATUS as PERFORMANCE_READY_STATUS,
)
from scripts.visionflow_presentation_quick_check import (
    READY_STATUS as QUICK_CHECK_READY_STATUS,
)
from scripts.visionflow_presentation_rehearsal import (
    READY_STATUS as REHEARSAL_READY_STATUS,
)
from scripts.visionflow_presentation_signoff import (
    BUNDLE_NAME,
    HTML_NAME,
    MANIFEST_NAME,
    READY_STATUS,
    SIDECAR_NAME,
    PresentationSignoffError,
    artifact_entry,
    create_signoff,
    sha256_bytes,
    sha256_file,
    verify_portable_bundle,
    verify_signoff_report,
)


NOW = datetime(2026, 7, 24, 14, 0, tzinfo=timezone.utc)


class VisionFlowPresentationSignoffTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.output = self.root / "artifacts/presentation-signoff"
        self.gate = {
            "schemaVersion": 1,
            "project": "visionflow",
            "operation": "PRESENTATION_DAY_SIGNOFF",
            "status": GATE_READY_STATUS,
        }
        self.gate_path = self.write_triplet(
            "artifacts/presentation-gate/"
            "visionflow-presentation-gate-20260724T130000Z.json",
            self.gate,
        )
        self.rehearsal = {
            "schemaVersion": 1,
            "project": "visionflow",
            "operation": "PRESENTATION_STABILITY_REHEARSAL",
            "status": REHEARSAL_READY_STATUS,
            "rehearsalId": "rehearsal-001",
            "sourcePresentationGate": artifact_entry(
                self.root,
                self.gate_path,
            ),
            "summary": {
                "passedRuns": 3,
                "requestedRuns": 3,
            },
        }
        self.rehearsal_path = self.write_triplet(
            "artifacts/presentation-rehearsal/"
            "visionflow-presentation-rehearsal-20260724T131000Z.json",
            self.rehearsal,
        )
        self.performance = {
            "schemaVersion": 1,
            "project": "visionflow",
            "operation": "PRESENTATION_PERFORMANCE_ANALYSIS",
            "status": PERFORMANCE_READY_STATUS,
            "analysisId": "analysis-001",
            "sourceRehearsal": artifact_entry(
                self.root,
                self.rehearsal_path,
            ),
            "sourceRehearsalId": "rehearsal-001",
            "analysis": {
                "bottleneck": {"name": "Demo AI detection"},
                "runTiming": {"budgetUsagePercent": 4.2},
                "summary": {"watchStageCount": 0},
            },
            "deferred": [
                {
                    "key": "smartphone-real-sensor-https",
                    "status": "DEFERRED",
                    "scope": "SECOND_PROJECT_FOLLOW_UP",
                    "reason": "later",
                },
                {
                    "key": "dji-mini4-pro-integration",
                    "status": "OUT_OF_SCOPE",
                    "scope": "THIRD_PROJECT",
                    "reason": "phase 3",
                },
            ],
        }
        self.performance_path = self.write_triplet(
            "artifacts/presentation-performance/"
            "visionflow-presentation-performance-20260724T132000Z.json",
            self.performance,
        )
        self.quick_check = {
            "schemaVersion": 1,
            "project": "visionflow",
            "operation": "PRESENTATION_QUICK_CHECK",
            "status": QUICK_CHECK_READY_STATUS,
            "sourcePerformance": artifact_entry(
                self.root,
                self.performance_path,
            ),
            "sourcePerformanceAnalysisId": "analysis-001",
            "summary": {"passed": 10, "total": 10},
            "diagnosis": {"code": "PRESENTATION_PATHS_HEALTHY"},
            "deferred": self.performance["deferred"],
        }
        self.quick_path = self.write_triplet(
            "artifacts/presentation-quick-check/"
            "visionflow-presentation-quick-check-20260724T133000Z.json",
            self.quick_check,
        )

    def write_triplet(self, relative: str, value: dict) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, ensure_ascii=False),
            encoding="utf-8",
        )
        html_path = path.with_suffix(".html")
        html_path.write_text("<html>evidence</html>", encoding="utf-8")
        sidecar = path.with_suffix(".sha256")
        sidecar.write_text(
            f"{sha256_file(path)}  {path.name}\n"
            f"{sha256_file(html_path)}  {html_path.name}\n",
            encoding="utf-8",
        )
        return path

    def verifier_patches(self) -> ExitStack:
        stack = ExitStack()
        mappings = (
            (
                "scripts.visionflow_presentation_signoff."
                "verify_gate_report",
                self.gate_path,
                self.gate,
            ),
            (
                "scripts.visionflow_presentation_signoff."
                "verify_rehearsal_report",
                self.rehearsal_path,
                self.rehearsal,
            ),
            (
                "scripts.visionflow_presentation_signoff."
                "verify_performance_report",
                self.performance_path,
                self.performance,
            ),
            (
                "scripts.visionflow_presentation_signoff."
                "verify_quick_check_report",
                self.quick_path,
                self.quick_check,
            ),
        )
        for target, expected_path, report in mappings:
            def verifier(root, value, path=expected_path, result=report):
                self.assertEqual(self.root, root)
                self.assertEqual(path, (self.root / value).resolve())
                return path, result

            stack.enter_context(patch(target, side_effect=verifier))
        return stack

    def create(self):
        with self.verifier_patches():
            return create_signoff(
                self.root,
                quick_check_value=None,
                output_root=self.output,
                now=NOW,
            )

    def verify(self, report_path: Path):
        with self.verifier_patches():
            return verify_signoff_report(
                root=self.root,
                report_path=report_path,
            )

    def portable_copy(
        self,
        bundle: Path,
        sidecar: Path,
    ) -> tuple[Path, Path]:
        directory = self.root / "portable"
        directory.mkdir()
        bundle_copy = directory / BUNDLE_NAME
        sidecar_copy = directory / SIDECAR_NAME
        shutil.copy2(bundle, bundle_copy)
        shutil.copy2(sidecar, sidecar_copy)
        return bundle_copy, sidecar_copy

    def rewrite_bundle(
        self,
        bundle: Path,
        values: dict[str, bytes],
    ) -> None:
        temporary = bundle.with_suffix(".tmp")
        with zipfile.ZipFile(
            temporary,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for name, content in sorted(values.items()):
                archive.writestr(name, content)
        temporary.replace(bundle)

    def refresh_bundle_digest(
        self,
        bundle: Path,
        sidecar: Path,
    ) -> None:
        lines = []
        for line in sidecar.read_text(encoding="utf-8").splitlines():
            digest, name = line.split()
            if name == BUNDLE_NAME:
                digest = sha256_file(bundle)
            lines.append(f"{digest}  {name}")
        sidecar.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_ready_chain_creates_and_verifies_signoff(self) -> None:
        report_path, html_path, bundle, sidecar, report = self.create()

        self.assertEqual(READY_STATUS, report["status"])
        self.assertEqual(4, report["summary"]["verifiedStages"])
        self.assertEqual(3, report["presentation"]["rehearsalPassedRuns"])
        self.assertEqual(10, report["presentation"]["quickCheckPassed"])
        self.assertTrue(report_path.is_file())
        self.assertTrue(html_path.is_file())
        self.assertTrue(bundle.is_file())
        self.assertTrue(sidecar.is_file())
        verified_path, verified = self.verify(report_path)
        self.assertEqual(report_path, verified_path)
        self.assertEqual(report, verified)

    def test_bundle_contains_fixed_safe_evidence(self) -> None:
        _, _, bundle, _, _ = self.create()

        with zipfile.ZipFile(bundle) as archive:
            names = archive.namelist()

        self.assertIn(MANIFEST_NAME, names)
        self.assertEqual(15, len(names))
        self.assertEqual(len(names), len(set(names)))
        self.assertFalse(
            any(
                name.lower().endswith(
                    (
                        ".pt", ".env", ".pem", ".key", ".p12",
                        ".pfx", ".mp4", ".sql", ".dump",
                    )
                )
                for name in names
            )
        )
        self.assertFalse(any(".." in name.split("/") for name in names))

    def test_bundle_manifest_matches_every_payload(self) -> None:
        _, _, bundle, _, _ = self.create()

        with zipfile.ZipFile(bundle) as archive:
            manifest = json.loads(
                archive.read(MANIFEST_NAME).decode("utf-8")
            )
            payload = {
                name: archive.read(name)
                for name in archive.namelist()
                if name != MANIFEST_NAME
            }

        self.assertEqual(
            set(payload),
            {item["path"] for item in manifest["files"]},
        )
        for item in manifest["files"]:
            self.assertEqual(
                len(payload[item["path"]]),
                item["sizeBytes"],
            )
        self.assertFalse(manifest["safety"]["modelWeightsIncluded"])
        self.assertFalse(manifest["safety"]["databaseBackupIncluded"])

    def test_changed_quick_check_invalidates_signoff(self) -> None:
        report_path, _, _, _, _ = self.create()
        self.quick_path.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(
            PresentationSignoffError,
            "파일 동일성",
        ):
            self.verify(report_path)

    def test_tampered_report_is_rejected_by_sidecar(self) -> None:
        report_path, _, _, _, _ = self.create()
        report_path.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(
            PresentationSignoffError,
            "SHA-256",
        ):
            self.verify(report_path)

    def test_tampered_bundle_is_rejected_by_sidecar(self) -> None:
        report_path, _, bundle, _, _ = self.create()
        bundle.write_bytes(b"changed")

        with self.assertRaisesRegex(
            PresentationSignoffError,
            "SHA-256",
        ):
            self.verify(report_path)

    def test_non_ready_quick_check_blocks_creation(self) -> None:
        self.quick_check["status"] = "PRESENTATION_QUICK_CHECK_BLOCKED"

        with (
            self.verifier_patches(),
            self.assertRaisesRegex(
                PresentationSignoffError,
                "퀵체크가 READY가 아닙니다",
            ),
        ):
            create_signoff(
                self.root,
                quick_check_value=None,
                output_root=self.output,
                now=NOW,
            )

    def test_output_outside_allowed_directory_is_rejected(self) -> None:
        with (
            self.verifier_patches(),
            self.assertRaisesRegex(
                PresentationSignoffError,
                "출력 폴더",
            ),
        ):
            create_signoff(
                self.root,
                quick_check_value=None,
                output_root=self.root / "outside",
                now=NOW,
            )

    def test_report_does_not_record_secrets_or_execute_deferred_work(
        self,
    ) -> None:
        report_path, html_path, _, _, report = self.create()
        value = (
            report_path.read_text(encoding="utf-8")
            + html_path.read_text(encoding="utf-8")
        )

        self.assertNotIn(str(self.root), value)
        self.assertNotIn("OPERATOR_", value)
        self.assertTrue(report["safety"]["readOnly"])
        self.assertFalse(report["safety"]["modelWeightsIncluded"])
        self.assertFalse(report["safety"]["databaseBackupIncluded"])
        self.assertFalse(report["safety"]["gpuValidationExecuted"])
        self.assertFalse(
            report["safety"]["smartphoneSensorValidationExecuted"]
        )
        self.assertFalse(report["safety"]["djiIntegrationExecuted"])

    def test_portable_bundle_verifies_without_original_artifacts(
        self,
    ) -> None:
        _, _, bundle, sidecar, report = self.create()
        bundle_copy, sidecar_copy = self.portable_copy(bundle, sidecar)
        shutil.rmtree(self.root / "artifacts")

        verified_bundle, verified_sidecar, verified = (
            verify_portable_bundle(
                bundle_path=bundle_copy,
                sidecar_path=sidecar_copy,
            )
        )

        self.assertEqual(bundle_copy, verified_bundle)
        self.assertEqual(sidecar_copy, verified_sidecar)
        self.assertEqual(report, verified)

    def test_portable_bundle_uses_sibling_sidecar_by_default(self) -> None:
        _, _, bundle, sidecar, _ = self.create()
        bundle_copy, sidecar_copy = self.portable_copy(bundle, sidecar)

        verified_bundle, verified_sidecar, _ = verify_portable_bundle(
            bundle_path=bundle_copy,
        )

        self.assertEqual(bundle_copy, verified_bundle)
        self.assertEqual(sidecar_copy, verified_sidecar)

    def test_generated_html_uses_canonical_lf_newlines(self) -> None:
        _, html_path, _, _, _ = self.create()

        self.assertNotIn(b"\r\n", html_path.read_bytes())

    def test_portable_bundle_accepts_authenticated_crlf_html(self) -> None:
        _, _, bundle, sidecar, report = self.create()
        bundle_copy, sidecar_copy = self.portable_copy(bundle, sidecar)
        with zipfile.ZipFile(bundle_copy) as archive:
            values = {
                name: archive.read(name)
                for name in archive.namelist()
            }
        html_name = f"signoff/{HTML_NAME}"
        values[html_name] = values[html_name].replace(b"\n", b"\r\n")
        manifest = json.loads(values[MANIFEST_NAME].decode("utf-8"))
        for item in manifest["files"]:
            if item["path"] == html_name:
                item["sizeBytes"] = len(values[html_name])
                item["sha256"] = sha256_bytes(values[html_name])
                break
        values[MANIFEST_NAME] = (
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        self.rewrite_bundle(bundle_copy, values)
        self.refresh_bundle_digest(bundle_copy, sidecar_copy)

        _, _, verified = verify_portable_bundle(
            bundle_path=bundle_copy,
            sidecar_path=sidecar_copy,
        )

        self.assertEqual(report, verified)

    def test_portable_bundle_rejects_changed_external_digest(self) -> None:
        _, _, bundle, sidecar, _ = self.create()
        bundle_copy, sidecar_copy = self.portable_copy(bundle, sidecar)
        bundle_copy.write_bytes(bundle_copy.read_bytes() + b"changed")

        with self.assertRaisesRegex(
            PresentationSignoffError,
            "ZIP SHA-256",
        ):
            verify_portable_bundle(
                bundle_path=bundle_copy,
                sidecar_path=sidecar_copy,
            )

    def test_portable_bundle_rejects_rewritten_invalid_manifest(
        self,
    ) -> None:
        _, _, bundle, sidecar, _ = self.create()
        bundle_copy, sidecar_copy = self.portable_copy(bundle, sidecar)
        with zipfile.ZipFile(bundle_copy) as archive:
            values = {
                name: archive.read(name)
                for name in archive.namelist()
            }
        manifest = json.loads(values[MANIFEST_NAME].decode("utf-8"))
        manifest["status"] = "PRESENTATION_SIGNOFF_BLOCKED"
        values[MANIFEST_NAME] = (
            json.dumps(manifest, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        self.rewrite_bundle(bundle_copy, values)
        self.refresh_bundle_digest(bundle_copy, sidecar_copy)

        with self.assertRaisesRegex(
            PresentationSignoffError,
            "manifest 메타데이터",
        ):
            verify_portable_bundle(
                bundle_path=bundle_copy,
                sidecar_path=sidecar_copy,
            )

    def test_portable_bundle_requires_external_sidecar(self) -> None:
        _, _, bundle, sidecar, _ = self.create()
        bundle_copy, sidecar_copy = self.portable_copy(bundle, sidecar)
        sidecar_copy.unlink()

        with self.assertRaisesRegex(
            PresentationSignoffError,
            "sidecar가 없습니다",
        ):
            verify_portable_bundle(bundle_path=bundle_copy)


if __name__ == "__main__":
    unittest.main()
