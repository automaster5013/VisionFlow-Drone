from __future__ import annotations

import pytest

from app.config import Settings


def _base_env(monkeypatch, tmp_path) -> None:
    dummy_video = tmp_path / "showdown.mp4"
    dummy_video.touch()
    monkeypatch.setenv("AI_SOURCE_TYPE", "DUMMY_VIDEO")
    monkeypatch.setenv("AI_DUMMY_VIDEO_PATH", str(dummy_video))
    monkeypatch.setenv("AI_MODEL_PROFILE", "DETERMINISTIC_COMPARE")
    monkeypatch.setenv("AI_MODEL_PATH", " ")
    monkeypatch.setenv("AI_COMPARE_BASELINE_MODEL_PATH", "models/yolo26m.pt")
    monkeypatch.setenv(
        "AI_COMPARE_CANDIDATE_MODEL_PATH",
        "models/yolo26m-visdrone-s2-best.pt",
    )
    monkeypatch.setenv(
        "AI_COMPARE_CANDIDATE_MANIFEST_PATH",
        "models/manifests/yolo26m-visdrone-s2-best.manifest.json",
    )
    monkeypatch.setenv("AI_PHASE3_ENABLED", "false")
    monkeypatch.setenv("AI_REPORT_EVENTS", "false")
    monkeypatch.setenv("AI_SNAPSHOT_POLICY", "OFF")
    monkeypatch.setenv("VISIONFLOW_AI_INTERNAL_SECURITY_ENABLED", "false")


def test_compare_settings_read_three_explicit_model_paths(
    monkeypatch,
    tmp_path,
) -> None:
    _base_env(monkeypatch, tmp_path)

    settings = Settings.from_env()

    assert settings.model_profile == "DETERMINISTIC_COMPARE"
    assert settings.model_path.strip() == ""
    assert settings.compare_baseline_model_path == "models/yolo26m.pt"
    assert settings.compare_candidate_model_path.endswith("visdrone-s2-best.pt")
    assert settings.compare_candidate_manifest_path.endswith("manifest.json")
    assert settings.report_events is False


@pytest.mark.parametrize(
    "name",
    [
        "AI_COMPARE_BASELINE_MODEL_PATH",
        "AI_COMPARE_CANDIDATE_MODEL_PATH",
        "AI_COMPARE_CANDIDATE_MANIFEST_PATH",
    ],
)
def test_compare_requires_all_model_paths(monkeypatch, tmp_path, name) -> None:
    _base_env(monkeypatch, tmp_path)
    monkeypatch.setenv(name, " ")

    with pytest.raises(ValueError, match=name):
        Settings.from_env()


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("AI_SOURCE_TYPE", "SMARTPHONE_LIVE", "AI_SOURCE_TYPE=DUMMY_VIDEO"),
        ("AI_PHASE3_ENABLED", "true", "AI_PHASE3_ENABLED=false"),
        ("AI_REPORT_EVENTS", "true", "AI_REPORT_EVENTS=false"),
        ("AI_SNAPSHOT_POLICY", "MANUAL", "AI_SNAPSHOT_POLICY=OFF"),
    ],
)
def test_compare_rejects_nondeterministic_or_auxiliary_paths(
    monkeypatch,
    tmp_path,
    name,
    value,
    message,
) -> None:
    _base_env(monkeypatch, tmp_path)
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=message):
        Settings.from_env()


def test_single_profile_does_not_require_compare_paths(monkeypatch, tmp_path) -> None:
    _base_env(monkeypatch, tmp_path)
    monkeypatch.setenv("AI_MODEL_PROFILE", "GENERAL_LIVE")
    monkeypatch.setenv("AI_MODEL_PATH", "models/yolo26m.pt")
    monkeypatch.setenv("AI_COMPARE_BASELINE_MODEL_PATH", " ")
    monkeypatch.setenv("AI_COMPARE_CANDIDATE_MODEL_PATH", " ")
    monkeypatch.setenv("AI_COMPARE_CANDIDATE_MANIFEST_PATH", " ")

    settings = Settings.from_env()

    assert settings.model_profile == "GENERAL_LIVE"
