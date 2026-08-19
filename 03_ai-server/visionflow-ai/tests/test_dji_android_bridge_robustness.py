from __future__ import annotations

import os
import shutil
import subprocess

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.domain import VideoSourceType
from app.sources.dji_android_bridge import DjiAndroidBridgeSource
from app.streaming import AnnotatedFrameHub, create_stream_app


DJI_BRIDGE_KEY_HEADER = "X-VisionFlow-DJI-Key"
DJI_BRIDGE_KEY = "dji-bridge-test-key-0123456789abcdef"


def _require_ffmpeg() -> str:
    executable = shutil.which("ffmpeg")
    if executable is not None:
        return executable

    if os.getenv("VISIONFLOW_REQUIRE_FFMPEG_TEST") == "1":
        pytest.fail("FFmpeg is required by the DJI Android Bridge robustness gate.")

    pytest.skip("FFmpeg is not installed in this AI test environment.")


def _frames(frame_count: int) -> list[np.ndarray]:
    frames: list[np.ndarray] = []
    for index in range(frame_count):
        frame = np.zeros((64, 96, 3), dtype=np.uint8)
        frame[:, :, index % 3] = 60 + ((index * 13) % 180)
        frames.append(frame)
    return frames


def _encoded_fixture(
    codec: str,
    *,
    frame_count: int = 8,
    fps: int = 10,
) -> bytes:
    executable = _require_ffmpeg()
    normalized = codec.upper()

    if normalized == "H264":
        encoder_args = [
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-tune",
            "zerolatency",
            "-f",
            "h264",
        ]
    elif normalized == "H265":
        encoder_args = [
            "-c:v",
            "libx265",
            "-preset",
            "ultrafast",
            "-tune",
            "zerolatency",
            "-x265-params",
            "log-level=error",
            "-f",
            "hevc",
        ]
    else:
        raise AssertionError(f"unsupported fixture codec: {codec}")

    frames = _frames(frame_count)
    result = subprocess.run(
        [
            executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            "96x64",
            "-r",
            str(fps),
            "-i",
            "pipe:0",
            "-frames:v",
            str(frame_count),
            *encoder_args,
            "pipe:1",
        ],
        input=b"".join(frame.tobytes() for frame in frames),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr.decode(
        "utf-8",
        errors="replace",
    )
    assert len(result.stdout) > 100
    return result.stdout


def _client(
    source: DjiAndroidBridgeSource,
) -> TestClient:
    app = create_stream_app(
        AnnotatedFrameHub(jpeg_quality=80),
        allowed_origins=("http://localhost:3000",),
        ingest_source=source,
        internal_security_enabled=False,
        dji_bridge_api_key=DJI_BRIDGE_KEY,
    )
    return TestClient(app)


def _post_stream(
    client: TestClient,
    *,
    payload: bytes,
    codec: str,
    content_type: str,
    source_id: str,
) -> object:
    return client.post(
        "/api/ingest/dji/stream",
        params={
            "droneId": 1,
            "sourceId": source_id,
            "sessionId": "phase3-bridge-robustness",
            "codec": codec,
        },
        headers={
            "Content-Type": content_type,
            DJI_BRIDGE_KEY_HEADER: DJI_BRIDGE_KEY,
        },
        content=payload,
    )


def test_h265_hevc_ingress_decodes_to_dji_live_frame() -> None:
    h265 = _encoded_fixture("H265")
    source = DjiAndroidBridgeSource(
        fps=10.0,
        queue_capacity=16,
        decoder_log_level="error",
    )

    with source, _client(source) as client:
        response = _post_stream(
            client,
            payload=h265,
            codec="HEVC",
            content_type="video/hevc",
            source_id="android-bridge-h265",
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["codec"] == "H265"
        assert body["sourceType"] == "DJI_LIVE"
        assert body["encodedBytes"] == len(h265)
        assert body["decodedFrames"] >= 1
        assert body["decoderExitCode"] == 0

        packet = source.read()
        assert packet is not None
        assert packet.source_type is VideoSourceType.DJI_LIVE
        assert packet.source_id == "android-bridge-h265"
        assert packet.image.shape[:2] == (64, 96)


def test_decoder_failure_releases_stream_for_reconnect() -> None:
    valid_h264 = _encoded_fixture("H264")
    source = DjiAndroidBridgeSource(
        fps=10.0,
        queue_capacity=16,
        decoder_log_level="error",
    )

    with source, _client(source) as client:
        failed = _post_stream(
            client,
            payload=(b"not-an-h264-annex-b-stream" * 128),
            codec="H264",
            content_type="video/h264",
            source_id="android-bridge-invalid",
        )
        assert failed.status_code == 422, failed.text

        after_failure = client.get(
            "/api/ingest/dji/status",
            headers={DJI_BRIDGE_KEY_HEADER: DJI_BRIDGE_KEY},
        )
        assert after_failure.status_code == 200
        failure_status = after_failure.json()
        assert failure_status["activeStream"] is False
        assert failure_status["connections"] == 1
        assert failure_status["decoderFailures"] >= 1

        recovered = _post_stream(
            client,
            payload=valid_h264,
            codec="H264",
            content_type="video/h264",
            source_id="android-bridge-reconnected",
        )
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["decodedFrames"] >= 1

        after_reconnect = client.get(
            "/api/ingest/dji/status",
            headers={DJI_BRIDGE_KEY_HEADER: DJI_BRIDGE_KEY},
        )
        assert after_reconnect.status_code == 200
        reconnect_status = after_reconnect.json()
        assert reconnect_status["activeStream"] is False
        assert reconnect_status["connections"] == 2


def test_decoded_frame_backpressure_keeps_latest_complete_frame() -> None:
    h264 = _encoded_fixture(
        "H264",
        frame_count=24,
        fps=24,
    )
    source = DjiAndroidBridgeSource(
        fps=24.0,
        queue_capacity=1,
        decoder_log_level="error",
    )

    with source, _client(source) as client:
        response = _post_stream(
            client,
            payload=h264,
            codec="H264",
            content_type="video/h264",
            source_id="android-bridge-backpressure",
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["decodedFrames"] >= 2

        status_response = client.get(
            "/api/ingest/dji/status",
            headers={DJI_BRIDGE_KEY_HEADER: DJI_BRIDGE_KEY},
        )
        assert status_response.status_code == 200
        status = status_response.json()

        assert status["queueCapacity"] == 1
        assert status["queueDepth"] == 1
        assert status["acceptedFrames"] == body["decodedFrames"]
        assert status["droppedFrames"] >= 1
        assert status["dropRatePct"] > 0.0

        packet = source.read()
        assert packet is not None
        assert packet.source_type is VideoSourceType.DJI_LIVE
        assert packet.source_id == "android-bridge-backpressure"
