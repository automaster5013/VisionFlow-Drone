from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray


class VideoSourceType(StrEnum):
    SMARTPHONE_LIVE = "SMARTPHONE_LIVE"
    DUMMY_VIDEO = "DUMMY_VIDEO"
    DJI_LIVE = "DJI_LIVE"


class SmartphoneInputMode(StrEnum):
    STREAM_URL = "STREAM_URL"
    BROWSER_UPLOAD = "BROWSER_UPLOAD"


@dataclass(frozen=True, slots=True)
class FramePacket:
    source_id: str
    session_id: str
    source_type: VideoSourceType
    drone_id: int
    frame_index: int
    captured_at: datetime
    image: NDArray[np.uint8]


@dataclass(frozen=True, slots=True)
class Detection:
    class_id: int
    class_name: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass(frozen=True, slots=True)
class InferencePacket:
    frame: FramePacket
    detections: tuple[Detection, ...]
    inference_ms: float
    annotated_image: NDArray[np.uint8]

    def to_event_payload(self) -> dict[str, object]:
        return {
            "sourceId": self.frame.source_id,
            "sessionId": self.frame.session_id,
            "sourceType": self.frame.source_type.value,
            "droneId": self.frame.drone_id,
            "frameIndex": self.frame.frame_index,
            "capturedAt": self.frame.captured_at.isoformat(),
            "inferenceMs": round(self.inference_ms, 2),
            "detectionCount": len(self.detections),
            "detections": [
                {
                    "classId": detection.class_id,
                    "className": detection.class_name,
                    "confidence": round(detection.confidence, 6),
                    "x1": round(detection.x1, 2),
                    "y1": round(detection.y1, 2),
                    "x2": round(detection.x2, 2),
                    "y2": round(detection.y2, 2),
                }
                for detection in self.detections
            ],
        }
