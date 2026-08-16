from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray
from ultralytics import YOLO

from app.inference.phase3_association import TrackedPersonBox
from app.inference.phase3_depth_enrichment import (
    DepthMeasurement,
    classify_depth_bucket,
)


class YoloDepthEstimator:
    def __init__(
        self,
        *,
        model_path: str,
        image_size: int = 768,
        device: str = "cpu",
        model: Any | None = None,
    ) -> None:
        if not model_path.strip():
            raise ValueError("model_path must not be blank.")
        if image_size <= 0:
            raise ValueError("image_size must be positive.")
        if not device.strip():
            raise ValueError("device must not be blank.")

        self._model_path = model_path
        self._image_size = image_size
        self._device = device
        self._model = model if model is not None else YOLO(model_path)

    @property
    def model_path(self) -> str:
        return self._model_path

    @property
    def image_size(self) -> int:
        return self._image_size

    @property
    def device(self) -> str:
        return self._device

    def warmup(self) -> None:
        frame = np.zeros(
            (self._image_size, self._image_size, 3),
            dtype=np.uint8,
        )
        self._model.predict(
            source=frame,
            imgsz=self._image_size,
            device=self._device,
            verbose=False,
        )

    def estimate(
        self,
        *,
        frame: NDArray[np.uint8],
        person_box: TrackedPersonBox,
    ) -> DepthMeasurement:
        _validate_frame(frame)
        person_box.validate()

        results = self._model.predict(
            source=frame,
            imgsz=self._image_size,
            device=self._device,
            verbose=False,
        )

        if not results:
            raise RuntimeError("YOLO depth prediction returned no results.")

        result = results[0]
        depth_object = getattr(result, "depth", None)
        if depth_object is None:
            raise RuntimeError("YOLO result does not contain a depth map.")

        depth_data = getattr(depth_object, "data", None)
        if depth_data is None:
            raise RuntimeError("YOLO depth result does not contain depth data.")

        depth = _to_depth_array(depth_data)
        scene_q33_m, scene_q66_m = _scene_depth_quantiles(depth)
        estimated_depth_m = _person_lower_half_depth(
            depth=depth,
            person_box=person_box,
            frame_width=frame.shape[1],
            frame_height=frame.shape[0],
        )
        bucket = classify_depth_bucket(
            estimated_depth_m=estimated_depth_m,
            scene_q33_m=scene_q33_m,
            scene_q66_m=scene_q66_m,
        )

        return DepthMeasurement(
            estimated_depth_m=estimated_depth_m,
            scene_q33_m=scene_q33_m,
            scene_q66_m=scene_q66_m,
            bucket=bucket,
        )


def _validate_frame(frame: NDArray[np.uint8]) -> None:
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError("frame must be an HxWx3 image.")
    if frame.size == 0:
        raise ValueError("frame must not be empty.")


def _to_depth_array(depth_data: Any) -> NDArray[np.float32]:
    value = depth_data

    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "float"):
        value = value.float()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()

    depth = np.asarray(value, dtype=np.float32)

    if depth.ndim != 2:
        raise RuntimeError(
            "YOLO depth map must have shape (H, W); "
            f"received shape={depth.shape}."
        )

    if depth.size == 0:
        raise RuntimeError("YOLO depth map must not be empty.")

    return depth


def _scene_depth_quantiles(
    depth: NDArray[np.float32],
) -> tuple[float, float]:
    valid = depth[np.isfinite(depth) & (depth > 0)]

    if valid.size == 0:
        return 0.0, 0.0

    return (
        float(np.percentile(valid, 33)),
        float(np.percentile(valid, 66)),
    )


def _person_lower_half_depth(
    *,
    depth: NDArray[np.float32],
    person_box: TrackedPersonBox,
    frame_width: int,
    frame_height: int,
) -> float:
    if frame_width <= 0 or frame_height <= 0:
        return 0.0

    clipped_x1 = max(0.0, min(float(frame_width), person_box.x1))
    clipped_y1 = max(0.0, min(float(frame_height), person_box.y1))
    clipped_x2 = max(0.0, min(float(frame_width), person_box.x2))
    clipped_y2 = max(0.0, min(float(frame_height), person_box.y2))

    if clipped_x2 <= clipped_x1 or clipped_y2 <= clipped_y1:
        return 0.0

    person_height = clipped_y2 - clipped_y1
    lower_y1 = clipped_y1 + 0.50 * person_height

    depth_height, depth_width = depth.shape
    scale_x = depth_width / float(frame_width)
    scale_y = depth_height / float(frame_height)

    x1 = int(np.floor(clipped_x1 * scale_x))
    x2 = int(np.ceil(clipped_x2 * scale_x))
    y1 = int(np.floor(lower_y1 * scale_y))
    y2 = int(np.ceil(clipped_y2 * scale_y))

    x1 = max(0, min(depth_width - 1, x1))
    y1 = max(0, min(depth_height - 1, y1))
    x2 = max(x1 + 1, min(depth_width, x2))
    y2 = max(y1 + 1, min(depth_height, y2))

    crop = depth[y1:y2, x1:x2]
    valid = crop[np.isfinite(crop) & (crop > 0)]

    if valid.size == 0:
        return 0.0

    return float(np.median(valid))
