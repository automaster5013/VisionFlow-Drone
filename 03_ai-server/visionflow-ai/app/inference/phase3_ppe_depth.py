from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

import numpy as np
from numpy.typing import NDArray

from app.domain import Detection
from app.inference.phase3_association import TrackedPersonBox
from app.inference.phase3_depth_enrichment import DepthEnrichmentRequest
from app.inference.phase3_policy import PpeComplianceState
from app.inference.phase3_processor import (
    Phase3PpeProcessor,
    PpeFrameResult,
)


class DepthEnrichmentSink(Protocol):
    def submit(self, request: DepthEnrichmentRequest) -> bool: ...

    def release_event(self, event_key: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class DepthTriggerAttempt:
    track_id: int
    event_key: str
    accepted: bool


@dataclass(frozen=True, slots=True)
class PpeDepthFrameResult:
    ppe: PpeFrameResult
    depth_triggers: tuple[DepthTriggerAttempt, ...]
    active_depth_tracks: tuple[int, ...]

    @property
    def accepted_depth_triggers(self) -> int:
        return sum(int(trigger.accepted) for trigger in self.depth_triggers)

    @property
    def rejected_depth_triggers(self) -> int:
        return sum(int(not trigger.accepted) for trigger in self.depth_triggers)


class Phase3PpeDepthCoordinator:
    def __init__(
        self,
        *,
        processor: Phase3PpeProcessor,
        depth_enricher: DepthEnrichmentSink,
        event_namespace: str,
    ) -> None:
        normalized_namespace = event_namespace.strip()
        if not normalized_namespace:
            raise ValueError("event_namespace must not be blank.")

        self._processor = processor
        self._depth_enricher = depth_enricher
        self._event_namespace = normalized_namespace
        self._active_depth_tracks: set[int] = set()

    @property
    def event_namespace(self) -> str:
        return self._event_namespace

    def process_sample(
        self,
        *,
        frame_index: int,
        event_time_sec: float,
        frame: NDArray[np.uint8],
        tracks: Iterable[TrackedPersonBox],
        detections: Iterable[Detection],
    ) -> PpeDepthFrameResult:
        if event_time_sec < 0:
            raise ValueError("event_time_sec must be non-negative.")
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("frame must be an HxWx3 image.")
        if frame.size == 0:
            raise ValueError("frame must not be empty.")

        ppe_result = self._processor.process_sample(
            frame_index=frame_index,
            tracks=tracks,
            detections=detections,
        )

        triggers: list[DepthTriggerAttempt] = []

        for assessment in ppe_result.assessments:
            track_id = assessment.track_id
            event_key = self._event_key(track_id)

            if assessment.state is PpeComplianceState.CONFIRMED_NO_HELMET:
                if track_id in self._active_depth_tracks:
                    continue

                accepted = self._depth_enricher.submit(
                    DepthEnrichmentRequest(
                        event_key=event_key,
                        track_id=track_id,
                        frame_index=frame_index,
                        event_time_sec=event_time_sec,
                        frame=frame,
                        person_box=assessment.track,
                    )
                )
                triggers.append(
                    DepthTriggerAttempt(
                        track_id=track_id,
                        event_key=event_key,
                        accepted=accepted,
                    )
                )

                if accepted:
                    self._active_depth_tracks.add(track_id)
                continue

            if track_id in self._active_depth_tracks:
                self._depth_enricher.release_event(event_key)
                self._active_depth_tracks.remove(track_id)

        return PpeDepthFrameResult(
            ppe=ppe_result,
            depth_triggers=tuple(triggers),
            active_depth_tracks=tuple(sorted(self._active_depth_tracks)),
        )

    def remove_track(self, track_id: int) -> bool:
        if track_id <= 0:
            raise ValueError("track_id must be positive.")

        removed = self._processor.remove_track(track_id)

        if track_id in self._active_depth_tracks:
            self._depth_enricher.release_event(self._event_key(track_id))
            self._active_depth_tracks.remove(track_id)

        return removed

    def clear(self) -> None:
        for track_id in tuple(self._active_depth_tracks):
            self._depth_enricher.release_event(self._event_key(track_id))

        self._active_depth_tracks.clear()
        self._processor.clear()

    def _event_key(self, track_id: int) -> str:
        return f"{self._event_namespace}:NO_HELMET:{track_id}"
