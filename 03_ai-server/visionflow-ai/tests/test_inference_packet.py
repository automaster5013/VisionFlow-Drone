from __future__ import annotations

from datetime import UTC, datetime

import numpy as np

from app.domain import (
    Detection,
    FramePacket,
    InferencePacket,
    VideoSourceType,
)


def test_event_payload_matches_spring_request_contract() -> None:
    image = np.zeros((10, 20, 3), dtype=np.uint8)
    frame = FramePacket(
        source_id="digital-twin-camera-001",
        session_id="test-session",
        source_type=VideoSourceType.DUMMY_VIDEO,
        drone_id=1,
        frame_index=7,
        captured_at=datetime(2026, 7, 19, 1, 0, tzinfo=UTC),
        image=image,
    )
    detection = Detection(
        class_id=0,
        class_name="person",
        confidence=0.934512,
        x1=10.0,
        y1=20.0,
        x2=100.0,
        y2=200.0,
    )
    inference = InferencePacket(
        frame=frame,
        detections=(detection,),
        inference_ms=18.421,
        annotated_image=image,
    )

    payload = inference.to_event_payload()

    assert payload["detectionCount"] == 1
    assert payload["capturedAt"] == "2026-07-19T01:00:00+00:00"
    detections = payload["detections"]
    assert isinstance(detections, list)
    assert detections[0] == {
        "classId": 0,
        "className": "person",
        "confidence": 0.934512,
        "x1": 10.0,
        "y1": 20.0,
        "x2": 100.0,
        "y2": 200.0,
    }
