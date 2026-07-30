from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.visionflow_post_closeout_changes import NO_CHANGES_STATUS
from scripts.visionflow_pre_transfer_refresh import (
    ARTIFACT_PATTERNS,
    CONFIRMATION,
    READY_STATUS,
    REQUIRED_ACCEPTANCE_KEYS,
    REQUIRED_SUPPORT_FILES,
    SCRIPT_FILES,
    CommandResult,
    PreTransferRefreshError,
    build_plan,
    execute_refresh,
    sha256_file,
    verify_refresh_report,
)
from scripts.visionflow_project_closeout import CLOSEOUT_STATUS
from scripts.visionflow_transfer_package import (
    READY_STATUS as TRANSFER_PACKAGE_STATUS,
)
from scripts.visionflow_transfer_rehearsal import (
    READY_STATUS as TRANSFER_REHEARSAL_STATUS,
)


NOW = datetime(2026, 7, 23, 9, 0, tzinfo=timezone.utc)


def write(path: Path, value: str = "fixture\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


PRIMARY_ARTIFACTS = {
    "integrated-acceptance": (
        "artifacts/visionflow-acceptance/"
        "visionflow-acceptance-20260723-180001.json"
    ),
    "csp-evidence": (
        "artifacts/csp-observability/"
        "visionflow-csp-observation-20260723T090002Z.json"
    ),
    "consistent-backup": "backups/visionflow-backup-20260723T090003Z.zip",
    "storage-audit": (
        "artifacts/storage-audit/storage-audit-20260723T090004Z/"
        "storage-audit.json"
    ),
    "retention-drill": (
        "artifacts/retention-drill/drill-20260723T090005Z/"
        "retention-recovery-drill.json"
    ),
    "ai-benchmark": (
        "artifacts/ai-benchmark/"
        "visionflow-ai-benchmark-20260723-180006.json"
    ),
    "release-gate": (
        "artifacts/release-readiness/"
        "visionflow-release-readiness-20260723T090007Z.json"
    ),
    "release-evidence": (
        "artifacts/release-evidence/"
        "visionflow-release-evidence-20260723T090008Z.zip"
    ),
    "source-release": (
        "artifacts/source-release/"
        "visionflow-source-release-20260723T090009Z.zip"
    ),
    "machine-baseline": (
        "artifacts/machine-readiness/"
        "visionflow-machine-baseline-20260723T090010Z.json"
    ),
    "migration-handoff": (
        "artifacts/migration-handoff/"
        "visionflow-migration-handoff-20260723T090011Z.zip"
    ),
    "cold-start": (
        "artifacts/cold-start-rehearsal/"
        "visionflow-cold-start-rehearsal-20260723T090012Z.json"
    ),
    "transfer-readiness": (
        "artifacts/transfer-readiness/"
        "visionflow-transfer-readiness-20260723T090013Z.json"
    ),
    "transfer-package": (
        "artifacts/transfer-package/"
        "visionflow-transfer-package-20260723T090014Z.zip"
    ),
    "transfer-rehearsal": (
        "artifacts/transfer-rehearsal/"
        "visionflow-transfer-rehearsal-20260723T090015Z.json"
    ),
    "project-closeout": (
        "artifacts/project-closeout/"
        "visionflow-project-closeout-20260723T090016Z.json"
    ),
    "source-stability": (
        "artifacts/post-closeout-changes/"
        "visionflow-post-closeout-changes-20260723T090017Z.zip"
    ),
}


class FakeRunner:
    def __init__(
        self,
        root: Path,
        *,
        fail_key: str | None = None,
        omit_key: str | None = None,
        bad_baseline: bool = False,
    ) -> None:
        self.root = root
        self.fail_key = fail_key
        self.omit_key = omit_key
        self.bad_baseline = bad_baseline
        self.calls: list[str] = []
        self.commands: list[list[str]] = []
        self.by_script = {
            script: key for key, script in SCRIPT_FILES.items()
        }

    def __call__(
        self,
        command,
        _root: Path,
        _timeout_seconds: int,
    ) -> CommandResult:
        self.commands.append(list(command))
        script = next(
            (
                Path(str(part)).name
                for part in command
                if str(part).lower().endswith(".bat")
            ),
            None,
        )
        if script is None:
            self.calls.append("scripts-tests")
            return CommandResult(0, "tests passed\n")
        key = self.by_script[script]
        self.calls.append(key)
        if key == self.fail_key:
            return CommandResult(7, f"{key} failed\n")
        if key == "evidence-catalog":
            return CommandResult(
                0,
                "VisionFlow evidence catalog: HEALTHY\n",
            )
        if key != self.omit_key:
            artifact = self.root / PRIMARY_ARTIFACTS[key]
            artifact.parent.mkdir(parents=True, exist_ok=True)
            if key == "machine-baseline":
                source = self.root / PRIMARY_ARTIFACTS["source-release"]
                value = (
                    '{"sourceIdentity":{"archiveSha256":"'
                    + (
                        "0" * 64
                        if self.bad_baseline
                        else sha256_file(source)
                    )
                    + '"}}'
                )
                artifact.write_text(value, encoding="utf-8")
            elif key == "transfer-readiness":
                handoff = self.root / PRIMARY_ARTIFACTS["migration-handoff"]
                cold_start = self.root / PRIMARY_ARTIFACTS["cold-start"]
                value = {
                    "handoff": {
                        "path": PRIMARY_ARTIFACTS["migration-handoff"],
                        "sha256": sha256_file(handoff),
                    },
                    "coldStart": {
                        "path": PRIMARY_ARTIFACTS["cold-start"],
                        "sha256": sha256_file(cold_start),
                    },
                }
                artifact.write_text(
                    json.dumps(value),
                    encoding="utf-8",
                )
            elif artifact.suffix == ".json":
                artifact.write_text("{}", encoding="utf-8")
            else:
                artifact.write_bytes(f"{key}-artifact".encode("utf-8"))
        return CommandResult(0, f"{key} passed\n")


class PreTransferRefreshTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        write(self.root / "compose.yaml", "services: {}\n")
        write(self.root / ".env.docker", "DB_PASSWORD=not-printed\n")
        for script in SCRIPT_FILES.values():
            write(self.root / "scripts" / script, "@echo off\n")
        for support in REQUIRED_SUPPORT_FILES:
            write(self.root / "scripts" / support, "# fixture\n")
        self.output = self.root / "artifacts/pre-transfer-refresh"
        self.environment = {
            key: f"value-for-{key.lower()}"
            for key in REQUIRED_ACCEPTANCE_KEYS
        }
        self.reused_benchmark = (
            self.root
            / "artifacts/ai-benchmark/"
            "visionflow-ai-benchmark-20260723-170000.json"
        )
        write(self.reused_benchmark, "{}")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def stable(_root: Path, value: str):
        return Path(value), {
            "status": NO_CHANGES_STATUS,
            "summary": {"totalChanges": 0},
        }

    def rehearsed(self, _root: Path, value: str):
        package = self.root / PRIMARY_ARTIFACTS["transfer-package"]
        return Path(value), {
            "status": TRANSFER_REHEARSAL_STATUS,
            "package": {
                "path": PRIMARY_ARTIFACTS["transfer-package"],
                "sha256": sha256_file(package),
            },
        }

    def execute(
        self,
        runner: FakeRunner,
        *,
        refresh_ai_benchmark: bool = False,
        stability_checker=None,
        rehearsal_checker=None,
    ):
        return execute_refresh(
            self.root,
            output_root=self.output,
            confirmation=CONFIRMATION,
            drone_id=1,
            refresh_ai_benchmark=refresh_ai_benchmark,
            timeout_seconds=300,
            environment=self.environment,
            now=NOW,
            runner=runner,
            stability_checker=stability_checker or self.stable,
            rehearsal_checker=rehearsal_checker or self.rehearsed,
            platform_name="nt",
        )

    def test_plan_is_read_only_and_marks_benchmark_reuse(self) -> None:
        plan = build_plan(False)
        self.assertEqual(19, len(plan))
        benchmark = next(
            item for item in plan if item["key"] == "ai-benchmark"
        )
        self.assertEqual("REUSE", benchmark["mode"])
        self.assertEqual("evidence-catalog", plan[0]["key"])
        self.assertEqual("scripts-tests", plan[1]["key"])
        self.assertEqual("source-stability", plan[-1]["key"])

    def test_confirmation_is_required_before_output_or_runner(self) -> None:
        runner = FakeRunner(self.root)
        with self.assertRaisesRegex(
            PreTransferRefreshError,
            CONFIRMATION,
        ):
            execute_refresh(
                self.root,
                output_root=self.output,
                confirmation="",
                drone_id=1,
                refresh_ai_benchmark=False,
                timeout_seconds=300,
                environment=self.environment,
                now=NOW,
                runner=runner,
                stability_checker=self.stable,
                platform_name="nt",
            )
        self.assertFalse(self.output.exists())
        self.assertEqual([], runner.calls)

    def test_missing_acceptance_key_is_rejected_without_value_output(self) -> None:
        environment = dict(self.environment)
        environment.pop("VISIONFLOW_ACCEPTANCE_ADMIN_KEY")
        runner = FakeRunner(self.root)
        with self.assertRaisesRegex(
            PreTransferRefreshError,
            "VISIONFLOW_ACCEPTANCE_ADMIN_KEY",
        ):
            execute_refresh(
                self.root,
                output_root=self.output,
                confirmation=CONFIRMATION,
                drone_id=1,
                refresh_ai_benchmark=False,
                timeout_seconds=300,
                environment=environment,
                now=NOW,
                runner=runner,
                stability_checker=self.stable,
                platform_name="nt",
            )
        self.assertEqual([], runner.calls)

    def test_missing_reused_benchmark_is_rejected(self) -> None:
        self.reused_benchmark.unlink()
        runner = FakeRunner(self.root)
        with self.assertRaisesRegex(
            PreTransferRefreshError,
            "AI CPU 기준선",
        ):
            self.execute(runner)
        self.assertEqual([], runner.calls)

    def test_missing_evidence_support_file_is_rejected_preflight(
        self,
    ) -> None:
        (
            self.root
            / "scripts"
            / "visionflow_evidence_catalog.py"
        ).unlink()
        runner = FakeRunner(self.root)

        with self.assertRaisesRegex(
            PreTransferRefreshError,
            "visionflow_evidence_catalog.py",
        ):
            self.execute(runner)

        self.assertEqual([], runner.calls)
        self.assertFalse(self.output.exists())

    def test_successful_refresh_uses_exact_order_and_reuses_benchmark(self) -> None:
        runner = FakeRunner(self.root)
        report_path, report, exit_code = self.execute(runner)
        self.assertEqual(0, exit_code)
        self.assertEqual(READY_STATUS, report["status"])
        self.assertTrue(report_path.is_file())
        self.assertEqual(19, len(report["steps"]))
        self.assertEqual(
            "REUSED",
            next(
                item
                for item in report["steps"]
                if item["key"] == "ai-benchmark"
            )["status"],
        )
        self.assertNotIn("ai-benchmark", runner.calls)
        self.assertEqual("evidence-catalog", runner.calls[0])
        self.assertEqual("scripts-tests", runner.calls[1])
        self.assertEqual("source-stability", runner.calls[-1])
        self.assertLess(
            runner.calls.index("transfer-package"),
            runner.calls.index("transfer-rehearsal"),
        )
        self.assertLess(
            runner.calls.index("transfer-rehearsal"),
            runner.calls.index("project-closeout"),
        )
        self.assertEqual(10, len(report["finalArtifacts"]))
        self.assertTrue(report["safety"]["demoDataMutation"])
        self.assertTrue(
            report["safety"]["actualDatabaseBackupIncluded"]
        )
        self.assertTrue(
            report["safety"]["evidenceIntegrityPrecheck"]
        )
        self.assertTrue(
            report["safety"]["offlineTransferRehearsal"]
        )

    def test_evidence_review_failure_stops_before_unit_tests(self) -> None:
        runner = FakeRunner(self.root, fail_key="evidence-catalog")

        _, report, exit_code = self.execute(runner)

        self.assertEqual(1, exit_code)
        self.assertEqual(["evidence-catalog"], runner.calls)
        self.assertEqual(1, len(report["steps"]))
        self.assertEqual(
            "evidence-catalog",
            report["steps"][0]["key"],
        )
        self.assertEqual("FAILED", report["steps"][0]["status"])

    def test_refresh_ai_benchmark_runs_new_measurement(self) -> None:
        runner = FakeRunner(self.root)
        _, report, exit_code = self.execute(
            runner,
            refresh_ai_benchmark=True,
        )
        self.assertEqual(0, exit_code)
        self.assertIn("ai-benchmark", runner.calls)
        benchmark = next(
            item
            for item in report["steps"]
            if item["key"] == "ai-benchmark"
        )
        self.assertEqual("PASS", benchmark["status"])

    def test_failed_step_stops_following_steps_and_writes_report(self) -> None:
        runner = FakeRunner(self.root, fail_key="storage-audit")
        report_path, report, exit_code = self.execute(runner)
        self.assertEqual(1, exit_code)
        self.assertEqual("PRE_TRANSFER_REFRESH_FAILED", report["status"])
        self.assertTrue(report_path.is_file())
        self.assertIn("storage-audit", runner.calls)
        self.assertNotIn("retention-drill", runner.calls)
        failed = next(
            item for item in report["steps"] if item["status"] == "FAILED"
        )
        self.assertEqual("storage-audit", failed["key"])

    def test_missing_new_artifact_fails_closed(self) -> None:
        runner = FakeRunner(self.root, omit_key="consistent-backup")
        _, report, exit_code = self.execute(runner)
        self.assertEqual(1, exit_code)
        self.assertIn("새 산출물", report["error"])
        self.assertNotIn("storage-audit", runner.calls)

    def test_machine_baseline_must_reference_new_source(self) -> None:
        runner = FakeRunner(self.root, bad_baseline=True)
        _, report, exit_code = self.execute(runner)
        self.assertEqual(1, exit_code)
        self.assertIn("이번 안전 소스 ZIP", report["error"])
        self.assertNotIn("migration-handoff", runner.calls)

    def test_source_change_during_refresh_blocks_ready_status(self) -> None:
        runner = FakeRunner(self.root)

        def changed(_root: Path, value: str):
            return Path(value), {
                "status": "POST_CLOSEOUT_CHANGES_READY",
                "summary": {"totalChanges": 1},
            }

        _, report, exit_code = self.execute(
            runner,
            stability_checker=changed,
        )
        self.assertEqual(1, exit_code)
        self.assertIn("소스가 다시 변경", report["error"])

    def test_rehearsal_failure_stops_before_project_closeout(self) -> None:
        runner = FakeRunner(self.root, fail_key="transfer-rehearsal")

        _, report, exit_code = self.execute(runner)

        self.assertEqual(1, exit_code)
        self.assertIn("transfer-rehearsal", runner.calls)
        self.assertNotIn("project-closeout", runner.calls)
        failed = next(
            item for item in report["steps"] if item["status"] == "FAILED"
        )
        self.assertEqual("transfer-rehearsal", failed["key"])

    def test_rehearsal_must_reference_new_transfer_package(self) -> None:
        runner = FakeRunner(self.root)

        def wrong_package(_root: Path, value: str):
            return Path(value), {
                "status": TRANSFER_REHEARSAL_STATUS,
                "package": {
                    "path": PRIMARY_ARTIFACTS["transfer-package"],
                    "sha256": "0" * 64,
                },
            }

        _, report, exit_code = self.execute(
            runner,
            rehearsal_checker=wrong_package,
        )

        self.assertEqual(1, exit_code)
        self.assertIn("이번 최종 패키지", report["error"])
        self.assertNotIn("project-closeout", runner.calls)

    def test_success_report_and_final_artifacts_verify(self) -> None:
        runner = FakeRunner(self.root)
        report_path, report, exit_code = self.execute(runner)
        self.assertEqual(0, exit_code)
        by_key = {
            item["key"]: self.root / item["path"]
            for item in report["finalArtifacts"]
        }

        def handoff(_root: Path, _value: str):
            return by_key["migration-handoff"], {
                "source": {
                    "sha256": sha256_file(by_key["source-release"]),
                },
                "evidence": {
                    "sha256": sha256_file(by_key["release-evidence"]),
                },
                "baseline": {
                    "sha256": sha256_file(by_key["machine-baseline"]),
                },
            }

        def transfer(_root: Path, _value: str):
            return by_key["transfer-package"], {
                "status": TRANSFER_PACKAGE_STATUS,
                "handoff": {
                    "sourcePath": PRIMARY_ARTIFACTS[
                        "migration-handoff"
                    ],
                    "sha256": sha256_file(
                        by_key["migration-handoff"]
                    ),
                },
                "transferReadiness": {
                    "sourcePath": PRIMARY_ARTIFACTS[
                        "transfer-readiness"
                    ],
                    "sha256": sha256_file(
                        by_key["transfer-readiness"]
                    ),
                },
            }

        def closeout(_root: Path, _value: str):
            return by_key["project-closeout"], {
                "status": CLOSEOUT_STATUS,
                "sourceArtifact": {
                    "path": PRIMARY_ARTIFACTS["transfer-package"],
                    "sha256": sha256_file(
                        by_key["transfer-package"]
                    ),
                },
            }

        def rehearsal(_root: Path, _value: str):
            return by_key["transfer-rehearsal"], {
                "status": TRANSFER_REHEARSAL_STATUS,
                "package": {
                    "path": PRIMARY_ARTIFACTS["transfer-package"],
                    "sha256": sha256_file(
                        by_key["transfer-package"]
                    ),
                },
            }

        def stability(_root: Path, _value: str):
            return by_key["source-stability"], {
                "status": NO_CHANGES_STATUS,
                "summary": {"totalChanges": 0},
                "baseline": {
                    "transferPackagePath": PRIMARY_ARTIFACTS[
                        "transfer-package"
                    ],
                    "transferPackageSha256": sha256_file(
                        by_key["transfer-package"]
                    ),
                },
            }

        verified_path, verified = verify_refresh_report(
            self.root,
            str(report_path),
            handoff_verifier=handoff,
            transfer_verifier=transfer,
            rehearsal_verifier=rehearsal,
            closeout_verifier=closeout,
            stability_verifier=stability,
        )
        self.assertEqual(report_path, verified_path)
        self.assertEqual(report, verified)

        report_path.with_suffix(".html").write_text(
            "tampered",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            PreTransferRefreshError,
            "SHA-256",
        ):
            verify_refresh_report(
                self.root,
                str(report_path),
                handoff_verifier=handoff,
                transfer_verifier=transfer,
                rehearsal_verifier=rehearsal,
                closeout_verifier=closeout,
                stability_verifier=stability,
            )

    def test_output_outside_artifacts_is_rejected(self) -> None:
        runner = FakeRunner(self.root)
        with self.assertRaisesRegex(
            PreTransferRefreshError,
            "출력 폴더",
        ):
            execute_refresh(
                self.root,
                output_root=self.root / "outside",
                confirmation=CONFIRMATION,
                drone_id=1,
                refresh_ai_benchmark=False,
                timeout_seconds=300,
                environment=self.environment,
                now=NOW,
                runner=runner,
                stability_checker=self.stable,
                platform_name="nt",
            )
        self.assertEqual([], runner.calls)


if __name__ == "__main__":
    unittest.main()
