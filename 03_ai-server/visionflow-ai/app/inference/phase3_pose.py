from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.inference.phase3_association import TrackedPersonBox


@dataclass(frozen=True, slots=True)
class PoseKeypoint:
    index: int
    x: float
    y: float
    confidence: float | None


@dataclass(frozen=True, slots=True)
class TrackedPoseObservation:
    track_id: int | None
    x1: float
    y1: float
    x2: float
    y2: float
    keypoints: tuple[PoseKeypoint, ...]

    @property
    def assigned(self) -> bool:
        return self.track_id is not None


@dataclass(frozen=True, slots=True)
class Phase3PoseFrameResult:
    frame_index: int
    observations: tuple[TrackedPoseObservation, ...]

    @property
    def assigned_count(self) -> int:
        return sum(1 for item in self.observations if item.assigned)

    @property
    def unassigned_count(self) -> int:
        return len(self.observations) - self.assigned_count


def build_pose_frame_result(
    *,
    result: Any,
    tracks: Iterable[TrackedPersonBox],
    frame_index: int,
    min_track_iou: float = 0.10,
) -> Phase3PoseFrameResult:
    if frame_index <= 0:
        raise ValueError("frame_index must be positive.")
    if not 0.0 <= min_track_iou <= 1.0:
        raise ValueError("min_track_iou must be in the range [0, 1].")

    boxes = getattr(result, "boxes", None)
    keypoints = getattr(result, "keypoints", None)

    if boxes is None or keypoints is None:
        return Phase3PoseFrameResult(
            frame_index=frame_index,
            observations=(),
        )

    coordinates = _to_list(getattr(boxes, "xyxy", None))
    keypoint_xy = _to_list(getattr(keypoints, "xy", None))
    keypoint_conf = _optional_to_list(getattr(keypoints, "conf", None))

    if not coordinates or not keypoint_xy:
        return Phase3PoseFrameResult(
            frame_index=frame_index,
            observations=(),
        )

    if len(coordinates) != len(keypoint_xy):
        raise ValueError(
            "Pose boxes and keypoint groups must have the same length."
        )

    if keypoint_conf is not None and len(keypoint_conf) != len(keypoint_xy):
        raise ValueError(
            "Pose keypoint confidence groups must match keypoint groups."
        )

    normalized_tracks = tuple(tracks)
    assignments = _associate_pose_boxes(
        pose_boxes=coordinates,
        tracks=normalized_tracks,
        min_track_iou=min_track_iou,
    )

    observations: list[TrackedPoseObservation] = []

    for pose_index, xyxy in enumerate(coordinates):
        if len(xyxy) < 4:
            raise ValueError("Pose boxes must contain four coordinates.")

        points = keypoint_xy[pose_index]
        confidences = (
            keypoint_conf[pose_index]
            if keypoint_conf is not None
            else None
        )

        if confidences is not None and len(confidences) != len(points):
            raise ValueError(
                "Each pose keypoint confidence list must match its points."
            )

        converted_points = tuple(
            PoseKeypoint(
                index=point_index,
                x=float(point[0]),
                y=float(point[1]),
                confidence=(
                    float(confidences[point_index])
                    if confidences is not None
                    else None
                ),
            )
            for point_index, point in enumerate(points)
        )

        observations.append(
            TrackedPoseObservation(
                track_id=assignments.get(pose_index),
                x1=float(xyxy[0]),
                y1=float(xyxy[1]),
                x2=float(xyxy[2]),
                y2=float(xyxy[3]),
                keypoints=converted_points,
            )
        )

    return Phase3PoseFrameResult(
        frame_index=frame_index,
        observations=tuple(observations),
    )


def _associate_pose_boxes(
    *,
    pose_boxes: list[list[float]],
    tracks: tuple[TrackedPersonBox, ...],
    min_track_iou: float,
) -> dict[int, int]:
    candidates: list[tuple[float, int, int]] = []

    for pose_index, pose_box in enumerate(pose_boxes):
        if len(pose_box) < 4:
            continue

        for track_index, track in enumerate(tracks):
            iou = _box_iou(
                (
                    float(pose_box[0]),
                    float(pose_box[1]),
                    float(pose_box[2]),
                    float(pose_box[3]),
                ),
                (track.x1, track.y1, track.x2, track.y2),
            )

            if iou >= min_track_iou:
                candidates.append((iou, pose_index, track_index))

    candidates.sort(reverse=True)

    assigned_pose: set[int] = set()
    assigned_tracks: set[int] = set()
    assignments: dict[int, int] = {}

    for _iou, pose_index, track_index in candidates:
        if pose_index in assigned_pose or track_index in assigned_tracks:
            continue

        assignments[pose_index] = tracks[track_index].track_id
        assigned_pose.add(pose_index)
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

    inter_width = max(0.0, inter_x2 - inter_x1)
    inter_height = max(0.0, inter_y2 - inter_y1)
    intersection = inter_width * inter_height

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


def _to_list(value: Any) -> list:
    if value is None:
        return []

    current = value

    detach = getattr(current, "detach", None)
    if callable(detach):
        current = detach()

    cpu = getattr(current, "cpu", None)
    if callable(cpu):
        current = cpu()

    tolist = getattr(current, "tolist", None)
    if callable(tolist):
        return tolist()

    return list(current)


def _optional_to_list(value: Any) -> list | None:
    if value is None:
        return None

    return _to_list(value)
