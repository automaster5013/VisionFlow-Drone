from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from app.inference.phase3_association import TrackedPersonBox


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
    track_id: int | None = None

    @property
    def assigned(self) -> bool:
        return self.track_id is not None

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
    def person_instance_count(self) -> int:
        return sum(
            instance.class_name.strip().lower() == "person"
            for instance in self.instances
        )

    @property
    def assigned_count(self) -> int:
        return sum(
            instance.assigned
            for instance in self.instances
            if instance.class_name.strip().lower() == "person"
        )

    @property
    def unassigned_count(self) -> int:
        return self.person_instance_count - self.assigned_count

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
    tracks: Iterable[TrackedPersonBox] = (),
    min_track_iou: float = 0.10,
) -> Phase3SegmentationFrameResult:
    if frame_index <= 0:
        raise ValueError("frame_index must be positive.")
    if not 0.0 <= min_track_iou <= 1.0:
        raise ValueError(
            "min_track_iou must be in the range [0, 1]."
        )

    normalized_tracks = tuple(tracks)
    _validate_tracks(normalized_tracks)

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

    assignments = _associate_person_instances(
        instances=tuple(instances),
        tracks=normalized_tracks,
        min_track_iou=min_track_iou,
    )

    return Phase3SegmentationFrameResult(
        frame_index=frame_index,
        instances=tuple(
            replace(
                instance,
                track_id=assignments.get(instance_index),
            )
            for instance_index, instance in enumerate(instances)
        ),
    )


def _validate_tracks(
    tracks: tuple[TrackedPersonBox, ...],
) -> None:
    seen_track_ids: set[int] = set()

    for track in tracks:
        track.validate()
        if track.track_id in seen_track_ids:
            raise ValueError(f"Duplicate track_id: {track.track_id}")
        seen_track_ids.add(track.track_id)


def _associate_person_instances(
    *,
    instances: tuple[SegmentationInstance, ...],
    tracks: tuple[TrackedPersonBox, ...],
    min_track_iou: float,
) -> dict[int, int]:
    candidates: list[tuple[float, int, int, int]] = []

    for instance_index, instance in enumerate(instances):
        if instance.class_name.strip().lower() != "person":
            continue

        instance_box = (
            instance.x1,
            instance.y1,
            instance.x2,
            instance.y2,
        )
        for track_index, track in enumerate(tracks):
            iou = _box_iou(
                instance_box,
                (track.x1, track.y1, track.x2, track.y2),
            )
            if iou >= min_track_iou:
                candidates.append(
                    (
                        iou,
                        instance_index,
                        track_index,
                        track.track_id,
                    )
                )

    candidates.sort(
        key=lambda item: (-item[0], item[1], item[3])
    )
    assigned_instances: set[int] = set()
    assigned_tracks: set[int] = set()
    assignments: dict[int, int] = {}

    for _iou, instance_index, track_index, track_id in candidates:
        if (
            instance_index in assigned_instances
            or track_index in assigned_tracks
        ):
            continue

        assignments[instance_index] = track_id
        assigned_instances.add(instance_index)
        assigned_tracks.add(track_index)

    return assignments


def _box_iou(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    first_x1, first_y1, first_x2, first_y2 = first
    second_x1, second_y1, second_x2, second_y2 = second

    inter_x1 = max(first_x1, second_x1)
    inter_y1 = max(first_y1, second_y1)
    inter_x2 = min(first_x2, second_x2)
    inter_y2 = min(first_y2, second_y2)
    intersection = (
        max(0.0, inter_x2 - inter_x1)
        * max(0.0, inter_y2 - inter_y1)
    )
    first_area = max(0.0, first_x2 - first_x1) * max(
        0.0,
        first_y2 - first_y1,
    )
    second_area = max(0.0, second_x2 - second_x1) * max(
        0.0,
        second_y2 - second_y1,
    )
    union = first_area + second_area - intersection

    if union <= 0.0:
        return 0.0

    return intersection / union
