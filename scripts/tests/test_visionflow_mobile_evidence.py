from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts.visionflow_mobile_evidence import (
    MobileEvidenceError,
    collect,
    evaluate,
    find_drone_ids,
    find_session,
    resolve_frontend_url,
)


class VisionFlowMobileEvidenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.now = datetime(2026, 7, 23, 3, 0, tzinfo=timezone.utc)
        self.session = {
            "sessionId": "11111111-2222-3333-4444-555555555555",
            "droneId": 1,
            "status": "COMPLETED",
            "sourceDeviceId": "visionflow-phone-001",
            "startedAt": "2026-07-23T11:50:00+09:00",
            "endedAt": "2026-07-23T11:51:00+09:00",
            "durationSeconds": 60,
            "telemetryCount": 3,
            "aiEventCount": 1,
            "detectionCount": 1,
        }
        self.replay = {
            "sessionId": self.session["sessionId"],
            "droneId": 1,
            "telemetryCount": 3,
            "aiEventCount": 1,
            "detectionCount": 1,
            "telemetry": [
                {
                    "telemetrySource": "MOBILE_SENSOR",
                    "latitude": 37.5,
                    "longitude": 126.9,
                    "heading": 120.0,
                    "pitch": 1.0,
                    "roll": 2.0,
                }
                for _ in range(3)
            ],
            "aiEvents": [{"id": 1}],
        }

    def test_evaluate_passes_without_exposing_coordinates(self) -> None:
        checks, evidence = evaluate(
            self.session,
            self.replay,
            frontend_status=200,
            frontend_headers={
                "permissions-policy": "camera=(self), geolocation=(self), microphone=()"
            },
            min_telemetry=3,
            min_ai_events=1,
            min_detections=1,
        )

        self.assertTrue(all(item["status"] == "PASS" for item in checks))
        serialized = json.dumps(evidence)
        self.assertNotIn("37.5", serialized)
        self.assertNotIn("126.9", serialized)
        self.assertNotIn("visionflow-phone-001", serialized)
        self.assertEqual(len(evidence["sourceDeviceIdSha256Prefix"]), 16)

    def test_orientation_missing_blocks_evidence(self) -> None:
        for item in self.replay["telemetry"]:
            item["heading"] = None
            item["pitch"] = None
            item["roll"] = None

        checks, _ = evaluate(
            self.session,
            self.replay,
            frontend_status=200,
            frontend_headers={
                "permissions-policy": "camera=(self), geolocation=(self), microphone=()"
            },
            min_telemetry=3,
            min_ai_events=1,
            min_detections=1,
        )

        orientation = next(item for item in checks if item["key"] == "orientation-values")
        self.assertEqual(orientation["status"], "BLOCKED")

    def test_numeric_strings_are_accepted_for_big_decimal_sensor_values(self) -> None:
        for item in self.replay["telemetry"]:
            item["latitude"] = "37.5"
            item["longitude"] = "126.9"
            item["heading"] = "120.0"

        checks, _ = evaluate(
            self.session,
            self.replay,
            frontend_status=200,
            frontend_headers={
                "permissions-policy": "camera=(self), geolocation=(self), microphone=()"
            },
            min_telemetry=3,
            min_ai_events=1,
            min_detections=1,
        )

        self.assertEqual(
            next(item for item in checks if item["key"] == "gps-values")["status"],
            "PASS",
        )
        self.assertEqual(
            next(
                item for item in checks if item["key"] == "orientation-values"
            )["status"],
            "PASS",
        )

    def test_frontend_url_comes_from_mobile_https_metadata(self) -> None:
        metadata = (
            self.root
            / "artifacts/mobile-https/certificates/visionflow-mobile-https.json"
        )
        metadata.parent.mkdir(parents=True, exist_ok=True)
        metadata.write_text(
            json.dumps(
                {
                    "mobileUrl": (
                        "https://192.168.46.89:3000/mobile-flight"
                    )
                }
            ),
            encoding="utf-8-sig",
        )

        self.assertEqual(
            resolve_frontend_url(self.root, None),
            "https://192.168.46.89:3000",
        )

    def test_find_session_uses_requested_uuid(self) -> None:
        selected = find_session(
            [self.session],
            session_id=self.session["sessionId"],
            min_telemetry=3,
        )
        self.assertIs(selected, self.session)

    def test_find_session_rejects_unknown_uuid(self) -> None:
        with self.assertRaisesRegex(MobileEvidenceError, "찾을 수 없습니다"):
            find_session([self.session], session_id="missing", min_telemetry=3)

    def test_find_session_chooses_latest_completed_session(self) -> None:
        older = {
            **self.session,
            "sessionId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "startedAt": "2026-07-22T11:50:00+09:00",
        }
        newer = {
            **self.session,
            "sessionId": "ffffffff-1111-2222-3333-444444444444",
            "startedAt": "2026-07-27T15:40:00+09:00",
        }

        selected = find_session(
            [older, newer],
            session_id=None,
            min_telemetry=3,
        )

        self.assertEqual(selected["sessionId"], newer["sessionId"])

    def test_find_drone_ids_returns_sorted_unique_positive_ids(self) -> None:
        self.assertEqual(
            find_drone_ids(
                [
                    {"id": 3},
                    {"id": 1},
                    {"id": 3},
                    {"id": 0},
                    {"id": True},
                    {"id": "2"},
                ]
            ),
            [1, 3],
        )

    def test_find_drone_ids_rejects_empty_inventory(self) -> None:
        with self.assertRaisesRegex(MobileEvidenceError, "등록 드론"):
            find_drone_ids([])

    @patch("scripts.visionflow_mobile_evidence.request")
    @patch("scripts.visionflow_mobile_evidence.request_json")
    def test_collect_writes_json_html_and_sidecar(
        self,
        request_json_mock,
        request_mock,
    ) -> None:
        request_json_mock.side_effect = [[self.session], self.replay]
        request_mock.return_value = (
            200,
            {
                "permissions-policy": "camera=(self), geolocation=(self), microphone=()"
            },
            b"<html></html>",
        )

        json_path, html_path, report, exit_code = collect(
            self.root,
            backend_url="http://localhost:8080",
            frontend_url="https://localhost:3000",
            operator_key="secret-used-only-in-request",
            drone_id=1,
            session_id=None,
            min_telemetry=3,
            min_ai_events=1,
            min_detections=1,
            timeout_seconds=10,
            output="artifacts/mobile-readiness",
            now=self.now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "SMARTPHONE_E2E_PASS")
        self.assertTrue(json_path.is_file())
        self.assertTrue(html_path.is_file())
        self.assertTrue(json_path.with_suffix(".sha256").is_file())
        self.assertNotIn("secret-used-only-in-request", json_path.read_text("utf-8-sig"))
        checksum = hashlib.sha256(json_path.read_bytes()).hexdigest()
        self.assertEqual(
            json_path.with_suffix(".sha256").read_text("utf-8"),
            f"{checksum}  {json_path.name}\n",
        )

    @patch("scripts.visionflow_mobile_evidence.request")
    @patch("scripts.visionflow_mobile_evidence.request_json")
    def test_collect_auto_selects_latest_session_across_all_drones(
        self,
        request_json_mock,
        request_mock,
    ) -> None:
        older_session = {
            **self.session,
            "sessionId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "droneId": 1,
            "startedAt": "2026-07-26T09:28:56+00:00",
        }
        latest_session = {
            **self.session,
            "sessionId": "3c0b11cc-c115-45b4-9814-9ef18ada6188",
            "droneId": 3,
            "startedAt": "2026-07-27T06:40:00+00:00",
        }
        latest_replay = {
            **self.replay,
            "sessionId": latest_session["sessionId"],
            "droneId": 3,
        }
        request_json_mock.side_effect = [
            [{"id": 1}, {"id": 3}],
            [older_session],
            [latest_session],
            latest_replay,
        ]
        request_mock.return_value = (
            200,
            {
                "permissions-policy": "camera=(self), geolocation=(self), microphone=()"
            },
            b"<html></html>",
        )

        _, _, report, exit_code = collect(
            self.root,
            backend_url="http://localhost:8080",
            frontend_url="https://localhost:3000",
            operator_key=None,
            drone_id=None,
            session_id=None,
            min_telemetry=3,
            min_ai_events=1,
            min_detections=1,
            timeout_seconds=10,
            output="artifacts/mobile-readiness",
            now=self.now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["evidence"]["droneId"], 3)
        self.assertEqual(
            report["evidence"]["sessionId"],
            latest_session["sessionId"],
        )
        replay_url = request_json_mock.call_args_list[-1].args[0]
        self.assertIn("/api/drones/3/flight-sessions/", replay_url)


if __name__ == "__main__":
    unittest.main()
