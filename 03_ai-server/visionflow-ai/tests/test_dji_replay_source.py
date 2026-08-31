from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from app.domain import VideoSourceType
from app.sources import DjiReplaySource


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


def test_dji_replay_emits_dji_live_packets(
    tmp_path: Path,
) -> None:
    video_path = tmp_path / "two-frames.avi"
    _create_test_video(video_path)

    source = DjiReplaySource(
        path=video_path,
        source_id="phase3-dji-replay",
        session_id="test-session",
        drone_id=1,
        loop=False,
        realtime=False,
    )

    with source:
        first = source.read()
        second = source.read()
        exhausted = source.read()

    assert first is not None
    assert second is not None
    assert exhausted is None
    assert first.source_type is VideoSourceType.DJI_LIVE
    assert second.source_type is VideoSourceType.DJI_LIVE
    assert first.source_id == "phase3-dji-replay"
    assert first.session_id == "test-session"
    assert first.drone_id == 1
    assert [first.frame_index, second.frame_index] == [0, 1]


def test_dji_replay_preserves_monotonic_index_when_looping(
    tmp_path: Path,
) -> None:
    video_path = tmp_path / "two-frames.avi"
    _create_test_video(video_path)

    source = DjiReplaySource(
        path=video_path,
        source_id="phase3-dji-replay",
        session_id="test-session",
        drone_id=1,
        loop=True,
        realtime=False,
    )

    with source:
        packets = [source.read() for _ in range(5)]

    assert all(packet is not None for packet in packets)
    assert [
        packet.frame_index
        for packet in packets
        if packet is not None
    ] == [0, 1, 2, 3, 4]
    assert all(
        packet.source_type is VideoSourceType.DJI_LIVE
        for packet in packets
        if packet is not None
    )
