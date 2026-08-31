from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.main as app_main


class _FakeSource:
    fps = 29.97


def test_optional_frame_analyzer_forwards_runtime_and_source_fps(
    monkeypatch,
) -> None:
    captured = {}
    sentinel = object()

    def fake_create_phase3_frame_analyzer(
        *,
        settings,
        runtime,
        source_fps,
        track_model,
        class_resolver,
    ):
        captured["settings"] = settings
        captured["runtime"] = runtime
        captured["source_fps"] = source_fps
        captured["track_model"] = track_model
        captured["class_resolver"] = class_resolver
        return sentinel

    monkeypatch.setattr(
        app_main,
        "create_phase3_frame_analyzer",
        fake_create_phase3_frame_analyzer,
    )

    settings = SimpleNamespace(phase3_enabled=True)
    runtime = object()
    detector = object()

    def resolver(class_id, source_name):
        return class_id, source_name

    selection = SimpleNamespace(resolve_class=resolver)
    analyzer = app_main.create_optional_phase3_frame_analyzer(
        settings=settings,
        source=_FakeSource(),
        phase3_runtime=runtime,
        detector=detector,
        model_selection=selection,
    )

    assert analyzer is sentinel
    assert captured["settings"] is settings
    assert captured["runtime"] is runtime
    assert captured["source_fps"] == pytest.approx(29.97)
    assert captured["track_model"] is detector
    assert captured["class_resolver"] is resolver


def test_optional_frame_analyzer_allows_disabled_runtime(
    monkeypatch,
) -> None:
    captured = {}

    def fake_create_phase3_frame_analyzer(
        *,
        settings,
        runtime,
        source_fps,
        track_model,
        class_resolver,
    ):
        captured["runtime"] = runtime
        return None

    monkeypatch.setattr(
        app_main,
        "create_phase3_frame_analyzer",
        fake_create_phase3_frame_analyzer,
    )

    analyzer = app_main.create_optional_phase3_frame_analyzer(
        settings=SimpleNamespace(phase3_enabled=False),
        source=_FakeSource(),
        phase3_runtime=None,
        detector=object(),
        model_selection=SimpleNamespace(resolve_class=lambda *_: None),
    )

    assert analyzer is None
    assert captured["runtime"] is None
