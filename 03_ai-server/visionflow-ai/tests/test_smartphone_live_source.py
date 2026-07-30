from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from app.domain import VideoSourceType
from app.sources import SmartphoneLiveSource


def _create_test_video(path: Path) -> None:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        10.0,
        (32, 24),
    )
    assert writer.isOpened()

    writer.write(np.zeros((24, 32, 3), dtype=np.uint8))
    writer.write(np.full((24, 32, 3), 255, dtype=np.uint8))
    writer.release()


def _create_source(stream_url: str, *, reconnect: bool) -> SmartphoneLiveSource:
    return SmartphoneLiveSource(
        stream_url=stream_url,
        source_id="smartphone-camera-001",
        session_id="test-session",
        drone_id=1,
        reconnect=reconnect,
        reconnect_delay_seconds=0,
        max_reconnect_attempts=1,
        open_timeout_ms=1_000,
        read_timeout_ms=1_000,
    )


def test_smartphone_source_creates_common_frame_packet(tmp_path: Path) -> None:
    video_path = tmp_path / "smartphone-stream.avi"
    _create_test_video(video_path)
    source = _create_source(str(video_path), reconnect=False)

    with source:
        packet = source.read()

    assert packet is not None
    assert packet.source_type is VideoSourceType.SMARTPHONE_LIVE
    assert packet.source_id == "smartphone-camera-001"
    assert packet.session_id == "test-session"
    assert packet.frame_index == 0


def test_smartphone_source_reconnects_after_stream_read_failure(
    tmp_path: Path,
) -> None:
    video_path = tmp_path / "reconnect-stream.avi"
    _create_test_video(video_path)
    source = _create_source(str(video_path), reconnect=True)

    with source:
        packets = [source.read() for _ in range(3)]

    assert all(packet is not None for packet in packets)
    assert [packet.frame_index for packet in packets if packet is not None] == [
        0,
        1,
        2,
    ]
