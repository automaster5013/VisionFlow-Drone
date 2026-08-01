from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np

from app.domain import (
    Detection,
    FramePacket,
    InferencePacket,
    VideoSourceType,
)
from app.pipeline import InferencePipeline


image = np.zeros((64, 64, 3), dtype=np.uint8)

pipeline = InferencePipeline(
    source=None,
    detector=None,
    save_annotated_video=False,
    output_video_path=Path("/tmp/gate-test.mp4"),
    show_preview=False,
    max_frames=0,
    reporter=None,
    frame_hub=None,
    snapshot_enabled=False,
    snapshot_jpeg_quality=85,
    event_min_consecutive_frames=5,
    event_cooldown_seconds=10.0,
    performance_monitor=None,
)


def packet(
    frame_index: int,
    class_id: int,
    class_name: str,
) -> InferencePacket:
    frame = FramePacket(
        source_id="gate-test-source",
        session_id="gate-test-session",
        source_type=VideoSourceType.DUMMY_VIDEO,
        drone_id=1,
        frame_index=frame_index,
        captured_at=datetime.now(timezone.utc),
        image=image,
    )
    detection = Detection(
        class_id=class_id,
        class_name=class_name,
        confidence=0.9,
        x1=10.0,
        y1=10.0,
        x2=30.0,
        y2=30.0,
    )
    return InferencePacket(
        frame=frame,
        detections=(detection,),
        inference_ms=10.0,
        annotated_image=image,
    )


reported: list[int] = []

# _should_report_event uses time.monotonic(), not captured_at. Simulate a
# deterministic 0.5-second interval for the 25 calls so frame 25 is exactly
# 10 seconds after the first report at frame 5.
monotonic_values = [index * 0.5 for index in range(25)]
with patch("app.pipeline.time.monotonic", side_effect=monotonic_values):
    for index in range(1, 21):
        if pipeline._should_report_event(
            packet(index, 0, "Hardhat")
        ):
            reported.append(index)

    for index in range(21, 26):
        if pipeline._should_report_event(
            packet(index, 1, "NO-Hardhat")
        ):
            reported.append(index)

print("reported_frames=", reported)
assert reported == [5, 25], reported
print("EVENT_GATE_TEST=PASS")
