from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SIMULATOR_DIR = ROOT / "scripts" / "phase3-dji-simulator"
if str(SIMULATOR_DIR) not in sys.path:
    sys.path.insert(0, str(SIMULATOR_DIR))

REPLAY_PATH = SIMULATOR_DIR / "phase3_dji_video_replay.py"
SPEC = importlib.util.spec_from_file_location(
    "phase3_dji_video_replay_ai_auth_test_target",
    REPLAY_PATH,
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load replay gate: {REPLAY_PATH}")
REPLAY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPLAY)


class Phase3DjiVideoReplayAiInternalAuthTest(unittest.TestCase):
    def replay_command(self) -> list[str]:
        return REPLAY.docker_replay_command(
            root=ROOT,
            video_path=ROOT / "fixture.mp4",
            image="visionflow-ai-server",
            network="visionflow_visionflow-network",
            backend_container="visionflow-backend",
            container_name="visionflow-ai-dji-replay-test",
            source_id="phase3-dji-replay-test",
            session_id="00000000-0000-0000-0000-000000000001",
            drone_id=1,
            max_frames=300,
        )

    def test_docker_command_inherits_named_ai_key_without_value(self) -> None:
        command = self.replay_command()
        key_indexes = [
            index
            for index, value in enumerate(command)
            if value == "VISIONFLOW_AI_INTERNAL_KEY"
        ]
        self.assertEqual(len(key_indexes), 1)
        self.assertGreater(key_indexes[0], 0)
        self.assertEqual(command[key_indexes[0] - 1], "-e")
        self.assertFalse(
            any(
                value.startswith("VISIONFLOW_AI_INTERNAL_KEY=")
                for value in command
            )
        )

    def test_run_replay_passes_private_environment_to_subprocess(self) -> None:
        environment = {
            "PATH": "mock-path",
            "VISIONFLOW_AI_INTERNAL_KEY": (
                "ai-key-123456789012345678901234567890"
            ),
        }
        completed = subprocess.CompletedProcess(
            args=["docker"],
            returncode=0,
            stdout="PHASE3_SUMMARY FRAMES=1",
            stderr="",
        )
        with mock.patch.object(
            REPLAY.subprocess,
            "run",
            return_value=completed,
        ) as run_mock:
            return_code, _ = REPLAY.run_replay(
                ["docker", "run"],
                timeout=5.0,
                environment=environment,
            )

        self.assertEqual(return_code, 0)
        self.assertIs(run_mock.call_args.kwargs["env"], environment)
        self.assertNotIn(
            environment["VISIONFLOW_AI_INTERNAL_KEY"],
            run_mock.call_args.args[0],
        )

    def test_triggered_missing_event_reports_auth_path_not_video(self) -> None:
        message = REPLAY.missing_event_diagnosis(
            {"frames": 300, "ppe": 50, "triggers": 22, "depth": 16}
        )
        self.assertIn("보고/인증 경로", message)
        self.assertNotIn("다른 MP4", message)

    def test_zero_trigger_missing_event_recommends_trigger_fixture(self) -> None:
        message = REPLAY.missing_event_diagnosis(
            {"frames": 300, "ppe": 50, "triggers": 0, "depth": 0}
        )
        self.assertIn("다른 MP4", message)
        self.assertNotIn("보고/인증 경로", message)

    def test_main_loads_key_and_keeps_it_out_of_evidence_fields(self) -> None:
        source = REPLAY_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "ai_internal_key = sim.require_ai_internal_key(root, env_file)",
            source,
        )
        self.assertIn('"aiInternalAuthentication": True', source)
        self.assertNotIn('"aiInternalKey": ai_internal_key', source)
        self.assertNotIn('f"VISIONFLOW_AI_INTERNAL_KEY={ai_internal_key}"', source)


if __name__ == "__main__":
    unittest.main()
