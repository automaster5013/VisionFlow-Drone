from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Iterable, Protocol

import numpy as np
from numpy.typing import NDArray

from app.config import Settings
from app.domain import Detection
from app.inference.phase3_association import TrackedPersonBox
from app.inference.phase3_depth_enrichment import (
    AsyncDepthEnricher,
    DepthEnrichmentResult,
    DepthEstimator,
)
from app.inference.phase3_ppe_depth import (
    PpeDepthFrameResult,
    Phase3PpeDepthCoordinator,
)
from app.inference.phase3_processor import Phase3PpeProcessor
from app.inference.phase3_yolo_depth import YoloDepthEstimator


class ManagedDepthEnricher(Protocol):
    def start(self) -> None: ...

    def submit(self, request) -> bool: ...

    def release_event(self, event_key: str) -> bool: ...

    def close(self) -> None: ...


DepthEstimatorFactory = Callable[..., DepthEstimator]
DepthEnricherFactory = Callable[..., ManagedDepthEnricher]
DepthResultCallback = Callable[[DepthEnrichmentResult], None]


@dataclass(slots=True)
class Phase3Runtime:
    processor: Phase3PpeProcessor
    sample_stride_frames: int
    effective_ppe_fps: float
    coordinator: Phase3PpeDepthCoordinator | None = None
    depth_enricher: ManagedDepthEnricher | None = None
    _started: bool = False

    @property
    def depth_enabled(self) -> bool:
        return self.coordinator is not None and self.depth_enricher is not None

    @property
    def started(self) -> bool:
        return self._started

    def start(self) -> None:
        if self._started:
            return

        if self.depth_enricher is not None:
            self.depth_enricher.start()

        self._started = True

    def process_sample(
        self,
        *,
        frame_index: int,
        event_time_sec: float,
        frame: NDArray[np.uint8],
        tracks: Iterable[TrackedPersonBox],
        detections: Iterable[Detection],
    ) -> PpeDepthFrameResult:
        if not self._started:
            raise RuntimeError("Phase3Runtime is not started.")

        if self.coordinator is not None:
            return self.coordinator.process_sample(
                frame_index=frame_index,
                event_time_sec=event_time_sec,
                frame=frame,
                tracks=tracks,
                detections=detections,
            )

        ppe = self.processor.process_sample(
            frame_index=frame_index,
            tracks=tracks,
            detections=detections,
        )
        return PpeDepthFrameResult(
            ppe=ppe,
            depth_triggers=(),
            active_depth_tracks=(),
        )

    def remove_track(self, track_id: int) -> bool:
        if self.coordinator is not None:
            return self.coordinator.remove_track(track_id)

        return self.processor.remove_track(track_id)

    def close(self) -> None:
        if not self._started:
            return

        if self.depth_enricher is not None:
            self.depth_enricher.close()

        if self.coordinator is not None:
            self.coordinator.clear()
        else:
            self.processor.clear()

        self._started = False


def compute_sample_stride(
    *,
    source_fps: float,
    target_fps: float,
) -> int:
    if source_fps <= 0:
        raise ValueError("source_fps must be positive.")
    if target_fps <= 0:
        raise ValueError("target_fps must be positive.")

    return max(1, int(math.ceil(source_fps / target_fps)))


def create_phase3_runtime(
    *,
    settings: Settings,
    source_fps: float,
    on_depth_result: DepthResultCallback | None = None,
    depth_estimator_factory: DepthEstimatorFactory | None = None,
    depth_enricher_factory: DepthEnricherFactory | None = None,
) -> Phase3Runtime | None:
    if not settings.phase3_enabled:
        return None

    sample_stride_frames = compute_sample_stride(
        source_fps=source_fps,
        target_fps=settings.phase3_ppe_target_fps,
    )
    effective_ppe_fps = source_fps / sample_stride_frames

    processor = Phase3PpeProcessor(
        source_fps=source_fps,
        sample_stride_frames=sample_stride_frames,
    )

    if not settings.phase3_depth_enabled:
        return Phase3Runtime(
            processor=processor,
            sample_stride_frames=sample_stride_frames,
            effective_ppe_fps=effective_ppe_fps,
        )

    estimator_factory = (
        depth_estimator_factory
        if depth_estimator_factory is not None
        else YoloDepthEstimator
    )
    enricher_factory = (
        depth_enricher_factory
        if depth_enricher_factory is not None
        else AsyncDepthEnricher
    )

    depth_estimator = estimator_factory(
        model_path=settings.phase3_depth_model_path,
        image_size=settings.phase3_depth_image_size,
        device=settings.device,
    )
    depth_enricher = enricher_factory(
        estimator=depth_estimator,
        queue_capacity=settings.phase3_depth_queue_capacity,
        on_result=on_depth_result,
    )
    coordinator = Phase3PpeDepthCoordinator(
        processor=processor,
        depth_enricher=depth_enricher,
        event_namespace=(
            f"{settings.source_id}:{settings.session_id}"
        ),
    )

    return Phase3Runtime(
        processor=processor,
        sample_stride_frames=sample_stride_frames,
        effective_ppe_fps=effective_ppe_fps,
        coordinator=coordinator,
        depth_enricher=depth_enricher,
    )
