from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from app.domain import Detection
from app.inference.phase3_association import TrackedPersonBox
from app.inference.phase3_runtime import (
    compute_sample_stride,
    create_phase3_runtime,
)


class _FakeEstimator:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.warmed = False

    def warmup(self) -> None:
        self.warmed = True


class _FakeEnricher:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.started = False
        self.closed = False
        self.requests = []
        self.released = []

    def start(self) -> None:
        self.started = True

    def submit(self, request) -> bool:
        self.requests.append(request)
        return True

    def release_event(self, event_key: str) -> bool:
        self.released.append(event_key)
        return True

    def close(self) -> None:
        self.closed = True


def _settings(
    *,
    enabled: bool = True,
    depth_enabled: bool = True,
):
    return SimpleNamespace(
        phase3_enabled=enabled,
        phase3_ppe_target_fps=10.0,
        phase3_pose_enabled=False,
        phase3_pose_model_path="/models/yolo26m-pose.pt",
        phase3_pose_target_fps=5.0,
        phase3_depth_enabled=depth_enabled,
        phase3_depth_model_path="/models/yolo26m-depth.pt",
        phase3_depth_image_size=768,
        phase3_depth_queue_capacity=4,
        device="0",
        source_id="camera-1",
        session_id="session-123",
    )


def _track() -> TrackedPersonBox:
    return TrackedPersonBox(
        track_id=1,
        x1=0,
        y1=0,
        x2=100,
        y2=200,
    )


def _head() -> Detection:
    return Detection(
        class_id=2,
        class_name="head",
        confidence=0.95,
        x1=35,
        y1=10,
        x2=65,
        y2=45,
    )


@pytest.mark.parametrize(
    ("source_fps", "target_fps", "expected"),
    [
        (30.0, 10.0, 3),
        (29.97, 10.0, 3),
        (25.0, 10.0, 3),
        (5.0, 10.0, 1),
    ],
)
def test_compute_sample_stride_never_exceeds_target_rate(
    source_fps: float,
    target_fps: float,
    expected: int,
) -> None:
    assert (
        compute_sample_stride(
            source_fps=source_fps,
            target_fps=target_fps,
        )
        == expected
    )


def test_disabled_phase3_does_not_construct_heavy_runtime() -> None:
    def fail_factory(**kwargs):
        raise AssertionError("factory must not be called")

    runtime = create_phase3_runtime(
        settings=_settings(enabled=False),
        source_fps=30.0,
        depth_estimator_factory=fail_factory,
        depth_enricher_factory=fail_factory,
    )

    assert runtime is None


def test_depth_disabled_builds_ppe_only_runtime() -> None:
    runtime = create_phase3_runtime(
        settings=_settings(depth_enabled=False),
        source_fps=30.0,
    )

    assert runtime is not None
    assert runtime.depth_enabled is False
    assert runtime.sample_stride_frames == 3
    assert runtime.effective_ppe_fps == pytest.approx(10.0)

    runtime.start()
    result = runtime.process_sample(
        frame_index=1,
        event_time_sec=1 / 30.0,
        frame=np.zeros((240, 320, 3), dtype=np.uint8),
        tracks=(_track(),),
        detections=(_head(),),
    )
    runtime.close()

    assert result.ppe.for_track(1).snapshot.sample_count == 1
    assert result.depth_triggers == ()

    runtime.start()
    restarted = runtime.process_sample(
        frame_index=1,
        event_time_sec=1 / 30.0,
        frame=np.zeros((240, 320, 3), dtype=np.uint8),
        tracks=(_track(),),
        detections=(_head(),),
    )
    runtime.close()

    assert restarted.ppe.for_track(1).snapshot.sample_count == 1


def test_depth_enabled_builds_managed_runtime_with_settings() -> None:
    created = {}

    def estimator_factory(**kwargs):
        estimator = _FakeEstimator(**kwargs)
        created["estimator"] = estimator
        return estimator

    def enricher_factory(**kwargs):
        enricher = _FakeEnricher(**kwargs)
        created["enricher"] = enricher
        return enricher

    callback = lambda result: None

    runtime = create_phase3_runtime(
        settings=_settings(),
        source_fps=30.0,
        on_depth_result=callback,
        depth_estimator_factory=estimator_factory,
        depth_enricher_factory=enricher_factory,
    )

    assert runtime is not None
    assert runtime.depth_enabled is True
    assert runtime.sample_stride_frames == 3
    assert runtime.effective_ppe_fps == pytest.approx(10.0)

    estimator = created["estimator"]
    assert estimator.kwargs == {
        "model_path": "/models/yolo26m-depth.pt",
        "image_size": 768,
        "device": "0",
    }

    enricher = created["enricher"]
    assert enricher.kwargs["estimator"] is estimator
    assert enricher.kwargs["queue_capacity"] == 4
    assert enricher.kwargs["on_result"] is callback

    runtime.start()
    assert runtime.started is True
    assert enricher.started is True
    assert estimator.warmed is True

    runtime.close()
    assert runtime.started is False
    assert enricher.closed is True


def test_runtime_requires_start_before_processing() -> None:
    runtime = create_phase3_runtime(
        settings=_settings(depth_enabled=False),
        source_fps=30.0,
    )
    assert runtime is not None

    with pytest.raises(RuntimeError, match="not started"):
        runtime.process_sample(
            frame_index=1,
            event_time_sec=1 / 30.0,
            frame=np.zeros((240, 320, 3), dtype=np.uint8),
            tracks=(),
            detections=(),
        )


def test_invalid_enabled_runtime_fps_is_rejected() -> None:
    with pytest.raises(ValueError, match="source_fps"):
        create_phase3_runtime(
            settings=_settings(),
            source_fps=0.0,
        )
