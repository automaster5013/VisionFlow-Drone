from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

from app.domain import InferencePacket
from app.inference import YoloDetector
from app.metrics import InferencePerformanceMonitor
from app.reporting import EventReporter
from app.sources import VideoSource
from app.streaming import AnnotatedFrameHub


@dataclass(slots=True)
class _EventGateState:
    consecutive_frames: int = 0
    last_reported_at: float | None = None
    last_seen_at: float = 0.0


class InferencePipeline:
    def __init__(
        self,
        *,
        source: VideoSource,
        detector: YoloDetector,
        save_annotated_video: bool,
        output_video_path: Path,
        show_preview: bool,
        max_frames: int,
        reporter: EventReporter | None,
        frame_hub: AnnotatedFrameHub | None,
        snapshot_enabled: bool,
        snapshot_jpeg_quality: int,
        event_min_consecutive_frames: int,
        event_cooldown_seconds: float,
        performance_monitor: InferencePerformanceMonitor | None = None,
    ) -> None:
        self._source = source
        self._detector = detector
        self._save_annotated_video = save_annotated_video
        self._output_video_path = output_video_path
        self._show_preview = show_preview
        self._max_frames = max_frames
        self._reporter = reporter
        self._frame_hub = frame_hub
        self._snapshot_enabled = snapshot_enabled
        self._snapshot_jpeg_quality = snapshot_jpeg_quality
        self._event_min_consecutive_frames = event_min_consecutive_frames
        self._event_cooldown_seconds = event_cooldown_seconds
        self._event_gate_states: dict[
            tuple[str, str, int],
            _EventGateState,
        ] = {}
        self._event_gate_state_ttl_seconds = max(
            60.0,
            event_cooldown_seconds * 6.0,
        )
        self._performance_monitor = performance_monitor

    def run(self) -> None:
        writer: cv2.VideoWriter | None = None
        processed_frames = 0

        try:
            if self._performance_monitor is not None:
                self._performance_monitor.start()

            if self._reporter is not None:
                self._reporter.start()

            with self._source:
                while True:
                    if self._max_frames > 0 and processed_frames >= self._max_frames:
                        break

                    frame = self._source.read()

                    if frame is None:
                        break

                    inference = self._detector.infer(frame)

                    if self._performance_monitor is not None:
                        self._performance_monitor.record(inference)

                    if writer is None and self._save_annotated_video:
                        writer = self._create_writer(
                            inference.annotated_image.shape[1],
                            inference.annotated_image.shape[0],
                        )

                    if writer is not None:
                        writer.write(inference.annotated_image)

                    if self._frame_hub is not None:
                        self._frame_hub.publish(inference)

                    if self._should_report_event(inference):
                        event_payload = inference.to_event_payload()
                        print(
                            json.dumps(
                                event_payload,
                                ensure_ascii=False,
                            ),
                            flush=True,
                        )

                        if self._reporter is not None:
                            snapshot_jpeg = (
                                self._encode_snapshot(inference.annotated_image)
                                if self._snapshot_enabled
                                else None
                            )
                            self._reporter.submit(
                                event_payload,
                                snapshot_jpeg,
                            )

                    if self._show_preview:
                        cv2.imshow("VisionFlow AI Digital Twin", inference.annotated_image)

                        if cv2.waitKey(1) & 0xFF == ord("q"):
                            break

                    processed_frames += 1
        finally:
            if writer is not None:
                writer.release()

            if self._reporter is not None:
                self._reporter.close()

            if self._performance_monitor is not None:
                self._performance_monitor.stop()

            if self._show_preview:
                cv2.destroyAllWindows()

        print(f"처리 완료: {processed_frames} 프레임", flush=True)

    # VisionFlow hard cooldown gate v2
    def _should_report_event(
        self,
        inference: InferencePacket,
    ) -> bool:
        now = time.monotonic()
        key = (
            inference.frame.source_id,
            inference.frame.session_id,
            inference.frame.drone_id,
        )

        self._prune_event_gate_states(now, keep_key=key)

        state = self._event_gate_states.setdefault(key, _EventGateState())
        state.last_seen_at = now

        if not inference.detections:
            state.consecutive_frames = 0
            return False

        state.consecutive_frames += 1
        if state.consecutive_frames < self._event_min_consecutive_frames:
            return False

        if (
            state.last_reported_at is not None
            and now - state.last_reported_at < self._event_cooldown_seconds
        ):
            return False

        # 탐지 클래스/개수 변화와 관계없이 스트림별 절대 쿨다운을 적용합니다.
        state.last_reported_at = now
        return True

    def _prune_event_gate_states(
        self,
        now: float,
        *,
        keep_key: tuple[str, str, int],
    ) -> None:
        stale_keys = [
            key
            for key, state in self._event_gate_states.items()
            if key != keep_key
            and now - state.last_seen_at >= self._event_gate_state_ttl_seconds
        ]
        for key in stale_keys:
            self._event_gate_states.pop(key, None)

    def _create_writer(self, width: int, height: int) -> cv2.VideoWriter:
        self._output_video_path.parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(
            str(self._output_video_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            self._source.fps,
            (width, height),
        )

        if not writer.isOpened():
            writer.release()
            raise RuntimeError(f"분석 영상 출력 파일을 열 수 없습니다: {self._output_video_path}")

        return writer

    def _encode_snapshot(
        self,
        image: NDArray[np.uint8],
    ) -> bytes | None:
        encoded, buffer = cv2.imencode(
            ".jpg",
            image,
            [cv2.IMWRITE_JPEG_QUALITY, self._snapshot_jpeg_quality],
        )

        if not encoded:
            print("AI 이벤트 스냅샷 JPEG 인코딩에 실패했습니다.", flush=True)
            return None

        return buffer.tobytes()
