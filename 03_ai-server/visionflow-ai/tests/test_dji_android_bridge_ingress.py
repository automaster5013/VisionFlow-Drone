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


def _require_ffmpeg() -> str:
    executable = shutil.which("ffmpeg")
    if executable is not None:
        return executable

    if os.getenv("VISIONFLOW_REQUIRE_FFMPEG_TEST") == "1":
        pytest.fail("FFmpeg is required by the DJI Android Bridge gate.")

    pytest.skip("FFmpeg is not installed in this legacy AI test image.")


def _build_h264_fixture() -> bytes:
    executable = _require_ffmpeg()
    frames: list[np.ndarray] = []

    for index in range(6):
        frame = np.zeros((48, 64, 3), dtype=np.uint8)
        frame[:, :, index % 3] = 80 + (index * 20)
        frames.append(frame)

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
            "64x48",
            "-r",
            "10",
            "-i",
            "pipe:0",
            "-frames:v",
            str(len(frames)),
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-tune",
            "zerolatency",
            "-pix_fmt",
            "yuv420p",
            "-f",
            "h264",
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


def _source() -> DjiAndroidBridgeSource:
    return DjiAndroidBridgeSource(
        fps=10.0,
        queue_capacity=8,
        decoder_log_level="error",
    )


def test_android_bridge_normalizes_h265_aliases() -> None:
    assert DjiAndroidBridgeSource.normalize_codec("h265") == "H265"
    assert DjiAndroidBridgeSource.normalize_codec("hevc") == "H265"


def test_android_bridge_rejects_wrong_stream_content_type() -> None:
    source = DjiAndroidBridgeSource(
        fps=10.0,
        queue_capacity=3,
        ffmpeg_executable=(
            "visionflow-ffmpeg-not-required-for-this-test"
        ),
    )
    app = create_stream_app(
        AnnotatedFrameHub(jpeg_quality=80),
        allowed_origins=("http://localhost:3000",),
        ingest_source=source,
        internal_security_enabled=False,
    )

    with source, TestClient(app) as client:
        response = client.post(
            "/api/ingest/dji/stream",
            params={
                "droneId": 1,
                "sourceId": "android-bridge-test",
                "sessionId": "session-test",
                "codec": "H264",
            },
            headers={"Content-Type": "image/jpeg"},
            content=b"not-used",
        )

    assert response.status_code == 415


def test_android_bridge_h264_http_ingress_emits_dji_live_packet() -> None:
    h264 = _build_h264_fixture()
    source = _source()
    app = create_stream_app(
        AnnotatedFrameHub(jpeg_quality=80),
        allowed_origins=("http://localhost:3000",),
        ingest_source=source,
        internal_security_enabled=False,
    )

    with source, TestClient(app) as client:
        before = client.get("/api/ingest/status")
        assert before.status_code == 200
        assert before.json()["inputMode"] == "ANDROID_BRIDGE"

        response = client.post(
            "/api/ingest/dji/stream",
            params={
                "droneId": 1,
                "sourceId": "android-bridge-test",
                "sessionId": "session-test",
                "codec": "H264",
            },
            headers={"Content-Type": "video/h264"},
            content=h264,
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["sourceType"] == "DJI_LIVE"
        assert body["codec"] == "H264"
        assert body["encodedBytes"] == len(h264)
        assert body["decodedFrames"] >= 1
        assert body["decoderExitCode"] == 0

        packet = source.read()
        assert packet is not None
        assert packet.source_type is VideoSourceType.DJI_LIVE
        assert packet.source_id == "android-bridge-test"
        assert packet.session_id == "session-test"
        assert packet.drone_id == 1
        assert packet.image.shape[:2] == (48, 64)

        status = client.get("/api/ingest/dji/status")
        assert status.status_code == 200
        assert status.json()["decodedFrames"] >= 1
        assert status.json()["activeStream"] is False
