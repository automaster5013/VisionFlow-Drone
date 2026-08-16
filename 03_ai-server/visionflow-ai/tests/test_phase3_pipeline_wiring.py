from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from app.domain import (
    Detection,
    FramePacket,
    InferencePacket,
    VideoSourceType,
)
from app.pipeline import InferencePipeline


def _frame() -> FramePacket:
    return FramePacket(
        source_id="camera-1",
        session_id="session-1",
        source_type=VideoSourceType.DUMMY_VIDEO,
        drone_id=1,
        frame_index=0,
        captured_at=datetime(2026, 8, 15, tzinfo=UTC),
        image=np.zeros((8, 12, 3), dtype=np.uint8),
    )


def _inference(frame: FramePacket, *, class_name: str) -> InferencePacket:
    return InferencePacket(
        frame=frame,
        detections=(
            Detection(
                class_id=0,
                class_name=class_name,
                confidence=0.95,
                x1=1.0,
                y1=1.0,
                x2=6.0,
                y2=7.0,
            ),
        ),
        inference_ms=4.2,
        annotated_image=np.full(
            frame.image.shape,
            7,
            dtype=np.uint8,
        ),
    )


class _FakeSource:
    fps = 30.0

    def __init__(self, frame: FramePacket) -> None:
        self._frame = frame
        self._reads = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        self._reads += 1
        return self._frame if self._reads == 1 else None


class _FakeDetector:
    def __init__(self, inference: InferencePacket) -> None:
        self._inference = inference
        self.calls = []

    def infer(self, frame: FramePacket) -> InferencePacket:
        self.calls.append(frame)
        return self._inference


class _FakeAnalyzer:
    def __init__(self, inference: InferencePacket) -> None:
        self._inference = inference
        self.calls = []

    def analyze(self, frame: FramePacket):
        self.calls.append(frame)
        return SimpleNamespace(inference=self._inference)


class _FakeMonitor:
    def __init__(self) -> None:
        self.events = []

    def start(self) -> None:
        self.events.append("start")

    def record(self, inference: InferencePacket) -> None:
        self.events.append(("record", inference))

    def stop(self) -> None:
        self.events.append("stop")


class _FakeReporter:
    def __init__(self) -> None:
        self.started = False
        self.closed = False
        self.submissions = []

    def start(self) -> None:
        self.started = True

    def submit(self, payload, snapshot_jpeg=None) -> None:
        self.submissions.append((payload, snapshot_jpeg))

    def close(self) -> None:
        self.closed = True


class _FakeHub:
    def __init__(self) -> None:
        self.published = []

    def publish(self, inference: InferencePacket) -> None:
        self.published.append(inference)


def _pipeline(
    *,
    frame: FramePacket,
    detector,
    phase3_analyzer=None,
    reporter=None,
    frame_hub=None,
    performance_monitor=None,
) -> InferencePipeline:
    return InferencePipeline(
        source=_FakeSource(frame),
        detector=detector,
        phase3_analyzer=phase3_analyzer,
        save_annotated_video=False,
        output_video_path=Path("unused.mp4"),
        show_preview=False,
        max_frames=1,
        reporter=reporter,
        frame_hub=frame_hub,
        snapshot_enabled=False,
        snapshot_jpeg_quality=85,
        event_min_consecutive_frames=1,
        event_cooldown_seconds=0.0,
        performance_monitor=performance_monitor,
    )


def test_phase3_analyzer_replaces_legacy_detector_inference() -> None:
    frame = _frame()
    legacy = _inference(frame, class_name="legacy")
    phase3 = _inference(frame, class_name="person")
    detector = _FakeDetector(legacy)
    analyzer = _FakeAnalyzer(phase3)

    pipeline = _pipeline(
        frame=frame,
        detector=detector,
        phase3_analyzer=analyzer,
    )
    pipeline.run()

    assert analyzer.calls == [frame]
    assert detector.calls == []


def test_without_phase3_analyzer_legacy_detector_is_unchanged() -> None:
    frame = _frame()
    legacy = _inference(frame, class_name="legacy")
    detector = _FakeDetector(legacy)

    pipeline = _pipeline(
        frame=frame,
        detector=detector,
        phase3_analyzer=None,
    )
    pipeline.run()

    assert detector.calls == [frame]


def test_phase3_inference_reuses_existing_downstream_pipeline() -> None:
    frame = _frame()
    phase3 = _inference(frame, class_name="person")
    detector = _FakeDetector(_inference(frame, class_name="legacy"))
    analyzer = _FakeAnalyzer(phase3)
    monitor = _FakeMonitor()
    reporter = _FakeReporter()
    hub = _FakeHub()

    pipeline = _pipeline(
        frame=frame,
        detector=detector,
        phase3_analyzer=analyzer,
        reporter=reporter,
        frame_hub=hub,
        performance_monitor=monitor,
    )
    pipeline.run()

    assert monitor.events[0] == "start"
    assert monitor.events[1] == ("record", phase3)
    assert monitor.events[2] == "stop"

    assert hub.published == [phase3]

    assert reporter.started is True
    assert reporter.closed is True
    assert len(reporter.submissions) == 1
    payload, snapshot = reporter.submissions[0]
    assert payload["detectionCount"] == 1
    assert payload["detections"][0]["className"] == "person"
    assert snapshot is None
