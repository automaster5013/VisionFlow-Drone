from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.domain import Detection
from app.inference.phase3_association import (
    PpeAssociationResult,
    TrackedPersonBox,
    associate_ppe_detections,
)
from app.inference.phase3_evidence import (
    TrackPpeEvidenceAccumulator,
    TrackPpeSnapshot,
)
from app.inference.phase3_policy import (
    PpeComplianceState,
    PpePolicyConfig,
)


@dataclass(frozen=True, slots=True)
class PpeTrackAssessment:
    track: TrackedPersonBox
    snapshot: TrackPpeSnapshot

    @property
    def track_id(self) -> int:
        return self.track.track_id

    @property
    def state(self) -> PpeComplianceState:
        return self.snapshot.decision.state


@dataclass(frozen=True, slots=True)
class PpeFrameResult:
    frame_index: int
    assessments: tuple[PpeTrackAssessment, ...]
    unassigned_count: int
    ignored_count: int

    def for_track(self, track_id: int) -> PpeTrackAssessment:
        for assessment in self.assessments:
            if assessment.track_id == track_id:
                return assessment

        raise KeyError(f"Unknown track_id: {track_id}")

    def confirmed_no_helmet(self) -> tuple[PpeTrackAssessment, ...]:
        return tuple(
            assessment
            for assessment in self.assessments
            if assessment.state is PpeComplianceState.CONFIRMED_NO_HELMET
        )


class Phase3PpeProcessor:
    def __init__(
        self,
        *,
        source_fps: float,
        sample_stride_frames: int,
        policy: PpePolicyConfig | None = None,
    ) -> None:
        self._accumulator = TrackPpeEvidenceAccumulator(
            source_fps=source_fps,
            sample_stride_frames=sample_stride_frames,
            policy=policy,
        )
        self._last_frame_index = 0

    @property
    def source_fps(self) -> float:
        return self._accumulator.source_fps

    @property
    def sample_stride_frames(self) -> int:
        return self._accumulator.sample_stride_frames

    @property
    def last_frame_index(self) -> int:
        return self._last_frame_index

    def process_sample(
        self,
        *,
        frame_index: int,
        tracks: Iterable[TrackedPersonBox],
        detections: Iterable[Detection],
    ) -> PpeFrameResult:
        if frame_index <= 0:
            raise ValueError("frame_index must be positive.")

        if self._last_frame_index and frame_index <= self._last_frame_index:
            raise ValueError(
                "frame_index must increase monotonically across PPE samples."
            )

        track_list = tuple(tracks)
        detection_list = tuple(detections)

        association = associate_ppe_detections(
            tracks=track_list,
            detections=detection_list,
        )
        assessments = self._build_assessments(
            frame_index=frame_index,
            tracks=track_list,
            association=association,
        )

        self._last_frame_index = frame_index

        return PpeFrameResult(
            frame_index=frame_index,
            assessments=assessments,
            unassigned_count=association.unassigned_count,
            ignored_count=association.ignored_count,
        )

    def remove_track(self, track_id: int) -> bool:
        return self._accumulator.remove(track_id)

    def clear(self) -> None:
        self._accumulator.clear()
        self._last_frame_index = 0

    def _build_assessments(
        self,
        *,
        frame_index: int,
        tracks: tuple[TrackedPersonBox, ...],
        association: PpeAssociationResult,
    ) -> tuple[PpeTrackAssessment, ...]:
        assessments: list[PpeTrackAssessment] = []

        for track in tracks:
            match = association.for_track(track.track_id)
            snapshot = self._accumulator.observe(
                track_id=track.track_id,
                frame_index=frame_index,
                has_helmet=match.has_helmet,
                has_head=match.has_head,
                has_vest=match.has_vest,
            )
            assessments.append(
                PpeTrackAssessment(
                    track=track,
                    snapshot=snapshot,
                )
            )

        return tuple(assessments)
