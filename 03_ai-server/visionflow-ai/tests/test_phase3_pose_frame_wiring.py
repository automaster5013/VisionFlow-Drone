from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import numpy as np
import pytest

from app.domain import FramePacket, VideoSourceType
from app.inference.phase3_frame import (
    Phase3FrameAnalyzer,
    create_phase3_frame_analyzer,
)


class _Tensor:
    def __init__(self, value) -> None:
        self._value = np.asarray(value)

    def detach(self):
        return self

    def cpu(self):
        return self

    def tolist(self):
        return self._value.tolist()


class _Boxes:
    def __init__(
        self,
        *,
        xyxy,
        conf=None,
        cls=None,
        ids=None,
    ) -> None:
        self.xyxy = _Tensor(xyxy)
        self.conf = None if conf is None else _Tensor(conf)
        self.cls = None if cls is None else _Tensor(cls)
        self.id = None if ids is None else _Tensor(ids)


class _Keypoints:
    def __init__(self, *, xy, conf=None) -> None:
        self.xy = _Tensor(xy)
        self.conf = None if conf is None else _Tensor(conf)


class _TrackResult:
    def __init__(self, *, person: bool = True) -> None:
        if person:
            self.boxes = _Boxes(
                xyxy=[[0, 0, 100, 200]],
                conf=[0.95],
                cls=[0],
                ids=[11],
            )
            self.names = {0: "person"}
        else:
            self.boxes = _Boxes(
                xyxy=[[0, 0, 100, 200]],
                conf=[0.90],
                cls=[2],
                ids=[22],
            )
            self.names = {2: "car"}

    def plot(self):
        return np.zeros((240, 320, 3), dtype=np.uint8)


class _PpeResult:
    def __init__(self) -> None:
        self.boxes = _Boxes(
            xyxy=[[25, 10, 75, 55]],
            conf=[0.90],
            cls=[2],
        )
        self.names = {2: "head"}


class _PoseResult:
    def __init__(self) -> None:
        self.boxes = _Boxes(
            xyxy=[[0, 0, 100, 200]],
        )
        self.keypoints = _Keypoints(
            xy=[[
                [50, 20],
                [45, 25],
                [55, 25],
                [40, 40],
                [60, 40],
            ]],
            conf=[[0.95, 0.90, 0.91, 0.88, 0.89]],
        )


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
    sample_stride_frames = 4
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

    def should_sample_pose(self, source_frame_index: int) -> bool:
        return False

    def process_sample(self, **kwargs):
        return SimpleNamespace(marker="ppe")


def _frame(frame_index: int) -> FramePacket:
    return FramePacket(
        source_id="camera-1",
        session_id="session-1",
        source_type=VideoSourceType.DUMMY_VIDEO,
        drone_id=1,
        frame_index=frame_index,
        captured_at=datetime(2026, 8, 16, tzinfo=UTC),
        image=np.zeros((240, 320, 3), dtype=np.uint8),
    )


def _pose_analyzer(*, person: bool = True):
    runtime = _PoseRuntime()
    track_model = _FakeModel(
        track_results=[_TrackResult(person=person)]
    )
    ppe_model = _FakeModel(
        predict_results=[_PpeResult()]
    )
    pose_model = _FakeModel(
        predict_results=[_PoseResult()]
    )
    models = iter([track_model, ppe_model, pose_model])

    analyzer = Phase3FrameAnalyzer(
        runtime=runtime,
        source_fps=30.0,
        track_model_path="track.pt",
        ppe_model_path="ppe.pt",
        pose_model_path="pose.pt",
        confidence=0.35,
        iou=0.70,
        image_size=640,
        device="0",
        model_factory=lambda path: next(models),
    )
    return analyzer, runtime, track_model, ppe_model, pose_model


def test_pose_runs_on_independent_stride_when_ppe_is_not_sampled() -> None:
    analyzer, runtime, _, ppe_model, pose_model = _pose_analyzer()

    analysis = analyzer.analyze(_frame(6))

    assert analysis.ppe_sampled is False
    assert analysis.ppe is None
    assert runtime.ppe_calls == []
    assert ppe_model.predict_calls == []

    assert analysis.pose_sampled is True
    assert analysis.pose is not None
    assert len(pose_model.predict_calls) == 1
    assert analysis.pose.frame_index == 7
    assert analysis.pose.assigned_count == 1
    assert analysis.pose.observations[0].track_id == 11


def test_pose_is_not_run_between_pose_sample_frames() -> None:
    analyzer, _, _, _, pose_model = _pose_analyzer()

    analysis = analyzer.analyze(_frame(5))

    assert analysis.pose_sampled is False
    assert analysis.pose is None
    assert pose_model.predict_calls == []


def test_pose_predict_uses_phase3_inference_configuration() -> None:
    analyzer, _, _, _, pose_model = _pose_analyzer()

    analyzer.analyze(_frame(6))

    call = pose_model.predict_calls[0]
    assert call["conf"] == pytest.approx(0.35)
    assert call["iou"] == pytest.approx(0.70)
    assert call["imgsz"] == 640
    assert call["device"] == "0"
    assert call["verbose"] is False


def test_pose_sample_without_tracked_person_skips_pose_model() -> None:
    analyzer, _, _, _, pose_model = _pose_analyzer(person=False)

    analysis = analyzer.analyze(_frame(6))

    assert analysis.tracked_person_count == 0
    assert analysis.pose_sampled is True
    assert analysis.pose is not None
    assert analysis.pose.observations == ()
    assert pose_model.predict_calls == []


def test_pose_enabled_requires_pose_model_path() -> None:
    runtime = _PoseRuntime()
    models = iter([
        _FakeModel(track_results=[_TrackResult()]),
        _FakeModel(predict_results=[_PpeResult()]),
    ])

    with pytest.raises(ValueError, match="pose_model_path"):
        Phase3FrameAnalyzer(
            runtime=runtime,
            source_fps=30.0,
            track_model_path="track.pt",
            ppe_model_path="ppe.pt",
            pose_model_path=None,
            confidence=0.35,
            iou=0.70,
            image_size=640,
            device="0",
            model_factory=lambda path: next(models),
        )


def test_factory_constructs_pose_model_only_when_runtime_enables_pose() -> None:
    settings = SimpleNamespace(
        model_path="track.pt",
        phase3_ppe_model_path="ppe.pt",
        phase3_pose_model_path="pose.pt",
        confidence=0.35,
        iou=0.70,
        image_size=640,
        device="0",
    )
    created_paths = []

    def model_factory(path):
        created_paths.append(path)
        return _FakeModel()

    analyzer = create_phase3_frame_analyzer(
        settings=settings,
        runtime=_PoseRuntime(),
        source_fps=30.0,
        model_factory=model_factory,
    )

    assert analyzer is not None
    assert created_paths == ["track.pt", "ppe.pt", "pose.pt"]

    created_paths.clear()

    analyzer = create_phase3_frame_analyzer(
        settings=settings,
        runtime=_NoPoseRuntime(),
        source_fps=30.0,
        model_factory=model_factory,
    )

    assert analyzer is not None
    assert created_paths == ["track.pt", "ppe.pt"]
