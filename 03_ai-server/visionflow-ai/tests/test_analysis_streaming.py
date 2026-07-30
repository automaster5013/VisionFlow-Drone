from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx
import numpy as np

from app.domain import (
    Detection,
    FramePacket,
    InferencePacket,
    VideoSourceType,
)
from app.metrics import InferencePerformanceMonitor
from app.streaming import AnnotatedFrameHub, create_stream_app


def _create_inference_packet() -> InferencePacket:
    image = np.zeros((24, 32, 3), dtype=np.uint8)
    frame = FramePacket(
        source_id="smartphone-camera-001",
        session_id="test-session",
        source_type=VideoSourceType.SMARTPHONE_LIVE,
        drone_id=1,
        frame_index=7,
        captured_at=datetime(2026, 7, 19, 10, 0, tzinfo=UTC),
        image=image,
    )
    detection = Detection(
        class_id=0,
        class_name="person",
        confidence=0.93,
        x1=1.0,
        y1=2.0,
        x2=20.0,
        y2=22.0,
    )

    return InferencePacket(
        frame=frame,
        detections=(detection,),
        inference_ms=12.3,
        annotated_image=image,
    )


def test_frame_hub_publishes_status_and_mjpeg_frame() -> None:
    hub = AnnotatedFrameHub(jpeg_quality=80)
    hub.publish(_create_inference_packet())

    status = hub.status()
    stream = hub.iter_mjpeg()
    chunk = next(stream)
    stream.close()
    hub.close()

    assert status["hasFrame"] is True
    assert status["frameIndex"] == 7
    assert status["detectionCount"] == 1
    assert b"Content-Type: image/jpeg" in chunk
    assert b"X-Frame-Index: 7" in chunk


def test_stream_api_returns_status_and_latest_jpeg() -> None:
    hub = AnnotatedFrameHub(jpeg_quality=80)
    packet = _create_inference_packet()
    hub.publish(packet)
    performance_monitor = InferencePerformanceMonitor(
        model_path="models/yolo11n.pt",
        device="cpu",
        source_type="DUMMY_VIDEO",
        configured_input_fps=5.0,
    )
    performance_monitor.record(packet)
    app = create_stream_app(
        hub,
        allowed_origins=("http://localhost:3000",),
        performance_monitor=performance_monitor,
        model_status_provider=lambda: {
            "profile": "test-cpu",
            "sha256": "abc123",
            "cudaAvailable": False,
        },
    )

    async def request_endpoints() -> tuple[
        httpx.Response,
        httpx.Response,
        httpx.Response,
        httpx.Response,
        httpx.Response,
        httpx.Response,
    ]:
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return (
                await client.get("/health"),
                await client.get("/api/streams/status"),
                await client.get("/api/streams/latest.jpg"),
                await client.get("/api/metrics/status"),
                await client.get("/api/models/status"),
                await client.post("/api/metrics/reset"),
            )

    (
        health_response,
        status_response,
        jpeg_response,
        metrics_response,
        model_response,
        reset_response,
    ) = asyncio.run(request_endpoints())

    hub.close()

    assert health_response.status_code == 200
    assert status_response.json()["frameIndex"] == 7
    assert jpeg_response.status_code == 200
    assert jpeg_response.headers["content-type"] == "image/jpeg"
    assert jpeg_response.headers["x-frame-index"] == "7"
    assert metrics_response.status_code == 200
    assert metrics_response.json()["processedFrames"] == 1
    assert metrics_response.json()["totalDetections"] == 1
    assert metrics_response.json()["modelName"] == "yolo11n.pt"
    assert metrics_response.json()["stream"]["frameIndex"] == 7
    assert model_response.status_code == 200
    assert model_response.json()["profile"] == "test-cpu"
    assert model_response.json()["sha256"] == "abc123"
    assert reset_response.status_code == 200
    assert reset_response.json()["running"] is True
    assert performance_monitor.snapshot()["processedFrames"] == 0
