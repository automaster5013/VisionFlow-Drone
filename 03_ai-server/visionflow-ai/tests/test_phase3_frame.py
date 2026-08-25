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
        conf,
        cls,
        ids=None,
    ) -> None:
        self.xyxy = _Tensor(xyxy)
        self.conf = _Tensor(conf)
        self.cls = _Tensor(cls)
        self.id = None if ids is None else _Tensor(ids)


class _Result:
    def __init__(
        self,
        *,
        boxes,
        names,
        masks=None,
        plotted_value: int = 9,
    ) -> None:
        self.boxes = boxes
        self.names = names
        self.masks = masks
        self._plotted_value = plotted_value

    def plot(self):
        return np.full(
            (4, 6, 3),
            self._plotted_value,
            dtype=np.uint8,
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


class _FakeRuntime:
    sample_stride_frames = 3
    pose_enabled = False
    segmentation_enabled = False

    def should_sample_pose(self, source_frame_index: int) -> bool:
        return False

    def should_sample_segmentation(
        self,
        source_frame_index: int,
    ) -> bool:
        return False

    def __init__(self) -> None:
        self.calls = []

    def process_sample(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(marker="ppe")


class _FakeSegmentationRuntime(_FakeRuntime):
    segmentation_enabled = True

    def should_sample_segmentation(
        self,
        source_frame_index: int,
    ) -> bool:
        return source_frame_index % 6 == 0


def _frame(frame_index: int) -> FramePacket:
    return FramePacket(
        source_id="camera-1",
        session_id="session-1",
        source_type=VideoSourceType.DUMMY_VIDEO,
        drone_id=1,
        frame_index=frame_index,
        captured_at=datetime(2026, 8, 15, tzinfo=UTC),
        image=np.zeros((4, 6, 3), dtype=np.uint8),
    )


def _track_result() -> _Result:
    return _Result(
        boxes=_Boxes(
            xyxy=[
                [0, 0, 3, 4],
                [3, 0, 6, 4],
            ],
            conf=[0.9, 0.8],
            cls=[0, 2],
            ids=[11, 22],
        ),
        names={
            0: "person",
            2: "car",
        },
    )


def _ppe_result() -> _Result:
    return _Result(
        boxes=_Boxes(
            xyxy=[
                [0.5, 0.0, 2.5, 1.5],
            ],
            conf=[0.95],
            cls=[2],
        ),
        names={
            0: "helmet",
            1: "vest",
            2: "head",
            3: "person",
        },
    )


def _segmentation_result() -> _Result:
    return _Result(
        boxes=_Boxes(
            xyxy=[[0, 0, 4, 4]],
            conf=[0.88],
            cls=[0],
        ),
        masks=SimpleNamespace(
            xy=[[[0, 0], [4, 0], [4, 4], [0, 4]]],
        ),
        names={0: "person"},
    )


def _analyzer(runtime=None):
    runtime = runtime or _FakeRuntime()
    track_model = _FakeModel(track_results=[_track_result()])
    ppe_model = _FakeModel(predict_results=[_ppe_result()])
    models = iter([track_model, ppe_model])

    analyzer = Phase3FrameAnalyzer(
        runtime=runtime,
        source_fps=30.0,
        track_model_path="track.pt",
        ppe_model_path="ppe.pt",
        confidence=0.35,
        iou=0.70,
        image_size=640,
        device="0",
        model_factory=lambda path: next(models),
    )
    return analyzer, runtime, track_model, ppe_model


def test_tracking_runs_on_every_frame_but_ppe_only_on_stride() -> None:
    analyzer, runtime, track_model, ppe_model = _analyzer()

    first = analyzer.analyze(_frame(0))
    second = analyzer.analyze(_frame(1))
    third = analyzer.analyze(_frame(2))
    fourth = analyzer.analyze(_frame(3))

    assert len(track_model.track_calls) == 4
    assert len(ppe_model.predict_calls) == 2
    assert len(runtime.calls) == 2

    assert first.ppe_sampled is True
    assert second.ppe_sampled is False
    assert third.ppe_sampled is False
    assert fourth.ppe_sampled is True


def test_zero_based_source_frame_is_converted_to_positive_policy_frame() -> None:
    analyzer, runtime, _, _ = _analyzer()

    analysis = analyzer.analyze(_frame(0))

    assert analysis.ppe is not None
    assert runtime.calls[0]["frame_index"] == 1
    assert runtime.calls[0]["event_time_sec"] == pytest.approx(0.0)


def test_primary_inference_packet_is_built_from_track_result() -> None:
    analyzer, _, _, _ = _analyzer()

    analysis = analyzer.analyze(_frame(0))

    assert len(analysis.inference.detections) == 2
    assert analysis.inference.detections[0].class_name == "person"
    assert analysis.inference.detections[1].class_name == "car"
    assert analysis.inference.annotated_image.shape == (4, 6, 3)
    assert analysis.inference.inference_ms >= 0.0


def test_only_person_class_becomes_phase3_track() -> None:
    analyzer, runtime, _, _ = _analyzer()

    analysis = analyzer.analyze(_frame(0))

    tracks = runtime.calls[0]["tracks"]
    assert len(tracks) == 1
    assert tracks[0].track_id == 11
    assert analysis.tracked_person_count == 1


def test_no_tracked_person_skips_ppe_model_but_advances_sample_clock() -> None:
    runtime = _FakeRuntime()
    track_result = _Result(
        boxes=_Boxes(
            xyxy=[[0, 0, 6, 4]],
            conf=[0.8],
            cls=[2],
            ids=[22],
        ),
        names={2: "car"},
    )
    track_model = _FakeModel(track_results=[track_result])
    ppe_model = _FakeModel(predict_results=[_ppe_result()])
    models = iter([track_model, ppe_model])

    analyzer = Phase3FrameAnalyzer(
        runtime=runtime,
        source_fps=30.0,
        track_model_path="track.pt",
        ppe_model_path="ppe.pt",
        confidence=0.35,
        iou=0.70,
        image_size=640,
        device="0",
        model_factory=lambda path: next(models),
    )

    analysis = analyzer.analyze(_frame(0))

    assert ppe_model.predict_calls == []
    assert len(runtime.calls) == 1
    assert runtime.calls[0]["tracks"] == ()
    assert runtime.calls[0]["detections"] == ()
    assert analysis.ppe_sampled is True


def test_segmentation_runs_only_on_its_independent_stride() -> None:
    runtime = _FakeSegmentationRuntime()
    track_model = _FakeModel(track_results=[_track_result()])
    ppe_model = _FakeModel(predict_results=[_ppe_result()])
    segmentation_model = _FakeModel(
        predict_results=[_segmentation_result()],
    )
    models = iter([track_model, ppe_model, segmentation_model])

    analyzer = Phase3FrameAnalyzer(
        runtime=runtime,
        source_fps=30.0,
        track_model_path="track.pt",
        ppe_model_path="ppe.pt",
        segmentation_model_path="seg.pt",
        confidence=0.35,
        iou=0.70,
        image_size=640,
        device="0",
        model_factory=lambda path: next(models),
    )

    first = analyzer.analyze(_frame(0))
    second = analyzer.analyze(_frame(1))
    seventh = analyzer.analyze(_frame(6))

    assert len(segmentation_model.predict_calls) == 2
    assert first.segmentation_sampled is True
    assert first.segmentation is not None
    assert first.segmentation.frame_index == 1
    assert first.segmentation.instance_count == 1
    assert (
        first.segmentation.instances[0].mask_area_pixels
        == pytest.approx(16.0)
    )
    assert second.segmentation_sampled is False
    assert second.segmentation is None
    assert seventh.segmentation_sampled is True
    assert seventh.segmentation is not None
    assert seventh.segmentation.frame_index == 7


def test_track_call_uses_phase3_runtime_configuration() -> None:
    analyzer, _, track_model, _, = _analyzer()

    analyzer.analyze(_frame(0))

    call = track_model.track_calls[0]
    assert call["persist"] is True
    assert call["tracker"] == "botsort.yaml"
    assert call["conf"] == pytest.approx(0.35)
    assert call["iou"] == pytest.approx(0.70)
    assert call["imgsz"] == 640
    assert call["device"] == "0"
    assert call["verbose"] is False


def test_factory_returns_none_without_runtime() -> None:
    called = False

    def model_factory(path):
        nonlocal called
        called = True
        raise AssertionError("model factory must not be called")

    settings = SimpleNamespace(
        model_path="track.pt",
        phase3_ppe_model_path="ppe.pt",
        confidence=0.35,
        iou=0.70,
        image_size=640,
        device="0",
    )

    analyzer = create_phase3_frame_analyzer(
        settings=settings,
        runtime=None,
        source_fps=30.0,
        model_factory=model_factory,
    )

    assert analyzer is None
    assert called is False
