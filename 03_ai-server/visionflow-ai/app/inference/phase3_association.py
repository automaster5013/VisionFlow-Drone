from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable

from app.domain import Detection


_SUPPORTED_PPE_CLASSES = frozenset({"helmet", "head", "vest"})


@dataclass(frozen=True, slots=True)
class TrackedPersonBox:
    track_id: int
    x1: float
    y1: float
    x2: float
    y2: float

    def validate(self) -> None:
        if self.track_id <= 0:
            raise ValueError("track_id must be positive.")

        coordinates = (self.x1, self.y1, self.x2, self.y2)
        if not all(isfinite(value) for value in coordinates):
            raise ValueError("Tracked person coordinates must be finite.")

        if self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError("Tracked person bounding box must have positive area.")

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1


@dataclass(frozen=True, slots=True)
class TrackPpeMatch:
    track_id: int
    helmet_count: int
    head_count: int
    vest_count: int

    @property
    def has_helmet(self) -> bool:
        return self.helmet_count > 0

    @property
    def has_head(self) -> bool:
        return self.head_count > 0

    @property
    def has_vest(self) -> bool:
        return self.vest_count > 0


@dataclass(frozen=True, slots=True)
class PpeAssociationResult:
    matches: tuple[TrackPpeMatch, ...]
    unassigned_count: int
    ignored_count: int

    def for_track(self, track_id: int) -> TrackPpeMatch:
        for match in self.matches:
            if match.track_id == track_id:
                return match

        raise KeyError(f"Unknown track_id: {track_id}")


@dataclass(slots=True)
class _MutableMatch:
    helmet_count: int = 0
    head_count: int = 0
    vest_count: int = 0


def associate_ppe_detections(
    *,
    tracks: Iterable[TrackedPersonBox],
    detections: Iterable[Detection],
) -> PpeAssociationResult:
    track_list = tuple(tracks)
    _validate_tracks(track_list)

    mutable_matches = {
        track.track_id: _MutableMatch()
        for track in track_list
    }

    unassigned_count = 0
    ignored_count = 0

    for detection in detections:
        class_name = detection.class_name.strip().lower()

        if class_name not in _SUPPORTED_PPE_CLASSES:
            ignored_count += 1
            continue

        _validate_detection(detection)

        track_id = _best_track_for_detection(
            detection=detection,
            class_name=class_name,
            tracks=track_list,
        )

        if track_id is None:
            unassigned_count += 1
            continue

        match = mutable_matches[track_id]
        if class_name == "helmet":
            match.helmet_count += 1
        elif class_name == "head":
            match.head_count += 1
        else:
            match.vest_count += 1

    return PpeAssociationResult(
        matches=tuple(
            TrackPpeMatch(
                track_id=track.track_id,
                helmet_count=mutable_matches[track.track_id].helmet_count,
                head_count=mutable_matches[track.track_id].head_count,
                vest_count=mutable_matches[track.track_id].vest_count,
            )
            for track in track_list
        ),
        unassigned_count=unassigned_count,
        ignored_count=ignored_count,
    )


def _validate_tracks(tracks: tuple[TrackedPersonBox, ...]) -> None:
    seen_track_ids: set[int] = set()

    for track in tracks:
        track.validate()

        if track.track_id in seen_track_ids:
            raise ValueError(f"Duplicate track_id: {track.track_id}")

        seen_track_ids.add(track.track_id)


def _validate_detection(detection: Detection) -> None:
    coordinates = (
        detection.x1,
        detection.y1,
        detection.x2,
        detection.y2,
    )

    if not all(isfinite(value) for value in coordinates):
        raise ValueError("PPE detection coordinates must be finite.")

    if detection.x2 <= detection.x1 or detection.y2 <= detection.y1:
        raise ValueError("PPE detection bounding box must have positive area.")


def _best_track_for_detection(
    *,
    detection: Detection,
    class_name: str,
    tracks: tuple[TrackedPersonBox, ...],
) -> int | None:
    center_x = (detection.x1 + detection.x2) / 2.0
    center_y = (detection.y1 + detection.y2) / 2.0

    candidates: list[tuple[float, int]] = []

    for track in tracks:
        if class_name in {"helmet", "head"}:
            inside = _inside_head_region(center_x, center_y, track)
            anchor_y_ratio = 0.18
        else:
            inside = _inside_torso_region(center_x, center_y, track)
            anchor_y_ratio = 0.42

        if not inside:
            continue

        anchor_x = track.x1 + 0.50 * track.width
        anchor_y = track.y1 + anchor_y_ratio * track.height

        dx = (center_x - anchor_x) / track.width
        dy = (center_y - anchor_y) / track.height
        score = dx * dx + dy * dy

        candidates.append((score, track.track_id))

    if not candidates:
        return None

    _, track_id = min(candidates, key=lambda item: (item[0], item[1]))
    return track_id


def _inside_head_region(
    center_x: float,
    center_y: float,
    track: TrackedPersonBox,
) -> bool:
    return (
        track.x1 - 0.10 * track.width
        <= center_x
        <= track.x2 + 0.10 * track.width
        and track.y1 - 0.08 * track.height
        <= center_y
        <= track.y1 + 0.55 * track.height
    )


def _inside_torso_region(
    center_x: float,
    center_y: float,
    track: TrackedPersonBox,
) -> bool:
    return (
        track.x1 - 0.10 * track.width
        <= center_x
        <= track.x2 + 0.10 * track.width
        and track.y1 + 0.10 * track.height
        <= center_y
        <= track.y1 + 0.78 * track.height
    )
