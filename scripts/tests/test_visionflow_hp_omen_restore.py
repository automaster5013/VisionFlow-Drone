from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.tests.test_visionflow_transfer_package import (
    create_backup,
    create_baseline,
    create_evidence,
    create_readiness,
    create_source,
    write_sidecar,
)
from scripts.visionflow_hp_omen_restore import (
    ACTIVATE_CONFIRMATION,
    ACTIVATED_STATUS,
    ACTIVATION_SCRIPTS,
    PREPARE_CONFIRMATION,
    PREPARED_STATUS,
    PREFLIGHT_BLOCKED_STATUS,
    PREFLIGHT_STATUS,
    RECOVERED_STATUS,
    RECOVERY_CONFIRMATION,
    REQUIRED_ACCEPTANCE_KEYS,
    CommandResult,
    HpOmenRestoreError,
    build_plan,
    create_activation_preflight,
    execute_activation,
    execute_activation_recovery,
    inspect_package,
    prepare_workspace,
    sha256_file,
    verify_activation_report,
    verify_activation_preflight_report,
    verify_prepare_report,
    verify_recovery_report,
)
from scripts.visionflow_gpu_preflight_evidence import write_evidence
from scripts.visionflow_machine_readiness import verify_extracted_source
from scripts.visionflow_migration_handoff import create_handoff
from scripts.visionflow_transfer_package import (
    CONFIRMATION as PACKAGE_CONFIRMATION,
    create_transfer_package,
)


NOW = datetime(2026, 7, 24, 1, 0, tzinfo=timezone.utc)


def write(path: Path, value: str = "fixture\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return path


class FakeActivationRunner:
    def __init__(
        self,
        root: Path,
        *,
        fail_key: str | None = None,
        omit_gpu_evidence: bool = False,
        backup_timestamp: str = "20260724T010001Z",
    ) -> None:
        self.root = root
        self.fail_key = fail_key
        self.omit_gpu_evidence = omit_gpu_evidence
        self.backup_timestamp = backup_timestamp
        self.calls: list[str] = []
        self.by_script = {
            script: key for key, script in ACTIVATION_SCRIPTS.items()
        }

    def __call__(
        self,
        command,
        _root: Path,
        _timeout_seconds: int,
    ) -> CommandResult:
        script = next(
            Path(str(item)).name
            for item in command
            if str(item).lower().endswith(".bat")
        )
        key = self.by_script[script]
        self.calls.append(key)
        if key == self.fail_key and key != "restore":
            return CommandResult(9, f"{key} failed\n")
        if key == "restore":
            backup = (
                self.root
                / "backups/pre-restore/"
                f"visionflow-backup-{self.backup_timestamp}.zip"
            )
            backup.parent.mkdir(parents=True, exist_ok=True)
            create_backup(backup)
        elif key == "gpu-stack" and not self.omit_gpu_evidence:
            model = (
                self.root
                / "03_ai-server/visionflow-ai/models/best.pt"
            )
            model_hash = sha256_file(model)
            container_result = {
                "success": True,
                "status": "GPU_MODEL_READY",
                "model": {
                    "profile": "best-gpu",
                    "localFile": True,
                    "sizeBytes": model.stat().st_size,
                    "sha256": model_hash,
                    "deviceRequested": "0",
                    "deviceEffective": "cuda:0",
                    "requireCuda": True,
                    "torchVersion": "2.12.1+cu130",
                    "torchCudaVersion": "13.0",
                    "cudaAvailable": True,
                    "cudaDeviceCount": 1,
                    "cudaDeviceIndex": 0,
                    "cudaDeviceName": "NVIDIA RTX 5060 Laptop GPU",
                    "cudaCapability": [12, 0],
                    "cudaTotalMemoryBytes": 8589934592,
                },
            }
            write_evidence(
                root=self.root,
                model_path=model,
                expected_sha256=model_hash,
                gpu_info="RTX 5060 Laptop GPU, 590.00, 8192 MiB\n",
                docker_info="29.6.1\n",
                container_output=json.dumps(container_result),
                output_directory=(
                    self.root / "artifacts/gpu-readiness"
                ),
                now=NOW + timedelta(seconds=1),
            )
        elif key == "target-profile":
            identity = verify_extracted_source(
                self.root,
                self.root / "SOURCE_MANIFEST.json",
            )
            target = (
                self.root
                / "artifacts/machine-readiness/"
                "visionflow-machine-target-20260724T010002Z.json"
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "project": "visionflow",
                        "operation": "MACHINE_READINESS_PROFILE",
                        "profileId": "22222222-2222-4222-8222-222222222222",
                        "role": "target",
                        "status": "TARGET_READY",
                        "sourceIdentity": identity,
                        "summary": {"blocking": 0},
                    }
                ),
                encoding="utf-8-sig",
            )
            write_sidecar(target)
        elif key == "machine-comparison":
            comparison = (
                self.root
                / "artifacts/machine-readiness/"
                "visionflow-machine-comparison-20260724T010003Z.json"
            )
            comparison.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "project": "visionflow",
                        "operation": "MACHINE_READINESS_COMPARISON",
                        "status": "COMPATIBLE_WITH_VERSION_DIFFERENCES",
                        "sourceIdentity": {"status": "MATCH"},
                        "summary": {"blocking": 0, "warnings": 1},
                    }
                ),
                encoding="utf-8-sig",
            )
        elif key == "acceptance":
            acceptance = (
                self.root
                / "artifacts/visionflow-acceptance/"
                "visionflow-acceptance-20260724-100004.json"
            )
            acceptance.parent.mkdir(parents=True, exist_ok=True)
            acceptance.write_text(
                json.dumps(
                    {
                        "configuration": {
                            "runDemo": True,
                            "runRbac": True,
                            "runSession": True,
                        },
                        "summary": {
                            "total": 10,
                            "passed": 10,
                            "failed": 0,
                        },
                    }
                ),
                encoding="utf-8-sig",
            )
        elif key == "benchmark":
            benchmark = (
                self.root
                / "artifacts/ai-benchmark/"
                "visionflow-ai-benchmark-20260724-100005.json"
            )
            write(benchmark, "{}")
        if key == self.fail_key:
            return CommandResult(9, f"{key} failed\n")
        return CommandResult(0, f"{key} passed\n")


