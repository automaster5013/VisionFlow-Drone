from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Protocol

import numpy as np
from numpy.typing import NDArray

from app.inference.phase3_association import TrackedPersonBox


class DepthBucket(StrEnum):
    UNKNOWN = "UNKNOWN"
    NEAR = "NEAR"
    MID = "MID"
    FAR = "FAR"


@dataclass(frozen=True, slots=True)
class DepthMeasurement:
    estimated_depth_m: float
    scene_q33_m: float
    scene_q66_m: float
    bucket: DepthBucket


@dataclass(frozen=True, slots=True)
class DepthEnrichmentRequest:
    event_key: str
    track_id: int
    frame_index: int
    event_time_sec: float
    frame: NDArray[np.uint8]
    person_box: TrackedPersonBox

    def validate(self) -> None:
        if not self.event_key.strip():
            raise ValueError("event_key must not be blank.")
        if self.track_id <= 0:
            raise ValueError("track_id must be positive.")
        if self.person_box.track_id != self.track_id:
            raise ValueError("person_box.track_id must match track_id.")
        if self.frame_index <= 0:
            raise ValueError("frame_index must be positive.")
        if self.event_time_sec < 0:
            raise ValueError("event_time_sec must be non-negative.")
        if self.frame.ndim != 3 or self.frame.shape[2] != 3:
            raise ValueError("frame must be an HxWx3 image.")
        if self.frame.size == 0:
            raise ValueError("frame must not be empty.")

        self.person_box.validate()


@dataclass(frozen=True, slots=True)
class DepthEnrichmentResult:
    event_key: str
    track_id: int
    frame_index: int
    event_time_sec: float
    person_box: TrackedPersonBox
    measurement: DepthMeasurement
    enrichment_latency_ms: float


@dataclass(frozen=True, slots=True)
class DepthEnricherStats:
    queued: int
    completed: int
    dropped: int
    duplicates: int
    failed: int
    queue_size: int
    queue_capacity: int
    running: bool


@dataclass(frozen=True, slots=True)
class _QueuedDepthRequest:
    request: DepthEnrichmentRequest
    queued_at: float


class DepthEstimator(Protocol):
    def estimate(
        self,
        *,
        frame: NDArray[np.uint8],
        person_box: TrackedPersonBox,
    ) -> DepthMeasurement: ...


DepthResultCallback = Callable[[DepthEnrichmentResult], None]


class AsyncDepthEnricher:
    def __init__(
        self,
        *,
        estimator: DepthEstimator,
        queue_capacity: int,
        on_result: DepthResultCallback | None = None,
    ) -> None:
        if queue_capacity <= 0:
            raise ValueError("queue_capacity must be positive.")

        self._estimator = estimator
        self._queue_capacity = queue_capacity
        self._on_result = on_result
        self._queue: queue.Queue[_QueuedDepthRequest | None] = queue.Queue(
            maxsize=queue_capacity
        )
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._seen_event_keys: set[str] = set()

        self._queued = 0
        self._completed = 0
        self._dropped = 0
        self._duplicates = 0
        self._failed = 0
        self._running = False

    def start(self) -> None:
        with self._lock:
            if self._running:
                return

            self._running = True
            self._thread = threading.Thread(
                target=self._run,
                name="visionflow-phase3-depth-enricher",
                daemon=True,
            )
            self._thread.start()

    def submit(self, request: DepthEnrichmentRequest) -> bool:
        request.validate()

        with self._lock:
            if not self._running:
                raise RuntimeError("AsyncDepthEnricher is not running.")

            if request.event_key in self._seen_event_keys:
                self._duplicates += 1
                return False

            queued_request = _QueuedDepthRequest(
                request=DepthEnrichmentRequest(
                    event_key=request.event_key,
                    track_id=request.track_id,
                    frame_index=request.frame_index,
                    event_time_sec=request.event_time_sec,
                    frame=request.frame.copy(),
                    person_box=request.person_box,
                ),
                queued_at=time.perf_counter(),
            )

            try:
                self._queue.put_nowait(queued_request)
            except queue.Full:
                self._dropped += 1
                return False

            self._seen_event_keys.add(request.event_key)
            self._queued += 1
            return True

    def release_event(self, event_key: str) -> bool:
        normalized = event_key.strip()
        if not normalized:
            raise ValueError("event_key must not be blank.")

        with self._lock:
            if normalized not in self._seen_event_keys:
                return False

            self._seen_event_keys.remove(normalized)
            return True

    def clear_seen_events(self) -> None:
        with self._lock:
            self._seen_event_keys.clear()

    def close(self) -> None:
        with self._lock:
            if not self._running:
                return

        self._queue.join()
        self._queue.put(None)

        thread = self._thread
        if thread is not None:
            thread.join()

        with self._lock:
            self._thread = None
            self._running = False

    def stats(self) -> DepthEnricherStats:
        with self._lock:
            return DepthEnricherStats(
                queued=self._queued,
                completed=self._completed,
                dropped=self._dropped,
                duplicates=self._duplicates,
                failed=self._failed,
                queue_size=self._queue.qsize(),
                queue_capacity=self._queue_capacity,
                running=self._running,
            )

    def _run(self) -> None:
        while True:
            queued_request = self._queue.get()

            try:
                if queued_request is None:
                    return

                request = queued_request.request

                try:
                    measurement = self._estimator.estimate(
                        frame=request.frame,
                        person_box=request.person_box,
                    )
                    result = DepthEnrichmentResult(
                        event_key=request.event_key,
                        track_id=request.track_id,
                        frame_index=request.frame_index,
                        event_time_sec=request.event_time_sec,
                        person_box=request.person_box,
                        measurement=measurement,
                        enrichment_latency_ms=(
                            time.perf_counter() - queued_request.queued_at
                        )
                        * 1_000.0,
                    )

                    if self._on_result is not None:
                        self._on_result(result)

                    with self._lock:
                        self._completed += 1
                except Exception as error:
                    with self._lock:
                        self._failed += 1

                    print(
                        "Phase 3 depth enrichment failed: "
                        f"eventKey={request.event_key}, "
                        f"trackId={request.track_id}, "
                        f"error={error}",
                        flush=True,
                    )
            finally:
                self._queue.task_done()


def classify_depth_bucket(
    *,
    estimated_depth_m: float,
    scene_q33_m: float,
    scene_q66_m: float,
) -> DepthBucket:
    if (
        estimated_depth_m <= 0
        or scene_q33_m <= 0
        or scene_q66_m <= 0
        or scene_q33_m > scene_q66_m
    ):
        return DepthBucket.UNKNOWN

    if estimated_depth_m <= scene_q33_m:
        return DepthBucket.NEAR

    if estimated_depth_m <= scene_q66_m:
        return DepthBucket.MID

    return DepthBucket.FAR
