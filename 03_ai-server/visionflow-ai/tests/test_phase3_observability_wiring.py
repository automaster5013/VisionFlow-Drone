from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np

import app.main as app_main
from app.domain import (
    FramePacket,
    InferencePacket,
    VideoSourceType,
)
from app.pipeline import InferencePipeline


class _FakeSource:
    fps = 30.0


class _FakeObserver:
    def __init__(self, events=None) -> None:
        self.events = events if events is not None else []
        self.analysis = []
        self.depth_results = []

    def record_analysis(self, analysis) -> None:
        self.analysis.append(analysis)

    def on_depth_result(self, result) -> None:
        self.depth_results.append(result)

    def emit_summary(self):
        self.events.append("observer.summary")


class _FakeRuntime:
    def __init__(self, events) -> None:
        self.events = events

    def start(self) -> None:
        self.events.append("phase3.start")

    def close(self) -> None:
        self.events.append("phase3.close")


class _FakePipelineRunner:
    def __init__(self, events) -> None:
        self.events = events

    def run(self) -> None:
        self.events.append("pipeline.run")


class _FakeAnalyzer:
    def __init__(self, analysis) -> None:
        self.analysis = analysis

    def analyze(self, frame):
        return self.analysis


class _FakeDetector:
    def infer(self, frame):
        raise AssertionError("legacy detector must not run")


class _OneFrameSource:
    fps = 30.0

    def __init__(self, frame) -> None:
        self.frame = frame
        self.reads = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        self.reads += 1
        return self.frame if self.reads == 1 else None


def _inference() -> InferencePacket:
    frame = FramePacket(
        source_id="camera-1",
        session_id="session-1",
        source_type=VideoSourceType.DUMMY_VIDEO,
        drone_id=1,
        frame_index=0,
        captured_at=__import__("datetime").datetime.now(
            __import__("datetime").UTC
        ),
        image=np.zeros((8, 12, 3), dtype=np.uint8),
    )
    return InferencePacket(
        frame=frame,
        detections=(),
        inference_ms=1.0,
        annotated_image=frame.image.copy(),
    )


def test_optional_observer_exists_only_when_phase3_enabled() -> None:
    enabled = app_main.create_optional_phase3_observer(
        SimpleNamespace(phase3_enabled=True)
    )
    disabled = app_main.create_optional_phase3_observer(
        SimpleNamespace(phase3_enabled=False)
    )

    assert enabled is not None
    assert disabled is None


def test_runtime_factory_receives_depth_callback_when_observer_exists(
    monkeypatch,
) -> None:
    captured = {}

    def fake_create_phase3_runtime(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(
        app_main,
        "create_phase3_runtime",
        fake_create_phase3_runtime,
    )

    observer = _FakeObserver()
    settings = SimpleNamespace(phase3_enabled=True)

    app_main.create_optional_phase3_runtime(
        settings=settings,
        source=_FakeSource(),
        phase3_observer=observer,
    )

    assert captured["settings"] is settings
    assert captured["source_fps"] == 30.0
    assert captured["on_depth_result"] == observer.on_depth_result


def test_summary_is_emitted_after_depth_runtime_closes() -> None:
    events = []
    observer = _FakeObserver(events)

    app_main.run_pipeline_with_optional_phase3(
        pipeline=_FakePipelineRunner(events),
        stream_server=None,
        phase3_runtime=_FakeRuntime(events),
        phase3_observer=observer,
    )

    assert events == [
        "phase3.start",
        "pipeline.run",
        "phase3.close",
        "observer.summary",
    ]


def test_pipeline_records_phase3_analysis_before_downstream_use() -> None:
    inference = _inference()
    analysis = SimpleNamespace(
        inference=inference,
        ppe=None,
        ppe_sampled=False,
    )
    observer = _FakeObserver()

    pipeline = InferencePipeline(
        source=_OneFrameSource(inference.frame),
        detector=_FakeDetector(),
        phase3_analyzer=_FakeAnalyzer(analysis),
        phase3_observer=observer,
        save_annotated_video=False,
        output_video_path=Path("unused.mp4"),
        show_preview=False,
        max_frames=1,
        reporter=None,
        frame_hub=None,
        snapshot_enabled=False,
        snapshot_jpeg_quality=85,
        event_min_consecutive_frames=1,
        event_cooldown_seconds=0.0,
        performance_monitor=None,
    )

    pipeline.run()

    assert observer.analysis == [analysis]
