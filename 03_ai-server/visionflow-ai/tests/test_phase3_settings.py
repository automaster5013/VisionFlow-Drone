from __future__ import annotations

import pytest

from app.config import Settings


def _base_env(monkeypatch, tmp_path) -> None:
    dummy_video = tmp_path / "dummy.mp4"
    dummy_video.touch()

    monkeypatch.setenv("AI_SOURCE_TYPE", "DUMMY_VIDEO")
    monkeypatch.setenv("AI_DUMMY_VIDEO_PATH", str(dummy_video))
    monkeypatch.setenv("VISIONFLOW_AI_INTERNAL_SECURITY_ENABLED", "false")


def test_phase3_is_disabled_by_default(monkeypatch, tmp_path) -> None:
    _base_env(monkeypatch, tmp_path)

    settings = Settings.from_env()

    assert settings.phase3_enabled is False
    assert settings.phase3_ppe_model_path == (
        "/app/models/ppe-yolo26m-best.pt"
    )
    assert settings.phase3_ppe_target_fps == pytest.approx(10.0)
    assert settings.phase3_depth_enabled is True
    assert settings.phase3_depth_model_path == (
        "/app/models/yolo26m-depth.pt"
    )
    assert settings.phase3_depth_image_size == 768
    assert settings.phase3_depth_queue_capacity == 4
    assert settings.phase3_report_events is False
    assert settings.backend_phase3_event_url == (
        "http://localhost:8080/api/ai/phase3/events"
    )


def test_phase3_reads_runtime_overrides(monkeypatch, tmp_path) -> None:
    _base_env(monkeypatch, tmp_path)
    monkeypatch.setenv("AI_PHASE3_ENABLED", "true")
    monkeypatch.setenv("AI_PHASE3_PPE_MODEL_PATH", "/models/custom-ppe.pt")
    monkeypatch.setenv("AI_PHASE3_PPE_TARGET_FPS", "8.0")
    monkeypatch.setenv("AI_PHASE3_DEPTH_ENABLED", "false")
    monkeypatch.setenv("AI_PHASE3_DEPTH_MODEL_PATH", "/models/custom-depth.pt")
    monkeypatch.setenv("AI_PHASE3_DEPTH_IMAGE_SIZE", "640")
    monkeypatch.setenv("AI_PHASE3_DEPTH_QUEUE_CAPACITY", "8")
    monkeypatch.setenv("AI_PHASE3_REPORT_EVENTS", "true")
    monkeypatch.setenv(
        "AI_BACKEND_PHASE3_EVENT_URL",
        "http://backend.test/api/ai/phase3/events",
    )

    settings = Settings.from_env()

    assert settings.phase3_enabled is True
    assert settings.phase3_ppe_model_path == "/models/custom-ppe.pt"
    assert settings.phase3_ppe_target_fps == pytest.approx(8.0)
    assert settings.phase3_depth_enabled is False
    assert settings.phase3_depth_model_path == "/models/custom-depth.pt"
    assert settings.phase3_depth_image_size == 640
    assert settings.phase3_depth_queue_capacity == 8
    assert settings.phase3_report_events is True
    assert settings.backend_phase3_event_url == (
        "http://backend.test/api/ai/phase3/events"
    )


def test_enabled_phase3_requires_ppe_model_path(
    monkeypatch,
    tmp_path,
) -> None:
    _base_env(monkeypatch, tmp_path)
    monkeypatch.setenv("AI_PHASE3_ENABLED", "true")
    monkeypatch.setenv("AI_PHASE3_PPE_MODEL_PATH", " ")

    with pytest.raises(ValueError, match="AI_PHASE3_PPE_MODEL_PATH"):
        Settings.from_env()


def test_enabled_depth_requires_positive_queue_capacity(
    monkeypatch,
    tmp_path,
) -> None:
    _base_env(monkeypatch, tmp_path)
    monkeypatch.setenv("AI_PHASE3_ENABLED", "true")
    monkeypatch.setenv("AI_PHASE3_DEPTH_ENABLED", "true")
    monkeypatch.setenv("AI_PHASE3_DEPTH_QUEUE_CAPACITY", "0")

    with pytest.raises(
        ValueError,
        match="AI_PHASE3_DEPTH_QUEUE_CAPACITY",
    ):
        Settings.from_env()


def test_disabled_phase3_ignores_dormant_invalid_phase3_values(
    monkeypatch,
    tmp_path,
) -> None:
    _base_env(monkeypatch, tmp_path)
    monkeypatch.setenv("AI_PHASE3_ENABLED", "false")
    monkeypatch.setenv("AI_PHASE3_PPE_MODEL_PATH", " ")
    monkeypatch.setenv("AI_PHASE3_PPE_TARGET_FPS", "-1")
    monkeypatch.setenv("AI_PHASE3_DEPTH_ENABLED", "true")
    monkeypatch.setenv("AI_PHASE3_DEPTH_MODEL_PATH", " ")
    monkeypatch.setenv("AI_PHASE3_DEPTH_IMAGE_SIZE", "0")
    monkeypatch.setenv("AI_PHASE3_DEPTH_QUEUE_CAPACITY", "0")

    settings = Settings.from_env()

    assert settings.phase3_enabled is False
