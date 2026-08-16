from __future__ import annotations

import json

import httpx

from app.phase3_reporting import Phase3EventReporter


def test_phase3_reporter_posts_event_and_updates_depth() -> None:
    requests: list[tuple[str, str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(
            (
                request.method,
                request.url.path,
                payload,
            )
        )
        return httpx.Response(200, json={"id": 1})

    reporter = Phase3EventReporter(
        event_url="http://backend.test/api/ai/phase3/events",
        timeout_seconds=1.0,
        max_retries=0,
        queue_capacity=10,
        transport=httpx.MockTransport(handler),
    )

    reporter.start()

    reporter.submit_event(
        {
            "eventKey": "source-1:session-1:NO_HELMET:7",
            "sourceId": "source-1",
            "sessionId": "session-1",
            "sourceType": "DUMMY_VIDEO",
            "droneId": 1,
            "trackId": 7,
            "frameIndex": 28,
            "capturedAt": "2026-08-16T09:00:00+00:00",
            "ppeState": "CONFIRMED_NO_HELMET",
            "noHelmetRate": 1.0,
            "helmetRate": 0.0,
            "unknownRate": 0.0,
            "streakSeconds": 0.9,
        }
    )

    reporter.submit_depth(
        "source-1:session-1:NO_HELMET:7",
        {
            "estimatedDepthM": 1.844,
            "sceneQ33M": 1.648,
            "sceneQ66M": 2.170,
            "depthBucket": "MID",
            "enrichmentLatencyMs": 66.44,
        },
    )

    reporter.close()

    assert len(requests) == 2

    create_method, create_path, create_payload = requests[0]
    assert create_method == "POST"
    assert create_path == "/api/ai/phase3/events"
    assert create_payload["trackId"] == 7
    assert create_payload["ppeState"] == "CONFIRMED_NO_HELMET"

    depth_method, depth_path, depth_payload = requests[1]
    assert depth_method == "PUT"
    assert depth_path == (
    "/api/ai/phase3/events/"
    "source-1:session-1:NO_HELMET:7/depth"
    )
    assert depth_payload["estimatedDepthM"] == 1.844
    assert depth_payload["depthBucket"] == "MID"