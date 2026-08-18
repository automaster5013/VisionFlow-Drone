from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path

from app.config import Settings
from app.domain import FramePacket, VideoSourceType
from app.sources.base import VideoSource
from app.sources.dummy_video import DummyVideoSource


class DjiInputMode(StrEnum):
    REPLAY_FILE = "REPLAY_FILE"
    ANDROID_BRIDGE = "ANDROID_BRIDGE"


class DjiReplaySource(DummyVideoSource):
    """Replay a recorded video while preserving DJI_LIVE source semantics."""

    def read(self) -> FramePacket | None:
        packet = super().read()
        if packet is None:
            return None

        return FramePacket(
            source_id=packet.source_id,
            session_id=packet.session_id,
            source_type=VideoSourceType.DJI_LIVE,
            drone_id=packet.drone_id,
            frame_index=packet.frame_index,
            captured_at=packet.captured_at,
            image=packet.image,
        )


def create_dji_live_source(settings: Settings) -> VideoSource:
    mode = _read_mode()

    if mode is DjiInputMode.REPLAY_FILE:
        path = Path(
            os.getenv(
                "AI_DJI_REPLAY_VIDEO_PATH",
                str(settings.dummy_video_path),
            )
        )
        return DjiReplaySource(
            path=path,
            source_id=settings.source_id,
            session_id=settings.session_id,
            drone_id=settings.drone_id,
            loop=_read_bool(
                "AI_DJI_REPLAY_LOOP",
                settings.loop_video,
            ),
            realtime=_read_bool(
                "AI_DJI_REPLAY_REALTIME",
                settings.realtime_playback,
            ),
        )

    if mode is DjiInputMode.ANDROID_BRIDGE:
        raise NotImplementedError(
            "DJI_LIVE ANDROID_BRIDGE 입력은 실제 MSDK encoded stream "
            "Adapter 단계에서 연결합니다."
        )

    raise AssertionError(f"Unhandled DJI input mode: {mode}")


def _read_mode() -> DjiInputMode:
    raw = os.getenv(
        "AI_DJI_INPUT_MODE",
        DjiInputMode.REPLAY_FILE.value,
    ).strip()
    try:
        return DjiInputMode(raw)
    except ValueError as error:
        supported = ", ".join(mode.value for mode in DjiInputMode)
        raise ValueError(
            f"AI_DJI_INPUT_MODE={raw!r} is invalid; "
            f"supported values: {supported}"
        ) from error


def _read_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
