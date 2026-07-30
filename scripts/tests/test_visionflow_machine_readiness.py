from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from scripts.visionflow_machine_readiness import (
    MachineReadinessError,
    REQUIRED_MOBILE_EVIDENCE_CHECKS,
    capture_profile,
    command_specs,
    compare_profiles,
    inspect_model,
    read_profile,
    verify_extracted_source,
)


class VisionFlowMachineReadinessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.now = datetime.now(timezone.utc)
        self.create_project()
        self.create_source_archive()

    def write(self, relative: str, value: bytes | str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, bytes):
            path.write_bytes(value)
        else:
            path.write_text(value, encoding="utf-8")
        return path

    def create_project(self) -> None:
        self.write("compose.yaml", "services: {}\n")
        self.write("01_frontend/visionflow-web/package.json", "{}\n")
        self.write("02_backend/visionflow-api/build.gradle", "plugins {}\n")
        self.write("03_ai-server/visionflow-ai/requirements.txt", "fastapi\n")

    def create_source_archive(self, *, sidecar_checksum: str | None = None) -> Path:
        archive = (
            self.root
            / "artifacts/source-release/visionflow-source-release-test.zip"
        )
        archive.parent.mkdir(parents=True, exist_ok=True)
        manifest = {
            "schemaVersion": 1,
            "project": "visionflow",
            "operation": "PORTABLE_SOURCE_RELEASE",
            "summary": {"includedFiles": 1},
            "files": [
                {
                    "path": "compose.yaml",
                    "sizeBytes": 13,
                    "sha256": "0" * 64,
                }
            ],
        }
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr(
                "VisionFlow-Drone/SOURCE_MANIFEST.json",
                json.dumps(manifest),
            )
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        archive.with_suffix(".sha256").write_text(
            f"{sidecar_checksum or checksum}  {archive.name}\n",
            encoding="utf-8",
        )
        return archive

    @staticmethod
    def runner_without_gpu(arguments: tuple[str, ...], timeout: int):
        if arguments[0] == "nvidia-smi":
            return {
                "status": "MISSING",
                "exitCode": None,
                "version": "",
                "durationMs": 1,
            }
        return {
            "status": "PASS",
            "exitCode": 0,
            "version": f"{Path(arguments[0]).name} test-version",
            "durationMs": 1,
        }

    @staticmethod
    def runner_with_gpu(arguments: tuple[str, ...], timeout: int):
        if arguments[0] == "nvidia-smi":
            version = "NVIDIA GeForce RTX 5060, 999.1, 8192"
        else:
            version = f"{Path(arguments[0]).name} test-version"
        return {
            "status": "PASS",
            "exitCode": 0,
            "version": version,
            "durationMs": 1,
        }

    def capture(self, **overrides):
        options = {
            "role": "baseline",
            "output_root": self.root / "artifacts/machine-readiness",
            "expect_gpu": False,
            "model": None,
            "expect_model": False,
            "timeout_seconds": 10,
            "now": self.now,
            "runner": self.runner_without_gpu,
            "port_checker": lambda host, port, timeout: False,
        }
        options.update(overrides)
        return capture_profile(self.root, **options)

    def test_lg_gram_baseline_is_ready_with_gpu_deferred(self) -> None:
        json_path, html_path, profile, exit_code = self.capture()

        self.assertEqual(exit_code, 0)
        self.assertEqual(profile["status"], "BASELINE_READY_WITH_DEFERRED")
        gpu = next(item for item in profile["tools"] if item["key"] == "nvidia-smi")
        self.assertEqual(gpu["status"], "DEFERRED")
        self.assertEqual(profile["summary"]["unreachableServices"], 4)
        self.assertTrue(json_path.is_file())
        self.assertTrue(html_path.is_file())
        self.assertTrue(json_path.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertTrue(json_path.with_suffix(".sha256").is_file())
        checksum = hashlib.sha256(json_path.read_bytes()).hexdigest()
        self.assertEqual(
            json_path.with_suffix(".sha256").read_text(encoding="utf-8"),
            f"{checksum}  {json_path.name}\n",
        )
        self.assertFalse(profile["platform"]["privacy"]["hostnameRecorded"])
        self.assertFalse(profile["platform"]["privacy"]["usernameRecorded"])
        smartphone = next(
            item
            for item in profile["deferred"]
            if item["key"] == "smartphone-real-sensor-https"
        )
        self.assertEqual(smartphone["status"], "DEFERRED")

    def create_mobile_evidence(self, *, checksum: str | None = None) -> Path:
        path = (
            self.root
            / "artifacts/mobile-readiness/visionflow-smartphone-e2e-test.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "schemaVersion": 1,
            "project": "visionflow",
            "operation": "SMARTPHONE_E2E_VERIFICATION",
            "generatedAt": self.now.isoformat(),
            "status": "SMARTPHONE_E2E_PASS",
            "checks": [
                {"key": key, "status": "PASS"}
                for key in sorted(REQUIRED_MOBILE_EVIDENCE_CHECKS)
            ],
            "evidence": {"sessionId": "test-session"},
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
        }
        path.write_text(json.dumps(report), encoding="utf-8-sig")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        path.with_suffix(".sha256").write_text(
            f"{checksum or actual}  {path.name}\n",
            encoding="utf-8",
        )
        return path

    def test_verified_mobile_evidence_changes_deferred_item_to_pass(self) -> None:
        self.create_mobile_evidence()

        _, _, profile, exit_code = self.capture()

        self.assertEqual(exit_code, 0)
        smartphone = next(
            item
            for item in profile["deferred"]
            if item["key"] == "smartphone-real-sensor-https"
        )
        self.assertEqual(smartphone["status"], "PASS")
        self.assertEqual(smartphone["evidence"]["sessionId"], "test-session")
        self.assertEqual(profile["summary"]["validatedDeferred"], 1)

    def test_tampered_mobile_evidence_remains_deferred(self) -> None:
        self.create_mobile_evidence(checksum="f" * 64)

        _, _, profile, exit_code = self.capture()

        self.assertEqual(exit_code, 0)
        smartphone = next(
            item
            for item in profile["deferred"]
            if item["key"] == "smartphone-real-sensor-https"
        )
        self.assertEqual(smartphone["status"], "DEFERRED")
        self.assertIn("SHA-256", smartphone["reason"])

    def test_windows_uses_npm_cmd_shim(self) -> None:
        specs = command_specs("nt", "python.exe")
        npm = next(item for item in specs if item[0] == "npm")
        python = next(item for item in specs if item[0] == "python")

        self.assertEqual(npm[2], ("npm.cmd", "--version"))
        self.assertEqual(python[2], ("python.exe", "--version"))

    def test_required_tool_failure_blocks_profile(self) -> None:
        def failed_docker(arguments: tuple[str, ...], timeout: int):
            result = self.runner_without_gpu(arguments, timeout)
            if arguments[:2] == ("docker", "--version"):
                result["status"] = "MISSING"
                result["exitCode"] = None
            return result

        _, _, profile, exit_code = self.capture(runner=failed_docker)

        self.assertEqual(exit_code, 1)
        self.assertEqual(profile["status"], "BLOCKED")

    def test_source_sidecar_mismatch_blocks_profile(self) -> None:
        archive = next((self.root / "artifacts/source-release").glob("*.zip"))
        archive.with_suffix(".sha256").write_text(
            f"{'f' * 64}  {archive.name}\n",
            encoding="utf-8",
        )

        _, _, profile, exit_code = self.capture()

        self.assertEqual(exit_code, 1)
        self.assertEqual(profile["sourceIdentity"]["status"], "FAILED")

    def test_hp_target_requires_gpu_and_model(self) -> None:
        model = self.write(
            "03_ai-server/visionflow-ai/models/best.pt",
            b"fine-tuned-model",
        )

        _, _, profile, exit_code = self.capture(
            role="target",
            expect_gpu=True,
            model=str(model),
            expect_model=True,
            runner=self.runner_with_gpu,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(profile["status"], "TARGET_READY")
        self.assertEqual(profile["model"]["status"], "PASS")
        self.assertEqual(len(profile["model"]["sha256"]), 64)

    def test_required_gpu_missing_blocks_target(self) -> None:
        _, _, profile, exit_code = self.capture(
            role="target",
            expect_gpu=True,
            expect_model=False,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(profile["status"], "BLOCKED")

    def test_model_outside_project_is_rejected(self) -> None:
        outside = Path(self.temporary.name).parent / "outside-best.pt"
        outside.write_bytes(b"model")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))

        with self.assertRaisesRegex(MachineReadinessError, "프로젝트 루트"):
            inspect_model(self.root, str(outside), True)

    def test_extracted_manifest_verifies_every_source_file(self) -> None:
        source = self.root / "compose.yaml"
        manifest = {
            "schemaVersion": 1,
            "project": "visionflow",
            "operation": "PORTABLE_SOURCE_RELEASE",
            "summary": {"includedFiles": 1},
            "files": [
                {
                    "path": "compose.yaml",
                    "sizeBytes": source.stat().st_size,
                    "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                }
            ],
        }
        manifest_path = self.root / "SOURCE_MANIFEST.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        result = verify_extracted_source(self.root, manifest_path)

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["mode"], "EXTRACTED")

    def profile_for_compare(self, role: str, manifest_sha: str, version: str):
        return {
            "schemaVersion": 1,
            "project": "visionflow",
            "operation": "MACHINE_READINESS_PROFILE",
            "profileId": role,
            "role": role,
            "status": "BASELINE_READY_WITH_DEFERRED" if role == "baseline" else "TARGET_READY",
            "tools": [
                {
                    "key": "docker-cli",
                    "required": True,
                    "status": "PASS",
                    "version": version,
                }
            ],
            "sourceIdentity": {
                "status": "PASS",
                "manifestSha256": manifest_sha,
            },
        }

    def test_comparison_allows_version_difference_when_source_matches(self) -> None:
        baseline = self.profile_for_compare("baseline", "a" * 64, "Docker 1")
        target = self.profile_for_compare("target", "a" * 64, "Docker 2")

        _, result, exit_code = compare_profiles(
            self.root,
            baseline,
            target,
            output_root=self.root / "artifacts/machine-readiness",
            now=self.now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(result["status"], "COMPATIBLE_WITH_VERSION_DIFFERENCES")

    def test_comparison_blocks_different_source_manifest(self) -> None:
        baseline = self.profile_for_compare("baseline", "a" * 64, "Docker 1")
        target = self.profile_for_compare("target", "b" * 64, "Docker 1")

        _, result, exit_code = compare_profiles(
            self.root,
            baseline,
            target,
            output_root=self.root / "artifacts/machine-readiness",
            now=self.now,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(result["status"], "BLOCKED")

    def test_profile_path_outside_artifacts_is_rejected(self) -> None:
        outside = self.root / "outside.json"
        outside.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(MachineReadinessError, "경로"):
            read_profile(self.root, str(outside), "baseline")

    def test_tampered_profile_is_rejected_by_sidecar(self) -> None:
        json_path, _, _, _ = self.capture()
        profile = json.loads(json_path.read_text(encoding="utf-8-sig"))
        profile["status"] = "TAMPERED"
        json_path.write_text(json.dumps(profile), encoding="utf-8")

        with self.assertRaisesRegex(MachineReadinessError, "SHA-256"):
            read_profile(self.root, str(json_path), "baseline")


if __name__ == "__main__":
    unittest.main()
