from __future__ import annotations

import shutil
import subprocess
import threading
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.domain import FramePacket, VideoSourceType
from app.sources.browser_upload import BrowserUploadSource


@dataclass(slots=True)
class _ActiveEncodedStream:
    token: str
    source_id: str
    session_id: str
    drone_id: int
    codec: str
    process: subprocess.Popen[bytes]
    encoded_bytes_start: int
    decoded_frames_start: int
    reader_thread: threading.Thread | None = None
    stderr_thread: threading.Thread | None = None


class DjiAndroidBridgeSource(BrowserUploadSource):
    """Decode DJI MSDK H.264/H.265 bytes into DJI_LIVE FramePackets."""

    _JPEG_SOI = b"\xff\xd8"
    _JPEG_EOI = b"\xff\xd9"
    _READ_SIZE = 64 * 1024
    _MAX_JPEG_PIPE_BUFFER = 8 * 1024 * 1024
    _SUPPORTED_CODECS = {"H264", "H265"}
    _SUPPORTED_LOG_LEVELS = {
        "quiet",
        "panic",
        "fatal",
        "error",
        "warning",
        "info",
    }

    def __init__(
        self,
        *,
        fps: float,
        queue_capacity: int,
        ffmpeg_executable: str = "ffmpeg",
        decoder_log_level: str = "warning",
    ) -> None:
        if fps <= 0:
            raise ValueError("DJI Android Bridge fps는 0보다 커야 합니다.")
        if queue_capacity < 1:
            raise ValueError(
                "DJI Android Bridge queue capacity는 1 이상이어야 합니다."
            )

        executable = ffmpeg_executable.strip()
        if not executable:
            raise ValueError("DJI Android Bridge FFmpeg 실행 파일이 필요합니다.")

        log_level = decoder_log_level.strip().lower()
        if log_level not in self._SUPPORTED_LOG_LEVELS:
            supported = ", ".join(sorted(self._SUPPORTED_LOG_LEVELS))
            raise ValueError(
                "AI_DJI_BRIDGE_DECODER_LOG_LEVEL 값이 올바르지 않습니다: "
                f"{log_level!r}; supported={supported}"
            )

        super().__init__(
            fps=fps,
            queue_capacity=queue_capacity,
        )
        self._ffmpeg_executable = executable
        self._decoder_log_level = log_level
        self._stream_lock = threading.Lock()
        self._active_stream: _ActiveEncodedStream | None = None
        self._bridge_closed = False
        self._connections = 0
        self._encoded_chunks = 0
        self._encoded_bytes = 0
        self._decoded_frames = 0
        self._decoder_failures = 0
        self._last_decoder_exit_code: int | None = None
        self._last_decoder_logs: deque[str] = deque(maxlen=20)
        self._last_encoded_at: datetime | None = None
        self._last_decoded_at: datetime | None = None

    def begin_stream(
        self,
        *,
        source_id: str,
        session_id: str,
        drone_id: int,
        codec: str,
    ) -> str:
        normalized_source_id = source_id.strip()
        normalized_session_id = session_id.strip()
        normalized_codec = self.normalize_codec(codec)

        if not normalized_source_id or len(normalized_source_id) > 100:
            raise ValueError("DJI sourceId는 1~100자여야 합니다.")
        if not normalized_session_id or len(normalized_session_id) > 36:
            raise ValueError("DJI sessionId는 1~36자여야 합니다.")
        if drone_id < 1:
            raise ValueError("DJI droneId는 1 이상이어야 합니다.")

        executable = shutil.which(self._ffmpeg_executable)
        if executable is None:
            raise RuntimeError(
                "DJI Android Bridge decoder를 시작할 수 없습니다: "
                f"FFmpeg 실행 파일을 찾을 수 없음 ({self._ffmpeg_executable})"
            )

        with self._stream_lock:
            if self._bridge_closed:
                raise RuntimeError("DJI Android Bridge 입력이 이미 종료되었습니다.")
            if self._active_stream is not None:
                raise RuntimeError(
                    "DJI Android Bridge에는 동시에 하나의 encoded publisher만 "
                    "연결할 수 있습니다."
                )

            try:
                process = subprocess.Popen(
                    self._decoder_command(
                        executable=executable,
                        codec=normalized_codec,
                    ),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0,
                )
            except OSError as error:
                raise RuntimeError(
                    "DJI Android Bridge FFmpeg process를 시작하지 못했습니다."
                ) from error

            token = uuid4().hex
            active = _ActiveEncodedStream(
                token=token,
                source_id=normalized_source_id,
                session_id=normalized_session_id,
                drone_id=drone_id,
                codec=normalized_codec,
                process=process,
                encoded_bytes_start=self._encoded_bytes,
                decoded_frames_start=self._decoded_frames,
            )
            self._active_stream = active
            self._connections += 1

            reader = threading.Thread(
                target=self._read_decoder_stdout,
                args=(active,),
                name="visionflow-dji-decoder-stdout",
                daemon=True,
            )
            stderr = threading.Thread(
                target=self._read_decoder_stderr,
                args=(active,),
                name="visionflow-dji-decoder-stderr",
                daemon=True,
            )
            active.reader_thread = reader
            active.stderr_thread = stderr
            reader.start()
            stderr.start()
            return token

    def submit_encoded(
        self,
        token: str,
        payload: bytes,
    ) -> None:
        if not payload:
            return

        with self._stream_lock:
            active = self._require_active(token)
            process = active.process
            stdin = process.stdin

        if stdin is None:
            self._record_decoder_failure()
            raise RuntimeError("DJI decoder stdin을 사용할 수 없습니다.")

        try:
            stdin.write(payload)
            stdin.flush()
        except (BrokenPipeError, OSError) as error:
            self._record_decoder_failure()
            raise RuntimeError(
                "DJI encoded stream을 FFmpeg decoder에 전달하지 못했습니다."
            ) from error

        now = datetime.now(UTC)
        with self._stream_lock:
            self._encoded_chunks += 1
            self._encoded_bytes += len(payload)
            self._last_encoded_at = now

    def end_stream(self, token: str) -> dict[str, object]:
        with self._stream_lock:
            active = self._require_active(token)
            process = active.process
            stdin = process.stdin

        if stdin is not None:
            try:
                stdin.close()
            except OSError:
                pass

        try:
            return_code = process.wait(timeout=10.0)
        except subprocess.TimeoutExpired:
            process.kill()
            return_code = process.wait(timeout=3.0)
            self._record_decoder_failure()

        for thread in (
            active.reader_thread,
            active.stderr_thread,
        ):
            if thread is not None:
                thread.join(timeout=2.0)

        with self._stream_lock:
            if return_code != 0:
                self._decoder_failures += 1
            self._last_decoder_exit_code = return_code

            encoded_bytes = self._encoded_bytes - active.encoded_bytes_start
            decoded_frames = self._decoded_frames - active.decoded_frames_start
            decoder_log = (
                self._last_decoder_logs[-1]
                if self._last_decoder_logs
                else None
            )

            if (
                self._active_stream is not None
                and self._active_stream.token == token
            ):
                self._active_stream = None

        return {
            "accepted": encoded_bytes > 0 and decoded_frames > 0,
            "sourceId": active.source_id,
            "sessionId": active.session_id,
            "droneId": active.drone_id,
            "sourceType": VideoSourceType.DJI_LIVE.value,
            "codec": active.codec,
            "encodedBytes": encoded_bytes,
            "decodedFrames": decoded_frames,
            "decoderExitCode": return_code,
            "decoderLog": decoder_log,
        }

    def read(self) -> FramePacket | None:
        packet = super().read()
        if packet is None:
            return None

        return FramePacket(
            source_id=packet.source_id,
            session_id=packet.session_id,
            source_type=VideoSourceType.DJI_LIVE,
            drone_id=packet.drone_id,
            frame_index=packet.frame_index,
            captured_at=packet.captured_at,
            image=packet.image,
        )

    def status(self) -> dict[str, object]:
        base = super().status()

        with self._stream_lock:
            active = self._active_stream
            base.update(
                {
                    "inputMode": "ANDROID_BRIDGE",
                    "activeStream": active is not None,
                    "codec": active.codec if active is not None else None,
                    "sourceId": (
                        active.source_id if active is not None else None
                    ),
                    "sessionId": (
                        active.session_id if active is not None else None
                    ),
                    "droneId": (
                        active.drone_id if active is not None else None
                    ),
                    "connections": self._connections,
                    "encodedChunks": self._encoded_chunks,
                    "encodedBytes": self._encoded_bytes,
                    "decodedFrames": self._decoded_frames,
                    "decoderFailures": self._decoder_failures,
                    "lastDecoderExitCode": self._last_decoder_exit_code,
                    "lastDecoderLog": (
                        self._last_decoder_logs[-1]
                        if self._last_decoder_logs
                        else None
                    ),
                    "lastEncodedAt": self._iso(self._last_encoded_at),
                    "lastDecodedAt": self._iso(self._last_decoded_at),
                }
            )

        return base

    def close(self) -> None:
        with self._stream_lock:
            self._bridge_closed = True
            token = (
                self._active_stream.token
                if self._active_stream is not None
                else None
            )

        if token is not None:
            try:
                self.end_stream(token)
            except (RuntimeError, ValueError):
                pass

        super().close()

    @classmethod
    def normalize_codec(cls, value: str) -> str:
        normalized = value.strip().upper().replace(".", "")
        if normalized == "HEVC":
            normalized = "H265"
        if normalized not in cls._SUPPORTED_CODECS:
            raise ValueError(
                "DJI encoded stream codec은 H264 또는 H265여야 합니다."
            )
        return normalized

    def _decoder_command(
        self,
        *,
        executable: str,
        codec: str,
    ) -> list[str]:
        input_format = "h264" if codec == "H264" else "hevc"

        return [
            executable,
            "-hide_banner",
            "-loglevel",
            self._decoder_log_level,
            "-f",
            input_format,
            "-i",
            "pipe:0",
            "-an",
            "-sn",
            "-dn",
            "-vf",
            f"fps={self.fps:.6f}",
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "-q:v",
            "5",
            "pipe:1",
        ]

    def _read_decoder_stdout(
        self,
        active: _ActiveEncodedStream,
    ) -> None:
        stdout = active.process.stdout
        if stdout is None:
            self._record_decoder_failure()
            return

        buffer = bytearray()

        try:
            while True:
                chunk = stdout.read(self._READ_SIZE)
                if not chunk:
                    return

                buffer.extend(chunk)
                self._drain_jpeg_buffer(
                    active=active,
                    buffer=buffer,
                )
        except OSError:
            self._record_decoder_failure()

    def _drain_jpeg_buffer(
        self,
        *,
        active: _ActiveEncodedStream,
        buffer: bytearray,
    ) -> None:
        while True:
            start = buffer.find(self._JPEG_SOI)
            if start < 0:
                self._discard_oversized_buffer(buffer)
                return

            if start > 0:
                del buffer[:start]

            end = buffer.find(
                self._JPEG_EOI,
                len(self._JPEG_SOI),
            )
            if end < 0:
                self._discard_oversized_buffer(buffer)
                return

            end += len(self._JPEG_EOI)
            jpeg = bytes(buffer[:end])
            del buffer[:end]
            self._submit_decoded_jpeg(
                active=active,
                jpeg=jpeg,
            )

    def _discard_oversized_buffer(self, buffer: bytearray) -> None:
        if len(buffer) <= self._MAX_JPEG_PIPE_BUFFER:
            return

        buffer.clear()
        self._record_decoder_failure()

    def _submit_decoded_jpeg(
        self,
        *,
        active: _ActiveEncodedStream,
        jpeg: bytes,
    ) -> None:
        captured_at = datetime.now(UTC)

        try:
            super().submit_jpeg(
                jpeg,
                source_id=active.source_id,
                session_id=active.session_id,
                drone_id=active.drone_id,
                captured_at=captured_at,
            )
        except (ValueError, RuntimeError):
            self._record_decoder_failure()
            return

        with self._stream_lock:
            self._decoded_frames += 1
            self._last_decoded_at = captured_at

    def _read_decoder_stderr(
        self,
        active: _ActiveEncodedStream,
    ) -> None:
        stderr = active.process.stderr
        if stderr is None:
            return

        try:
            for raw in iter(stderr.readline, b""):
                text = raw.decode(
                    "utf-8",
                    errors="replace",
                ).strip()
                if not text:
                    continue
                with self._stream_lock:
                    self._last_decoder_logs.append(text)
        except OSError:
            return

    def _require_active(
        self,
        token: str,
    ) -> _ActiveEncodedStream:
        active = self._active_stream
        if active is None or active.token != token:
            raise ValueError("활성 DJI encoded stream token이 아닙니다.")
        return active

    def _record_decoder_failure(self) -> None:
        with self._stream_lock:
            self._decoder_failures += 1

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None
