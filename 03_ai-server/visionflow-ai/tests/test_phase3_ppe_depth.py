from __future__ import annotations

import numpy as np
import pytest

from app.domain import Detection
from app.inference.phase3_association import TrackedPersonBox
from app.inference.phase3_ppe_depth import Phase3PpeDepthCoordinator
from app.inference.phase3_processor import Phase3PpeProcessor


class _FakeDepthEnricher:
    def __init__(self, *, accept: bool = True) -> None:
        self.accept = accept
        self.requests = []
        self.released = []

    def submit(self, request) -> bool:
        self.requests.append(request)
        return self.accept

    def release_event(self, event_key: str) -> bool:
        self.released.append(event_key)
        return True


def _frame() -> np.ndarray:
    return np.zeros((240, 320, 3), dtype=np.uint8)


def _head_detection() -> Detection:
    return Detection(
        class_id=2,
        class_name="head",
        confidence=0.95,
        x1=35,
        y1=10,
        x2=65,
        y2=45,
    )


def _helmet_detection() -> Detection:
    return Detection(
        class_id=0,
        class_name="helmet",
        confidence=0.95,
        x1=35,
        y1=10,
        x2=65,
        y2=45,
    )


def _track(track_id: int = 1) -> TrackedPersonBox:
    return TrackedPersonBox(
        track_id=track_id,
        x1=0,
        y1=0,
        x2=100,
        y2=200,
    )


def _coordinator(depth_enricher=None) -> Phase3PpeDepthCoordinator:
    return Phase3PpeDepthCoordinator(
        processor=Phase3PpeProcessor(
            source_fps=30.0,
            sample_stride_frames=3,
        ),
        depth_enricher=depth_enricher or _FakeDepthEnricher(),
        event_namespace="session-123",
    )


def test_confirmed_transition_submits_depth_once() -> None:
    depth = _FakeDepthEnricher()
    coordinator = _coordinator(depth)

    result = None
    for frame_index in range(1, 29, 3):
        result = coordinator.process_sample(
            frame_index=frame_index,
            event_time_sec=frame_index / 30.0,
            frame=_frame(),
            tracks=(_track(),),
            detections=(_head_detection(),),
        )

    assert result is not None
    assert len(depth.requests) == 1
    assert depth.requests[0].track_id == 1
    assert depth.requests[0].event_key == "session-123:NO_HELMET:1"
    assert result.accepted_depth_triggers == 1
    assert result.active_depth_tracks == (1,)

    repeated = coordinator.process_sample(
        frame_index=31,
        event_time_sec=31 / 30.0,
        frame=_frame(),
        tracks=(_track(),),
        detections=(_head_detection(),),
    )

    assert len(depth.requests) == 1
    assert repeated.depth_triggers == ()


def test_recovery_releases_event_and_allows_future_retrigger() -> None:
    depth = _FakeDepthEnricher()
    coordinator = _coordinator(depth)

    for frame_index in range(1, 29, 3):
        coordinator.process_sample(
            frame_index=frame_index,
            event_time_sec=frame_index / 30.0,
            frame=_frame(),
            tracks=(_track(),),
            detections=(_head_detection(),),
        )

    recovered = coordinator.process_sample(
        frame_index=31,
        event_time_sec=31 / 30.0,
        frame=_frame(),
        tracks=(_track(),),
        detections=(_helmet_detection(),),
    )

    assert recovered.active_depth_tracks == ()
    assert depth.released == ["session-123:NO_HELMET:1"]

    for frame_index in range(34, 64, 3):
        coordinator.process_sample(
            frame_index=frame_index,
            event_time_sec=frame_index / 30.0,
            frame=_frame(),
            tracks=(_track(),),
            detections=(_head_detection(),),
        )

    assert len(depth.requests) == 2
    assert depth.requests[1].event_key == "session-123:NO_HELMET:1"


def test_rejected_depth_submit_is_retried_on_next_confirmed_sample() -> None:
    depth = _FakeDepthEnricher(accept=False)
    coordinator = _coordinator(depth)

    for frame_index in range(1, 29, 3):
        result = coordinator.process_sample(
            frame_index=frame_index,
            event_time_sec=frame_index / 30.0,
            frame=_frame(),
            tracks=(_track(),),
            detections=(_head_detection(),),
        )

    assert result.rejected_depth_triggers == 1
    assert result.active_depth_tracks == ()
    assert len(depth.requests) == 1

    coordinator.process_sample(
        frame_index=31,
        event_time_sec=31 / 30.0,
        frame=_frame(),
        tracks=(_track(),),
        detections=(_head_detection(),),
    )

    assert len(depth.requests) == 2


def test_non_confirmed_track_does_not_submit_depth() -> None:
    depth = _FakeDepthEnricher()
    coordinator = _coordinator(depth)

    result = coordinator.process_sample(
        frame_index=1,
        event_time_sec=1 / 30.0,
        frame=_frame(),
        tracks=(_track(),),
        detections=(_helmet_detection(),),
    )

    assert depth.requests == []
    assert result.depth_triggers == ()
    assert result.active_depth_tracks == ()


def test_two_tracks_are_triggered_independently() -> None:
    depth = _FakeDepthEnricher()
    coordinator = _coordinator(depth)

    tracks = (
        _track(1),
        TrackedPersonBox(
            track_id=2,
            x1=150,
            y1=0,
            x2=250,
            y2=200,
        ),
    )
    detections = (
        _head_detection(),
        Detection(
            class_id=2,
            class_name="head",
            confidence=0.95,
            x1=185,
            y1=10,
            x2=215,
            y2=45,
        ),
    )

    result = None
    for frame_index in range(1, 29, 3):
        result = coordinator.process_sample(
            frame_index=frame_index,
            event_time_sec=frame_index / 30.0,
            frame=_frame(),
            tracks=tracks,
            detections=detections,
        )

    assert result is not None
    assert [request.track_id for request in depth.requests] == [1, 2]
    assert result.active_depth_tracks == (1, 2)


def test_remove_track_releases_active_event() -> None:
    depth = _FakeDepthEnricher()
    coordinator = _coordinator(depth)

    for frame_index in range(1, 29, 3):
        coordinator.process_sample(
            frame_index=frame_index,
            event_time_sec=frame_index / 30.0,
            frame=_frame(),
            tracks=(_track(),),
            detections=(_head_detection(),),
        )

    assert coordinator.remove_track(1) is True
    assert depth.released == ["session-123:NO_HELMET:1"]


def test_constructor_and_frame_validation() -> None:
    with pytest.raises(ValueError, match="event_namespace"):
        Phase3PpeDepthCoordinator(
            processor=Phase3PpeProcessor(
                source_fps=30.0,
                sample_stride_frames=3,
            ),
            depth_enricher=_FakeDepthEnricher(),
            event_namespace=" ",
        )

    coordinator = _coordinator()

    with pytest.raises(ValueError, match="event_time_sec"):
        coordinator.process_sample(
            frame_index=1,
            event_time_sec=-0.1,
            frame=_frame(),
            tracks=(),
            detections=(),
        )
