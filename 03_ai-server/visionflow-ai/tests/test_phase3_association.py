from __future__ import annotations

import pytest

from app.domain import Detection
from app.inference.phase3_association import (
    TrackedPersonBox,
    associate_ppe_detections,
)


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


def test_head_and_helmet_are_assigned_to_correct_person_track() -> None:
    tracks = (
        TrackedPersonBox(track_id=1, x1=0, y1=0, x2=100, y2=200),
        TrackedPersonBox(track_id=2, x1=150, y1=0, x2=250, y2=200),
    )
    detections = (
        _detection("helmet", 35, 10, 65, 40),
        _detection("head", 180, 20, 220, 60),
    )

    result = associate_ppe_detections(
        tracks=tracks,
        detections=detections,
    )

    left = result.for_track(1)
    right = result.for_track(2)

    assert left.has_helmet is True
    assert left.has_head is False
    assert right.has_helmet is False
    assert right.has_head is True
    assert result.unassigned_count == 0
    assert result.ignored_count == 0


def test_vest_is_assigned_only_inside_torso_region() -> None:
    track = TrackedPersonBox(
        track_id=7,
        x1=100,
        y1=100,
        x2=300,
        y2=500,
    )
    detections = (
        _detection("vest", 150, 220, 250, 380),
        _detection("vest", 150, 460, 250, 500),
    )

    result = associate_ppe_detections(
        tracks=(track,),
        detections=detections,
    )

    match = result.for_track(7)
    assert match.vest_count == 1
    assert match.has_vest is True
    assert result.unassigned_count == 1


def test_recognized_ppe_outside_all_tracks_is_unassigned() -> None:
    track = TrackedPersonBox(
        track_id=3,
        x1=0,
        y1=0,
        x2=100,
        y2=200,
    )

    result = associate_ppe_detections(
        tracks=(track,),
        detections=(
            _detection("helmet", 300, 300, 340, 340),
        ),
    )

    assert result.for_track(3).helmet_count == 0
    assert result.unassigned_count == 1
    assert result.ignored_count == 0


def test_overlapping_tracks_use_nearest_anatomical_anchor() -> None:
    tracks = (
        TrackedPersonBox(track_id=10, x1=0, y1=0, x2=120, y2=240),
        TrackedPersonBox(track_id=11, x1=40, y1=0, x2=160, y2=240),
    )

    result = associate_ppe_detections(
        tracks=tracks,
        detections=(
            _detection("helmet", 95, 20, 115, 40),
        ),
    )

    assert result.for_track(10).helmet_count == 0
    assert result.for_track(11).helmet_count == 1


def test_non_ppe_classes_are_ignored() -> None:
    track = TrackedPersonBox(
        track_id=5,
        x1=0,
        y1=0,
        x2=100,
        y2=200,
    )

    result = associate_ppe_detections(
        tracks=(track,),
        detections=(
            _detection("person", 0, 0, 100, 200),
            _detection("boots", 20, 150, 80, 195),
        ),
    )

    match = result.for_track(5)
    assert match.helmet_count == 0
    assert match.head_count == 0
    assert match.vest_count == 0
    assert result.unassigned_count == 0
    assert result.ignored_count == 2


def test_duplicate_track_ids_are_rejected() -> None:
    tracks = (
        TrackedPersonBox(track_id=1, x1=0, y1=0, x2=100, y2=200),
        TrackedPersonBox(track_id=1, x1=200, y1=0, x2=300, y2=200),
    )

    with pytest.raises(ValueError, match="Duplicate track_id"):
        associate_ppe_detections(
            tracks=tracks,
            detections=(),
        )


def test_invalid_ppe_detection_box_is_rejected() -> None:
    track = TrackedPersonBox(
        track_id=1,
        x1=0,
        y1=0,
        x2=100,
        y2=200,
    )

    with pytest.raises(ValueError, match="positive area"):
        associate_ppe_detections(
            tracks=(track,),
            detections=(
                _detection("helmet", 50, 20, 40, 30),
            ),
        )
