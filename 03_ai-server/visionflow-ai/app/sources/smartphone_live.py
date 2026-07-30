from __future__ import annotations

import time
from datetime import UTC, datetime

import cv2
import numpy as np
from numpy.typing import NDArray

from app.domain import FramePacket, VideoSourceType
from app.sources.base import VideoSource


class SmartphoneLiveSource(VideoSource):
    def __init__(
        self,
        *,
        stream_url: str,
        source_id: str,
        session_id: str,
        drone_id: int,
        reconnect: bool,
        reconnect_delay_seconds: float,
        max_reconnect_attempts: int,
        open_timeout_ms: int,
        read_timeout_ms: int,
    ) -> None:
        self._stream_url = stream_url
        self._source_id = source_id
        self._session_id = session_id
        self._drone_id = drone_id
        self._reconnect = reconnect
        self._reconnect_delay_seconds = reconnect_delay_seconds
        self._max_reconnect_attempts = max_reconnect_attempts
        self._open_timeout_ms = open_timeout_ms
        self._read_timeout_ms = read_timeout_ms
        self._capture: cv2.VideoCapture | None = None
        self._fps = 30.0
        self._frame_index = 0

    @property
    def fps(self) -> float:
        return self._fps

    def open(self) -> None:
        if self._capture is not None:
            return

        self._frame_index = 0

        if self._connect():
            return

        if self._reconnect and self._reconnect_until_open():
            return

        raise RuntimeError(
            "스마트폰 영상 스트림을 열 수 없습니다. "
            "휴대폰과 PC의 네트워크 및 스트림 주소를 확인하세요."
        )

    def read(self) -> FramePacket | None:
        if self._capture is None:
            raise RuntimeError("스마트폰 영상 소스가 열리지 않았습니다.")

        frame = self._read_frame()

        if frame is None and self._reconnect:
            frame = self._reconnect_and_read()

        if frame is None:
            return None

        packet = FramePacket(
            source_id=self._source_id,
            session_id=self._session_id,
            source_type=VideoSourceType.SMARTPHONE_LIVE,
            drone_id=self._drone_id,
            frame_index=self._frame_index,
            captured_at=datetime.now(UTC),
            image=frame,
        )
        self._frame_index += 1
        return packet

    def close(self) -> None:
        self._release_capture()

    def _connect(self) -> bool:
        self._release_capture()

        parameters = [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
            self._open_timeout_ms,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC,
            self._read_timeout_ms,
        ]

        capture = cv2.VideoCapture(
            self._stream_url,
            cv2.CAP_FFMPEG,
            parameters,
        )

        is_network_stream = self._stream_url.lower().startswith(
            ("http://", "https://", "rtsp://", "rtsps://")
        )

        if not capture.isOpened() and not is_network_stream:
            capture.release()
            capture = cv2.VideoCapture(self._stream_url)

        if not capture.isOpened():
            capture.release()
            return False

        detected_fps = float(capture.get(cv2.CAP_PROP_FPS))
        self._fps = detected_fps if detected_fps > 0 else 30.0
        self._capture = capture
        return True

    def _read_frame(self) -> NDArray[np.uint8] | None:
        if self._capture is None:
            return None

        success, frame = self._capture.read()

        if not success or frame is None:
            return None

        return frame

    def _reconnect_until_open(self) -> bool:
        attempt = 0

        while self._can_retry(attempt):
            attempt += 1
            self._wait_before_retry(attempt)

            if self._connect():
                print(
                    f"스마트폰 영상 스트림 연결 성공: 재시도 {attempt}회",
                    flush=True,
                )
                return True

        return False

    def _reconnect_and_read(self) -> NDArray[np.uint8] | None:
        self._release_capture()
        attempt = 0

        while self._can_retry(attempt):
            attempt += 1
            self._wait_before_retry(attempt)

            if not self._connect():
                continue

            frame = self._read_frame()

            if frame is not None:
                print(
                    f"스마트폰 영상 스트림 재연결 성공: 재시도 {attempt}회",
                    flush=True,
                )
                return frame

            self._release_capture()

        print(
            "스마트폰 영상 스트림 재연결에 실패해 입력을 종료합니다.",
            flush=True,
        )
        return None

    def _can_retry(self, completed_attempts: int) -> bool:
        return (
            self._max_reconnect_attempts == 0 or completed_attempts < self._max_reconnect_attempts
        )

    def _wait_before_retry(self, attempt: int) -> None:
        print(
            f"스마트폰 영상 스트림 연결 재시도: {attempt}회",
            flush=True,
        )

        if self._reconnect_delay_seconds > 0:
            time.sleep(self._reconnect_delay_seconds)

    def _release_capture(self) -> None:
        if self._capture is not None:
            self._capture.release()

        self._capture = None
