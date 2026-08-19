from __future__ import annotations

import asyncio
import threading
import time
from secrets import compare_digest
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

import cv2
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.security import APIKeyHeader

from app.domain import InferencePacket
from app.metrics import InferencePerformanceMonitor
from app.sources.browser_upload import BrowserUploadSource
from app.sources.dji_android_bridge import DjiAndroidBridgeSource

MJPEG_BOUNDARY = "visionflow-frame"
AI_INTERNAL_KEY_HEADER = "X-VisionFlow-AI-Key"


@dataclass(frozen=True, slots=True)
class AnnotatedFrameSnapshot:
    sequence: int
    frame_index: int
    source_id: str
    source_type: str
    drone_id: int
    captured_at: datetime
    detection_count: int
    jpeg: bytes


class AnnotatedFrameHub:
    def __init__(self, *, jpeg_quality: int) -> None:
        self._jpeg_quality = jpeg_quality
        self._condition = threading.Condition()
        self._snapshot: AnnotatedFrameSnapshot | None = None
        self._sequence = 0
        self._closed = False
        self._connected_clients = 0

    def publish(self, inference: InferencePacket) -> None:
        encoded, buffer = cv2.imencode(
            ".jpg",
            inference.annotated_image,
            [cv2.IMWRITE_JPEG_QUALITY, self._jpeg_quality],
        )

        if not encoded:
            print(
                f"분석 프레임 JPEG 인코딩 실패: {inference.frame.frame_index}",
                flush=True,
            )
            return

        with self._condition:
            if self._closed:
                return

            self._sequence += 1
            self._snapshot = AnnotatedFrameSnapshot(
                sequence=self._sequence,
                frame_index=inference.frame.frame_index,
                source_id=inference.frame.source_id,
                source_type=inference.frame.source_type.value,
                drone_id=inference.frame.drone_id,
                captured_at=inference.frame.captured_at,
                detection_count=len(inference.detections),
                jpeg=buffer.tobytes(),
            )
            self._condition.notify_all()

    def latest(self) -> AnnotatedFrameSnapshot | None:
        with self._condition:
            return self._snapshot

    def status(self) -> dict[str, object]:
        with self._condition:
            snapshot = self._snapshot

            return {
                "running": not self._closed,
                "hasFrame": snapshot is not None,
                "connectedClients": self._connected_clients,
                "frameIndex": snapshot.frame_index if snapshot else None,
                "sourceId": snapshot.source_id if snapshot else None,
                "sourceType": snapshot.source_type if snapshot else None,
                "droneId": snapshot.drone_id if snapshot else None,
                "capturedAt": (snapshot.captured_at.isoformat() if snapshot else None),
                "detectionCount": (snapshot.detection_count if snapshot else 0),
            }

    def iter_mjpeg(self) -> Iterator[bytes]:
        last_sequence = 0

        with self._condition:
            self._connected_clients += 1

        try:
            while True:
                with self._condition:
                    snapshot = self._snapshot

                    if not self._closed and (
                        snapshot is None or snapshot.sequence <= last_sequence
                    ):
                        self._condition.wait(timeout=10.0)

                    if self._closed:
                        return

                    snapshot = self._snapshot

                    if snapshot is None or snapshot.sequence <= last_sequence:
                        continue

                    last_sequence = snapshot.sequence

                yield (
                    (
                        f"--{MJPEG_BOUNDARY}\r\n"
                        "Content-Type: image/jpeg\r\n"
                        f"Content-Length: {len(snapshot.jpeg)}\r\n"
                        f"X-Frame-Index: {snapshot.frame_index}\r\n"
                        f"X-Detection-Count: {snapshot.detection_count}\r\n"
                        "\r\n"
                    ).encode("ascii")
                    + snapshot.jpeg
                    + b"\r\n"
                )
        finally:
            with self._condition:
                self._connected_clients = max(
                    self._connected_clients - 1,
                    0,
                )

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()


