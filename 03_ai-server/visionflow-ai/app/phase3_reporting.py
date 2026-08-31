from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote

import httpx

AI_INTERNAL_KEY_HEADER = "X-VisionFlow-AI-Key"


class Phase3EventReporterLike(Protocol):
    def start(self) -> None: ...

    def submit_event(
        self,
        payload: dict[str, object],
    ) -> None: ...

    def submit_depth(
        self,
        event_key: str,
        payload: dict[str, object],
    ) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class _CreateReport:
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class _DepthReport:
    event_key: str
    payload: dict[str, object]


_Report = _CreateReport | _DepthReport


class Phase3EventReporter:

    def __init__(
        self,
        *,
        event_url: str,
        timeout_seconds: float,
        max_retries: int,
        queue_capacity: int,
        internal_api_key: str = "",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._event_url = event_url.rstrip("/")
        self._max_retries = max_retries
        self._queue: queue.Queue[_Report | None] = queue.Queue(
            maxsize=queue_capacity
        )
        headers = {}
        normalized_key = internal_api_key.strip()
        if normalized_key:
            headers[AI_INTERNAL_KEY_HEADER] = normalized_key

        self._client = httpx.Client(
            timeout=timeout_seconds,
            headers=headers,
            transport=transport,
        )
        self._thread: threading.Thread | None = None
        self._started = False

    def start(self) -> None:
        if self._started:
            return

        self._started = True
        self._thread = threading.Thread(
            target=self._run,
            name="visionflow-phase3-event-reporter",
            daemon=True,
        )
        self._thread.start()

    def submit_event(
        self,
        payload: dict[str, object],
    ) -> None:
        self._submit(_CreateReport(payload=payload))

    def submit_depth(
        self,
        event_key: str,
        payload: dict[str, object],
    ) -> None:
        self._submit(
            _DepthReport(
                event_key=event_key,
                payload=payload,
            )
        )

    def close(self) -> None:
        if not self._started:
            self._client.close()
            return

        self._queue.put(None)

        if self._thread is not None:
            self._thread.join()

        self._thread = None
        self._started = False

    def _submit(self, report: _Report) -> None:
        if not self._started:
            raise RuntimeError(
                "Phase 3 event reporter is not started."
            )

        try:
            self._queue.put_nowait(report)
        except queue.Full:
            print(
                "Phase 3 event reporter queue is full; "
                "dropping report.",
                flush=True,
            )

    def _run(self) -> None:
        try:
            while True:
                report = self._queue.get()

                try:
                    if report is None:
                        return

                    if isinstance(report, _CreateReport):
                        self._send_create(report)
                    else:
                        self._send_depth(report)
                finally:
                    self._queue.task_done()
        finally:
            self._client.close()

    def _send_create(self, report: _CreateReport) -> None:
        self._send_with_retry(
            method="POST",
            url=self._event_url,
            payload=report.payload,
            label="create",
        )

    def _send_depth(self, report: _DepthReport) -> None:
        encoded_event_key = quote(
            report.event_key,
            safe="",
        )

        self._send_with_retry(
            method="PUT",
            url=(
                f"{self._event_url}/"
                f"{encoded_event_key}/depth"
            ),
            payload=report.payload,
            label="depth",
        )

    def _send_with_retry(
        self,
        *,
        method: str,
        url: str,
        payload: dict[str, object],
        label: str,
    ) -> None:
        total_attempts = self._max_retries + 1

        for attempt in range(total_attempts):
            try:
                response = self._client.request(
                    method,
                    url,
                    json=payload,
                )
                response.raise_for_status()
                return
            except httpx.HTTPError as error:
                final_attempt = attempt + 1 >= total_attempts

                if final_attempt:
                    print(
                        "Phase 3 backend report failed: "
                        f"type={label}, "
                        f"error={error}",
                        flush=True,
                    )
                    return

                time.sleep(0.25 * (2**attempt))