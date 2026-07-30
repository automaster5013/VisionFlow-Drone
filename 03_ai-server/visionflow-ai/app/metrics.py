from __future__ import annotations

import math
import threading
import time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean

from app.domain import InferencePacket


@dataclass(frozen=True, slots=True)
class PerformanceThresholds:
    warning_p95_inference_ms: float = 250.0
    critical_p95_inference_ms: float = 500.0
    warning_processing_ratio: float = 0.90
    critical_processing_ratio: float = 0.70
    warning_drop_rate_pct: float = 1.0
    critical_drop_rate_pct: float = 5.0
    warning_queue_utilization_pct: float = 67.0
    critical_queue_utilization_pct: float = 100.0
    stale_after_seconds: float = 5.0
    min_sample_count: int = 5


class InferencePerformanceMonitor:
    def __init__(
        self,
        *,
        model_path: str,
        device: str,
        source_type: str,
        configured_input_fps: float,
        rolling_window_seconds: float = 10.0,
        latency_sample_capacity: int = 600,
        thresholds: PerformanceThresholds | None = None,
    ) -> None:
        if rolling_window_seconds <= 0:
            raise ValueError("rolling_window_seconds는 양수여야 합니다.")

        if latency_sample_capacity <= 0:
            raise ValueError("latency_sample_capacity는 양수여야 합니다.")

        self._model_name = Path(model_path).name
        self._device = device
        self._source_type = source_type
        self._configured_input_fps = configured_input_fps
        self._rolling_window_seconds = rolling_window_seconds
        self._thresholds = thresholds or PerformanceThresholds()
        self._samples: deque[tuple[float, float]] = deque(
            maxlen=latency_sample_capacity
        )
        self._lock = threading.Lock()
        self._running = False
        self._started_at: datetime | None = None
        self._started_monotonic: float | None = None
        self._last_processed_at: datetime | None = None
        self._processed_frames = 0
        self._detected_frames = 0
        self._total_detections = 0
        self._maximum_inference_ms = 0.0

    def start(self) -> None:
        with self._lock:
            if self._started_at is None:
                self._started_at = datetime.now(UTC)
                self._started_monotonic = time.monotonic()

            self._running = True

    def record(self, inference: InferencePacket) -> None:
        recorded_monotonic = time.monotonic()
        recorded_at = datetime.now(UTC)

        with self._lock:
            if self._started_at is None:
                self._started_at = recorded_at
                self._started_monotonic = recorded_monotonic

            self._running = True
            self._processed_frames += 1
            detection_count = len(inference.detections)

            if detection_count > 0:
                self._detected_frames += 1

            self._total_detections += detection_count
            self._maximum_inference_ms = max(
                self._maximum_inference_ms,
                inference.inference_ms,
            )
            self._last_processed_at = recorded_at
            self._samples.append(
                (recorded_monotonic, inference.inference_ms)
            )
            self._prune_samples(recorded_monotonic)

    def stop(self) -> None:
        with self._lock:
            self._running = False

    def reset(self) -> dict[str, object]:
        reset_at = datetime.now(UTC)
        reset_monotonic = time.monotonic()

        with self._lock:
            self._samples.clear()
            self._started_at = reset_at
            self._started_monotonic = reset_monotonic
            self._last_processed_at = None
            self._processed_frames = 0
            self._detected_frames = 0
            self._total_detections = 0
            self._maximum_inference_ms = 0.0
            running = self._running

        return {
            "resetAt": reset_at.isoformat(),
            "running": running,
        }

    def snapshot(
        self,
        *,
        ingest_status: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        now_monotonic = time.monotonic()
        now = datetime.now(UTC)

        with self._lock:
            self._prune_samples(now_monotonic)
            samples = tuple(self._samples)
            latencies = tuple(sample[1] for sample in samples)
            rolling_fps = self._calculate_fps(samples)
            average_inference_ms = fmean(latencies) if latencies else 0.0
            p95_inference_ms = self._percentile(latencies, 0.95)
            uptime_seconds = (
                max(now_monotonic - self._started_monotonic, 0.0)
                if self._started_monotonic is not None
                else 0.0
            )

            metrics: dict[str, object] = {
                "running": self._running,
                "startedAt": (
                    self._started_at.isoformat()
                    if self._started_at is not None
                    else None
                ),
                "lastProcessedAt": (
                    self._last_processed_at.isoformat()
                    if self._last_processed_at is not None
                    else None
                ),
                "uptimeSeconds": round(uptime_seconds, 2),
                "modelName": self._model_name,
                "device": self._device,
                "sourceType": self._source_type,
                "configuredInputFps": round(self._configured_input_fps, 2),
                "processedFrames": self._processed_frames,
                "detectedFrames": self._detected_frames,
                "totalDetections": self._total_detections,
                "processingFps": round(rolling_fps, 2),
                "averageInferenceMs": round(average_inference_ms, 2),
                "p95InferenceMs": round(p95_inference_ms, 2),
                "maximumInferenceMs": round(
                    self._maximum_inference_ms,
                    2,
                ),
                "rollingSampleCount": len(samples),
                "rollingWindowSeconds": self._rolling_window_seconds,
            }

        metrics["health"] = evaluate_performance_health(
            metrics=metrics,
            ingest_status=ingest_status,
            thresholds=self._thresholds,
            evaluated_at=now,
        )
        return metrics

    def _prune_samples(self, now_monotonic: float) -> None:
        threshold = now_monotonic - self._rolling_window_seconds

        while self._samples and self._samples[0][0] < threshold:
            self._samples.popleft()

    @staticmethod
    def _calculate_fps(samples: tuple[tuple[float, float], ...]) -> float:
        if len(samples) < 2:
            return 0.0

        elapsed = samples[-1][0] - samples[0][0]
        return (len(samples) - 1) / elapsed if elapsed > 0 else 0.0

    @staticmethod
    def _percentile(values: tuple[float, ...], percentile: float) -> float:
        if not values:
            return 0.0

        ordered = sorted(values)
        rank = max(math.ceil(percentile * len(ordered)) - 1, 0)
        return ordered[rank]


def evaluate_performance_health(
    *,
    metrics: Mapping[str, object],
    ingest_status: Mapping[str, object] | None,
    thresholds: PerformanceThresholds,
    evaluated_at: datetime | None = None,
) -> dict[str, object]:
    now = evaluated_at or datetime.now(UTC)
    running = bool(metrics.get("running", False))
    processed_frames = _number(metrics.get("processedFrames"))
    processing_fps = _number(metrics.get("processingFps"))
    p95_inference_ms = _number(metrics.get("p95InferenceMs"))
    rolling_sample_count = int(_number(metrics.get("rollingSampleCount")))
    seconds_since_processed = _seconds_since(
        metrics.get("lastProcessedAt"),
        now,
    )
    input_fps = (
        _number(ingest_status.get("inputFps"))
        if ingest_status is not None
        else 0.0
    )
    seconds_since_input = (
        _seconds_since(ingest_status.get("lastReceivedAt"), now)
        if ingest_status is not None
        else None
    )
    input_active = (
        input_fps > 0
        or (
            seconds_since_input is not None
            and seconds_since_input <= thresholds.stale_after_seconds
        )
    )
    processing_ratio = (
        processing_fps / input_fps
        if input_fps > 0
        else None
    )
    drop_rate_pct = (
        _number(ingest_status.get("dropRatePct"))
        if ingest_status is not None
        else 0.0
    )
    queue_depth = (
        _number(ingest_status.get("queueDepth"))
        if ingest_status is not None
        else 0.0
    )
    queue_capacity = (
        _number(ingest_status.get("queueCapacity"))
        if ingest_status is not None
        else 0.0
    )
    queue_utilization_pct = (
        queue_depth / queue_capacity * 100.0
        if queue_capacity > 0
        else 0.0
    )
    critical_reasons: list[str] = []
    warning_reasons: list[str] = []

    if not running:
        status = "STOPPED"
        reason_codes = ["PIPELINE_STOPPED"]
    elif processed_frames <= 0 and not input_active:
        status = "WAITING_INPUT"
        reason_codes = ["NO_INPUT_FRAMES"]
    elif (
        seconds_since_processed is not None
        and seconds_since_processed > thresholds.stale_after_seconds
    ):
        if input_active:
            status = "CRITICAL"
            reason_codes = ["PROCESSING_STALLED"]
        else:
            status = "WAITING_INPUT"
            reason_codes = ["INPUT_STALE"]
    else:
        enough_samples = rolling_sample_count >= thresholds.min_sample_count

        if enough_samples:
            if p95_inference_ms >= thresholds.critical_p95_inference_ms:
                critical_reasons.append("P95_LATENCY_CRITICAL")
            elif p95_inference_ms >= thresholds.warning_p95_inference_ms:
                warning_reasons.append("P95_LATENCY_WARNING")

        if processing_ratio is not None:
            if processing_ratio < thresholds.critical_processing_ratio:
                critical_reasons.append("PROCESSING_RATIO_CRITICAL")
            elif processing_ratio < thresholds.warning_processing_ratio:
                warning_reasons.append("PROCESSING_RATIO_WARNING")

        if drop_rate_pct >= thresholds.critical_drop_rate_pct:
            critical_reasons.append("DROP_RATE_CRITICAL")
        elif drop_rate_pct >= thresholds.warning_drop_rate_pct:
            warning_reasons.append("DROP_RATE_WARNING")

        if queue_utilization_pct >= thresholds.critical_queue_utilization_pct:
            critical_reasons.append("QUEUE_FULL")
        elif queue_utilization_pct >= thresholds.warning_queue_utilization_pct:
            warning_reasons.append("QUEUE_PRESSURE")

        if critical_reasons:
            status = "CRITICAL"
            reason_codes = critical_reasons + warning_reasons
        elif warning_reasons:
            status = "WARNING"
            reason_codes = warning_reasons
        else:
            status = "NORMAL"
            reason_codes = []

    return {
        "status": status,
        "reasonCodes": reason_codes,
        "evaluatedAt": now.isoformat(),
        "secondsSinceLastProcessed": _rounded_or_none(
            seconds_since_processed,
        ),
        "secondsSinceLastInput": _rounded_or_none(seconds_since_input),
        "inputToProcessingRatio": _rounded_or_none(processing_ratio),
        "queueUtilizationPct": round(queue_utilization_pct, 2),
        "thresholds": {
            "warningP95InferenceMs": thresholds.warning_p95_inference_ms,
            "criticalP95InferenceMs": thresholds.critical_p95_inference_ms,
            "warningProcessingRatio": thresholds.warning_processing_ratio,
            "criticalProcessingRatio": thresholds.critical_processing_ratio,
            "warningDropRatePct": thresholds.warning_drop_rate_pct,
            "criticalDropRatePct": thresholds.critical_drop_rate_pct,
            "warningQueueUtilizationPct": (
                thresholds.warning_queue_utilization_pct
            ),
            "criticalQueueUtilizationPct": (
                thresholds.critical_queue_utilization_pct
            ),
            "staleAfterSeconds": thresholds.stale_after_seconds,
            "minSampleCount": thresholds.min_sample_count,
        },
    }


def _number(value: object) -> float:
    if isinstance(value, bool):
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    return 0.0


def _seconds_since(value: object, now: datetime) -> float | None:
    if not isinstance(value, str) or not value:
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)

    return max((now - parsed.astimezone(UTC)).total_seconds(), 0.0)


def _rounded_or_none(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None
