from __future__ import annotations

import queue
import threading
import time
from collections import deque
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime

import cv2
import numpy as np
from numpy.typing import NDArray

from app.domain import FramePacket, VideoSourceType
from app.sources.base import VideoSource


_MAX_JPEG_DIMENSION = 8192
_MAX_JPEG_PIXELS = 16_777_216
_JPEG_START_OF_FRAME_MARKERS = {
    0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
    0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
}


def _jpeg_dimensions(payload: bytes) -> tuple[int, int] | None:
    """Read JPEG dimensions from its marker stream without decoding pixels."""
    if len(payload) < 4 or payload[:2] != b"\xff\xd8":
        return None

    offset = 2
    while offset < len(payload):
        if payload[offset] != 0xFF:
            return None
        while offset < len(payload) and payload[offset] == 0xFF:
            offset += 1
        if offset >= len(payload):
            return None

        marker = payload[offset]
        offset += 1
        if marker in (0xD8, 0xD9, 0x01) or 0xD0 <= marker <= 0xD7:
            if marker == 0xD9:
                return None
            continue
        if marker == 0xDA:  # Start of scan before a frame header is invalid here.
            return None
        if offset + 2 > len(payload):
            return None

        segment_length = int.from_bytes(payload[offset : offset + 2], "big")
        if segment_length < 2:
            return None
        segment_end = offset + segment_length
        if segment_end > len(payload):
            return None
        if marker in _JPEG_START_OF_FRAME_MARKERS:
            if segment_length < 8:
                return None
            height = int.from_bytes(payload[offset + 3 : offset + 5], "big")
            width = int.from_bytes(payload[offset + 5 : offset + 7], "big")
            if width <= 0 or height <= 0:
                return None
            return width, height
        offset = segment_end

    return None


@dataclass(frozen=True, slots=True)
class BrowserSubmittedFrame:
    source_id: str
    session_id: str
    drone_id: int
    captured_at: datetime
    image: NDArray[np.uint8]
    source_type: VideoSourceType


class BrowserUploadSource(VideoSource):
    def __init__(self, *, fps: float, queue_capacity: int) -> None:
        self._fps = fps
        self._queue_capacity = queue_capacity
        self._queue: queue.Queue[BrowserSubmittedFrame | None] = queue.Queue(
            maxsize=queue_capacity
        )
        self._input_fps_window_seconds = 5.0
        self._received_samples: deque[float] = deque()
        self._lock = threading.Lock()
        self._opened = False
        self._closed = False
        self._frame_index = 0
        self._accepted_frames = 0
        self._dropped_frames = 0
        self._last_received_at: datetime | None = None

    @property
    def fps(self) -> float:
        return self._fps

    def open(self) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("이미 종료된 브라우저 영상 입력은 다시 열 수 없습니다.")

            self._opened = True

    def submit_jpeg(
        self,
        jpeg: bytes,
        *,
        source_id: str,
        session_id: str,
        drone_id: int,
        captured_at: datetime | None,
        source_type: VideoSourceType = VideoSourceType.SMARTPHONE_LIVE,
    ) -> dict[str, object]:
        if source_type not in (VideoSourceType.SMARTPHONE_LIVE, VideoSourceType.DUMMY_VIDEO):
            raise ValueError("Unsupported browser video source type")
        if not jpeg:
            raise ValueError("JPEG 프레임 본문이 비어 있습니다.")

        dimensions = _jpeg_dimensions(jpeg)
        if dimensions is None:
            raise ValueError("올바른 JPEG 프레임 헤더가 아닙니다.")
        width, height = dimensions
        if (
            width > _MAX_JPEG_DIMENSION
            or height > _MAX_JPEG_DIMENSION
            or width * height > _MAX_JPEG_PIXELS
        ):
            raise ValueError("JPEG 프레임 해상도 제한을 초과했습니다.")

        encoded = np.frombuffer(jpeg, dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)

        if image is None or image.size == 0:
            raise ValueError("올바른 JPEG 영상 프레임이 아닙니다.")

        if captured_at is None:
            normalized_captured_at = datetime.now(UTC)
        elif captured_at.tzinfo is None:
            normalized_captured_at = captured_at.replace(tzinfo=UTC)
        else:
            normalized_captured_at = captured_at.astimezone(UTC)

        submitted = BrowserSubmittedFrame(
            source_id=source_id,
            session_id=session_id,
            drone_id=drone_id,
            captured_at=normalized_captured_at,
            image=image,
            source_type=source_type,
        )

        with self._lock:
            if self._closed:
                raise RuntimeError("브라우저 영상 입력이 종료되었습니다.")

            dropped = False

            try:
                self._queue.put_nowait(submitted)
            except queue.Full:
                with suppress(queue.Empty):
                    self._queue.get_nowait()

                self._queue.put_nowait(submitted)
                self._dropped_frames += 1
                dropped = True

            self._accepted_frames += 1
            self._last_received_at = datetime.now(UTC)
            received_monotonic = time.monotonic()
            self._received_samples.append(received_monotonic)
            self._prune_received_samples(received_monotonic)

            return {
                "accepted": True,
                "droppedPreviousFrame": dropped,
                "queueDepth": self._queue.qsize(),
                "acceptedFrames": self._accepted_frames,
                "droppedFrames": self._dropped_frames,
            }

    def read(self) -> FramePacket | None:
        while True:
            with self._lock:
                if self._closed:
                    return None

            try:
                submitted = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if submitted is None:
                return None

            packet = FramePacket(
                source_id=submitted.source_id,
                session_id=submitted.session_id,
                source_type=submitted.source_type,
                drone_id=submitted.drone_id,
                frame_index=self._frame_index,
                captured_at=submitted.captured_at,
                image=submitted.image,
            )
            self._frame_index += 1
            return packet

    def status(self) -> dict[str, object]:
        with self._lock:
            now_monotonic = time.monotonic()
            self._prune_received_samples(now_monotonic)
            input_fps = self._calculate_input_fps()
            drop_rate = (
                self._dropped_frames / self._accepted_frames * 100.0
                if self._accepted_frames > 0
                else 0.0
            )

            return {
                "enabled": True,
                "running": self._opened and not self._closed,
                "queueDepth": self._queue.qsize(),
                "queueCapacity": self._queue_capacity,
                "acceptedFrames": self._accepted_frames,
                "droppedFrames": self._dropped_frames,
                "dropRatePct": round(drop_rate, 2),
                "inputFps": round(input_fps, 2),
                "lastReceivedAt": (
                    self._last_received_at.isoformat()
                    if self._last_received_at is not None
                    else None
                ),
            }

    def _prune_received_samples(self, now_monotonic: float) -> None:
        threshold = now_monotonic - self._input_fps_window_seconds

        while (
            self._received_samples
            and self._received_samples[0] < threshold
        ):
            self._received_samples.popleft()

    def _calculate_input_fps(self) -> float:
        if len(self._received_samples) < 2:
            return 0.0

        elapsed = self._received_samples[-1] - self._received_samples[0]
        return (
            (len(self._received_samples) - 1) / elapsed
            if elapsed > 0
            else 0.0
        )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return

            self._closed = True

            try:
                self._queue.put_nowait(None)
            except queue.Full:
                with suppress(queue.Empty):
                    self._queue.get_nowait()

                self._queue.put_nowait(None)
