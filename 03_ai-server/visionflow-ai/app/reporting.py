from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

AI_INTERNAL_KEY_HEADER = "X-VisionFlow-AI-Key"


class EventReporter(Protocol):
    def start(self) -> None: ...

    def submit(
        self,
        payload: dict[str, object],
        snapshot_jpeg: bytes | None = None,
    ) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class EventReport:
    payload: dict[str, object]
    snapshot_jpeg: bytes | None


class SpringEventReporter:
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
        self._event_url = event_url
        self._max_retries = max_retries
        self._queue: queue.Queue[EventReport | None] = queue.Queue(
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
            name="visionflow-ai-event-reporter",
            daemon=True,
        )
        self._thread.start()

    def submit(
        self,
        payload: dict[str, object],
        snapshot_jpeg: bytes | None = None,
    ) -> None:
        if not self._started:
            raise RuntimeError("이벤트 전송기가 시작되지 않았습니다.")

        try:
            self._queue.put_nowait(
                EventReport(
                    payload=payload,
                    snapshot_jpeg=snapshot_jpeg,
                )
            )
        except queue.Full:
            print(
                "AI 이벤트 전송 큐가 가득 차 이벤트를 건너뜁니다: "
                f"frameIndex={payload.get('frameIndex')}",
                flush=True,
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

    def _run(self) -> None:
        try:
            while True:
                payload = self._queue.get()

                try:
                    if payload is None:
                        return

                    self._send_with_retry(payload)
                finally:
                    self._queue.task_done()
        finally:
            self._client.close()

    def _send_with_retry(self, report: EventReport) -> None:
        total_attempts = self._max_retries + 1

        for attempt in range(total_attempts):
            try:
                response = self._client.post(
                    self._event_url,
                    json=report.payload,
                )
                response.raise_for_status()

                response_payload = response.json()
                event_id = int(response_payload["id"])

                if report.snapshot_jpeg is not None:
                    snapshot_response = self._client.put(
                        f"{self._event_url.rstrip('/')}/{event_id}/snapshot",
                        files={
                            "file": (
                                f"event-{event_id}.jpg",
                                report.snapshot_jpeg,
                                "image/jpeg",
                            )
                        },
                    )
                    snapshot_response.raise_for_status()

                return
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
                final_attempt = attempt + 1 >= total_attempts

                if final_attempt:
                    print(
                        "AI 이벤트 또는 스냅샷 전송 실패: "
                        f"frameIndex={report.payload.get('frameIndex')}, "
                        f"error={error}",
                        flush=True,
                    )
                    return

                time.sleep(0.25 * (2**attempt))
