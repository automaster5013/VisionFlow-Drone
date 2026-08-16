from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from app.inference.phase3_association import TrackedPersonBox
from app.inference.phase3_depth_enrichment import DepthBucket
from app.inference.phase3_yolo_depth import YoloDepthEstimator


class _FakeDepthTensor:
    def __init__(self, array: np.ndarray) -> None:
        self._array = array

    def detach(self):
        return self

    def float(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self._array


class _FakeModel:
    def __init__(self, depth: np.ndarray | None) -> None:
        self._depth = depth
        self.calls = []

    def predict(self, **kwargs):
        self.calls.append(kwargs)

        if self._depth is None:
            return [SimpleNamespace(depth=None)]

        return [
            SimpleNamespace(
                depth=SimpleNamespace(
                    data=_FakeDepthTensor(self._depth),
                )
            )
        ]


def _frame(height: int = 4, width: int = 4) -> np.ndarray:
    return np.zeros((height, width, 3), dtype=np.uint8)


def test_estimator_returns_person_lower_half_metric_depth() -> None:
    depth = np.array(
        [
            [1.0, 1.0, 1.0, 1.0],
            [1.0, 1.0, 1.0, 1.0],
            [2.0, 2.0, 4.0, 4.0],
            [2.0, 2.0, 4.0, 4.0],
        ],
        dtype=np.float32,
    )
    model = _FakeModel(depth)
    estimator = YoloDepthEstimator(
        model_path="/models/yolo26m-depth.pt",
        image_size=768,
        device="0",
        model=model,
    )

    measurement = estimator.estimate(
        frame=_frame(),
        person_box=TrackedPersonBox(
            track_id=1,
            x1=0,
            y1=0,
            x2=2,
            y2=4,
        ),
    )

    assert measurement.estimated_depth_m == pytest.approx(2.0)
    assert measurement.scene_q33_m == pytest.approx(1.0)
    assert measurement.scene_q66_m == pytest.approx(2.0)
    assert measurement.bucket is DepthBucket.MID

    assert len(model.calls) == 1
    call = model.calls[0]
    assert call["source"].shape == (4, 4, 3)
    assert call["imgsz"] == 768
    assert call["device"] == "0"
    assert call["verbose"] is False


def test_estimator_scales_person_box_when_depth_resolution_differs() -> None:
    depth = np.array(
        [
            [1.0, 1.0],
            [5.0, 9.0],
        ],
        dtype=np.float32,
    )
    estimator = YoloDepthEstimator(
        model_path="depth.pt",
        model=_FakeModel(depth),
    )

    measurement = estimator.estimate(
        frame=_frame(height=8, width=8),
        person_box=TrackedPersonBox(
            track_id=2,
            x1=0,
            y1=0,
            x2=4,
            y2=8,
        ),
    )

    assert measurement.estimated_depth_m == pytest.approx(5.0)


def test_estimator_filters_invalid_scene_and_person_pixels() -> None:
    depth = np.array(
        [
            [np.nan, -1.0, 1.0, 1.0],
            [0.0, np.inf, 1.0, 1.0],
            [2.0, 4.0, 6.0, 8.0],
            [2.0, 4.0, 6.0, 8.0],
        ],
        dtype=np.float32,
    )
    estimator = YoloDepthEstimator(
        model_path="depth.pt",
        model=_FakeModel(depth),
    )

    measurement = estimator.estimate(
        frame=_frame(),
        person_box=TrackedPersonBox(
            track_id=3,
            x1=0,
            y1=0,
            x2=2,
            y2=4,
        ),
    )

    assert measurement.estimated_depth_m == pytest.approx(3.0)
    assert measurement.scene_q33_m > 0
    assert measurement.scene_q66_m > measurement.scene_q33_m


def test_estimator_returns_unknown_when_person_crop_has_no_valid_depth() -> None:
    depth = np.array(
        [
            [1.0, 1.0, 3.0, 3.0],
            [1.0, 1.0, 3.0, 3.0],
            [0.0, 0.0, 3.0, 3.0],
            [np.nan, -1.0, 3.0, 3.0],
        ],
        dtype=np.float32,
    )
    estimator = YoloDepthEstimator(
        model_path="depth.pt",
        model=_FakeModel(depth),
    )

    measurement = estimator.estimate(
        frame=_frame(),
        person_box=TrackedPersonBox(
            track_id=4,
            x1=0,
            y1=0,
            x2=2,
            y2=4,
        ),
    )

    assert measurement.estimated_depth_m == 0.0
    assert measurement.bucket is DepthBucket.UNKNOWN


def test_estimator_rejects_missing_depth_output() -> None:
    estimator = YoloDepthEstimator(
        model_path="depth.pt",
        model=_FakeModel(None),
    )

    with pytest.raises(RuntimeError, match="does not contain a depth map"):
        estimator.estimate(
            frame=_frame(),
            person_box=TrackedPersonBox(
                track_id=5,
                x1=0,
                y1=0,
                x2=2,
                y2=4,
            ),
        )


def test_estimator_rejects_non_2d_depth_map() -> None:
    estimator = YoloDepthEstimator(
        model_path="depth.pt",
        model=_FakeModel(
            np.zeros((1, 4, 4), dtype=np.float32)
        ),
    )

    with pytest.raises(RuntimeError, match=r"shape \(H, W\)"):
        estimator.estimate(
            frame=_frame(),
            person_box=TrackedPersonBox(
                track_id=6,
                x1=0,
                y1=0,
                x2=2,
                y2=4,
            ),
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"model_path": ""}, "model_path"),
        ({"model_path": "depth.pt", "image_size": 0}, "image_size"),
        ({"model_path": "depth.pt", "device": ""}, "device"),
    ],
)
def test_constructor_validates_configuration(kwargs, message) -> None:
    with pytest.raises(ValueError, match=message):
        YoloDepthEstimator(
            **kwargs,
            model=_FakeModel(
                np.ones((2, 2), dtype=np.float32)
            ),
        )
