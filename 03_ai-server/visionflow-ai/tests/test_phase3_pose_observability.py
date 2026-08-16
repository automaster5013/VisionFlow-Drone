from __future__ import annotations

from io import StringIO
from types import SimpleNamespace

from app.inference.phase3_observability import Phase3ConsoleObserver
from app.inference.phase3_pose import (
    Phase3PoseFrameResult,
    TrackedPoseObservation,
)


def _pose_result() -> Phase3PoseFrameResult:
    return Phase3PoseFrameResult(
        frame_index=7,
        observations=(
            TrackedPoseObservation(
                track_id=11,
                x1=0.0,
                y1=0.0,
                x2=100.0,
                y2=200.0,
                keypoints=(),
            ),
            TrackedPoseObservation(
                track_id=None,
                x1=200.0,
                y1=0.0,
                x2=300.0,
                y2=200.0,
                keypoints=(),
            ),
        ),
    )


def test_pose_sample_counts_assigned_and_unassigned_observations() -> None:
    stream = StringIO()
    observer = Phase3ConsoleObserver(stream=stream)

    observer.record_analysis(
        SimpleNamespace(
            ppe=None,
            ppe_sampled=False,
            pose=_pose_result(),
            pose_sampled=True,
        )
    )

    snapshot = observer.snapshot()

    assert snapshot.frames_analyzed == 1
    assert snapshot.ppe_samples == 0
    assert snapshot.pose_samples == 1
    assert snapshot.pose_assigned == 1
    assert snapshot.pose_unassigned == 1


def test_non_pose_frame_does_not_increment_pose_counters() -> None:
    observer = Phase3ConsoleObserver(stream=StringIO())

    observer.record_analysis(
        SimpleNamespace(
            ppe=None,
            ppe_sampled=False,
            pose=None,
            pose_sampled=False,
        )
    )

    snapshot = observer.snapshot()

    assert snapshot.frames_analyzed == 1
    assert snapshot.pose_samples == 0
    assert snapshot.pose_assigned == 0
    assert snapshot.pose_unassigned == 0


def test_missing_pose_attributes_preserve_backward_compatibility() -> None:
    observer = Phase3ConsoleObserver(stream=StringIO())

    observer.record_analysis(
        SimpleNamespace(
            ppe=None,
            ppe_sampled=False,
        )
    )

    snapshot = observer.snapshot()

    assert snapshot.frames_analyzed == 1
    assert snapshot.pose_samples == 0
    assert snapshot.pose_assigned == 0
    assert snapshot.pose_unassigned == 0


def test_summary_includes_pose_observability_fields() -> None:
    stream = StringIO()
    observer = Phase3ConsoleObserver(stream=stream)

    observer.record_analysis(
        SimpleNamespace(
            ppe=None,
            ppe_sampled=False,
            pose=_pose_result(),
            pose_sampled=True,
        )
    )

    observer.emit_summary()
    output = stream.getvalue()

    assert "PHASE3_SUMMARY" in output
    assert "FRAMES_ANALYZED=1" in output
    assert "PPE_SAMPLES=0" in output
    assert "POSE_SAMPLES=1" in output
    assert "POSE_ASSIGNED=1" in output
    assert "POSE_UNASSIGNED=1" in output
    assert "DEPTH_TRIGGER_ATTEMPTS=0" in output
    assert "DEPTH_RESULTS=0" in output