def create_stream_app(
    hub: AnnotatedFrameHub,
    *,
    allowed_origins: tuple[str, ...],
    ingest_source: BrowserUploadSource | None = None,
    ingest_max_payload_bytes: int = 2_000_000,
    performance_monitor: InferencePerformanceMonitor | None = None,
    model_status_provider: Callable[[], dict[str, object]] | None = None,
    internal_security_enabled: bool = True,
    internal_api_key: str = "",
) -> FastAPI:
    app = FastAPI(
        title="VisionFlow AI Analysis Stream",
        version="0.6.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    api_key_header = APIKeyHeader(
        name=AI_INTERNAL_KEY_HEADER,
        auto_error=False,
    )

    async def require_ai_internal_key(
        provided_key: str | None = Security(api_key_header),
    ) -> None:
        if not internal_security_enabled:
            return
        if not provided_key or not compare_digest(provided_key, internal_api_key):
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "AI_INTERNAL_AUTHENTICATION_REQUIRED",
                    "message": "AI 내부 서비스 인증이 필요합니다.",
                },
            )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "UP"}

    @app.get(
        "/api/streams/status",
        dependencies=[Depends(require_ai_internal_key)],
    )
    def stream_status() -> dict[str, object]:
        return hub.status()

    @app.get(
        "/api/metrics/status",
        dependencies=[Depends(require_ai_internal_key)],
    )
    def performance_status() -> dict[str, object]:
        if performance_monitor is None:
            raise HTTPException(
                status_code=503,
                detail="AI 성능 계측기가 준비되지 않았습니다.",
            )

        ingest_status = (
            ingest_source.status() if ingest_source is not None else None
        )
        metrics = performance_monitor.snapshot(
            ingest_status=ingest_status,
        )
        metrics["ingest"] = ingest_status
        metrics["stream"] = hub.status()
        return metrics

    @app.post(
        "/api/metrics/reset",
        dependencies=[Depends(require_ai_internal_key)],
    )
    def reset_performance_metrics() -> dict[str, object]:
        if performance_monitor is None:
            raise HTTPException(
                status_code=503,
                detail="AI 성능 계측기가 준비되지 않았습니다.",
            )

        return performance_monitor.reset()

    @app.get(
        "/api/models/status",
        dependencies=[Depends(require_ai_internal_key)],
    )
    def model_status() -> dict[str, object]:
        if model_status_provider is None:
            raise HTTPException(
                status_code=503,
                detail="YOLO 모델 상태 정보가 준비되지 않았습니다.",
            )

        return model_status_provider()

    @app.get(
        "/api/streams/latest.jpg",
        dependencies=[Depends(require_ai_internal_key)],
    )
    def latest_frame() -> Response:
        snapshot = hub.latest()

        if snapshot is None:
            raise HTTPException(
                status_code=503,
                detail="아직 분석된 영상 프레임이 없습니다.",
            )

        return Response(
            content=snapshot.jpeg,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "X-Frame-Index": str(snapshot.frame_index),
                "X-Detection-Count": str(snapshot.detection_count),
            },
        )

    @app.get(
        "/api/streams/annotated.mjpeg",
        dependencies=[Depends(require_ai_internal_key)],
    )
    def annotated_stream() -> StreamingResponse:
        return StreamingResponse(
            hub.iter_mjpeg(),
            media_type=(f"multipart/x-mixed-replace; boundary={MJPEG_BOUNDARY}"),
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
            },
        )

    if ingest_source is not None:

        @app.get(
            "/api/ingest/status",
            dependencies=[Depends(require_ai_internal_key)],
        )
        def ingest_status() -> dict[str, object]:
            return ingest_source.status()

    if (
        ingest_source is not None
        and not isinstance(
            ingest_source,
            DjiAndroidBridgeSource,
        )
    ):

        @app.post(
            "/api/ingest/frame",
            dependencies=[Depends(require_ai_internal_key)],
        )
        async def ingest_frame(
            request: Request,
            drone_id: Annotated[int, Query(alias="droneId", ge=1)],
            source_id: Annotated[
                str,
                Query(alias="sourceId", min_length=1, max_length=100),
            ],
            session_id: Annotated[
                str,
                Query(alias="sessionId", min_length=1, max_length=36),
            ],
            captured_at: Annotated[
                datetime | None,
                Query(alias="capturedAt"),
            ] = None,
        ) -> dict[str, object]:
            content_type = request.headers.get(
                "content-type",
                "",
            ).split(";", 1)[0]

            if content_type.lower() != "image/jpeg":
                raise HTTPException(
                    status_code=415,
                    detail="Content-Type은 image/jpeg여야 합니다.",
                )

            content_length = request.headers.get("content-length")

            if content_length is not None:
                try:
                    declared_length = int(content_length)
                except ValueError as error:
                    raise HTTPException(
                        status_code=400,
                        detail="Content-Length가 올바르지 않습니다.",
                    ) from error

                if declared_length > ingest_max_payload_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail="JPEG 프레임 용량 제한을 초과했습니다.",
                    )

            jpeg = await request.body()

            if len(jpeg) > ingest_max_payload_bytes:
                raise HTTPException(
                    status_code=413,
                    detail="JPEG 프레임 용량 제한을 초과했습니다.",
                )

            try:
                return ingest_source.submit_jpeg(
                    jpeg,
                    source_id=source_id,
                    session_id=session_id,
                    drone_id=drone_id,
                    captured_at=captured_at,
                )
            except ValueError as error:
                raise HTTPException(
                    status_code=400,
                    detail=str(error),
                ) from error
            except RuntimeError as error:
                raise HTTPException(
                    status_code=503,
                    detail=str(error),
                ) from error

    if isinstance(ingest_source, DjiAndroidBridgeSource):

        @app.get(
            "/api/ingest/dji/status",
            dependencies=[Depends(require_ai_internal_key)],
        )
        def dji_ingest_status() -> dict[str, object]:
            return ingest_source.status()

        @app.post(
            "/api/ingest/dji/stream",
            dependencies=[Depends(require_ai_internal_key)],
        )
        async def ingest_dji_stream(
            request: Request,
            drone_id: Annotated[int, Query(alias="droneId", ge=1)],
            source_id: Annotated[
                str,
                Query(alias="sourceId", min_length=1, max_length=100),
            ],
            session_id: Annotated[
                str,
                Query(alias="sessionId", min_length=1, max_length=36),
            ],
            codec: Annotated[
                str,
                Query(alias="codec", min_length=4, max_length=4),
            ] = "H264",
        ) -> dict[str, object]:
            try:
                normalized_codec = ingest_source.normalize_codec(codec)
            except ValueError as error:
                raise HTTPException(
                    status_code=400,
                    detail=str(error),
                ) from error

            content_type = request.headers.get(
                "content-type",
                "",
            ).split(";", 1)[0].strip().lower()
            expected_content_types = (
                {"video/h264"}
                if normalized_codec == "H264"
                else {"video/h265", "video/hevc"}
            )
            if content_type not in expected_content_types:
                expected = " or ".join(
                    sorted(expected_content_types)
                )
                raise HTTPException(
                    status_code=415,
                    detail=(
                        "DJI encoded stream Content-Type은 "
                        f"{expected}여야 합니다."
                    ),
                )

            try:
                token = ingest_source.begin_stream(
                    source_id=source_id,
                    session_id=session_id,
                    drone_id=drone_id,
                    codec=normalized_codec,
                )
            except ValueError as error:
                raise HTTPException(
                    status_code=400,
                    detail=str(error),
                ) from error
            except RuntimeError as error:
                raise HTTPException(
                    status_code=409,
                    detail=str(error),
                ) from error

            result: dict[str, object] | None = None

            try:
                async for chunk in request.stream():
                    if not chunk:
                        continue
                    await asyncio.to_thread(
                        ingest_source.submit_encoded,
                        token,
                        chunk,
                    )
            except RuntimeError as error:
                raise HTTPException(
                    status_code=503,
                    detail=str(error),
                ) from error
            finally:
                result = await asyncio.to_thread(
                    ingest_source.end_stream,
                    token,
                )

            encoded_bytes = int(
                result.get("encodedBytes", 0)
            )
            decoded_frames = int(
                result.get("decodedFrames", 0)
            )
            decoder_exit_code = int(
                result.get("decoderExitCode", -1)
            )

            if encoded_bytes <= 0:
                raise HTTPException(
                    status_code=400,
                    detail="DJI encoded stream 본문이 비어 있습니다.",
                )
            if decoder_exit_code != 0 or decoded_frames <= 0:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "message": (
                            "DJI encoded stream을 영상 프레임으로 "
                            "디코딩하지 못했습니다."
                        ),
                        "decoderExitCode": decoder_exit_code,
                        "decodedFrames": decoded_frames,
                        "decoderLog": result.get("decoderLog"),
                    },
                )

            return result

    return app


