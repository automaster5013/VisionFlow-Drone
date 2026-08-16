from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.main as app_main


class _FakeSource:
    fps = 29.97


class _FakePipeline:
    def __init__(self, events, *, interrupt: bool = False) -> None:
        self._events = events
        self._interrupt = interrupt

    def run(self) -> None:
        self._events.append("pipeline.run")
        if self._interrupt:
            raise KeyboardInterrupt


class _FakeStreamServer:
    def __init__(self, events) -> None:
        self._events = events

    def start(self) -> None:
        self._events.append("stream.start")

    def close(self) -> None:
        self._events.append("stream.close")


class _FakePhase3Runtime:
    def __init__(self, events) -> None:
        self._events = events

    def start(self) -> None:
        self._events.append("phase3.start")

    def close(self) -> None:
        self._events.append("phase3.close")


class _FakePhase3Reporter:
    def __init__(self, events) -> None:
        self._events = events

    def start(self) -> None:
        self._events.append("phase3.reporter.start")

    def close(self) -> None:
        self._events.append("phase3.reporter.close")


def test_create_optional_phase3_runtime_forwards_settings_and_source_fps(
    monkeypatch,
) -> None:
    captured = {}
    sentinel = object()

    def fake_create_phase3_runtime(*, settings, source_fps):
        captured["settings"] = settings
        captured["source_fps"] = source_fps
        return sentinel

    monkeypatch.setattr(
        app_main,
        "create_phase3_runtime",
        fake_create_phase3_runtime,
    )

    settings = SimpleNamespace(phase3_enabled=True)
    runtime = app_main.create_optional_phase3_runtime(
        settings=settings,
        source=_FakeSource(),
    )

    assert runtime is sentinel
    assert captured["settings"] is settings
    assert captured["source_fps"] == pytest.approx(29.97)


def test_lifecycle_starts_phase3_before_pipeline_and_closes_it_afterward() -> None:
    events = []

    app_main.run_pipeline_with_optional_phase3(
        pipeline=_FakePipeline(events),
        stream_server=_FakeStreamServer(events),
        phase3_runtime=_FakePhase3Runtime(events),
    )

    assert events == [
        "stream.start",
        "phase3.start",
        "pipeline.run",
        "phase3.close",
        "stream.close",
    ]


def test_lifecycle_without_phase3_preserves_existing_stream_behavior() -> None:
    events = []

    app_main.run_pipeline_with_optional_phase3(
        pipeline=_FakePipeline(events),
        stream_server=_FakeStreamServer(events),
        phase3_runtime=None,
    )

    assert events == [
        "stream.start",
        "pipeline.run",
        "stream.close",
    ]


def test_keyboard_interrupt_closes_both_runtimes(
    capsys,
) -> None:
    events = []

    app_main.run_pipeline_with_optional_phase3(
        pipeline=_FakePipeline(events, interrupt=True),
        stream_server=_FakeStreamServer(events),
        phase3_runtime=_FakePhase3Runtime(events),
    )

    assert events == [
        "stream.start",
        "phase3.start",
        "pipeline.run",
        "phase3.close",
        "stream.close",
    ]
    assert "사용자 요청으로 분석을 종료합니다." in capsys.readouterr().out


def test_lifecycle_allows_no_stream_server() -> None:
    events = []

    app_main.run_pipeline_with_optional_phase3(
        pipeline=_FakePipeline(events),
        stream_server=None,
        phase3_runtime=_FakePhase3Runtime(events),
    )

    assert events == [
        "phase3.start",
        "pipeline.run",
        "phase3.close",
    ]


def test_lifecycle_keeps_phase3_reporter_alive_until_depth_runtime_closes() -> None:
    events = []

    app_main.run_pipeline_with_optional_phase3(
        pipeline=_FakePipeline(events),
        stream_server=_FakeStreamServer(events),
        phase3_runtime=_FakePhase3Runtime(events),
        phase3_reporter=_FakePhase3Reporter(events),
    )

    assert events == [
        "stream.start",
        "phase3.reporter.start",
        "phase3.start",
        "pipeline.run",
        "phase3.close",
        "phase3.reporter.close",
        "stream.close",
    ]