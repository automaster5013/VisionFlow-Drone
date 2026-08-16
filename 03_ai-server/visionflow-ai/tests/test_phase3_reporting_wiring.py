from __future__ import annotations

from types import SimpleNamespace

import app.main as app_main


class _FakeReporter:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


class _FakeObserver:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


def _report_settings(*, enabled: bool = True, report: bool = True):
    return SimpleNamespace(
        phase3_enabled=enabled,
        phase3_report_events=report,
        backend_phase3_event_url=(
            "http://backend.test/api/ai/phase3/events"
        ),
        report_timeout_seconds=2.5,
        report_max_retries=2,
        report_queue_capacity=32,
    )


def test_optional_phase3_reporter_is_disabled_without_reporting() -> None:
    assert (
        app_main.create_optional_phase3_reporter(
            _report_settings(report=False)
        )
        is None
    )
    assert (
        app_main.create_optional_phase3_reporter(
            _report_settings(enabled=False)
        )
        is None
    )


def test_optional_phase3_reporter_uses_runtime_reporting_settings(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        app_main,
        "Phase3EventReporter",
        _FakeReporter,
    )

    reporter = app_main.create_optional_phase3_reporter(
        _report_settings()
    )

    assert isinstance(reporter, _FakeReporter)
    assert reporter.kwargs == {
        "event_url": "http://backend.test/api/ai/phase3/events",
        "timeout_seconds": 2.5,
        "max_retries": 2,
        "queue_capacity": 32,
    }


def test_optional_phase3_observer_receives_reporter(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        app_main,
        "Phase3ConsoleObserver",
        _FakeObserver,
    )
    reporter = object()

    observer = app_main.create_optional_phase3_observer(
        SimpleNamespace(phase3_enabled=True),
        phase3_reporter=reporter,
    )

    assert isinstance(observer, _FakeObserver)
    assert observer.kwargs["reporter"] is reporter
