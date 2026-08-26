from __future__ import annotations

import math
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from typing import Protocol

import cv2
import numpy as np
import torch
from numpy.typing import NDArray

from app.domain import Detection, FramePacket, InferencePacket
from app.model_runtime import ShowdownComparisonPolicy


class InferenceEngine(Protocol):
    def infer(self, frame: FramePacket) -> InferencePacket: ...


StatusProvider = Callable[[], Mapping[str, object]]
Clock = Callable[[], float]
CudaMemoryProvider = Callable[[], Mapping[str, object]]


def _percentile(values: tuple[float, ...], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(math.ceil(percentile * len(ordered)) - 1, 0)
    return ordered[rank]


def _latency_status(values: tuple[float, ...]) -> dict[str, object]:
    if not values:
        return {
            "sampleCount": 0,
            "averageMs": 0.0,
            "p50Ms": 0.0,
            "p95Ms": 0.0,
            "maximumMs": 0.0,
        }
    return {
        "sampleCount": len(values),
        "averageMs": round(sum(values) / len(values), 2),
        "p50Ms": round(_percentile(values, 0.50), 2),
        "p95Ms": round(_percentile(values, 0.95), 2),
        "maximumMs": round(max(values), 2),
    }


def _intersection_over_union(left: Detection, right: Detection) -> float:
    intersection_width = max(min(left.x2, right.x2) - max(left.x1, right.x1), 0.0)
    intersection_height = max(min(left.y2, right.y2) - max(left.y1, right.y1), 0.0)
    intersection = intersection_width * intersection_height
    left_area = max(left.x2 - left.x1, 0.0) * max(left.y2 - left.y1, 0.0)
    right_area = max(right.x2 - right.x1, 0.0) * max(right.y2 - right.y1, 0.0)
    union = left_area + right_area - intersection
    return intersection / union if union > 0.0 else 0.0


def _candidate_only_indices(
    baseline: tuple[Detection, ...],
    candidate: tuple[Detection, ...],
    *,
    match_iou_threshold: float,
) -> tuple[int, ...]:
    possible_matches: list[tuple[float, int, int]] = []
    for baseline_index, baseline_detection in enumerate(baseline):
        for candidate_index, candidate_detection in enumerate(candidate):
            if baseline_detection.class_name != candidate_detection.class_name:
                continue
            iou = _intersection_over_union(baseline_detection, candidate_detection)
            if iou >= match_iou_threshold:
                possible_matches.append((-iou, baseline_index, candidate_index))

    matched_baseline: set[int] = set()
    matched_candidate: set[int] = set()
    for _, baseline_index, candidate_index in sorted(possible_matches):
        if baseline_index in matched_baseline or candidate_index in matched_candidate:
            continue
        matched_baseline.add(baseline_index)
        matched_candidate.add(candidate_index)

    return tuple(
        index for index in range(len(candidate)) if index not in matched_candidate
    )


def _clipped_box_area(
    detection: Detection,
    *,
    image_width: int,
    image_height: int,
) -> float:
    x1 = min(max(detection.x1, 0.0), float(image_width))
    y1 = min(max(detection.y1, 0.0), float(image_height))
    x2 = min(max(detection.x2, 0.0), float(image_width))
    y2 = min(max(detection.y2, 0.0), float(image_height))
    return max(x2 - x1, 0.0) * max(y2 - y1, 0.0)


def _copy_frame(frame: FramePacket) -> FramePacket:
    return FramePacket(
        source_id=frame.source_id,
        session_id=frame.session_id,
        source_type=frame.source_type,
        drone_id=frame.drone_id,
        frame_index=frame.frame_index,
        captured_at=frame.captured_at,
        image=frame.image.copy(),
    )


def _process_cuda_memory_status() -> Mapping[str, object]:
    status: dict[str, object] = {
        "available": False,
        "scope": "PROCESS_DUAL_MODEL_RESIDENT",
        "perModelAttributionAvailable": False,
        "allocatedBytes": None,
        "reservedBytes": None,
        "maximumAllocatedBytes": None,
    }
    if not torch.cuda.is_available():
        return status

    try:
        status.update(
            {
                "available": True,
                "allocatedBytes": int(torch.cuda.memory_allocated()),
                "reservedBytes": int(torch.cuda.memory_reserved()),
                "maximumAllocatedBytes": int(torch.cuda.max_memory_allocated()),
            }
        )
    except (AttributeError, RuntimeError):
        return status
    return status


class SmallObjectShowdown:
    def __init__(
        self,
        *,
        baseline: InferenceEngine,
        candidate: InferenceEngine,
        policy: ShowdownComparisonPolicy,
        baseline_status_provider: StatusProvider,
        candidate_status_provider: StatusProvider,
        latency_sample_capacity: int = 600,
        clock: Clock = time.perf_counter,
        cuda_memory_provider: CudaMemoryProvider = _process_cuda_memory_status,
    ) -> None:
        if latency_sample_capacity <= 0:
            raise ValueError("latency_sample_capacity는 양수여야 합니다.")
        self._baseline = baseline
        self._candidate = candidate
        self._policy = policy
        self._baseline_status_provider = baseline_status_provider
        self._candidate_status_provider = candidate_status_provider
        self._clock = clock
        self._cuda_memory_provider = cuda_memory_provider
        self._baseline_latencies: deque[float] = deque(maxlen=latency_sample_capacity)
        self._candidate_latencies: deque[float] = deque(maxlen=latency_sample_capacity)
        self._comparison_latencies: deque[float] = deque(maxlen=latency_sample_capacity)
        self._lock = threading.Lock()
        self._processed_frames = 0
        self._baseline_total_detections = 0
        self._candidate_total_detections = 0
        self._recovered_total = 0
        self._current_baseline_detections = 0
        self._current_candidate_detections = 0
        self._current_recovered: tuple[dict[str, object], ...] = ()

    def infer(self, frame: FramePacket) -> InferencePacket:
        baseline_frame = _copy_frame(frame)
        candidate_frame = _copy_frame(frame)
        started_at = self._clock()
        baseline_result = self._baseline.infer(baseline_frame)
        candidate_result = self._candidate.infer(candidate_frame)

        candidate_only = _candidate_only_indices(
            baseline_result.detections,
            candidate_result.detections,
            match_iou_threshold=self._policy.match_iou_threshold,
        )
        image_height, image_width = frame.image.shape[:2]
        recovered_indices = tuple(
            index
            for index in candidate_only
            if _clipped_box_area(
                candidate_result.detections[index],
                image_width=image_width,
                image_height=image_height,
            )
            < self._policy.small_object_max_area_px
        )
        recovered = tuple(
            {
                "candidateIndex": index,
                "className": candidate_result.detections[index].class_name,
                "bbox": [
                    candidate_result.detections[index].x1,
                    candidate_result.detections[index].y1,
                    candidate_result.detections[index].x2,
                    candidate_result.detections[index].y2,
                ],
            }
            for index in recovered_indices
        )
        annotated = self._render_comparison(
            baseline_result,
            candidate_result,
            recovered_indices,
            target_width=image_width,
            target_height=image_height,
        )
        comparison_ms = max((self._clock() - started_at) * 1_000.0, 0.0)

        with self._lock:
            self._processed_frames += 1
            self._baseline_total_detections += len(baseline_result.detections)
            self._candidate_total_detections += len(candidate_result.detections)
            self._recovered_total += len(recovered_indices)
            self._current_baseline_detections = len(baseline_result.detections)
            self._current_candidate_detections = len(candidate_result.detections)
            self._current_recovered = recovered
            self._baseline_latencies.append(baseline_result.inference_ms)
            self._candidate_latencies.append(candidate_result.inference_ms)
            self._comparison_latencies.append(comparison_ms)

        return InferencePacket(
            frame=frame,
            detections=candidate_result.detections,
            inference_ms=comparison_ms,
            annotated_image=annotated,
        )

    def status(self) -> dict[str, object]:
        with self._lock:
            baseline_latencies = tuple(self._baseline_latencies)
            candidate_latencies = tuple(self._candidate_latencies)
            comparison_latencies = tuple(self._comparison_latencies)
            processed_frames = self._processed_frames
            baseline_total = self._baseline_total_detections
            candidate_total = self._candidate_total_detections
            recovered_total = self._recovered_total
            current_baseline = self._current_baseline_detections
            current_candidate = self._current_candidate_detections
            current_recovered = tuple(dict(item) for item in self._current_recovered)

        total_comparison_ms = sum(comparison_latencies)
        comparison_fps = (
            processed_frames * 1_000.0 / total_comparison_ms
            if total_comparison_ms > 0.0
            else 0.0
        )
        return {
            "profile": "DETERMINISTIC_COMPARE",
            "mode": "COMPARE",
            "executionOrder": ["baseline", "candidate"],
            "sameInputFrames": True,
            "models": {
                "baseline": dict(self._baseline_status_provider()),
                "candidate": dict(self._candidate_status_provider()),
            },
            "comparison": {
                **self._policy.status(),
                "processedFrames": processed_frames,
                "comparisonFps": round(comparison_fps, 2),
                "current": {
                    "baselineDetectionCount": current_baseline,
                    "candidateDetectionCount": current_candidate,
                    "recoveredSmallObjectCount": len(current_recovered),
                    "recoveredSmallObjects": list(current_recovered),
                },
                "totals": {
                    "baselineDetections": baseline_total,
                    "candidateDetections": candidate_total,
                    "recoveredSmallObjects": recovered_total,
                },
                "latency": {
                    "baseline": _latency_status(baseline_latencies),
                    "candidate": _latency_status(candidate_latencies),
                    "sequentialComparison": _latency_status(comparison_latencies),
                },
            },
            "cudaMemory": dict(self._cuda_memory_provider()),
        }

    def _render_comparison(
        self,
        baseline: InferencePacket,
        candidate: InferencePacket,
        recovered_indices: tuple[int, ...],
        *,
        target_width: int,
        target_height: int,
    ) -> NDArray[np.uint8]:
        baseline_image = cv2.resize(
            np.asarray(baseline.annotated_image),
            (target_width, target_height),
        )
        candidate_image = cv2.resize(
            np.asarray(candidate.annotated_image),
            (target_width, target_height),
        )
        candidate_image = candidate_image.copy()
        for index in recovered_indices:
            detection = candidate.detections[index]
            start = (int(round(detection.x1)), int(round(detection.y1)))
            end = (int(round(detection.x2)), int(round(detection.y2)))
            cv2.rectangle(candidate_image, start, end, (0, 255, 0), 2)
            text_y = max(start[1] - 8, 16)
            cv2.putText(
                candidate_image,
                self._policy.recovered_label,
                (max(start[0], 0), text_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 255, 0),
                1,
                cv2.LINE_AA,
            )

        header_height = 36
        canvas = np.zeros(
            (target_height + header_height, target_width * 2, 3),
            dtype=np.uint8,
        )
        canvas[header_height:, :target_width] = baseline_image
        canvas[header_height:, target_width:] = candidate_image
        cv2.putText(
            canvas,
            f"BASELINE  detections={len(baseline.detections)}",
            (10, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            canvas,
            (
                f"VISDRONE S2  detections={len(candidate.detections)}  "
                f"recovered={len(recovered_indices)}"
            ),
            (target_width + 10, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            1,
            cv2.LINE_AA,
        )
        return canvas


__all__ = ["InferenceEngine", "SmallObjectShowdown"]
