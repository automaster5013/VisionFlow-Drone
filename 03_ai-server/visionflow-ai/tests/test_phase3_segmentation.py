from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.inference.phase3_segmentation import (
    build_segmentation_frame_result,
)


class _Tensor:
    def __init__(self, value) -> None:
        self.value = value

    def detach(self):
        return self

    def cpu(self):
        return self

    def tolist(self):
        return self.value


def _result(*, boxes, confidence, class_ids, polygons, names):
    return SimpleNamespace(
        boxes=SimpleNamespace(
            xyxy=_Tensor(boxes),
            conf=_Tensor(confidence),
            cls=_Tensor(class_ids),
        ),
        masks=SimpleNamespace(xy=polygons),
        names=names,
    )


def test_fake_segmentation_result_is_converted() -> None:
    result = build_segmentation_frame_result(
        result=_result(
            boxes=[
                [10, 20, 50, 80],
                [100, 120, 160, 200],
            ],
            confidence=[0.91, 0.72],
            class_ids=[0, 1],
            polygons=[
                [[10, 20], [50, 20], [50, 80], [10, 80]],
                [[100, 120], [160, 120], [160, 200], [100, 200]],
            ],
            names={0: "person", 1: "vehicle"},
        ),
        frame_index=7,
    )

    assert result.frame_index == 7
    assert result.instance_count == 2
    assert result.count_for_class("person") == 1
    assert result.count_for_class("vehicle") == 1

    person = result.instances[0]
    assert person.class_id == 0
    assert person.class_name == "person"
    assert person.confidence == pytest.approx(0.91)
    assert person.mask_area_pixels == pytest.approx(2_400.0)
    assert result.total_mask_area_pixels == pytest.approx(7_200.0)


def test_sequence_class_names_and_fallback_are_supported() -> None:
    sequence_result = build_segmentation_frame_result(
        result=_result(
            boxes=[[0, 0, 10, 10]],
            confidence=[0.5],
            class_ids=[1],
            polygons=[[[0, 0], [10, 0], [10, 10], [0, 10]]],
            names=("person", "forklift"),
        ),
        frame_index=1,
    )
    fallback_result = build_segmentation_frame_result(
        result=_result(
            boxes=[[0, 0, 1, 1]],
            confidence=[0.4],
            class_ids=[9],
            polygons=[[[0, 0], [1, 0], [1, 1], [0, 1]]],
            names={0: "person"},
        ),
        frame_index=2,
    )

    assert sequence_result.instances[0].class_name == "forklift"
    assert fallback_result.instances[0].class_name == "9"


@pytest.mark.parametrize(
    "result",
    [
        SimpleNamespace(boxes=None, masks=None),
        SimpleNamespace(boxes=SimpleNamespace(), masks=None),
    ],
)
def test_missing_segmentation_outputs_return_empty_result(result) -> None:
    frame = build_segmentation_frame_result(
        result=result,
        frame_index=3,
    )

    assert frame.instances == ()
    assert frame.instance_count == 0
    assert frame.total_mask_area_pixels == 0.0


def test_mismatched_output_lengths_are_rejected() -> None:
    with pytest.raises(ValueError, match="same length"):
        build_segmentation_frame_result(
            result=_result(
                boxes=[[0, 0, 10, 10]],
                confidence=[0.8],
                class_ids=[0],
                polygons=[],
                names={0: "person"},
            ),
            frame_index=5,
        )


@pytest.mark.parametrize(
    ("frame_index", "box", "polygon", "match"),
    [
        (0, [0, 0, 10, 10], [[0, 0], [10, 0], [0, 10]], "frame_index"),
        (1, [0, 0, 10], [[0, 0], [10, 0], [0, 10]], "four coordinates"),
        (1, [0, 0, 10, 10], [[0], [10, 0], [0, 10]], "x and y"),
    ],
)
def test_segmentation_result_validation(
    frame_index: int,
    box,
    polygon,
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        build_segmentation_frame_result(
            result=_result(
                boxes=[box],
                confidence=[0.8],
                class_ids=[0],
                polygons=[polygon],
                names={0: "person"},
            ),
            frame_index=frame_index,
        )
