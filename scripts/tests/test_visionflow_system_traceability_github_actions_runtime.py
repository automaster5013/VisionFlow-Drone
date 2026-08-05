from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import visionflow_system_traceability_audit as traceability


class SystemTraceabilityGithubActionsRuntimeTest(unittest.TestCase):
    def test_current_github_actions_runtime_is_node24(self) -> None:
        root = SCRIPT_DIR.parent
        self.assertEqual(
            traceability.github_actions_node24_runtime_policy_drift(root),
            [],
        )

    def test_checkout_node20_major_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = self.copy_workflow(root)
            source = workflow.read_text(encoding="utf-8")
            workflow.write_text(
                source.replace("actions/checkout@v6", "actions/checkout@v4"),
                encoding="utf-8",
            )

            drift = (
                traceability.github_actions_node24_runtime_policy_drift(root)
            )

        self.assertIn(
            "version:github-actions:actions/checkout:"
            "expected-v6:actual-v4",
            drift,
        )

    def test_upload_artifact_node20_major_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = self.copy_workflow(root)
            source = workflow.read_text(encoding="utf-8")
            workflow.write_text(
                source.replace(
                    "actions/upload-artifact@v7",
                    "actions/upload-artifact@v4",
                ),
                encoding="utf-8",
            )

            drift = (
                traceability.github_actions_node24_runtime_policy_drift(root)
            )

        self.assertIn(
            "version:github-actions:actions/upload-artifact:"
            "expected-v7:actual-v4",
            drift,
        )

    def test_insecure_node_runtime_opt_out_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = self.copy_workflow(root)
            source = workflow.read_text(encoding="utf-8")
            workflow.write_text(
                source
                + "\nenv:\n"
                + "  ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION: true\n",
                encoding="utf-8",
            )

            drift = (
                traceability.github_actions_node24_runtime_policy_drift(root)
            )

        self.assertIn(
            "override:github-actions:insecure-node-runtime-opt-out",
            drift,
        )

    def copy_workflow(self, target_root: Path) -> Path:
        relative = Path(".github/workflows/api-audit.yml")
        source = SCRIPT_DIR.parent / relative
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return target


if __name__ == "__main__":
    unittest.main()
