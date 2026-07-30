from __future__ import annotations

from datetime import UTC, datetime

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.domain import VideoSourceType
from app.sources import BrowserUploadSource
from app.streaming import AnnotatedFrameHub, create_stream_app


def _jpeg(value: int = 0) -> bytes:
    image = np.full((24, 32, 3), value, dtype=np.uint8)
    encoded, buffer = cv2.imencode(".jpg", image)
    assert encoded
    return buffer.tobytes()


def test_browser_upload_source_creates_smartphone_frame_packet() -> None:
    source = BrowserUploadSource(fps=5.0, queue_capacity=2)
    captured_at = datetime.now(UTC)
    source.open()

    source.submit_jpeg(
        _jpeg(),
        source_id="browser-camera-001",
        session_id="test-session",
        drone_id=1,
        captured_at=captured_at,
    )
    packet = source.read()
    source.close()

    assert packet is not None
    assert packet.source_type is VideoSourceType.SMARTPHONE_LIVE
    assert packet.source_id == "browser-camera-001"
    assert packet.session_id == "test-session"
    assert packet.drone_id == 1
    assert packet.frame_index == 0
    assert packet.captured_at == captured_at


def test_browser_upload_source_drops_oldest_frame_when_queue_is_full() -> None:
    source = BrowserUploadSource(fps=5.0, queue_capacity=1)
    source.open()

    source.submit_jpeg(
        _jpeg(0),
        source_id="browser-camera-001",
        session_id="test-session",
        drone_id=1,
        captured_at=None,
    )
    result = source.submit_jpeg(
        _jpeg(255),
        source_id="browser-camera-001",
        session_id="test-session",
        drone_id=1,
        captured_at=None,
    )
    packet = source.read()
    source.close()

    assert result["droppedPreviousFrame"] is True
    assert result["droppedFrames"] == 1
    assert packet is not None
    assert float(packet.image.mean()) > 250


def test_browser_upload_source_rejects_invalid_jpeg() -> None:
    source = BrowserUploadSource(fps=5.0, queue_capacity=1)

    with pytest.raises(ValueError, match="JPEG"):
        source.submit_jpeg(
            b"not-an-image",
            source_id="browser-camera-001",
            session_id="test-session",
            drone_id=1,
            captured_at=None,
        )


def test_ingest_api_accepts_jpeg_and_exposes_status() -> None:
    source = BrowserUploadSource(fps=5.0, queue_capacity=2)
    source.open()
    app = create_stream_app(
        AnnotatedFrameHub(jpeg_quality=80),
        allowed_origins=("http://localhost:3000",),
        ingest_source=source,
        ingest_max_payload_bytes=100_000,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/ingest/frame",
            params={
                "droneId": 2,
                "sourceId": "browser-camera-002",
                "sessionId": "api-test-session",
                "capturedAt": datetime.now(UTC).isoformat(),
            },
            content=_jpeg(),
            headers={"Content-Type": "image/jpeg"},
        )
        status_response = client.get("/api/ingest/status")

    packet = source.read()
    source.close()

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert status_response.status_code == 200
    assert status_response.json()["acceptedFrames"] == 1
    assert status_response.json()["queueCapacity"] == 2
    assert status_response.json()["inputFps"] >= 0
    assert status_response.json()["dropRatePct"] == 0
    assert packet is not None
    assert packet.drone_id == 2


def test_ingest_api_rejects_payload_over_limit() -> None:
    source = BrowserUploadSource(fps=5.0, queue_capacity=1)
    app = create_stream_app(
        AnnotatedFrameHub(jpeg_quality=80),
        allowed_origins=("http://localhost:3000",),
        ingest_source=source,
        ingest_max_payload_bytes=10,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/ingest/frame",
            params={
                "droneId": 1,
                "sourceId": "browser-camera-001",
                "sessionId": "api-test-session",
            },
            content=_jpeg(),
            headers={"Content-Type": "image/jpeg"},
        )

    assert response.status_code == 413
