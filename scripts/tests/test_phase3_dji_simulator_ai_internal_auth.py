from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SIMULATOR_PATH = (
    ROOT / "scripts" / "phase3-dji-simulator" / "phase3_dji_simulator.py"
)
SPEC = importlib.util.spec_from_file_location(
    "phase3_dji_simulator_ai_auth_test_target",
    SIMULATOR_PATH,
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load simulator: {SIMULATOR_PATH}")
SIMULATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SIMULATOR)


class StubResponse:
    status = 200

    def __enter__(self) -> "StubResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return b"{}"


class Phase3DjiSimulatorAiInternalAuthTest(unittest.TestCase):
    def test_json_request_adds_both_security_headers(self) -> None:
        operator_key = "operator-key-123456789012345678901234"
        ai_internal_key = "ai-key-123456789012345678901234567890"

        with mock.patch.object(
            SIMULATOR,
            "urlopen",
            return_value=StubResponse(),
        ) as urlopen_mock:
            SIMULATOR.json_request(
                "POST",
                "http://127.0.0.1:8080/api/ai/phase3/events",
                operator_key=operator_key,
                ai_internal_key=ai_internal_key,
                body={"eventKey": "test"},
            )

        request = urlopen_mock.call_args.args[0]
        headers = {name.lower(): value for name, value in request.header_items()}
        self.assertEqual(
            headers[SIMULATOR.OPERATOR_KEY_HEADER.lower()],
            operator_key,
        )
        self.assertEqual(
            headers[SIMULATOR.AI_INTERNAL_KEY_HEADER.lower()],
            ai_internal_key,
        )

    def test_ai_internal_key_loads_from_env_file_without_logging_value(self) -> None:
        ai_internal_key = "ai-key-123456789012345678901234567890"
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                f"VISIONFLOW_AI_INTERNAL_KEY={ai_internal_key}\n",
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {"VISIONFLOW_AI_INTERNAL_KEY": ""},
                clear=False,
            ):
                actual = SIMULATOR.require_ai_internal_key(
                    Path(directory),
                    env_file,
                )

        self.assertEqual(actual, ai_internal_key)

    def test_missing_ai_internal_key_fails_before_runtime_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("VISIONFLOW_OPERATOR_KEY=unused\n", encoding="utf-8")
            with mock.patch.dict(
                os.environ,
                {"VISIONFLOW_AI_INTERNAL_KEY": ""},
                clear=False,
            ):
                with self.assertRaisesRegex(
                    SIMULATOR.SimulatorError,
                    "VISIONFLOW_AI_INTERNAL_KEY",
                ):
                    SIMULATOR.require_ai_internal_key(
                        Path(directory),
                        env_file,
                    )

    def test_phase3_mutations_forward_ai_internal_key(self) -> None:
        ai_internal_key = "ai-key-123456789012345678901234567890"
        event_key = "phase3-dji-sim-test-run"
        with mock.patch.object(
            SIMULATOR,
            "json_request",
            side_effect=[
                {"eventKey": event_key},
                {"depthBucket": "MID"},
            ],
        ) as request_mock:
            SIMULATOR.create_phase3_event(
                "http://127.0.0.1:8080",
                1,
                "00000000-0000-0000-0000-000000000001",
                "test-run",
                11,
                ai_internal_key,
            )
            SIMULATOR.enrich_phase3_event(
                "http://127.0.0.1:8080",
                event_key,
                ai_internal_key,
            )

        self.assertEqual(
            request_mock.call_args_list[0].kwargs["ai_internal_key"],
            ai_internal_key,
        )
        self.assertEqual(
            request_mock.call_args_list[1].kwargs["ai_internal_key"],
            ai_internal_key,
        )


if __name__ == "__main__":
    unittest.main()
