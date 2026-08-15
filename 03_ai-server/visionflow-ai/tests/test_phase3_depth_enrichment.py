from __future__ import annotations

import threading

import numpy as np
import pytest

from app.inference.phase3_association import TrackedPersonBox
from app.inference.phase3_depth_enrichment import (
    AsyncDepthEnricher,
    DepthBucket,
    DepthEnrichmentRequest,
    DepthMeasurement,
    classify_depth_bucket,
)


class _FixedEstimator:
    def __init__(self) -> None:
        self.calls = 0

    def estimate(self, *, frame, person_box) -> DepthMeasurement:
        self.calls += 1
        return DepthMeasurement(
            estimated_depth_m=1.8,
            scene_q33_m=1.2,
            scene_q66_m=2.4,
            bucket=DepthBucket.MID,
        )


class _BlockingEstimator:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def estimate(self, *, frame, person_box) -> DepthMeasurement:
        self.started.set()
        assert self.release.wait(timeout=2.0)
        return DepthMeasurement(
            estimated_depth_m=1.0,
            scene_q33_m=1.0,
            scene_q66_m=2.0,
            bucket=DepthBucket.NEAR,
        )


class _FailOnceEstimator:
    def __init__(self) -> None:
        self.calls = 0

    def estimate(self, *, frame, person_box) -> DepthMeasurement:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("synthetic depth failure")

        return DepthMeasurement(
            estimated_depth_m=3.0,
            scene_q33_m=1.0,
            scene_q66_m=2.0,
            bucket=DepthBucket.FAR,
        )


def _request(event_key: str, track_id: int = 1) -> DepthEnrichmentRequest:
    return DepthEnrichmentRequest(
        event_key=event_key,
        track_id=track_id,
        frame_index=28,
        event_time_sec=0.933,
        frame=np.zeros((32, 48, 3), dtype=np.uint8),
        person_box=TrackedPersonBox(
            track_id=track_id,
            x1=4,
            y1=2,
            x2=30,
            y2=30,
        ),
    )


def test_async_enricher_completes_request_and_calls_callback() -> None:
    estimator = _FixedEstimator()
    results = []
    enricher = AsyncDepthEnricher(
        estimator=estimator,
        queue_capacity=2,
        on_result=results.append,
    )
    enricher.start()

    assert enricher.submit(_request("session-1:track-1")) is True
    enricher.close()

    stats = enricher.stats()
    assert estimator.calls == 1
    assert len(results) == 1
    assert results[0].event_key == "session-1:track-1"
    assert results[0].measurement.bucket is DepthBucket.MID
    assert results[0].enrichment_latency_ms >= 0.0
    assert stats.queued == 1
    assert stats.completed == 1
    assert stats.dropped == 0
    assert stats.duplicates == 0
    assert stats.failed == 0
    assert stats.running is False


def test_duplicate_event_is_suppressed_until_released() -> None:
    estimator = _FixedEstimator()
    enricher = AsyncDepthEnricher(
        estimator=estimator,
        queue_capacity=2,
    )
    enricher.start()

    request = _request("session-1:track-7", track_id=7)
    assert enricher.submit(request) is True
    assert enricher.submit(request) is False
    enricher.close()

    stats = enricher.stats()
    assert estimator.calls == 1
    assert stats.duplicates == 1

    assert enricher.release_event("session-1:track-7") is True
    assert enricher.release_event("session-1:track-7") is False


def test_full_queue_drops_new_event_without_marking_it_seen() -> None:
    estimator = _BlockingEstimator()
    enricher = AsyncDepthEnricher(
        estimator=estimator,
        queue_capacity=1,
    )
    enricher.start()

    assert enricher.submit(_request("event-1", track_id=1)) is True
    assert estimator.started.wait(timeout=1.0)

    assert enricher.submit(_request("event-2", track_id=2)) is True
    assert enricher.submit(_request("event-3", track_id=3)) is False

    stats_while_blocked = enricher.stats()
    assert stats_while_blocked.queued == 2
    assert stats_while_blocked.dropped == 1

    estimator.release.set()
    enricher.close()

    assert enricher.release_event("event-3") is False
    assert enricher.stats().completed == 2


def test_worker_survives_estimator_failure_and_processes_next_event() -> None:
    estimator = _FailOnceEstimator()
    results = []
    enricher = AsyncDepthEnricher(
        estimator=estimator,
        queue_capacity=2,
        on_result=results.append,
    )
    enricher.start()

    assert enricher.submit(_request("bad-event", track_id=1)) is True
    assert enricher.submit(_request("good-event", track_id=2)) is True
    enricher.close()

    stats = enricher.stats()
    assert estimator.calls == 2
    assert stats.failed == 1
    assert stats.completed == 1
    assert len(results) == 1
    assert results[0].event_key == "good-event"


def test_submit_requires_running_enricher() -> None:
    enricher = AsyncDepthEnricher(
        estimator=_FixedEstimator(),
        queue_capacity=1,
    )

    with pytest.raises(RuntimeError, match="not running"):
        enricher.submit(_request("event-1"))


@pytest.mark.parametrize(
    ("estimated", "q33", "q66", "expected"),
    [
        (0.0, 1.0, 2.0, DepthBucket.UNKNOWN),
        (1.0, 1.0, 2.0, DepthBucket.NEAR),
        (1.5, 1.0, 2.0, DepthBucket.MID),
        (2.5, 1.0, 2.0, DepthBucket.FAR),
        (1.5, 3.0, 2.0, DepthBucket.UNKNOWN),
    ],
)
def test_classify_depth_bucket(
    estimated: float,
    q33: float,
    q66: float,
    expected: DepthBucket,
) -> None:
    assert (
        classify_depth_bucket(
            estimated_depth_m=estimated,
            scene_q33_m=q33,
            scene_q66_m=q66,
        )
        is expected
    )
