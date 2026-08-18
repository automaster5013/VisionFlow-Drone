#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import phase3_dji_simulator as sim


class ReplayError(RuntimeError):
    pass


SUMMARY_PATTERN = re.compile(
    r"PHASE3_SUMMARY "
    r"FRAMES_ANALYZED=(?P<frames>\d+) "
    r"PPE_SAMPLES=(?P<ppe>\d+) "
    r"POSE_SAMPLES=(?P<pose>\d+) "
    r"POSE_ASSIGNED=(?P<pose_assigned>\d+) "
    r"POSE_UNASSIGNED=(?P<pose_unassigned>\d+) "
    r"DEPTH_TRIGGER_ATTEMPTS=(?P<triggers>\d+) "
    r"DEPTH_TRIGGERS_ACCEPTED=(?P<accepted>\d+) "
    r"DEPTH_TRIGGERS_REJECTED=(?P<rejected>\d+) "
    r"DEPTH_RESULTS=(?P<depth>\d+)"
)


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def command_output(args: list[str], *, timeout: float = 30.0) -> str:
    try:
        result = subprocess.run(
            args,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as error:
        raise ReplayError(
            f"명령을 찾을 수 없습니다: {args[0]}"
        ) from error
    except subprocess.CalledProcessError as error:
        output = (
            (error.stdout or "")
            + "\n"
            + (error.stderr or "")
        ).strip()
        raise ReplayError(
            f"명령 실패: {' '.join(args)}\n{output}"
        ) from error
    except subprocess.TimeoutExpired as error:
        raise ReplayError(
            f"명령 timeout: {' '.join(args)}"
        ) from error

    return result.stdout.strip()


def inspect_runtime(
    *,
    ai_container: str,
    backend_container: str,
    network: str,
    image: str,
) -> None:
    ai_state = command_output(
        [
            "docker",
            "inspect",
            ai_container,
            "--format",
            "{{.State.Health.Status}}",
        ]
    )
    backend_state = command_output(
        [
            "docker",
            "inspect",
            backend_container,
            "--format",
            "{{.State.Health.Status}}",
        ]
    )
    image_id = command_output(
        [
            "docker",
            "image",
            "inspect",
            image,
            "--format",
            "{{.Id}}",
        ]
    )
    network_id = command_output(
        [
            "docker",
            "network",
            "inspect",
            network,
            "--format",
            "{{.Id}}",
        ]
    )

    if ai_state.lower() != "healthy":
        raise ReplayError(
            f"{ai_container} health={ai_state}; healthy가 필요합니다."
        )
    if backend_state.lower() != "healthy":
        raise ReplayError(
            f"{backend_container} health={backend_state}; healthy가 필요합니다."
        )
    if not image_id or not network_id:
        raise ReplayError("AI image 또는 Docker network를 확인할 수 없습니다.")


def ensure_session(
    *,
    backend_url: str,
    drone_id: int,
    operator_key: str,
    run_id: str,
) -> tuple[str, bool]:
    active = sim.find_active_session(
        backend_url,
        drone_id,
        operator_key,
    )
    if active is not None:
        session_id = str(active.get("sessionId", "")).strip()
        if not session_id:
            raise ReplayError(
                "ACTIVE Flight Session에 sessionId가 없습니다."
            )
        return session_id, False

    created = sim.create_session(
        backend_url,
        drone_id,
        operator_key,
        f"video-{run_id}",
    )
    session_id = str(
        sim.find_value(created, "sessionId") or ""
    ).strip()
    if not session_id:
        raise ReplayError(
            "Replay 전용 Flight Session 생성 응답에 sessionId가 없습니다."
        )
    return session_id, True


def recent_events(
    *,
    backend_url: str,
    drone_id: int,
    operator_key: str,
) -> list[dict[str, Any]]:
    payload = sim.json_request(
        "GET",
        (
            f"{backend_url}/api/ai/phase3/events"
            f"?droneId={drone_id}&limit=200"
        ),
        operator_key=operator_key,
    )
    return [
        item
        for item in sim.as_list(payload)
        if isinstance(item, dict)
    ]


def parse_summary(log_text: str) -> dict[str, int] | None:
    matches = list(SUMMARY_PATTERN.finditer(log_text))
    if not matches:
        return None
    match = matches[-1]
    return {
        key: int(value)
        for key, value in match.groupdict().items()
    }


def docker_replay_command(
    *,
    root: Path,
    video_path: Path,
    image: str,
    network: str,
    backend_container: str,
    container_name: str,
    source_id: str,
    session_id: str,
    drone_id: int,
    max_frames: int,
) -> list[str]:
    ai_root = root / "03_ai-server" / "visionflow-ai"
    models = ai_root / "models"

    return [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
        "--gpus",
        "all",
        "--network",
        network,
        "-v",
        f"{ai_root}:/workspace:ro",
        "-v",
        f"{models}:/app/models:ro",
        "-v",
        f"{video_path}:/app/data/dji-replay/input.mp4:ro",
        "-w",
        "/workspace",
        "-e",
        "PYTHONPATH=/workspace",
        "-e",
        "AI_SOURCE_TYPE=DJI_LIVE",
        "-e",
        f"AI_SOURCE_ID={source_id}",
        "-e",
        f"AI_SESSION_ID={session_id}",
        "-e",
        f"AI_DRONE_ID={drone_id}",
        "-e",
        "AI_DJI_INPUT_MODE=REPLAY_FILE",
        "-e",
        "AI_DJI_REPLAY_VIDEO_PATH=/app/data/dji-replay/input.mp4",
        "-e",
        "AI_DJI_REPLAY_LOOP=true",
        "-e",
        "AI_DJI_REPLAY_REALTIME=false",
        "-e",
        "AI_MODEL_PROFILE=phase3-dji-replay-gpu",
        "-e",
        "AI_MODEL_PATH=/app/models/yolo26m.pt",
        "-e",
        "AI_REQUIRE_CUDA=true",
        "-e",
        "AI_REQUIRE_LOCAL_MODEL=true",
        "-e",
        "AI_DEVICE=0",
        "-e",
        "AI_CONFIDENCE=0.35",
        "-e",
        "AI_IOU=0.70",
        "-e",
        "AI_IMAGE_SIZE=640",
        "-e",
        "AI_PHASE3_ENABLED=true",
        "-e",
        "AI_PHASE3_REPORT_EVENTS=true",
        "-e",
        (
            "AI_BACKEND_PHASE3_EVENT_URL="
            f"http://{backend_container}:8080/api/ai/phase3/events"
        ),
        "-e",
        "AI_PHASE3_PPE_MODEL_PATH=/app/models/ppe-yolo26m-best.pt",
        "-e",
        "AI_PHASE3_PPE_TARGET_FPS=5.0",
        "-e",
        "AI_PHASE3_POSE_ENABLED=false",
        "-e",
        "AI_PHASE3_DEPTH_ENABLED=true",
        "-e",
        "AI_PHASE3_DEPTH_MODEL_PATH=/app/models/yolo26m-depth.pt",
        "-e",
        "AI_PHASE3_DEPTH_IMAGE_SIZE=768",
        "-e",
        "AI_PHASE3_DEPTH_QUEUE_CAPACITY=4",
        "-e",
        "AI_REPORT_EVENTS=false",
        "-e",
        "AI_STREAM_ENABLED=false",
        "-e",
        "AI_SAVE_ANNOTATED_VIDEO=false",
        "-e",
        "AI_SHOW_PREVIEW=false",
        "-e",
        f"AI_MAX_FRAMES={max_frames}",
        "-e",
        "VISIONFLOW_AI_INTERNAL_SECURITY_ENABLED=false",
        image,
        "python",
        "-m",
        "app.main",
    ]


def run_replay(
    command: list[str],
    *,
    timeout: float,
) -> tuple[int, str]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        output = (
            (error.stdout or "")
            + "\n"
            + (error.stderr or "")
        )
        return 124, output

    return (
        result.returncode,
        (result.stdout or "") + (result.stderr or ""),
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a recorded MP4 through the DJI_LIVE Phase 3 AI pipeline "
            "in an isolated one-off GPU container."
        )
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--video",
        default=(
            "03_ai-server/visionflow-ai/data/dummy/sample.mp4"
        ),
    )
    parser.add_argument("--env-file", default=".env")
    parser.add_argument(
        "--backend-url",
        default="http://127.0.0.1:8080",
    )
    parser.add_argument("--drone-id", type=int, default=1)
    parser.add_argument("--max-frames", type=int, default=180)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--image", default="visionflow-ai-server")
    parser.add_argument(
        "--network",
        default="visionflow_visionflow-network",
    )
    parser.add_argument(
        "--ai-container",
        default="visionflow-ai",
    )
    parser.add_argument(
        "--backend-container",
        default="visionflow-backend",
    )
    parser.add_argument(
        "--evidence-dir",
        default="artifacts/phase3-dji-simulator",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.repo_root).resolve()
    video = Path(args.video)
    if not video.is_absolute():
        video = root / video
    video = video.resolve()

    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = root / env_file

    evidence_dir = Path(args.evidence_dir)
    if not evidence_dir.is_absolute():
        evidence_dir = root / evidence_dir

    if args.drone_id < 1:
        print("[FAIL] --drone-id는 1 이상이어야 합니다.", file=sys.stderr)
        return 2
    if args.max_frames <= 0:
        print("[FAIL] --max-frames는 1 이상이어야 합니다.", file=sys.stderr)
        return 2
    if not video.is_file():
        print(f"[FAIL] MP4 파일이 없습니다: {video}", file=sys.stderr)
        return 2

    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    short_id = run_id[-8:]
    source_id = f"phase3-dji-replay-{short_id}"
    container_name = f"visionflow-ai-dji-replay-{short_id}"
    log_path = evidence_dir / f"video-replay-{run_id}.log"
    evidence_path = evidence_dir / f"video-replay-{run_id}.json"

    created_session = False
    session_id: str | None = None

    try:
        operator_key = sim.require_operator_key(root, env_file)

        print("[STEP] Replay preflight")
        inspect_runtime(
            ai_container=args.ai_container,
            backend_container=args.backend_container,
            network=args.network,
            image=args.image,
        )
        print("[PASS] Docker AI/Backend/Image/Network 확인")

        health = sim.json_request(
            "GET",
            f"{args.backend_url.rstrip('/')}/actuator/health",
        )
        if not isinstance(health, dict) or health.get("status") != "UP":
            raise ReplayError("Backend health가 UP이 아닙니다.")
        print("[PASS] Backend health - UP")

        session_id, created_session = ensure_session(
            backend_url=args.backend_url.rstrip("/"),
            drone_id=args.drone_id,
            operator_key=operator_key,
            run_id=run_id,
        )
        print(
            "[PASS] Flight Session 준비 - "
            f"sessionId={session_id}; "
            + (
                "REPLAY_CREATED"
                if created_session
                else "REUSED_ACTIVE"
            )
        )

        before = recent_events(
            backend_url=args.backend_url.rstrip("/"),
            drone_id=args.drone_id,
            operator_key=operator_key,
        )
        before_ids = {
            item.get("id")
            for item in before
            if item.get("id") is not None
        }

        print(
            "[STEP] DJI_LIVE MP4 Replay - "
            f"video={video.name}, maxFrames={args.max_frames}"
        )
        command = docker_replay_command(
            root=root,
            video_path=video,
            image=args.image,
            network=args.network,
            backend_container=args.backend_container,
            container_name=container_name,
            source_id=source_id,
            session_id=session_id,
            drone_id=args.drone_id,
            max_frames=args.max_frames,
        )
        return_code, log_text = run_replay(
            command,
            timeout=args.timeout,
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            log_text,
            encoding="utf-8",
        )

        summary = parse_summary(log_text)
        if return_code != 0:
            raise ReplayError(
                f"Replay container exit={return_code}; "
                f"log={log_path}"
            )
        if summary is None:
            raise ReplayError(
                f"PHASE3_SUMMARY를 찾지 못했습니다: {log_path}"
            )
        if summary["frames"] <= 0 or summary["ppe"] <= 0:
            raise ReplayError(
                "AI pipeline은 종료됐지만 frame/PPE sample이 없습니다: "
                f"{summary}"
            )

        print(
            "[PASS] AI Replay pipeline - "
            f"frames={summary['frames']}, "
            f"ppeSamples={summary['ppe']}, "
            f"triggers={summary['triggers']}, "
            f"depthResults={summary['depth']}"
        )

        after = recent_events(
            backend_url=args.backend_url.rstrip("/"),
            drone_id=args.drone_id,
            operator_key=operator_key,
        )
        replay_events = [
            item
            for item in after
            if item.get("id") not in before_ids
            and str(item.get("sourceId", "")) == source_id
            and str(item.get("sessionId", "")) == session_id
        ]

        if not replay_events:
            evidence = {
                "runId": run_id,
                "status": "NO_PHASE3_EVENT",
                "sourceId": source_id,
                "sourceType": "DJI_LIVE",
                "video": str(video),
                "sessionId": session_id,
                "sessionCreatedByReplay": created_session,
                "phase3Summary": summary,
                "log": str(log_path),
                "completedAt": utc_now(),
            }
            write_json(evidence_path, evidence)
            raise ReplayError(
                "Replay 영상에서는 Backend Phase3 Event가 생성되지 않았습니다. "
                "파이프라인 frame/PPE 처리는 PASS이며, 사람/PPE trigger가 있는 "
                "다른 MP4로 재검증이 필요합니다. "
                f"evidence={evidence_path}"
            )

        invalid_source_types = [
            item
            for item in replay_events
            if str(item.get("sourceType", "")) != "DJI_LIVE"
        ]
        if invalid_source_types:
            raise ReplayError(
                "Replay Event 중 sourceType != DJI_LIVE 항목이 있습니다."
            )

        depth_enriched = [
            item
            for item in replay_events
            if item.get("depthBucket") not in (None, "")
        ]

        event_ids = [item.get("id") for item in replay_events]
        event_keys = [
            str(item.get("eventKey", ""))
            for item in replay_events
        ]

        evidence = {
            "runId": run_id,
            "status": "PASS",
            "backendUrl": args.backend_url.rstrip("/"),
            "droneId": args.drone_id,
            "sourceId": source_id,
            "sourceType": "DJI_LIVE",
            "video": str(video),
            "sessionId": session_id,
            "sessionCreatedByReplay": created_session,
            "phase3Summary": summary,
            "backendEventCount": len(replay_events),
            "backendEventIds": event_ids,
            "backendEventKeys": event_keys,
            "depthEnrichedEventCount": len(depth_enriched),
            "log": str(log_path),
            "completedAt": utc_now(),
        }
        write_json(evidence_path, evidence)

        print(
            "[PASS] Backend/MySQL Phase3 correlation - "
            f"events={len(replay_events)}, "
            f"depthEnriched={len(depth_enriched)}"
        )
        print(f"[PASS] Evidence 저장 - {evidence_path}")

        if created_session:
            completed = sim.finish_session(
                args.backend_url.rstrip("/"),
                args.drone_id,
                session_id,
                operator_key,
            )
            status = str(
                sim.find_value(completed, "status") or ""
            ).upper()
            if status != "COMPLETED":
                raise ReplayError(
                    "Replay 전용 Flight Session complete 실패: "
                    f"status={status}"
                )
            print("[PASS] Replay 전용 Flight Session complete")
        else:
            print(
                "[INFO] 기존 ACTIVE Session 재사용 - "
                "complete/abort하지 않습니다."
            )

        print("")
        print("=== PHASE 3 DJI VIDEO REPLAY E2E: PASS ===")
        print(f"sourceId={source_id}")
        print(f"sessionId={session_id}")
        print(f"events={len(replay_events)}")
        print(f"depthEnriched={len(depth_enriched)}")
        print(f"evidence={evidence_path}")
        return 0

    except (ReplayError, sim.SimulatorError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        if created_session and session_id:
            sim.abort_session_best_effort(
                args.backend_url.rstrip("/"),
                args.drone_id,
                session_id,
                (
                    operator_key
                    if "operator_key" in locals()
                    else ""
                ),
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
