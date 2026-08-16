from __future__ import annotations

import pytest

from app.inference.phase3_evidence import TrackPpeEvidenceAccumulator
from app.inference.phase3_policy import PpeComplianceState


def test_accumulator_confirms_sustained_no_helmet_track() -> None:
    accumulator = TrackPpeEvidenceAccumulator(
        source_fps=30.0,
        sample_stride_frames=3,
    )

    snapshot = None
    for frame_index in range(1, 29, 3):
        snapshot = accumulator.observe(
            track_id=1,
            frame_index=frame_index,
            has_helmet=False,
            has_head=True,
            has_vest=False,
        )

    assert snapshot is not None
    assert snapshot.sample_count == 10
    assert snapshot.head_no_helmet_rate == pytest.approx(1.0)
    assert snapshot.current_streak_seconds == pytest.approx(0.9)
    assert snapshot.max_streak_seconds == pytest.approx(0.9)
    assert snapshot.decision.state is PpeComplianceState.CONFIRMED_NO_HELMET


def test_accumulator_marks_dominant_helmet_track_safe() -> None:
    accumulator = TrackPpeEvidenceAccumulator(
        source_fps=30.0,
        sample_stride_frames=3,
    )

    snapshot = None
    for frame_index in range(1, 31, 3):
        snapshot = accumulator.observe(
            track_id=7,
            frame_index=frame_index,
            has_helmet=True,
            has_head=False,
            has_vest=True,
        )

    assert snapshot is not None
    assert snapshot.sample_count == 10
    assert snapshot.helmet_rate == pytest.approx(1.0)
    assert snapshot.vest_rate == pytest.approx(1.0)
    assert snapshot.current_streak_seconds == pytest.approx(0.0)
    assert snapshot.decision.state is PpeComplianceState.SAFE


def test_gap_resets_current_streak_but_preserves_max_streak() -> None:
    accumulator = TrackPpeEvidenceAccumulator(
        source_fps=30.0,
        sample_stride_frames=3,
    )

    for frame_index in (1, 4, 7, 10):
        accumulator.observe(
            track_id=2,
            frame_index=frame_index,
            has_helmet=False,
            has_head=True,
            has_vest=False,
        )

    before_gap = accumulator.snapshot(2)
    assert before_gap.current_streak_seconds == pytest.approx(0.3)
    assert before_gap.max_streak_seconds == pytest.approx(0.3)

    after_gap = accumulator.observe(
        track_id=2,
        frame_index=20,
        has_helmet=False,
        has_head=True,
        has_vest=False,
    )

    assert after_gap.current_streak_start_frame == 20
    assert after_gap.current_streak_end_frame == 20
    assert after_gap.current_streak_seconds == pytest.approx(0.0)
    assert after_gap.max_streak_seconds == pytest.approx(0.3)
    assert after_gap.decision.state is PpeComplianceState.NO_HELMET_CANDIDATE


def test_unknown_observation_accumulates_unknown_rate() -> None:
    accumulator = TrackPpeEvidenceAccumulator(
        source_fps=25.0,
        sample_stride_frames=3,
    )

    snapshot = None
    for frame_index in range(1, 31, 3):
        snapshot = accumulator.observe(
            track_id=3,
            frame_index=frame_index,
            has_helmet=False,
            has_head=False,
            has_vest=False,
        )

    assert snapshot is not None
    assert snapshot.sample_count == 10
    assert snapshot.unknown_rate == pytest.approx(1.0)
    assert snapshot.decision.state is PpeComplianceState.UNKNOWN


def test_frame_index_must_be_monotonic_per_track() -> None:
    accumulator = TrackPpeEvidenceAccumulator(
        source_fps=30.0,
        sample_stride_frames=3,
    )

    accumulator.observe(
        track_id=4,
        frame_index=10,
        has_helmet=True,
        has_head=False,
        has_vest=False,
    )

    with pytest.raises(ValueError, match="monotonically"):
        accumulator.observe(
            track_id=4,
            frame_index=10,
            has_helmet=True,
            has_head=False,
            has_vest=False,
        )


def test_tracks_are_independent_and_can_be_removed() -> None:
    accumulator = TrackPpeEvidenceAccumulator(
        source_fps=30.0,
        sample_stride_frames=3,
    )

    accumulator.observe(
        track_id=1,
        frame_index=1,
        has_helmet=True,
        has_head=False,
        has_vest=True,
    )
    accumulator.observe(
        track_id=2,
        frame_index=1,
        has_helmet=False,
        has_head=True,
        has_vest=False,
    )

    snapshots = accumulator.snapshots()
    assert [snapshot.track_id for snapshot in snapshots] == [1, 2]

    assert accumulator.remove(1) is True
    assert accumulator.remove(1) is False

    remaining = accumulator.snapshots()
    assert [snapshot.track_id for snapshot in remaining] == [2]
