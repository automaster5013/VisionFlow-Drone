from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE_PATH = (
    ROOT / "scripts" / "phase3-dji-simulator" / "phase3_software_gate.py"
)
SPEC = importlib.util.spec_from_file_location(
    "phase3_software_gate_repository_mount_test_target",
    GATE_PATH,
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load software gate: {GATE_PATH}")
GATE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GATE
SPEC.loader.exec_module(GATE)


class Phase3SoftwareGateRepositoryMountTest(unittest.TestCase):
    def replay_step(self, *, s1_controlled_live: bool) -> object:
        steps = GATE.build_steps(
            root=Path("/visionflow-repository"),
            backend_url="http://127.0.0.1:8080",
            drone_id=1,
            fixture_video=Path("/visionflow-repository/fixture.mp4"),
            replay_max_frames=300,
            s1_controlled_live=s1_controlled_live,
        )
        return next(step for step in steps if "video replay E2E" in step.name)

    def test_ai_suite_mounts_repository_and_ai_workspace_read_only(self) -> None:
        root = Path("/visionflow-repository")
        command = GATE.ai_test_command(root)

        self.assertIn("VISIONFLOW_REPOSITORY_ROOT=/repo", command)
        self.assertIn(f"{root}:/repo:ro", command)
        self.assertIn(
            f"{root / '03_ai-server' / 'visionflow-ai'}:/workspace:ro",
            command,
        )

    def test_repository_mount_precedes_nested_workspace_mount(self) -> None:
        root = Path("/visionflow-repository")
        command = GATE.ai_test_command(root)
        repository_mount = command.index(f"{root}:/repo:ro")
        workspace_mount = command.index(
            f"{root / '03_ai-server' / 'visionflow-ai'}:/workspace:ro"
        )

        self.assertLess(repository_mount, workspace_mount)
        self.assertEqual(command[repository_mount - 1], "-v")
        self.assertEqual(command[workspace_mount - 1], "-v")

    def test_repository_root_is_not_writable(self) -> None:
        root = Path("/visionflow-repository")
        command = GATE.ai_test_command(root)
        repository_mounts = [
            value
            for value in command
            if value.endswith(":/repo:ro")
        ]
        self.assertEqual(repository_mounts, [f"{root}:/repo:ro"])

    def test_default_replay_step_preserves_general_mode(self) -> None:
        step = self.replay_step(s1_controlled_live=False)
        self.assertNotIn("--s1-controlled-live", step.command)
        self.assertEqual(step.name, "DJI_LIVE video replay E2E")

    def test_s1_replay_step_passes_explicit_opt_in(self) -> None:
        step = self.replay_step(s1_controlled_live=True)
        self.assertEqual(step.command.count("--s1-controlled-live"), 1)
        self.assertEqual(
            step.name,
            "DJI_LIVE S1 controlled-live video replay E2E",
        )


if __name__ == "__main__":
    unittest.main()
