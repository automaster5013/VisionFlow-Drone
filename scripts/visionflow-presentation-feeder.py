from __future__ import annotations

import json
import math
import os
import signal
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime

import cv2

VIDEO = "/tmp/presentation-dummy.mp4"
PID_FILE = "/tmp/visionflow-presentation-feeder.pid"
STATUS_FILE = "/tmp/visionflow-presentation-feeder.status.json"
API = "http://127.0.0.1:8000/api/ingest/frame"
running = True
playback: dict[str, object] = {}


def playback_position(elapsed: float, source_fps: float, frame_count: int) -> tuple[int, int]:
    absolute_frame = int(max(0.0, elapsed) * source_fps)
    return absolute_frame % frame_count, absolute_frame // frame_count + 1


def stop(*_: object) -> None:
    global running
    running = False


def save_status(frames: int, loops: int, error: str | None = None) -> None:
    with open(STATUS_FILE + ".tmp", "w", encoding="utf-8") as handle:
        json.dump({"running": running, "frames": frames, "loops": loops, "error": error, "updatedAt": datetime.now(UTC).isoformat(), **playback}, handle)
    os.replace(STATUS_FILE + ".tmp", STATUS_FILE)


def main() -> None:
    global running
    key = os.environ.get("VISIONFLOW_AI_INTERNAL_KEY", "")
    if len(key) < 32:
        raise RuntimeError("AI internal key is unavailable")
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    with open(PID_FILE, "w", encoding="ascii") as handle:
        handle.write(str(os.getpid()))

    frames = 0
    loops = 0
    failure = None
    capture = cv2.VideoCapture(VIDEO)
    try:
        if not capture.isOpened():
            raise RuntimeError("presentation video could not be opened")
        source_fps = capture.get(cv2.CAP_PROP_FPS)
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        target_fps = float(os.environ.get("VISIONFLOW_PRESENTATION_FPS", "15"))
        if not math.isfinite(source_fps) or source_fps <= 0 or frame_count <= 0:
            raise RuntimeError("presentation video timing metadata is invalid")
        if not math.isfinite(target_fps) or not 1 <= target_fps <= 30:
            raise RuntimeError("VISIONFLOW_PRESENTATION_FPS must be between 1 and 30")
        target_fps = min(target_fps, source_fps)
        started = time.monotonic()
        next_frame = 0
        previous_loop = 1
        previous_absolute_frame = -1
        skipped = 0
        while running:
            elapsed = time.monotonic() - started
            target_frame, loops = playback_position(elapsed, source_fps, frame_count)
            absolute_frame = (loops - 1) * frame_count + target_frame
            if absolute_frame == previous_absolute_frame:
                time.sleep(1.0 / target_fps)
                continue
            # Read only the image belonging to the current wall-clock position.
            # Never replay a backlog of old frames after decoding/network delays.
            if loops != previous_loop or target_frame < next_frame or target_frame - next_frame > source_fps:
                capture.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                next_frame = target_frame
            while next_frame <= target_frame:
                if not capture.grab():
                    raise RuntimeError("presentation frame could not be decoded")
                next_frame += 1
            ok, image = capture.retrieve()
            if not ok:
                raise RuntimeError("presentation frame could not be retrieved")
            skipped += max(0, absolute_frame - previous_absolute_frame - 1)
            previous_absolute_frame = absolute_frame
            previous_loop = loops
            encoded, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not encoded:
                raise RuntimeError("presentation JPEG encoding failed")
            query = urllib.parse.urlencode({"droneId": 1, "sourceId": "presentation-dummy-001", "sessionId": "presentation-server-loop", "capturedAt": datetime.now(UTC).isoformat()})
            request = urllib.request.Request(f"{API}?{query}", data=jpeg.tobytes(), headers={"Content-Type": "image/jpeg", "Accept": "application/json", "X-VisionFlow-AI-Key": key}, method="POST")
            with urllib.request.urlopen(request, timeout=5) as response:
                response.read()
            frames += 1
            playback.update(sourceFps=source_fps, targetFps=target_fps, sourceFrameIndex=target_frame,
                            sourceTimeSeconds=round(absolute_frame / source_fps, 3),
                            elapsedSeconds=round(elapsed, 3), skippedFrames=skipped,
                            playbackRate=1.0, durationSeconds=round(frame_count / source_fps, 3))
            save_status(frames, loops)
            now = time.monotonic()
            next_tick = started + (math.floor((now - started) * target_fps) + 1) / target_fps
            time.sleep(max(0.0, next_tick - now))
    except Exception as error:
        failure = str(error)
        raise
    finally:
        capture.release()
        running = False
        save_status(frames, loops, failure)
        try:
            os.remove(PID_FILE)
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
