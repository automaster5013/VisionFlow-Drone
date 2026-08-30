from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
import tempfile
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
sys.modules[SPEC.name] = REPLAY
SPEC.loader.exec_module(REPLAY)


class Phase3DjiVideoReplayAiInternalAuthTest(unittest.TestCase):
    def replay_command(self, *, s1_controlled_live: bool = False) -> list[str]:
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
            model_config=REPLAY.replay_model_config(s1_controlled_live),
        )

    def test_default_command_preserves_general_replay_model(self) -> None:
        command = self.replay_command()
        self.assertIn("AI_MODEL_PROFILE=phase3-dji-replay-gpu", command)
        self.assertIn("AI_MODEL_PATH=/app/models/yolo26m.pt", command)
        self.assertIn("AI_CONFIDENCE=0.35", command)
        self.assertIn("AI_IMAGE_SIZE=640", command)
        self.assertFalse(
            any(value.startswith("AI_MODEL_MANIFEST_PATH=") for value in command)
        )
        self.assertFalse(
            any(value.startswith("AI_EXPECTED_MODEL_SHA256=") for value in command)
        )

    def test_s1_command_locks_controlled_live_contract(self) -> None:
        command = self.replay_command(s1_controlled_live=True)
        self.assertIn("AI_MODEL_PROFILE=AERIAL_SMALL_OBJECT_LIVE", command)
        self.assertIn(
            "AI_MODEL_PATH=/app/models/yolo26m-visdrone-s1-best.pt",
            command,
        )
        self.assertIn(
            "AI_MODEL_MANIFEST_PATH=/app/models/manifests/"
            "yolo26m-visdrone-s1-best.manifest.json",
            command,
        )
        self.assertIn(
            "AI_MODEL_PROFILES_PATH=/workspace/config/model-profiles-v1.json",
            command,
        )
        self.assertIn(
            f"AI_EXPECTED_MODEL_SHA256={REPLAY.S1_EXPECTED_SHA256}",
            command,
        )
        self.assertIn("AI_CONFIDENCE=0.25", command)
        self.assertIn("AI_IMAGE_SIZE=1280", command)
        self.assertNotIn("AI_MODEL_PATH=/app/models/yolo26m.pt", command)

    def test_s1_evidence_identifies_presentation_model_without_secret(self) -> None:
        evidence = REPLAY.replay_model_config(True).evidence()
        self.assertEqual(evidence["mode"], "S1_CONTROLLED_LIVE")
        self.assertEqual(evidence["profile"], "AERIAL_SMALL_OBJECT_LIVE")
        self.assertEqual(
            evidence["profilesPath"],
            "/workspace/config/model-profiles-v1.json",
        )
        self.assertEqual(evidence["expectedModelSha256"], REPLAY.S1_EXPECTED_SHA256)
        self.assertNotIn("aiInternalKey", evidence)

    def test_s1_asset_validation_accepts_exact_weight_sha(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            weight = root / REPLAY.S1_WEIGHT_RELATIVE
            manifest = root / REPLAY.S1_MANIFEST_RELATIVE
            profiles = root / REPLAY.S1_PROFILES_RELATIVE
            for path in (weight, manifest, profiles):
                path.parent.mkdir(parents=True, exist_ok=True)
            weight_bytes = b"visionflow-s1-test-weight"
            weight.write_bytes(weight_bytes)
            manifest.write_text("{}\n", encoding="utf-8")
            profiles.write_text("{}\n", encoding="utf-8")
            expected = hashlib.sha256(weight_bytes).hexdigest()

            with mock.patch.object(REPLAY, "S1_EXPECTED_SHA256", expected):
                REPLAY.validate_s1_controlled_live_assets(root)

    def test_s1_asset_validation_rejects_wrong_weight_sha(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            weight = root / REPLAY.S1_WEIGHT_RELATIVE
            manifest = root / REPLAY.S1_MANIFEST_RELATIVE
            profiles = root / REPLAY.S1_PROFILES_RELATIVE
            for path in (weight, manifest, profiles):
                path.parent.mkdir(parents=True, exist_ok=True)
            weight.write_bytes(b"wrong-weight")
            manifest.write_text("{}\n", encoding="utf-8")
            profiles.write_text("{}\n", encoding="utf-8")

            with self.assertRaisesRegex(REPLAY.ReplayError, "SHA-256"):
                REPLAY.validate_s1_controlled_live_assets(root)

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

    def test_parse_summary_accepts_segmentation_metrics(self) -> None:
        summary = REPLAY.parse_summary(
            "PHASE3_SUMMARY FRAMES_ANALYZED=300 PPE_SAMPLES=50 "
            "POSE_SAMPLES=0 POSE_ASSIGNED=0 POSE_UNASSIGNED=0 "
            "SEGMENTATION_SAMPLES=0 SEGMENTATION_INSTANCES=0 "
            "SEGMENTATION_ASSIGNED=0 SEGMENTATION_UNASSIGNED=0 "
            "SEGMENTATION_MASK_AREA_PX=0.000 "
            "DEPTH_TRIGGER_ATTEMPTS=80 DEPTH_TRIGGERS_ACCEPTED=46 "
            "DEPTH_TRIGGERS_REJECTED=34 DEPTH_RESULTS=46"
        )

        self.assertEqual(
            summary,
            {
                "frames": 300,
                "ppe": 50,
                "pose": 0,
                "pose_assigned": 0,
                "pose_unassigned": 0,
                "triggers": 80,
                "accepted": 46,
                "rejected": 34,
                "depth": 46,
            },
        )

    def test_parse_summary_rejects_missing_required_metric(self) -> None:
        summary = REPLAY.parse_summary(
            "PHASE3_SUMMARY FRAMES_ANALYZED=300 PPE_SAMPLES=50 "
            "POSE_SAMPLES=0 POSE_ASSIGNED=0 POSE_UNASSIGNED=0 "
            "DEPTH_TRIGGER_ATTEMPTS=80 DEPTH_TRIGGERS_ACCEPTED=46 "
            "DEPTH_RESULTS=46"
        )

        self.assertIsNone(summary)

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
