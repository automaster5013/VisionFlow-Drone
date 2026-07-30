from __future__ import annotations

from datetime import UTC, datetime

import numpy as np

from app.domain import Detection, FramePacket, InferencePacket, VideoSourceType
from app.metrics import (
    InferencePerformanceMonitor,
    PerformanceThresholds,
    evaluate_performance_health,
)


def _packet(inference_ms: float, detection_count: int) -> InferencePacket:
    image = np.zeros((8, 8, 3), dtype=np.uint8)
    frame = FramePacket(
        source_id="benchmark-source",
        session_id="benchmark-session",
        source_type=VideoSourceType.DUMMY_VIDEO,
        drone_id=1,
        frame_index=0,
        captured_at=datetime.now(UTC),
        image=image,
    )
    detections = tuple(
        Detection(
            class_id=index,
            class_name="person",
            confidence=0.9,
            x1=1.0,
            y1=1.0,
            x2=4.0,
            y2=4.0,
        )
        for index in range(detection_count)
    )
    return InferencePacket(
        frame=frame,
        detections=detections,
        inference_ms=inference_ms,
        annotated_image=image,
    )


def test_monitor_aggregates_latency_frames_and_detections() -> None:
    monitor = InferencePerformanceMonitor(
        model_path="models/yolo11n.pt",
        device="cpu",
        source_type="DUMMY_VIDEO",
        configured_input_fps=30.0,
    )

    monitor.start()
    monitor.record(_packet(10.0, 0))
    monitor.record(_packet(20.0, 2))
    monitor.record(_packet(30.0, 1))
    snapshot = monitor.snapshot()
    monitor.stop()

    assert snapshot["running"] is True
    assert snapshot["modelName"] == "yolo11n.pt"
    assert snapshot["device"] == "cpu"
    assert snapshot["processedFrames"] == 3
    assert snapshot["detectedFrames"] == 2
    assert snapshot["totalDetections"] == 3
    assert snapshot["averageInferenceMs"] == 20.0
    assert snapshot["p95InferenceMs"] == 30.0
    assert snapshot["maximumInferenceMs"] == 30.0
    assert snapshot["rollingSampleCount"] == 3
    assert snapshot["health"]["status"] == "NORMAL"


def test_monitor_reports_waiting_when_no_input_has_arrived() -> None:
    monitor = InferencePerformanceMonitor(
        model_path="models/yolo26n.pt",
        device="cpu",
        source_type="SMARTPHONE_LIVE",
        configured_input_fps=5.0,
    )
    monitor.start()

    snapshot = monitor.snapshot(
        ingest_status={
            "inputFps": 0.0,
            "dropRatePct": 0.0,
            "queueDepth": 0,
            "queueCapacity": 3,
            "lastReceivedAt": None,
        }
    )

    assert snapshot["health"]["status"] == "WAITING_INPUT"
    assert snapshot["health"]["reasonCodes"] == ["NO_INPUT_FRAMES"]


def test_monitor_reset_clears_benchmark_window_without_stopping_pipeline() -> None:
    monitor = InferencePerformanceMonitor(
        model_path="models/yolo26n.pt",
        device="cpu",
        source_type="SMARTPHONE_LIVE",
        configured_input_fps=5.0,
    )
    monitor.start()
    monitor.record(_packet(834.18, 1))

    reset_result = monitor.reset()
    snapshot = monitor.snapshot()

    assert reset_result["running"] is True
    assert snapshot["running"] is True
    assert snapshot["processedFrames"] == 0
    assert snapshot["detectedFrames"] == 0
    assert snapshot["totalDetections"] == 0
    assert snapshot["averageInferenceMs"] == 0.0
    assert snapshot["p95InferenceMs"] == 0.0
    assert snapshot["maximumInferenceMs"] == 0.0


def test_health_reports_warning_for_high_p95_latency() -> None:
    now = datetime.now(UTC)
    health = evaluate_performance_health(
        metrics={
            "running": True,
            "processedFrames": 100,
            "processingFps": 5.0,
            "p95InferenceMs": 300.0,
            "rollingSampleCount": 10,
            "lastProcessedAt": now.isoformat(),
        },
        ingest_status={
            "inputFps": 5.0,
            "dropRatePct": 0.0,
            "queueDepth": 0,
            "queueCapacity": 3,
            "lastReceivedAt": now.isoformat(),
        },
        thresholds=PerformanceThresholds(),
        evaluated_at=now,
    )

    assert health["status"] == "WARNING"
    assert health["reasonCodes"] == ["P95_LATENCY_WARNING"]


def test_health_reports_critical_for_processing_backlog() -> None:
    now = datetime.now(UTC)
    health = evaluate_performance_health(
        metrics={
            "running": True,
            "processedFrames": 100,
            "processingFps": 2.0,
            "p95InferenceMs": 100.0,
            "rollingSampleCount": 10,
            "lastProcessedAt": now.isoformat(),
        },
        ingest_status={
            "inputFps": 5.0,
            "dropRatePct": 6.0,
            "queueDepth": 3,
            "queueCapacity": 3,
            "lastReceivedAt": now.isoformat(),
        },
        thresholds=PerformanceThresholds(),
        evaluated_at=now,
    )

    assert health["status"] == "CRITICAL"
    assert "PROCESSING_RATIO_CRITICAL" in health["reasonCodes"]
    assert "DROP_RATE_CRITICAL" in health["reasonCodes"]
    assert "QUEUE_FULL" in health["reasonCodes"]