class FakeRecoveryRunner:
    def __init__(
        self,
        root: Path,
        *,
        fail: bool = False,
    ) -> None:
        self.root = root
        self.fail = fail
        self.calls: list[list[str]] = []

    def __call__(
        self,
        command,
        _root: Path,
        _timeout_seconds: int,
    ) -> CommandResult:
        self.calls.append([str(item) for item in command])
        backup = (
            self.root
            / "backups/pre-restore/"
            "visionflow-backup-20260724T010006Z.zip"
        )
        backup.parent.mkdir(parents=True, exist_ok=True)
        create_backup(backup)
        return CommandResult(
            7 if self.fail else 0,
            "recovery failed\n" if self.fail else "recovery passed\n",
        )


class HpOmenRestoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source_root = self.base / "source"
        for relative in (
            "artifacts/source-release",
            "artifacts/release-evidence",
            "artifacts/machine-readiness",
            "artifacts/migration-handoff",
            "artifacts/transfer-readiness",
            "artifacts/transfer-package",
            "backups",
        ):
            (self.source_root / relative).mkdir(parents=True)
        backup = (
            self.source_root
            / "backups/visionflow-backup-20260724T000001Z.zip"
        )
        create_backup(backup)
        source = (
            self.source_root
            / "artifacts/source-release/"
            "visionflow-source-release-20260724T000002Z.zip"
        )
        source_sha, manifest_sha = create_source(source)
        evidence = (
            self.source_root
            / "artifacts/release-evidence/"
            "visionflow-release-evidence-20260724T000003Z.zip"
        )
        create_evidence(evidence, backup)
        baseline = (
            self.source_root
            / "artifacts/machine-readiness/"
            "visionflow-machine-baseline-20260724T000004Z.json"
        )
        create_baseline(baseline, source_sha, manifest_sha)
        handoff, _, _ = create_handoff(
            self.source_root,
            output_root=(
                self.source_root / "artifacts/migration-handoff"
            ),
            now=NOW - timedelta(hours=2),
        )
        readiness = (
            self.source_root
            / "artifacts/transfer-readiness/"
            "visionflow-transfer-readiness-20260724T000005Z.json"
        )
        create_readiness(
            readiness,
            handoff,
            generated_at=NOW - timedelta(hours=1),
        )
        self.package, self.package_sidecar, _ = create_transfer_package(
            self.source_root,
            readiness_value=str(readiness),
            handoff_value=str(handoff),
            backup_value=str(backup),
            output_root=(
                self.source_root / "artifacts/transfer-package"
            ),
            max_readiness_age_hours=24,
            confirmation=PACKAGE_CONFIRMATION,
            now=NOW,
        )
        self.destination = self.base / "HP-Workspace"
        self.environment = {
            key: f"test-{key.lower()}"
            for key in REQUIRED_ACCEPTANCE_KEYS
        }

    def prepare(self):
        return prepare_workspace(
            str(self.package),
            str(self.destination),
            confirmation=PREPARE_CONFIRMATION,
            now=NOW,
        )

    def make_activation_ready(self) -> None:
        write(self.destination / ".env.docker", "MYSQL_PASSWORD=fixture\n")
        write(self.destination / "compose.gpu.yaml", "services: {}\n")
        for script in ACTIVATION_SCRIPTS.values():
            write(self.destination / "scripts" / script, "@echo off\n")
        model = (
            self.destination
            / "03_ai-server/visionflow-ai/models/best.pt"
        )
        model.parent.mkdir(parents=True, exist_ok=True)
        model.write_bytes(b"fine-tuned-model")

    def activate(
        self,
        runner: FakeActivationRunner,
        *,
        run_benchmark: bool = False,
    ):
        return execute_activation(
            self.destination,
            prepare_report_value=None,
            model_value=(
                "03_ai-server/visionflow-ai/models/best.pt"
            ),
            confirmation=ACTIVATE_CONFIRMATION,
            drone_id=1,
            run_benchmark=run_benchmark,
            timeout_seconds=300,
            environment=self.environment,
            now=NOW,
            runner=runner,
            platform_name="nt",
        )

    def test_plan_is_read_only_and_orders_guarded_phases(self) -> None:
        plan = build_plan()
        self.assertEqual(9, len(plan))
        self.assertEqual("READ_ONLY", plan[0]["mode"])
        self.assertEqual("PREPARE_CONFIRMATION", plan[1]["mode"])
        self.assertEqual("PREFLIGHT", plan[3]["mode"])
        self.assertEqual("ACTIVATE_CONFIRMATION", plan[4]["mode"])
        self.assertEqual("RECOVERY_CONFIRMATION", plan[8]["mode"])

    def test_inspect_verifies_package_outside_project_root(self) -> None:
        package, manifest, checksum = inspect_package(str(self.package))
        self.assertEqual(self.package, package)
        self.assertEqual(
            "TRANSFER_PACKAGE_READY_WITH_DEFERRED",
            manifest["status"],
        )
        self.assertEqual(sha256_file(package), checksum)

    def test_prepare_confirmation_is_required_before_destination_io(self) -> None:
        with self.assertRaisesRegex(
            HpOmenRestoreError,
            PREPARE_CONFIRMATION,
        ):
            prepare_workspace(
                str(self.package),
                str(self.destination),
                confirmation="",
                now=NOW,
            )
        self.assertFalse(self.destination.exists())

    def test_prepare_creates_and_verifies_isolated_workspace(self) -> None:
        report_path, report = self.prepare()
        self.assertEqual(PREPARED_STATUS, report["status"])
        self.assertTrue(report_path.is_file())
        self.assertTrue((self.destination / "compose.yaml").is_file())
        self.assertTrue(
            (self.destination / "SOURCE_MANIFEST.json").is_file()
        )
        verified_path, verified = verify_prepare_report(
            self.destination,
            str(report_path),
        )
        self.assertEqual(report_path, verified_path)
        self.assertEqual(report, verified)

    def test_prepare_refuses_existing_destination(self) -> None:
        self.destination.mkdir()
        with self.assertRaisesRegex(HpOmenRestoreError, "이미 존재"):
            self.prepare()
        self.assertEqual([], list(self.destination.iterdir()))

    def test_tampered_package_sidecar_is_rejected(self) -> None:
        self.package_sidecar.write_text(
            f"{'0' * 64}  {self.package.name}\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(HpOmenRestoreError, "SHA-256"):
            self.prepare()
        self.assertFalse(self.destination.exists())

    def test_prepared_source_tamper_is_detected(self) -> None:
        report_path, _ = self.prepare()
        write(self.destination / "compose.yaml", "changed\n")
        with self.assertRaisesRegex(
            HpOmenRestoreError,
            "크기|SHA-256",
        ):
            verify_prepare_report(
                self.destination,
                str(report_path),
            )

    def test_activation_preflight_is_safe_and_independently_verifiable(
        self,
    ) -> None:
        self.prepare()
        self.make_activation_ready()

        report_path, report, exit_code = create_activation_preflight(
            self.destination,
            prepare_report_value=None,
            model_value=(
                "03_ai-server/visionflow-ai/models/best.pt"
            ),
            environment=self.environment,
            platform_name="nt",
            now=NOW,
        )

        self.assertEqual(0, exit_code)
        self.assertEqual(PREFLIGHT_STATUS, report["status"])
        self.assertEqual(7, report["summary"]["passed"])
        self.assertEqual(0, report["summary"]["blocking"])
        self.assertTrue(
            all(item["status"] == "PASS" for item in report["checks"])
        )
        self.assertFalse(report["safety"]["databaseMutation"])
        self.assertFalse(report["safety"]["dockerStarted"])
        self.assertFalse(report["safety"]["serviceStarted"])
        serialized = report_path.read_text(encoding="utf-8-sig")
        for value in self.environment.values():
            self.assertNotIn(value, serialized)

        verified_path, verified = verify_activation_preflight_report(
            self.destination,
            str(report_path),
            environment=self.environment,
            platform_name="nt",
        )
        self.assertEqual(report_path, verified_path)
        self.assertEqual(report, verified)

    def test_activation_preflight_reports_all_missing_role_keys(self) -> None:
        self.prepare()
        self.make_activation_ready()

        report_path, report, exit_code = create_activation_preflight(
            self.destination,
            prepare_report_value=None,
            model_value=(
                "03_ai-server/visionflow-ai/models/best.pt"
            ),
            environment={},
            platform_name="nt",
            now=NOW,
        )

        self.assertEqual(1, exit_code)
        self.assertEqual(PREFLIGHT_BLOCKED_STATUS, report["status"])
        self.assertEqual(1, report["summary"]["blocking"])
        key_check = next(
            item
            for item in report["checks"]
            if item["key"] == "acceptance-keys"
        )
        self.assertEqual("BLOCKED", key_check["status"])
        self.assertTrue(report_path.is_file())
        with self.assertRaisesRegex(
            HpOmenRestoreError,
            "통과 보고서",
        ):
            verify_activation_preflight_report(
                self.destination,
                str(report_path),
                environment={},
                platform_name="nt",
            )

    def test_changed_model_invalidates_activation_preflight_report(
        self,
    ) -> None:
        self.prepare()
        self.make_activation_ready()
        report_path, _, exit_code = create_activation_preflight(
            self.destination,
            prepare_report_value=None,
            model_value=(
                "03_ai-server/visionflow-ai/models/best.pt"
            ),
            environment=self.environment,
            platform_name="nt",
            now=NOW,
        )
        self.assertEqual(0, exit_code)
        (
            self.destination
            / "03_ai-server/visionflow-ai/models/best.pt"
        ).write_bytes(b"changed-after-preflight")

        with self.assertRaisesRegex(
            HpOmenRestoreError,
            "핵심 입력 동일성",
        ):
            verify_activation_preflight_report(
                self.destination,
                str(report_path),
                environment=self.environment,
                platform_name="nt",
            )

    def test_activation_confirmation_is_required_before_runner(self) -> None:
        self.prepare()
        self.make_activation_ready()
        runner = FakeActivationRunner(self.destination)
        with self.assertRaisesRegex(
            HpOmenRestoreError,
            ACTIVATE_CONFIRMATION,
        ):
            execute_activation(
                self.destination,
                prepare_report_value=None,
                model_value=(
                    "03_ai-server/visionflow-ai/models/best.pt"
                ),
                confirmation="",
                drone_id=1,
                run_benchmark=False,
                timeout_seconds=300,
                environment=self.environment,
                now=NOW,
                runner=runner,
                platform_name="nt",
            )
        self.assertEqual([], runner.calls)

    def test_activation_missing_model_is_rejected(self) -> None:
        self.prepare()
        self.make_activation_ready()
        (
            self.destination
            / "03_ai-server/visionflow-ai/models/best.pt"
        ).unlink()
        runner = FakeActivationRunner(self.destination)
        with self.assertRaisesRegex(HpOmenRestoreError, "best.pt"):
            self.activate(runner)
        self.assertEqual([], runner.calls)

    def test_activation_success_uses_order_and_defers_benchmark(self) -> None:
        self.prepare()
        self.make_activation_ready()
        runner = FakeActivationRunner(self.destination)
        report_path, report, exit_code = self.activate(runner)
        self.assertEqual(0, exit_code)
        self.assertEqual(ACTIVATED_STATUS, report["status"])
        self.assertEqual(
            "FIRST_ACTIVATION",
            report["activationLineage"]["status"],
        )
        self.assertTrue(report_path.is_file())
        self.assertEqual(
            [
                "restore",
                "gpu-stack",
                "target-profile",
                "machine-comparison",
                "acceptance",
            ],
            runner.calls,
        )
        self.assertEqual("DEFERRED", report["steps"][-1]["status"])
        self.assertTrue(report["safety"]["databaseRestored"])
        self.assertTrue(report["safety"]["dockerGpuStackStarted"])
        self.assertTrue(report["safety"]["gpuEvidenceCreated"])
        self.assertEqual(
            "GPU_MODEL_READY",
            report["runtime"]["gpuPreflightStatus"],
        )
        self.assertTrue(
            any(
                item["key"] == "gpu-preflight"
                for item in report["artifacts"]
            )
        )

    def test_activation_fails_closed_when_gpu_evidence_is_missing(
        self,
    ) -> None:
        self.prepare()
        self.make_activation_ready()
        runner = FakeActivationRunner(
            self.destination,
            omit_gpu_evidence=True,
        )

        _, report, exit_code = self.activate(runner)

        self.assertEqual(1, exit_code)
        self.assertEqual(
            "HP_OMEN_RUNTIME_ACTIVATION_FAILED",
            report["status"],
        )
        self.assertEqual(["restore", "gpu-stack"], runner.calls)
        self.assertFalse(report["safety"]["gpuEvidenceCreated"])

    def test_activation_can_include_gpu_benchmark(self) -> None:
        self.prepare()
        self.make_activation_ready()
        runner = FakeActivationRunner(self.destination)
        _, report, exit_code = self.activate(
            runner,
            run_benchmark=True,
        )
        self.assertEqual(0, exit_code)
        self.assertEqual("benchmark", runner.calls[-1])
        self.assertTrue(report["runtime"]["benchmarkExecuted"])
        self.assertTrue(
            any(
                item["key"] == "gpu-benchmark"
                for item in report["artifacts"]
            )
        )

    def test_failed_activation_step_stops_following_steps(self) -> None:
        self.prepare()
        self.make_activation_ready()
        runner = FakeActivationRunner(
            self.destination,
            fail_key="gpu-stack",
        )
        _, report, exit_code = self.activate(runner)
        self.assertEqual(1, exit_code)
        self.assertEqual(
            "HP_OMEN_RUNTIME_ACTIVATION_FAILED",
            report["status"],
        )
        self.assertEqual(["restore", "gpu-stack"], runner.calls)
        self.assertFalse(report["safety"]["dockerGpuStackStarted"])
        self.assertTrue(
            any(
                item["key"] == "pre-restore-safety-backup"
                for item in report["artifacts"]
            )
        )

    def test_recovery_requires_confirmation_before_runner(self) -> None:
        self.prepare()
        self.make_activation_ready()
        activation_runner = FakeActivationRunner(
            self.destination,
            fail_key="gpu-stack",
        )
        failed_path, _, failed_code = self.activate(activation_runner)
        self.assertEqual(1, failed_code)
        recovery_runner = FakeRecoveryRunner(self.destination)

        with self.assertRaisesRegex(
            HpOmenRestoreError,
            RECOVERY_CONFIRMATION,
        ):
            execute_activation_recovery(
                self.destination,
                failed_report_value=str(failed_path),
                confirmation="",
                timeout_seconds=300,
                now=NOW + timedelta(seconds=10),
                runner=recovery_runner,
                platform_name="nt",
            )

        self.assertEqual([], recovery_runner.calls)

    def test_failed_activation_can_recover_pre_activation_state(
        self,
    ) -> None:
        self.prepare()
        self.make_activation_ready()
        activation_runner = FakeActivationRunner(
            self.destination,
            fail_key="gpu-stack",
        )
        failed_path, failed, failed_code = self.activate(
            activation_runner
        )
        self.assertEqual(1, failed_code)
        self.assertTrue(failed["safety"]["databaseRestored"])
        recovery_runner = FakeRecoveryRunner(self.destination)

        report_path, report, exit_code = execute_activation_recovery(
            self.destination,
            failed_report_value=str(failed_path),
            confirmation=RECOVERY_CONFIRMATION,
            timeout_seconds=300,
            now=NOW + timedelta(seconds=10),
            runner=recovery_runner,
            platform_name="nt",
        )

        self.assertEqual(0, exit_code)
        self.assertEqual(RECOVERED_STATUS, report["status"])
        self.assertEqual(1, len(recovery_runner.calls))
        self.assertTrue(
            report["safety"]["databaseRestoredToPreActivation"]
        )
        self.assertEqual(
            {
                "failed-activation-report",
                "rollback-source-backup",
                "recovery-pre-restore-backup",
            },
            {item["key"] for item in report["artifacts"]},
        )
        verified_path, verified = verify_recovery_report(
            self.destination,
            str(report_path),
        )
        self.assertEqual(report_path, verified_path)
        self.assertEqual(report, verified)

    def test_restore_failure_with_safety_backup_can_recover(
        self,
    ) -> None:
        self.prepare()
        self.make_activation_ready()
        activation_runner = FakeActivationRunner(
            self.destination,
            fail_key="restore",
        )
        failed_path, failed, failed_code = self.activate(
            activation_runner
        )

        self.assertEqual(1, failed_code)
        self.assertFalse(failed["safety"]["databaseRestored"])
        self.assertTrue(
            failed["safety"]["preRestoreSafetyBackupCreated"]
        )
        self.assertEqual(
            {"pre-restore-safety-backup"},
            {item["key"] for item in failed["artifacts"]},
        )
        recovery_runner = FakeRecoveryRunner(self.destination)
        _, recovered, recovery_code = execute_activation_recovery(
            self.destination,
            failed_report_value=str(failed_path),
            confirmation=RECOVERY_CONFIRMATION,
            timeout_seconds=300,
            now=NOW + timedelta(seconds=10),
            runner=recovery_runner,
            platform_name="nt",
        )

        self.assertEqual(0, recovery_code)
        self.assertEqual(RECOVERED_STATUS, recovered["status"])

    def test_successful_activation_is_not_a_recovery_source(self) -> None:
        self.prepare()
        self.make_activation_ready()
        activation_runner = FakeActivationRunner(self.destination)
        activation_path, _, activation_code = self.activate(
            activation_runner
        )
        self.assertEqual(0, activation_code)
        recovery_runner = FakeRecoveryRunner(self.destination)

        with self.assertRaisesRegex(
            HpOmenRestoreError,
            "복구 가능한",
        ):
            execute_activation_recovery(
                self.destination,
                failed_report_value=str(activation_path),
                confirmation=RECOVERY_CONFIRMATION,
                timeout_seconds=300,
                now=NOW + timedelta(seconds=10),
                runner=recovery_runner,
                platform_name="nt",
            )

        self.assertEqual([], recovery_runner.calls)

    def test_failed_recovery_preserves_new_safety_backup_evidence(
        self,
    ) -> None:
        self.prepare()
        self.make_activation_ready()
        activation_runner = FakeActivationRunner(
            self.destination,
            fail_key="gpu-stack",
        )
        failed_path, _, failed_code = self.activate(activation_runner)
        self.assertEqual(1, failed_code)
        recovery_runner = FakeRecoveryRunner(
            self.destination,
            fail=True,
        )

        report_path, report, recovery_code = (
            execute_activation_recovery(
                self.destination,
                failed_report_value=str(failed_path),
                confirmation=RECOVERY_CONFIRMATION,
                timeout_seconds=300,
                now=NOW + timedelta(seconds=10),
                runner=recovery_runner,
                platform_name="nt",
            )
        )

        self.assertEqual(1, recovery_code)
        self.assertEqual(
            "HP_OMEN_ACTIVATION_RECOVERY_FAILED",
            report["status"],
        )
        self.assertTrue(report["safety"]["recoveryAttempted"])
        self.assertFalse(
            report["safety"]["databaseRestoredToPreActivation"]
        )
        self.assertTrue(
            any(
                item["key"] == "recovery-pre-restore-backup"
                for item in report["artifacts"]
            )
        )
        self.assertTrue(report_path.is_file())

    def test_changed_rollback_backup_blocks_recovery(self) -> None:
        self.prepare()
        self.make_activation_ready()
        activation_runner = FakeActivationRunner(
            self.destination,
            fail_key="gpu-stack",
        )
        failed_path, failed, failed_code = self.activate(
            activation_runner
        )
        self.assertEqual(1, failed_code)
        rollback = next(
            item
            for item in failed["artifacts"]
            if item["key"] == "pre-restore-safety-backup"
        )
        (self.destination / rollback["path"]).write_bytes(b"tampered")
        recovery_runner = FakeRecoveryRunner(self.destination)

        with self.assertRaisesRegex(
            HpOmenRestoreError,
            "동일성|손상|ZIP|SHA-256",
        ):
            execute_activation_recovery(
                self.destination,
                failed_report_value=str(failed_path),
                confirmation=RECOVERY_CONFIRMATION,
                timeout_seconds=300,
                now=NOW + timedelta(seconds=10),
                runner=recovery_runner,
                platform_name="nt",
            )

        self.assertEqual([], recovery_runner.calls)

    def test_successful_activation_blocks_duplicate_activation(
        self,
    ) -> None:
        self.prepare()
        self.make_activation_ready()
        _, _, first_code = self.activate(
            FakeActivationRunner(self.destination)
        )
        self.assertEqual(0, first_code)
        duplicate_runner = FakeActivationRunner(
            self.destination,
            backup_timestamp="20260724T010007Z",
        )

        with self.assertRaisesRegex(HpOmenRestoreError, "이미 완료"):
            self.activate(duplicate_runner)

        self.assertEqual([], duplicate_runner.calls)

    def test_unrecovered_failed_activation_blocks_retry(self) -> None:
        self.prepare()
        self.make_activation_ready()
        _, _, failed_code = self.activate(
            FakeActivationRunner(
                self.destination,
                fail_key="gpu-stack",
            )
        )
        self.assertEqual(1, failed_code)
        retry_runner = FakeActivationRunner(
            self.destination,
            backup_timestamp="20260724T010007Z",
        )

        with self.assertRaisesRegex(
            HpOmenRestoreError,
            "아직 복구되지 않았습니다",
        ):
            self.activate(retry_runner)

        self.assertEqual([], retry_runner.calls)

    def test_successful_recovery_allows_one_activation_retry(
        self,
    ) -> None:
        self.prepare()
        self.make_activation_ready()
        failed_path, _, failed_code = self.activate(
            FakeActivationRunner(
                self.destination,
                fail_key="gpu-stack",
            )
        )
        self.assertEqual(1, failed_code)
        recovery_path, _, recovery_code = execute_activation_recovery(
            self.destination,
            failed_report_value=str(failed_path),
            confirmation=RECOVERY_CONFIRMATION,
            timeout_seconds=300,
            now=NOW + timedelta(seconds=10),
            runner=FakeRecoveryRunner(self.destination),
            platform_name="nt",
        )
        self.assertEqual(0, recovery_code)

        retry_path, retry, retry_code = self.activate(
            FakeActivationRunner(
                self.destination,
                backup_timestamp="20260724T010007Z",
            )
        )

        self.assertEqual(0, retry_code)
        lineage = retry["activationLineage"]
        self.assertEqual("RECOVERED_RETRY_READY", lineage["status"])
        self.assertEqual(
            str(failed_path.relative_to(self.destination)).replace(
                "\\",
                "/",
            ),
            lineage["previousFailedActivation"]["path"],
        )
        self.assertEqual(
            str(recovery_path.relative_to(self.destination)).replace(
                "\\",
                "/",
            ),
            lineage["recoveryReport"]["path"],
        )
        verified_path, verified = verify_activation_report(
            self.destination,
            str(retry_path),
        )
        self.assertEqual(retry_path, verified_path)
        self.assertEqual(retry, verified)

    def test_tampered_latest_recovery_blocks_retry(self) -> None:
        self.prepare()
        self.make_activation_ready()
        failed_path, _, failed_code = self.activate(
            FakeActivationRunner(
                self.destination,
                fail_key="gpu-stack",
            )
        )
        self.assertEqual(1, failed_code)
        recovery_path, _, recovery_code = execute_activation_recovery(
            self.destination,
            failed_report_value=str(failed_path),
            confirmation=RECOVERY_CONFIRMATION,
            timeout_seconds=300,
            now=NOW + timedelta(seconds=10),
            runner=FakeRecoveryRunner(self.destination),
            platform_name="nt",
        )
        self.assertEqual(0, recovery_code)
        recovery_path.with_suffix(".html").write_text(
            "tampered",
            encoding="utf-8",
        )
        retry_runner = FakeActivationRunner(
            self.destination,
            backup_timestamp="20260724T010007Z",
        )

        with self.assertRaisesRegex(HpOmenRestoreError, "SHA-256"):
            self.activate(retry_runner)

        self.assertEqual([], retry_runner.calls)

    def test_activation_report_verifies_and_html_tamper_fails(self) -> None:
        self.prepare()
        self.make_activation_ready()
        runner = FakeActivationRunner(self.destination)
        report_path, report, exit_code = self.activate(runner)
        self.assertEqual(0, exit_code)
        verified_path, verified = verify_activation_report(
            self.destination,
            str(report_path),
        )
        self.assertEqual(report_path, verified_path)
        self.assertEqual(report, verified)
        report_path.with_suffix(".html").write_text(
            "tampered",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(HpOmenRestoreError, "SHA-256"):
            verify_activation_report(
                self.destination,
                str(report_path),
            )

    def test_changed_best_model_invalidates_activation_report(self) -> None:
        self.prepare()
        self.make_activation_ready()
        runner = FakeActivationRunner(self.destination)
        report_path, _, exit_code = self.activate(runner)
        self.assertEqual(0, exit_code)
        (
            self.destination
            / "03_ai-server/visionflow-ai/models/best.pt"
        ).write_bytes(b"changed-model")

        with self.assertRaisesRegex(
            HpOmenRestoreError,
            "현재 모델 파일|best.pt 동일성",
        ):
            verify_activation_report(
                self.destination,
                str(report_path),
            )


if __name__ == "__main__":
    unittest.main()
