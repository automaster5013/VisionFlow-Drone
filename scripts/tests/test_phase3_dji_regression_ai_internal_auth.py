from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SIMULATOR_DIR = ROOT / "scripts" / "phase3-dji-simulator"
if str(SIMULATOR_DIR) not in sys.path:
    sys.path.insert(0, str(SIMULATOR_DIR))

REGRESSION_PATH = SIMULATOR_DIR / "phase3_dji_regression.py"
SPEC = importlib.util.spec_from_file_location(
    "phase3_dji_regression_ai_auth_test_target",
    REGRESSION_PATH,
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load regression suite: {REGRESSION_PATH}")
REGRESSION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REGRESSION)


class StubResponse:
    status = 200

    def __enter__(self) -> "StubResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return b"{}"


class Phase3DjiRegressionAiInternalAuthTest(unittest.TestCase):
    def test_raw_request_adds_ai_internal_header(self) -> None:
        ai_internal_key = "ai-key-123456789012345678901234567890"
        with mock.patch.object(
            REGRESSION,
            "urlopen",
            return_value=StubResponse(),
        ) as urlopen_mock:
            status, _ = REGRESSION.raw_request(
                "PUT",
                "http://127.0.0.1:8080/api/ai/phase3/events/missing/depth",
                ai_internal_key=ai_internal_key,
                body={"depthBucket": "MID"},
            )

        self.assertEqual(status, 200)
        request = urlopen_mock.call_args.args[0]
        headers = {name.lower(): value for name, value in request.header_items()}
        self.assertEqual(
            headers[REGRESSION.sim.AI_INTERNAL_KEY_HEADER.lower()],
            ai_internal_key,
        )

    def test_missing_depth_check_forwards_ai_internal_key(self) -> None:
        ai_internal_key = "ai-key-123456789012345678901234567890"
        results: list[dict[str, object]] = []
        with mock.patch.object(
            REGRESSION,
            "raw_request",
            return_value=(404, {}),
        ) as request_mock:
            REGRESSION.test_missing_depth_event(
                "http://127.0.0.1:8080",
                ai_internal_key,
                results,
            )

        self.assertEqual(
            request_mock.call_args.kwargs["ai_internal_key"],
            ai_internal_key,
        )
        self.assertEqual(results[0]["status"], "PASS")

    def test_duplicate_event_check_forwards_key_to_both_requests(self) -> None:
        ai_internal_key = "ai-key-123456789012345678901234567890"
        results: list[dict[str, object]] = []
        with mock.patch.object(
            REGRESSION.sim,
            "create_phase3_event",
            side_effect=[
                {"id": 82, "eventKey": "phase3-dji-sim-reg-test-run"},
                {"id": 82, "eventKey": "phase3-dji-sim-reg-test-run"},
            ],
        ) as create_mock:
            event_key, event_id = REGRESSION.test_duplicate_event_idempotency(
                "http://127.0.0.1:8080",
                1,
                "00000000-0000-0000-0000-000000000001",
                "test-run",
                ai_internal_key,
                results,
            )

        self.assertEqual(event_key, "phase3-dji-sim-reg-test-run")
        self.assertEqual(event_id, 82)
        self.assertEqual(
            create_mock.call_args_list[0].kwargs["ai_internal_key"],
            ai_internal_key,
        )
        self.assertEqual(
            create_mock.call_args_list[1].kwargs["ai_internal_key"],
            ai_internal_key,
        )
        self.assertEqual(results[0]["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
