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

AI_INTERNAL_KEY_HEADER = "X-VisionFlow-AI-Key"
DJI_BRIDGE_KEY_HEADER = "X-VisionFlow-DJI-Key"
AI_INTERNAL_KEY = "ai-internal-test-key-0123456789abcdef"
DJI_BRIDGE_KEY = "dji-bridge-test-key-0123456789abcdef"


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
        capture_output=True,
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


def test_android_bridge_decoder_caps_input_frame_pixels() -> None:
    source = DjiAndroidBridgeSource(
        fps=10.0,
        queue_capacity=3,
    )

    command = source._decoder_command(
        executable="ffmpeg",
        codec="H264",
    )

    max_pixels_index = command.index("-max_pixels")
    input_index = command.index("-i")
    assert command[max_pixels_index + 1] == "16777216"
    assert max_pixels_index < input_index


def test_android_bridge_requires_distinct_dedicated_key() -> None:
    source = DjiAndroidBridgeSource(
        fps=10.0,
        queue_capacity=3,
        ffmpeg_executable=(
            "visionflow-ffmpeg-not-required-for-this-test"
        ),
    )

    with pytest.raises(ValueError, match="VISIONFLOW_DJI_BRIDGE_KEY"):
        create_stream_app(
            AnnotatedFrameHub(jpeg_quality=80),
            allowed_origins=("http://localhost:3000",),
            ingest_source=source,
            internal_security_enabled=False,
        )

    with pytest.raises(ValueError, match="서로 달라야"):
        create_stream_app(
            AnnotatedFrameHub(jpeg_quality=80),
            allowed_origins=("http://localhost:3000",),
            ingest_source=source,
            internal_api_key=DJI_BRIDGE_KEY,
            dji_bridge_api_key=DJI_BRIDGE_KEY,
        )


def test_android_bridge_key_cannot_access_general_ai_endpoints() -> None:
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
        internal_security_enabled=True,
        internal_api_key=AI_INTERNAL_KEY,
        dji_bridge_api_key=DJI_BRIDGE_KEY,
    )

    with source, TestClient(app) as client:
        missing = client.get("/api/ingest/dji/status")
        ai_key_only = client.get(
            "/api/ingest/dji/status",
            headers={AI_INTERNAL_KEY_HEADER: AI_INTERNAL_KEY},
        )
        dji_status = client.get(
            "/api/ingest/dji/status",
            headers={DJI_BRIDGE_KEY_HEADER: DJI_BRIDGE_KEY},
        )
        dji_to_general = client.get(
            "/api/streams/status",
            headers={DJI_BRIDGE_KEY_HEADER: DJI_BRIDGE_KEY},
        )
        ai_to_general = client.get(
            "/api/streams/status",
            headers={AI_INTERNAL_KEY_HEADER: AI_INTERNAL_KEY},
        )

    assert missing.status_code == 401
    assert ai_key_only.status_code == 401
    assert dji_status.status_code == 200
    assert dji_to_general.status_code == 401
    assert ai_to_general.status_code == 200


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
        dji_bridge_api_key=DJI_BRIDGE_KEY,
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
            headers={
                "Content-Type": "image/jpeg",
                DJI_BRIDGE_KEY_HEADER: DJI_BRIDGE_KEY,
            },
            content=b"not-used",
        )

    assert response.status_code == 415


def _ingress_app(source: DjiAndroidBridgeSource, **limits: object):
    return create_stream_app(
        AnnotatedFrameHub(jpeg_quality=80),
        allowed_origins=("http://localhost:3000",),
        ingest_source=source,
        internal_security_enabled=False,
        dji_bridge_api_key=DJI_BRIDGE_KEY,
        **limits,
    )


def _mock_ingest_source(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[DjiAndroidBridgeSource, list[bytes], list[str], list[str]]:
    source = DjiAndroidBridgeSource(
        fps=10.0,
        queue_capacity=3,
        ffmpeg_executable="visionflow-ffmpeg-not-required-for-this-test",
    )
    submitted: list[bytes] = []
    ended: list[str] = []
    begun: list[str] = []
    monkeypatch.setattr(
        source,
        "begin_stream",
        lambda **_kwargs: begun.append("test-token") or "test-token",
    )
    monkeypatch.setattr(
        source,
        "submit_encoded",
        lambda _token, payload: submitted.append(payload),
    )
    monkeypatch.setattr(
        source,
        "end_stream",
        lambda token: ended.append(token) or {"decodedFrames": 0},
    )
    return source, submitted, ended, begun


def _stream_request(client: TestClient, *, content: object, **kwargs: object):
    headers = {
        "Content-Type": "video/h264",
        DJI_BRIDGE_KEY_HEADER: DJI_BRIDGE_KEY,
        **kwargs.pop("headers", {}),
    }
    return client.post(
        "/api/ingest/dji/stream",
        params={
            "droneId": 1,
            "sourceId": "android-bridge-test",
            "sessionId": "session-test",
            "codec": "H264",
        },
        headers=headers,
        content=content,
        **kwargs,
    )


def test_android_bridge_rejects_declared_stream_over_limit_before_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, submitted, ended, begun = _mock_ingest_source(monkeypatch)
    app = _ingress_app(source, dji_bridge_max_stream_bytes=4)

    with TestClient(app) as client:
        response = _stream_request(
            client,
            content=b"12345",
            headers={
                "Content-Type": "video/h264",
                DJI_BRIDGE_KEY_HEADER: DJI_BRIDGE_KEY,
                "Content-Length": "5",
            },
        )

    assert response.status_code == 413
    assert begun == []
    assert submitted == []
    assert ended == []


def test_android_bridge_caps_stream_without_content_length_and_closes_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, submitted, ended, begun = _mock_ingest_source(monkeypatch)
    app = _ingress_app(source, dji_bridge_max_stream_bytes=5)

    with TestClient(app) as client:
        response = _stream_request(
            client,
            content=iter((b"1234", b"5678")),
        )

    assert response.status_code == 413
    assert begun == ["test-token"]
    assert submitted == []
    assert ended == ["test-token"]


def test_android_bridge_h264_http_ingress_emits_dji_live_packet() -> None:
    h264 = _build_h264_fixture()
    source = _source()
    app = create_stream_app(
        AnnotatedFrameHub(jpeg_quality=80),
        allowed_origins=("http://localhost:3000",),
        ingest_source=source,
        internal_security_enabled=False,
        dji_bridge_api_key=DJI_BRIDGE_KEY,
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
            headers={
                "Content-Type": "video/h264",
                DJI_BRIDGE_KEY_HEADER: DJI_BRIDGE_KEY,
            },
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

        status = client.get(
            "/api/ingest/dji/status",
            headers={DJI_BRIDGE_KEY_HEADER: DJI_BRIDGE_KEY},
        )
        assert status.status_code == 200
        assert status.json()["decodedFrames"] >= 1
        assert status.json()["activeStream"] is False
