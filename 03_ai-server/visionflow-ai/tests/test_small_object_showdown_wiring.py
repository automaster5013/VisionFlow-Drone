from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import numpy as np

import app.main as app_main
from app.domain import FramePacket, InferencePacket, VideoSourceType
from app.model_runtime import ShowdownComparisonPolicy


class _FakeSelection:
    def __init__(self, profile: str, path: str) -> None:
        self.requested_profile = profile
        self.model_path = path

    def resolve_class(self, class_id: int, source_name: str):
        return class_id, source_name

    def enrich_status(self, status, contract):
        return {**status, "runtimeContract": dict(contract)}


class _FakeComparison:
    def __init__(self) -> None:
        self.baseline = _FakeSelection("GENERAL_LIVE", "models/yolo26m.pt")
        self.candidate = _FakeSelection(
            "AERIAL_SMALL_OBJECT_LIVE",
            "models/yolo26m-visdrone-s2-best.pt",
        )
        self.policy = ShowdownComparisonPolicy(
            match_iou_threshold=0.5,
            small_object_definition=(
                "COCO_AREA_LT_32_SQUARED_PX_AT_ORIGINAL_RESOLUTION"
            ),
            small_object_max_area_px=1024,
            metric_provenance="MODEL_DIFFERENCE_PROXY",
            recovered_label="RECOVERED SMALL OBJECT",
        )
        self.validated_statuses = None

    def validate_loaded_status(self, *, baseline_status, candidate_status):
        self.validated_statuses = (baseline_status, candidate_status)
        return {
            "baseline": {"validation": "PROFILE_REGISTRY"},
            "candidate": {"validation": "WEIGHT_MANIFEST"},
        }


class _FakeDetector:
    def __init__(self, options) -> None:
        self.options = options

    def status(self):
        return {"profile": self.options["model_profile"]}

    def infer(self, frame: FramePacket) -> InferencePacket:
        return InferencePacket(
            frame=frame,
            detections=(),
            inference_ms=1.0,
            annotated_image=frame.image.copy(),
        )


def test_compare_wiring_builds_two_detectors_with_shared_inference_knobs(
    monkeypatch,
) -> None:
    comparison = _FakeComparison()
    comparison_factory_calls = []
    detector_calls = []

    def fake_comparison_factory(**kwargs):
        comparison_factory_calls.append(kwargs)
        return comparison

    def fake_detector_factory(**kwargs):
        detector_calls.append(kwargs)
        return _FakeDetector(kwargs)

    monkeypatch.setattr(
        app_main,
        "create_runtime_model_comparison_selection",
        fake_comparison_factory,
    )
    settings = SimpleNamespace(
        model_profile="DETERMINISTIC_COMPARE",
        model_path="",
        model_manifest_path="",
        model_profiles_path="config/model-profiles-v1.json",
        compare_baseline_model_path="models/yolo26m.pt",
        compare_candidate_model_path="models/yolo26m-visdrone-s2-best.pt",
        compare_candidate_manifest_path="models/manifests/s2.manifest.json",
        require_cuda=True,
        require_local_model=True,
        confidence=0.26,
        iou=0.50,
        image_size=1280,
        device="cuda:0",
    )

    runtime = app_main.create_runtime_inference(
        settings,
        detector_factory=fake_detector_factory,
    )

    assert comparison_factory_calls == [
        {
            "baseline_model_path": "models/yolo26m.pt",
            "candidate_model_path": "models/yolo26m-visdrone-s2-best.pt",
            "candidate_manifest_path": "models/manifests/s2.manifest.json",
            "profiles_path": "config/model-profiles-v1.json",
        }
    ]
    assert [call["model_profile"] for call in detector_calls] == [
        "GENERAL_LIVE",
        "AERIAL_SMALL_OBJECT_LIVE",
    ]
    for call in detector_calls:
        assert call["require_cuda"] is True
        assert call["require_local_model"] is True
        assert call["confidence"] == 0.26
        assert call["iou"] == 0.50
        assert call["image_size"] == 1280
        assert call["device"] == "cuda:0"
    assert comparison.validated_statuses is not None
    assert runtime.phase3_detector is None
    assert runtime.phase3_model_selection is None
    assert runtime.performance_model_path == "DETERMINISTIC_COMPARE"

    frame = FramePacket(
        source_id="camera",
        session_id="session",
        source_type=VideoSourceType.DUMMY_VIDEO,
        drone_id=1,
        frame_index=0,
        captured_at=datetime(2026, 8, 26, tzinfo=UTC),
        image=np.zeros((16, 16, 3), dtype=np.uint8),
    )
    inference = runtime.inferencer.infer(frame)
    status = runtime.model_status_provider()

    assert inference.annotated_image.shape == (52, 32, 3)
    assert status["models"]["baseline"]["profile"] == "GENERAL_LIVE"
    assert status["models"]["candidate"]["profile"] == (
        "AERIAL_SMALL_OBJECT_LIVE"
    )
