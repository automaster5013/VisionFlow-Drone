from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

import cv2

from app.domain import FramePacket, VideoSourceType
from app.sources.base import VideoSource


class DummyVideoSource(VideoSource):
    def __init__(
        self,
        *,
        path: Path,
        source_id: str,
        session_id: str,
        drone_id: int,
        loop: bool,
        realtime: bool,
    ) -> None:
        self._path = path
        self._source_id = source_id
        self._session_id = session_id
        self._drone_id = drone_id
        self._loop = loop
        self._realtime = realtime
        self._capture: cv2.VideoCapture | None = None
        self._fps = 30.0
        self._frame_index = 0
        self._next_frame_at: float | None = None

    @property
    def fps(self) -> float:
        return self._fps

    def open(self) -> None:
        if self._capture is not None:
            return

        capture = cv2.VideoCapture(str(self._path))

        if not capture.isOpened():
            capture.release()
            raise RuntimeError(f"더미 영상을 열 수 없습니다: {self._path}")

        detected_fps = float(capture.get(cv2.CAP_PROP_FPS))
        self._fps = detected_fps if detected_fps > 0 else 30.0
        self._capture = capture
        self._frame_index = 0
        self._next_frame_at = None

    def read(self) -> FramePacket | None:
        if self._capture is None:
            raise RuntimeError("영상 소스가 열리지 않았습니다.")

        success, frame = self._capture.read()

        if not success and self._loop:
            self._capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            success, frame = self._capture.read()

        if not success or frame is None:
            return None

        self._pace_frame()

        packet = FramePacket(
            source_id=self._source_id,
            session_id=self._session_id,
            source_type=VideoSourceType.DUMMY_VIDEO,
            drone_id=self._drone_id,
            frame_index=self._frame_index,
            captured_at=datetime.now(UTC),
            image=frame,
        )
        self._frame_index += 1
        return packet

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()

        self._capture = None
        self._next_frame_at = None

    def _pace_frame(self) -> None:
        if not self._realtime:
            return

        frame_interval = 1.0 / max(self._fps, 1.0)
        now = time.perf_counter()

        if self._next_frame_at is None:
            self._next_frame_at = now

        if now < self._next_frame_at:
            time.sleep(self._next_frame_at - now)

        self._next_frame_at = max(
            self._next_frame_at + frame_interval,
            time.perf_counter(),
        )
