from __future__ import annotations

import json

import httpx

from app.reporting import SpringEventReporter


def test_event_reporter_posts_payload() -> None:
    received_payloads: list[dict[str, object]] = []
    uploaded_snapshots: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            received_payloads.append(json.loads(request.content))
            return httpx.Response(201, json={"id": 1})

        assert request.method == "PUT"
        assert request.url.path == "/api/ai/events/1/snapshot"
        assert request.headers["content-type"].startswith("multipart/form-data;")
        uploaded_snapshots.append(request.content)
        return httpx.Response(200, json={"id": 1, "snapshotAvailable": True})

    reporter = SpringEventReporter(
        event_url="http://backend.test/api/ai/events",
        timeout_seconds=1.0,
        max_retries=0,
        queue_capacity=10,
        transport=httpx.MockTransport(handler),
    )

    reporter.start()
    snapshot_jpeg = b"\xff\xd8test-jpeg\xff\xd9"

    reporter.submit(
        {
            "sourceId": "digital-twin-camera-001",
            "sessionId": "test-session",
            "sourceType": "DUMMY_VIDEO",
            "droneId": 1,
            "frameIndex": 7,
            "capturedAt": "2026-07-19T01:00:00+00:00",
            "inferenceMs": 18.42,
            "detectionCount": 1,
            "detections": [
                {
                    "classId": 0,
                    "className": "person",
                    "confidence": 0.93,
                    "x1": 10.0,
                    "y1": 20.0,
                    "x2": 100.0,
                    "y2": 200.0,
                }
            ],
        },
        snapshot_jpeg,
    )
    reporter.close()

    assert len(received_payloads) == 1
    assert received_payloads[0]["frameIndex"] == 7
    assert received_payloads[0]["sessionId"] == "test-session"
    detections = received_payloads[0]["detections"]
    assert isinstance(detections, list)
    assert detections[0]["x2"] == 100.0
    assert len(uploaded_snapshots) == 1
    assert snapshot_jpeg in uploaded_snapshots[0]
