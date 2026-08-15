from __future__ import annotations

import pytest

from app.domain import Detection
from app.inference.phase3_association import TrackedPersonBox
from app.inference.phase3_policy import PpeComplianceState
from app.inference.phase3_processor import Phase3PpeProcessor


def _detection(
    class_name: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> Detection:
    return Detection(
        class_id=0,
        class_name=class_name,
        confidence=0.95,
        x1=x1,
        y1=y1,
        x2=x2,
        y2=y2,
    )


def test_processor_confirms_no_helmet_end_to_end() -> None:
    processor = Phase3PpeProcessor(
        source_fps=30.0,
        sample_stride_frames=3,
    )
    track = TrackedPersonBox(
        track_id=1,
        x1=0,
        y1=0,
        x2=100,
        y2=200,
    )

    result = None
    for frame_index in range(1, 29, 3):
        result = processor.process_sample(
            frame_index=frame_index,
            tracks=(track,),
            detections=(
                _detection("head", 35, 10, 65, 45),
            ),
        )

    assert result is not None
    assessment = result.for_track(1)

    assert assessment.state is PpeComplianceState.CONFIRMED_NO_HELMET
    assert assessment.snapshot.sample_count == 10
    assert assessment.snapshot.head_no_helmet_rate == pytest.approx(1.0)
    assert assessment.snapshot.current_streak_seconds == pytest.approx(0.9)
    assert result.confirmed_no_helmet() == (assessment,)


def test_processor_marks_helmet_track_safe_end_to_end() -> None:
    processor = Phase3PpeProcessor(
        source_fps=30.0,
        sample_stride_frames=3,
    )
    track = TrackedPersonBox(
        track_id=7,
        x1=100,
        y1=100,
        x2=300,
        y2=500,
    )

    result = None
    for frame_index in range(1, 31, 3):
        result = processor.process_sample(
            frame_index=frame_index,
            tracks=(track,),
            detections=(
                _detection("helmet", 165, 115, 235, 175),
                _detection("vest", 155, 220, 245, 370),
            ),
        )

    assert result is not None
    assessment = result.for_track(7)

    assert assessment.state is PpeComplianceState.SAFE
    assert assessment.snapshot.helmet_rate == pytest.approx(1.0)
    assert assessment.snapshot.vest_rate == pytest.approx(1.0)
    assert result.confirmed_no_helmet() == ()


def test_processor_keeps_two_tracks_independent() -> None:
    processor = Phase3PpeProcessor(
        source_fps=30.0,
        sample_stride_frames=3,
    )
    tracks = (
        TrackedPersonBox(track_id=10, x1=0, y1=0, x2=100, y2=200),
        TrackedPersonBox(track_id=11, x1=150, y1=0, x2=250, y2=200),
    )

    result = None
    for frame_index in range(1, 29, 3):
        result = processor.process_sample(
            frame_index=frame_index,
            tracks=tracks,
            detections=(
                _detection("helmet", 35, 10, 65, 40),
                _detection("head", 185, 10, 215, 45),
            ),
        )

    assert result is not None
    safe = result.for_track(10)
    violation = result.for_track(11)

    assert safe.state is PpeComplianceState.SAFE
    assert violation.state is PpeComplianceState.CONFIRMED_NO_HELMET
    assert [item.track_id for item in result.confirmed_no_helmet()] == [11]


def test_processor_forwards_unassigned_and_ignored_counts() -> None:
    processor = Phase3PpeProcessor(
        source_fps=30.0,
        sample_stride_frames=3,
    )
    track = TrackedPersonBox(
        track_id=2,
        x1=0,
        y1=0,
        x2=100,
        y2=200,
    )

    result = processor.process_sample(
        frame_index=1,
        tracks=(track,),
        detections=(
            _detection("helmet", 300, 300, 340, 340),
            _detection("person", 0, 0, 100, 200),
        ),
    )

    assert result.unassigned_count == 1
    assert result.ignored_count == 1
    assert result.for_track(2).state is PpeComplianceState.UNKNOWN


def test_processor_gap_resets_current_streak() -> None:
    processor = Phase3PpeProcessor(
        source_fps=30.0,
        sample_stride_frames=3,
    )
    track = TrackedPersonBox(
        track_id=4,
        x1=0,
        y1=0,
        x2=100,
        y2=200,
    )

    for frame_index in (1, 4, 7, 10):
        processor.process_sample(
            frame_index=frame_index,
            tracks=(track,),
            detections=(
                _detection("head", 35, 10, 65, 45),
            ),
        )

    result = processor.process_sample(
        frame_index=20,
        tracks=(track,),
        detections=(
            _detection("head", 35, 10, 65, 45),
        ),
    )
    assessment = result.for_track(4)

    assert assessment.state is PpeComplianceState.NO_HELMET_CANDIDATE
    assert assessment.snapshot.current_streak_seconds == pytest.approx(0.0)
    assert assessment.snapshot.max_streak_seconds == pytest.approx(0.3)


def test_processor_rejects_non_monotonic_sample_frames() -> None:
    processor = Phase3PpeProcessor(
        source_fps=30.0,
        sample_stride_frames=3,
    )

    processor.process_sample(
        frame_index=10,
        tracks=(),
        detections=(),
    )

    with pytest.raises(ValueError, match="monotonically"):
        processor.process_sample(
            frame_index=10,
            tracks=(),
            detections=(),
        )


def test_remove_track_discards_old_evidence_and_clear_resets_frame_clock() -> None:
    processor = Phase3PpeProcessor(
        source_fps=30.0,
        sample_stride_frames=3,
    )
    track = TrackedPersonBox(
        track_id=9,
        x1=0,
        y1=0,
        x2=100,
        y2=200,
    )

    processor.process_sample(
        frame_index=1,
        tracks=(track,),
        detections=(
            _detection("head", 35, 10, 65, 45),
        ),
    )

    assert processor.remove_track(9) is True
    assert processor.remove_track(9) is False

    result = processor.process_sample(
        frame_index=4,
        tracks=(track,),
        detections=(
            _detection("helmet", 35, 10, 65, 40),
        ),
    )
    assert result.for_track(9).snapshot.sample_count == 1

    processor.clear()
    assert processor.last_frame_index == 0

    reset = processor.process_sample(
        frame_index=1,
        tracks=(track,),
        detections=(
            _detection("helmet", 35, 10, 65, 40),
        ),
    )
    assert reset.for_track(9).snapshot.sample_count == 1
