from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import numpy as np

from app.domain import FramePacket, VideoSourceType
from app.inference.phase3_frame import Phase3FrameAnalyzer


class _FakeModel:
    def __init__(self, *, track_results=None, predict_results=None) -> None:
        self.track_results = track_results or []
        self.predict_results = predict_results or []
        self.track_calls = []
        self.predict_calls = []

    def track(self, **kwargs):
        self.track_calls.append(kwargs)
        return self.track_results

    def predict(self, **kwargs):
        self.predict_calls.append(kwargs)
        return self.predict_results


class _PoseRuntime:
    sample_stride_frames = 3
    pose_stride_frames = 6
    pose_enabled = True

    def __init__(self) -> None:
        self.ppe_calls = []

    def should_sample_pose(self, source_frame_index: int) -> bool:
        return source_frame_index % self.pose_stride_frames == 0

    def process_sample(self, **kwargs):
        self.ppe_calls.append(kwargs)
        return SimpleNamespace(marker="ppe")


class _NoPoseRuntime:
    sample_stride_frames = 3
    pose_enabled = False

    def __init__(self) -> None:
        self.ppe_calls = []

    def should_sample_pose(self, source_frame_index: int) -> bool:
        return False

    def process_sample(self, **kwargs):
        self.ppe_calls.append(kwargs)
        return SimpleNamespace(marker="ppe")


def _frame(frame_index: int) -> FramePacket:
    return FramePacket(
        source_id="camera-empty",
        session_id="session-empty",
        source_type=VideoSourceType.DUMMY_VIDEO,
        drone_id=1,
        frame_index=frame_index,
        captured_at=datetime(2026, 8, 16, tzinfo=UTC),
        image=np.zeros((240, 320, 3), dtype=np.uint8),
    )


def _analyzer(runtime):
    track_model = _FakeModel(track_results=[])
    ppe_model = _FakeModel()
    pose_model = _FakeModel()
    models = (
        iter([track_model, ppe_model, pose_model])
        if runtime.pose_enabled
        else iter([track_model, ppe_model])
    )

    analyzer = Phase3FrameAnalyzer(
        runtime=runtime,
        source_fps=30.0,
        track_model_path="track.pt",
        ppe_model_path="ppe.pt",
        pose_model_path="pose.pt" if runtime.pose_enabled else None,
        confidence=0.35,
        iou=0.70,
        image_size=640,
        device="0",
        model_factory=lambda path: next(models),
    )
    return analyzer, track_model, ppe_model, pose_model


def test_empty_track_result_advances_ppe_and_pose_sample_clocks() -> None:
    runtime = _PoseRuntime()
    analyzer, track_model, ppe_model, pose_model = _analyzer(runtime)

    analysis = analyzer.analyze(_frame(0))

    assert len(track_model.track_calls) == 1
    assert analysis.inference.detections == ()
    assert np.array_equal(
        analysis.inference.annotated_image,
        _frame(0).image,
    )
    assert analysis.tracked_person_count == 0

    assert analysis.ppe_sampled is True
    assert analysis.ppe is not None
    assert len(runtime.ppe_calls) == 1
    assert runtime.ppe_calls[0]["tracks"] == ()
    assert runtime.ppe_calls[0]["detections"] == ()
    assert ppe_model.predict_calls == []

    assert analysis.pose_sampled is True
    assert analysis.pose is not None
    assert analysis.pose.observations == ()
    assert pose_model.predict_calls == []


def test_empty_track_result_between_sample_frames_skips_both_tasks() -> None:
    runtime = _PoseRuntime()
    analyzer, _, ppe_model, pose_model = _analyzer(runtime)

    analysis = analyzer.analyze(_frame(1))

    assert analysis.ppe_sampled is False
    assert analysis.ppe is None
    assert runtime.ppe_calls == []
    assert ppe_model.predict_calls == []

    assert analysis.pose_sampled is False
    assert analysis.pose is None
    assert pose_model.predict_calls == []


def test_empty_track_result_preserves_pose_disabled_behavior() -> None:
    runtime = _NoPoseRuntime()
    analyzer, _, ppe_model, pose_model = _analyzer(runtime)

    analysis = analyzer.analyze(_frame(0))

    assert analysis.ppe_sampled is True
    assert len(runtime.ppe_calls) == 1
    assert runtime.ppe_calls[0]["tracks"] == ()
    assert runtime.ppe_calls[0]["detections"] == ()
    assert ppe_model.predict_calls == []

    assert analysis.pose_sampled is False
    assert analysis.pose is None
    assert pose_model.predict_calls == []
