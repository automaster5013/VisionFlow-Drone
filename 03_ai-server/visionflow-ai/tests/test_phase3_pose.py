from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.inference.phase3_association import TrackedPersonBox
from app.inference.phase3_pose import build_pose_frame_result


class _Tensor:
    def __init__(self, value) -> None:
        self.value = value

    def detach(self):
        return self

    def cpu(self):
        return self

    def tolist(self):
        return self.value


def _result(*, boxes, keypoints, confidence=None):
    return SimpleNamespace(
        boxes=SimpleNamespace(
            xyxy=_Tensor(boxes),
        ),
        keypoints=SimpleNamespace(
            xy=_Tensor(keypoints),
            conf=(
                _Tensor(confidence)
                if confidence is not None
                else None
            ),
        ),
    )


def _track(
    track_id: int,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> TrackedPersonBox:
    return TrackedPersonBox(
        track_id=track_id,
        x1=x1,
        y1=y1,
        x2=x2,
        y2=y2,
    )


def test_single_pose_is_assigned_to_overlapping_track() -> None:
    result = build_pose_frame_result(
        result=_result(
            boxes=[[10, 10, 110, 210]],
            keypoints=[[[20, 30], [40, 50], [60, 70]]],
            confidence=[[0.9, 0.8, 0.7]],
        ),
        tracks=(_track(7, 0, 0, 120, 220),),
        frame_index=1,
    )

    assert result.frame_index == 1
    assert result.assigned_count == 1
    assert result.unassigned_count == 0

    observation = result.observations[0]
    assert observation.track_id == 7
    assert observation.assigned is True
    assert len(observation.keypoints) == 3
    assert observation.keypoints[0].index == 0
    assert observation.keypoints[0].confidence == pytest.approx(0.9)


def test_two_pose_boxes_are_assigned_one_to_one() -> None:
    result = build_pose_frame_result(
        result=_result(
            boxes=[
                [0, 0, 100, 200],
                [200, 0, 300, 200],
            ],
            keypoints=[
                [[10, 10], [20, 20]],
                [[210, 10], [220, 20]],
            ],
        ),
        tracks=(
            _track(1, 0, 0, 100, 200),
            _track(2, 200, 0, 300, 200),
        ),
        frame_index=7,
    )

    assert tuple(
        item.track_id for item in result.observations
    ) == (1, 2)
    assert result.assigned_count == 2


def test_pose_below_iou_threshold_stays_unassigned() -> None:
    result = build_pose_frame_result(
        result=_result(
            boxes=[[300, 300, 400, 500]],
            keypoints=[[[320, 330], [340, 350]]],
        ),
        tracks=(_track(1, 0, 0, 100, 200),),
        frame_index=13,
        min_track_iou=0.10,
    )

    assert result.assigned_count == 0
    assert result.unassigned_count == 1
    assert result.observations[0].track_id is None


def test_missing_keypoint_confidence_is_supported() -> None:
    result = build_pose_frame_result(
        result=_result(
            boxes=[[0, 0, 100, 200]],
            keypoints=[[[10, 20], [30, 40]]],
            confidence=None,
        ),
        tracks=(_track(3, 0, 0, 100, 200),),
        frame_index=19,
    )

    assert tuple(
        point.confidence
        for point in result.observations[0].keypoints
    ) == (None, None)


def test_missing_pose_outputs_return_empty_result() -> None:
    result = build_pose_frame_result(
        result=SimpleNamespace(
            boxes=None,
            keypoints=None,
        ),
        tracks=(),
        frame_index=25,
    )

    assert result.observations == ()
    assert result.assigned_count == 0
    assert result.unassigned_count == 0


def test_mismatched_pose_box_and_keypoint_lengths_are_rejected() -> None:
    with pytest.raises(ValueError, match="same length"):
        build_pose_frame_result(
            result=_result(
                boxes=[
                    [0, 0, 100, 200],
                    [200, 0, 300, 200],
                ],
                keypoints=[[[10, 20], [30, 40]]],
            ),
            tracks=(),
            frame_index=31,
        )


@pytest.mark.parametrize(
    ("frame_index", "min_track_iou", "match"),
    [
        (0, 0.1, "frame_index"),
        (1, -0.1, "min_track_iou"),
        (1, 1.1, "min_track_iou"),
    ],
)
def test_pose_result_validation(
    frame_index: int,
    min_track_iou: float,
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        build_pose_frame_result(
            result=_result(
                boxes=[],
                keypoints=[],
            ),
            tracks=(),
            frame_index=frame_index,
            min_track_iou=min_track_iou,
        )
