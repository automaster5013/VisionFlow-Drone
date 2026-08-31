from __future__ import annotations

import pytest

import app.config as config_module
from app.config import Settings


SEGMENTATION_ENV_NAMES = (
    "AI_PHASE3_ENABLED",
    "AI_PHASE3_SEGMENTATION_ENABLED",
    "AI_PHASE3_SEGMENTATION_MODEL_PATH",
    "AI_PHASE3_SEGMENTATION_TARGET_FPS",
    "AI_PHASE3_DEPTH_ENABLED",
)


def _prepare_base_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)

    for name in SEGMENTATION_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)

    video = tmp_path / "sample.mp4"
    video.write_bytes(b"phase3-segmentation-settings-test")

    monkeypatch.setenv("AI_DUMMY_VIDEO_PATH", str(video))
    monkeypatch.setenv(
        "VISIONFLOW_AI_INTERNAL_SECURITY_ENABLED",
        "false",
    )
    monkeypatch.setenv("AI_STREAM_ENABLED", "false")


def test_segmentation_is_disabled_by_default(monkeypatch, tmp_path) -> None:
    _prepare_base_env(monkeypatch, tmp_path)

    settings = Settings.from_env()

    assert settings.phase3_segmentation_enabled is False
    assert (
        settings.phase3_segmentation_model_path
        == "/app/models/yolo26m-seg.pt"
    )
    assert settings.phase3_segmentation_target_fps == 5.0


def test_segmentation_reads_runtime_overrides(monkeypatch, tmp_path) -> None:
    _prepare_base_env(monkeypatch, tmp_path)

    monkeypatch.setenv("AI_PHASE3_ENABLED", "true")
    monkeypatch.setenv("AI_PHASE3_SEGMENTATION_ENABLED", "true")
    monkeypatch.setenv(
        "AI_PHASE3_SEGMENTATION_MODEL_PATH",
        "/models/custom-seg.pt",
    )
    monkeypatch.setenv("AI_PHASE3_SEGMENTATION_TARGET_FPS", "4.0")
    monkeypatch.setenv("AI_PHASE3_DEPTH_ENABLED", "false")

    settings = Settings.from_env()

    assert settings.phase3_segmentation_enabled is True
    assert settings.phase3_segmentation_model_path == "/models/custom-seg.pt"
    assert settings.phase3_segmentation_target_fps == 4.0


def test_enabled_segmentation_requires_model_path(
    monkeypatch,
    tmp_path,
) -> None:
    _prepare_base_env(monkeypatch, tmp_path)

    monkeypatch.setenv("AI_PHASE3_ENABLED", "true")
    monkeypatch.setenv("AI_PHASE3_SEGMENTATION_ENABLED", "true")
    monkeypatch.setenv("AI_PHASE3_SEGMENTATION_MODEL_PATH", "   ")
    monkeypatch.setenv("AI_PHASE3_DEPTH_ENABLED", "false")

    with pytest.raises(
        ValueError,
        match="AI_PHASE3_SEGMENTATION_MODEL_PATH",
    ):
        Settings.from_env()


def test_enabled_segmentation_requires_positive_target_fps(
    monkeypatch,
    tmp_path,
) -> None:
    _prepare_base_env(monkeypatch, tmp_path)

    monkeypatch.setenv("AI_PHASE3_ENABLED", "true")
    monkeypatch.setenv("AI_PHASE3_SEGMENTATION_ENABLED", "true")
    monkeypatch.setenv("AI_PHASE3_SEGMENTATION_TARGET_FPS", "0")
    monkeypatch.setenv("AI_PHASE3_DEPTH_ENABLED", "false")

    with pytest.raises(
        ValueError,
        match="AI_PHASE3_SEGMENTATION_TARGET_FPS",
    ):
        Settings.from_env()


def test_disabled_phase3_ignores_dormant_invalid_segmentation_values(
    monkeypatch,
    tmp_path,
) -> None:
    _prepare_base_env(monkeypatch, tmp_path)

    monkeypatch.setenv("AI_PHASE3_ENABLED", "false")
    monkeypatch.setenv("AI_PHASE3_SEGMENTATION_ENABLED", "true")
    monkeypatch.setenv("AI_PHASE3_SEGMENTATION_MODEL_PATH", "   ")
    monkeypatch.setenv("AI_PHASE3_SEGMENTATION_TARGET_FPS", "-1")

    settings = Settings.from_env()

    assert settings.phase3_enabled is False
    assert settings.phase3_segmentation_enabled is True
    assert settings.phase3_segmentation_model_path == "   "
    assert settings.phase3_segmentation_target_fps == -1.0
