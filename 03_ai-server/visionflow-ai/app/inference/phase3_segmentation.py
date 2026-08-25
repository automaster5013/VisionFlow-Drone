from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SegmentationPoint:
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class SegmentationInstance:
    class_id: int
    class_name: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float
    polygon: tuple[SegmentationPoint, ...]

    @property
    def mask_area_pixels(self) -> float:
        if len(self.polygon) < 3:
            return 0.0

        twice_area = sum(
            point.x * next_point.y - next_point.x * point.y
            for point, next_point in zip(
                self.polygon,
                self.polygon[1:] + self.polygon[:1],
                strict=True,
            )
        )
        return abs(twice_area) / 2.0


@dataclass(frozen=True, slots=True)
class Phase3SegmentationFrameResult:
    frame_index: int
    instances: tuple[SegmentationInstance, ...]

    @property
    def instance_count(self) -> int:
        return len(self.instances)

    @property
    def total_mask_area_pixels(self) -> float:
        return sum(
            instance.mask_area_pixels
            for instance in self.instances
        )

    def count_for_class(self, class_name: str) -> int:
        return sum(
            instance.class_name == class_name
            for instance in self.instances
        )


def _to_list(value: Any) -> list[Any]:
    if value is None:
        return []

    if hasattr(value, "detach"):
        value = value.detach()

    if hasattr(value, "cpu"):
        value = value.cpu()

    if hasattr(value, "tolist"):
        value = value.tolist()

    return list(value)


def _class_name(names: Any, class_id: int) -> str:
    if isinstance(names, Mapping):
        return str(names.get(class_id, class_id))

    if (
        isinstance(names, Sequence)
        and not isinstance(names, (str, bytes))
        and 0 <= class_id < len(names)
    ):
        return str(names[class_id])

    return str(class_id)


def build_segmentation_frame_result(
    *,
    result: Any,
    frame_index: int,
) -> Phase3SegmentationFrameResult:
    if frame_index <= 0:
        raise ValueError("frame_index must be positive.")

    boxes = getattr(result, "boxes", None)
    masks = getattr(result, "masks", None)

    if boxes is None or masks is None:
        return Phase3SegmentationFrameResult(
            frame_index=frame_index,
            instances=(),
        )

    coordinates = _to_list(getattr(boxes, "xyxy", None))
    confidences = _to_list(getattr(boxes, "conf", None))
    class_ids = _to_list(getattr(boxes, "cls", None))
    polygons = _to_list(getattr(masks, "xy", None))

    lengths = {
        len(coordinates),
        len(confidences),
        len(class_ids),
        len(polygons),
    }
    if len(lengths) != 1:
        raise ValueError(
            "Segmentation boxes, confidence, class, and mask "
            "collections must have the same length."
        )

    names = getattr(result, "names", None)
    instances: list[SegmentationInstance] = []

    for box, confidence, raw_class_id, raw_polygon in zip(
        coordinates,
        confidences,
        class_ids,
        polygons,
        strict=True,
    ):
        if len(box) != 4:
            raise ValueError(
                "Each segmentation box must contain four coordinates."
            )

        points: list[SegmentationPoint] = []
        for point in raw_polygon:
            if len(point) != 2:
                raise ValueError(
                    "Each segmentation polygon point must contain x and y."
                )
            points.append(
                SegmentationPoint(
                    x=float(point[0]),
                    y=float(point[1]),
                )
            )

        class_id = int(raw_class_id)
        instances.append(
            SegmentationInstance(
                class_id=class_id,
                class_name=_class_name(names, class_id),
                confidence=float(confidence),
                x1=float(box[0]),
                y1=float(box[1]),
                x2=float(box[2]),
                y2=float(box[3]),
                polygon=tuple(points),
            )
        )

    return Phase3SegmentationFrameResult(
        frame_index=frame_index,
        instances=tuple(instances),
    )
