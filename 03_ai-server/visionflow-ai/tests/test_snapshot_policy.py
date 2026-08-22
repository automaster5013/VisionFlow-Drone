from __future__ import annotations

from pathlib import Path

import pytest

import app.config as config_module
from app.config import Settings
from app.domain import SnapshotPolicy


def _prepare_settings_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dummy_video = tmp_path / "dummy.mp4"
    dummy_video.touch()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "load_dotenv", lambda: False)
    monkeypatch.setenv("AI_SOURCE_TYPE", "DUMMY_VIDEO")
    monkeypatch.setenv("AI_DUMMY_VIDEO_PATH", str(dummy_video))
    monkeypatch.setenv("VISIONFLOW_AI_INTERNAL_SECURITY_ENABLED", "false")
    monkeypatch.delenv("AI_SNAPSHOT_POLICY", raising=False)


def test_snapshot_policy_default_is_off(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _prepare_settings_env(monkeypatch, tmp_path)
    monkeypatch.delenv("AI_SNAPSHOT_ENABLED", raising=False)
    assert Settings.from_env().snapshot_policy is SnapshotPolicy.OFF


def test_legacy_snapshot_enabled_true_does_not_reenable_persistence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _prepare_settings_env(monkeypatch, tmp_path)
    monkeypatch.setenv("AI_SNAPSHOT_ENABLED", "true")
    assert Settings.from_env().snapshot_policy is SnapshotPolicy.OFF


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("OFF", SnapshotPolicy.OFF),
        ("manual", SnapshotPolicy.MANUAL),
        ("incident_only", SnapshotPolicy.INCIDENT_ONLY),
    ],
)
def test_snapshot_policy_parses_explicit_modes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: str, expected: SnapshotPolicy
) -> None:
    _prepare_settings_env(monkeypatch, tmp_path)
    monkeypatch.setenv("AI_SNAPSHOT_POLICY", value)
    assert Settings.from_env().snapshot_policy is expected


def test_snapshot_policy_rejects_unknown_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _prepare_settings_env(monkeypatch, tmp_path)
    monkeypatch.setenv("AI_SNAPSHOT_POLICY", "ALWAYS_ON")
    with pytest.raises(ValueError):
        Settings.from_env()


def test_only_incident_policy_allows_automatic_persistence() -> None:
    assert SnapshotPolicy.OFF.allows_automatic_persistence is False
    assert SnapshotPolicy.MANUAL.allows_automatic_persistence is False
    assert SnapshotPolicy.INCIDENT_ONLY.allows_automatic_persistence is True


def test_runtime_and_active_docs_are_fail_closed() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    pipeline_source = (repository_root / "03_ai-server/visionflow-ai/app/pipeline.py").read_text(
        encoding="utf-8"
    )
    compose_source = (repository_root / "compose.yaml").read_text(encoding="utf-8")
    root_env = (repository_root / ".env.example").read_text(encoding="utf-8")
    ai_env = (repository_root / "03_ai-server/visionflow-ai/.env.example").read_text(
        encoding="utf-8"
    )
    assert "self._snapshot_policy.allows_automatic_persistence" in pipeline_source
    assert "_snapshot_enabled" not in pipeline_source
    assert "AI_SNAPSHOT_POLICY: ${AI_SNAPSHOT_POLICY:-OFF}" in compose_source
    assert "AI_SNAPSHOT_ENABLED:" not in compose_source
    assert "AI_SNAPSHOT_POLICY=OFF" in root_env
    assert "AI_SNAPSHOT_POLICY=OFF" in ai_env
