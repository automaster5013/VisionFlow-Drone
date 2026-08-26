from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

import numpy as np
import pytest

from app.domain import Detection, FramePacket, InferencePacket, VideoSourceType
from app.inference.small_object_showdown import SmallObjectShowdown
from app.model_runtime import ShowdownComparisonPolicy


def _policy() -> ShowdownComparisonPolicy:
    return ShowdownComparisonPolicy(
        match_iou_threshold=0.5,
        small_object_definition=(
            "COCO_AREA_LT_32_SQUARED_PX_AT_ORIGINAL_RESOLUTION"
        ),
        small_object_max_area_px=1024,
        metric_provenance="MODEL_DIFFERENCE_PROXY",
        recovered_label="RECOVERED SMALL OBJECT",
    )


def _frame() -> FramePacket:
    image = np.arange(64 * 64 * 3, dtype=np.uint8).reshape((64, 64, 3))
    return FramePacket(
        source_id="showdown-camera",
        session_id="showdown-session",
        source_type=VideoSourceType.DUMMY_VIDEO,
        drone_id=1,
        frame_index=26,
        captured_at=datetime(2026, 8, 26, tzinfo=UTC),
        image=image,
    )


def _detection(
    class_name: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> Detection:
    return Detection(
        class_id=0,
        class_name=class_name,
        confidence=0.9,
        x1=x1,
        y1=y1,
        x2=x2,
        y2=y2,
    )


class _FakeEngine:
    def __init__(
        self,
        name: str,
        calls: list[tuple[str, bytes]],
        results: Iterable[tuple[tuple[Detection, ...], float]],
        *,
        mutate_input: bool = False,
    ) -> None:
        self._name = name
        self._calls = calls
        self._results = iter(results)
        self._mutate_input = mutate_input

    def infer(self, frame: FramePacket) -> InferencePacket:
        self._calls.append((self._name, frame.image.tobytes()))
        detections, inference_ms = next(self._results)
        annotated = np.zeros_like(frame.image)
        if self._mutate_input:
            frame.image.fill(255)
        return InferencePacket(
            frame=frame,
            detections=detections,
            inference_ms=inference_ms,
            annotated_image=annotated,
        )


def _showdown(
    baseline_results: Iterable[tuple[tuple[Detection, ...], float]],
    candidate_results: Iterable[tuple[tuple[Detection, ...], float]],
    *,
    calls: list[tuple[str, bytes]] | None = None,
    clock_values: Iterable[float] = (10.0, 10.01),
    baseline_mutates: bool = False,
    cuda_status: dict[str, object] | None = None,
) -> SmallObjectShowdown:
    shared_calls = calls if calls is not None else []
    clock = iter(clock_values)
    return SmallObjectShowdown(
        baseline=_FakeEngine(
            "baseline",
            shared_calls,
            baseline_results,
            mutate_input=baseline_mutates,
        ),
        candidate=_FakeEngine("candidate", shared_calls, candidate_results),
        policy=_policy(),
        baseline_status_provider=lambda: {"profile": "GENERAL_LIVE"},
        candidate_status_provider=lambda: {
            "profile": "AERIAL_SMALL_OBJECT_LIVE"
        },
        clock=lambda: next(clock),
        cuda_memory_provider=lambda: cuda_status
        or {
            "available": False,
            "scope": "PROCESS_DUAL_MODEL_RESIDENT",
            "perModelAttributionAvailable": False,
            "allocatedBytes": None,
            "reservedBytes": None,
            "maximumAllocatedBytes": None,
        },
    )


def test_same_frame_bytes_are_copied_before_fixed_sequential_order() -> None:
    calls: list[tuple[str, bytes]] = []
    frame = _frame()
    original_bytes = frame.image.tobytes()
    showdown = _showdown(
        [((), 2.0)],
        [((), 3.0)],
        calls=calls,
        baseline_mutates=True,
    )

    showdown.infer(frame)

    assert [name for name, _ in calls] == ["baseline", "candidate"]
    assert calls[0][1] == original_bytes
    assert calls[1][1] == original_bytes
    assert frame.image.tobytes() == original_bytes


def test_matching_is_class_aware_one_to_one_and_deterministic() -> None:
    baseline = (_detection("person", 0, 0, 10, 10),)
    candidate = (
        _detection("person", 0, 0, 10, 10),
        _detection("person", 0, 0, 10, 10),
        _detection("car", 0, 0, 10, 10),
    )
    showdown = _showdown([(baseline, 2.0)], [(candidate, 3.0)])

    showdown.infer(_frame())
    current = showdown.status()["comparison"]["current"]

    assert current["recoveredSmallObjectCount"] == 2
    assert [
        item["candidateIndex"] for item in current["recoveredSmallObjects"]
    ] == [1, 2]


def test_small_object_area_boundary_is_strictly_less_than_32_squared() -> None:
    candidate = (
        _detection("person", 0, 0, 32, 32),
        _detection("car", 0, 0, 31, 32),
    )
    showdown = _showdown([((), 1.0)], [(candidate, 1.0)])

    inference = showdown.infer(_frame())
    comparison = showdown.status()["comparison"]

    assert comparison["current"]["recoveredSmallObjectCount"] == 1
    assert comparison["current"]["recoveredSmallObjects"][0]["candidateIndex"] == 1
    assert inference.annotated_image.shape == (100, 128, 3)
    assert np.any(inference.annotated_image[:, 64:, 1] == 255)


def test_status_reports_proxy_provenance_latency_fps_and_process_vram() -> None:
    cuda_status = {
        "available": True,
        "scope": "PROCESS_DUAL_MODEL_RESIDENT",
        "perModelAttributionAvailable": False,
        "allocatedBytes": 100,
        "reservedBytes": 200,
        "maximumAllocatedBytes": 300,
    }
    showdown = _showdown(
        [((), 10.0), ((), 30.0)],
        [((_detection("car", 1, 1, 5, 5),), 20.0), ((), 40.0)],
        clock_values=(0.0, 0.01, 0.01, 0.03),
        cuda_status=cuda_status,
    )

    showdown.infer(_frame())
    showdown.infer(_frame())
    status = showdown.status()
    comparison = status["comparison"]

    assert status["models"]["baseline"]["profile"] == "GENERAL_LIVE"
    assert comparison["metricProvenance"] == "MODEL_DIFFERENCE_PROXY"
    assert comparison["groundTruthRecallAvailable"] is False
    assert "smallObjectRecall" not in comparison
    assert comparison["comparisonFps"] == pytest.approx(66.67)
    assert comparison["latency"]["baseline"] == {
        "sampleCount": 2,
        "averageMs": 20.0,
        "p50Ms": 10.0,
        "p95Ms": 30.0,
        "maximumMs": 30.0,
    }
    assert comparison["latency"]["candidate"]["p95Ms"] == 40.0
    assert comparison["totals"]["candidateDetections"] == 1
    assert status["cudaMemory"] == cuda_status


def test_empty_status_is_honest_without_cuda_or_ground_truth() -> None:
    showdown = _showdown([], [])

    status = showdown.status()

    assert status["comparison"]["processedFrames"] == 0
    assert status["comparison"]["comparisonFps"] == 0.0
    assert status["comparison"]["latency"]["baseline"]["sampleCount"] == 0
    assert status["cudaMemory"]["available"] is False
    assert status["cudaMemory"]["perModelAttributionAvailable"] is False