class AnalysisStreamServer:
    def __init__(
        self,
        *,
        hub: AnnotatedFrameHub,
        host: str,
        port: int,
        allowed_origins: tuple[str, ...],
        ingest_source: BrowserUploadSource | None = None,
        ingest_max_payload_bytes: int = 2_000_000,
        performance_monitor: InferencePerformanceMonitor | None = None,
        model_status_provider: Callable[[], dict[str, object]] | None = None,
        internal_security_enabled: bool = True,
        internal_api_key: str = "",
    ) -> None:
        self._hub = hub
        self._host = host
        self._port = port
        self._server = uvicorn.Server(
            uvicorn.Config(
                create_stream_app(
                    hub,
                    allowed_origins=allowed_origins,
                    ingest_source=ingest_source,
                    ingest_max_payload_bytes=ingest_max_payload_bytes,
                    performance_monitor=performance_monitor,
                    model_status_provider=model_status_provider,
                    internal_security_enabled=internal_security_enabled,
                    internal_api_key=internal_api_key,
                ),
                host=host,
                port=port,
                log_level="info",
                access_log=False,
            )
        )
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return

        self._thread = threading.Thread(
            target=self._server.run,
            name="visionflow-ai-stream-server",
            daemon=True,
        )
        self._thread.start()

        deadline = time.monotonic() + 5.0

        while time.monotonic() < deadline:
            if self._server.started:
                print(
                    f"AI 분석 영상 스트림 시작: http://{self._host}:{self._port}",
                    flush=True,
                )
                return

            if not self._thread.is_alive():
                break

            time.sleep(0.05)

        self.close()
        raise RuntimeError(
            f"AI 분석 영상 스트림 서버를 시작하지 못했습니다: {self._host}:{self._port}"
        )

    def close(self) -> None:
        self._hub.close()
        self._server.should_exit = True

        if self._thread is not None:
            self._thread.join(timeout=5.0)

        self._thread = None
