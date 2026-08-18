#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

OPERATOR_KEY_HEADER = "X-VisionFlow-Operator-Key"
SOURCE_DEVICE_ID = "phase3-dji-simulator"
PHASE3_SOURCE_ID = "phase3-dji-simulator"


class SimulatorError(RuntimeError):
    pass


def utc_instant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def utc_local_datetime() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(tzinfo=None)
        .isoformat(timespec="milliseconds")
    )


def load_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def json_request(
    method: str,
    url: str,
    *,
    operator_key: str | None = None,
    body: dict[str, Any] | None = None,
    expected: tuple[int, ...] = (200,),
    timeout: float = 8.0,
) -> Any:
    headers = {"Accept": "application/json"}
    data: bytes | None = None

    if operator_key:
        headers[OPERATOR_KEY_HEADER] = operator_key
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")

    request = Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            status = response.status
            payload = response.read()
    except HTTPError as error:
        payload = error.read()
        message = payload.decode("utf-8", errors="replace")
        raise SimulatorError(
            f"{method} {url} -> HTTP {error.code}: {message}"
        ) from error
    except URLError as error:
        raise SimulatorError(f"{method} {url} 연결 실패: {error}") from error

    if status not in expected:
        raise SimulatorError(
            f"{method} {url} -> 예상 HTTP {expected}, 실제 HTTP {status}"
        )

    if not payload:
        return None
    try:
        return json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise SimulatorError(
            f"{method} {url} 응답이 JSON이 아닙니다."
        ) from error


def unwrap_data(payload: Any) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def as_list(payload: Any) -> list[Any]:
    value = unwrap_data(payload)
    return value if isinstance(value, list) else []


def find_value(payload: Any, key: str) -> Any:
    value = unwrap_data(payload)
    if isinstance(value, dict) and key in value:
        return value[key]
    if isinstance(payload, dict) and key in payload:
        return payload[key]
    return None


def require_operator_key(root: Path, env_file: Path) -> str:
    file_values = load_env_file(env_file)
    operator_key = (
        os.environ.get("VISIONFLOW_OPERATOR_KEY", "").strip()
        or file_values.get("VISIONFLOW_OPERATOR_KEY", "").strip()
    )
    if len(operator_key) < 24:
        raise SimulatorError(
            "VISIONFLOW_OPERATOR_KEY를 찾을 수 없거나 길이가 너무 짧습니다. "
            f"환경변수 또는 {env_file}를 확인하세요."
        )
    return operator_key


def print_step(name: str, detail: str = "") -> None:
    suffix = f" - {detail}" if detail else ""
    print(f"[STEP] {name}{suffix}")


def print_pass(name: str, detail: str = "") -> None:
    suffix = f" - {detail}" if detail else ""
    print(f"[PASS] {name}{suffix}")


def find_active_session(
    backend_url: str,
    drone_id: int,
    operator_key: str,
) -> dict[str, Any] | None:
    payload = json_request(
        "GET",
        f"{backend_url}/api/drones/{drone_id}/flight-sessions?limit=100",
        operator_key=operator_key,
    )
    for item in as_list(payload):
        if isinstance(item, dict) and str(item.get("status", "")).upper() == "ACTIVE":
            return item
    return None


def create_session(
    backend_url: str,
    drone_id: int,
    operator_key: str,
    run_id: str,
) -> dict[str, Any]:
    return json_request(
        "POST",
        f"{backend_url}/api/drones/{drone_id}/flight-sessions",
        operator_key=operator_key,
        body={
            "name": f"Phase3 DJI Simulator {run_id}",
            "description": (
                "Software-only Phase 3 DJI telemetry/event E2E validation. "
                "No physical aircraft is used."
            ),
            "sourceDeviceId": SOURCE_DEVICE_ID,
        },
        expected=(200, 201),
    )


def send_telemetry(
    backend_url: str,
    drone_id: int,
    session_id: str,
    operator_key: str,
    *,
    samples: int,
    interval: float,
    latitude: float,
    longitude: float,
    altitude: float,
) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    for index in range(samples):
        progress = index / max(samples - 1, 1)
        payload = {
            "latitude": round(latitude + (index * 0.000015), 7),
            "longitude": round(longitude + (index * 0.000020), 7),
            "altitude": round(altitude + (progress * 3.0), 2),
            "batteryLevel": max(0, 96 - (index // 4)),
            "heading": round((45.0 + (index * 7.5)) % 360.0, 2),
            "pitch": round(-2.0 + (progress * 4.0), 2),
            "roll": round(-1.0 + (progress * 2.0), 2),
            "groundSpeed": round(2.5 + (progress * 1.5), 2),
            "horizontalAccuracy": 0.8,
            "verticalAccuracy": 1.2,
            "telemetrySource": "DJI_DEVICE",
            "sourceDeviceId": SOURCE_DEVICE_ID,
            "flightSessionId": session_id,
            "lastConnectedAt": utc_local_datetime(),
        }
        json_request(
            "PATCH",
            f"{backend_url}/api/drones/{drone_id}/telemetry",
            operator_key=operator_key,
            body=payload,
        )
        sent.append(payload)
        if interval > 0 and index + 1 < samples:
            time.sleep(interval)

    return sent


def create_phase3_event(
    backend_url: str,
    drone_id: int,
    session_id: str,
    run_id: str,
    frame_index: int,
) -> dict[str, Any]:
    event_key = f"phase3-dji-sim-{run_id}"
    payload = json_request(
        "POST",
        f"{backend_url}/api/ai/phase3/events",
        body={
            "eventKey": event_key,
            "sourceId": PHASE3_SOURCE_ID,
            "sessionId": session_id,
            "sourceType": "DJI_LIVE",
            "droneId": drone_id,
            "trackId": 1,
            "frameIndex": frame_index,
            "capturedAt": utc_instant(),
            "ppeState": "UNKNOWN",
            "noHelmetRate": 0.0,
            "helmetRate": 0.0,
            "unknownRate": 1.0,
            "streakSeconds": 0.0,
        },
        expected=(200, 201),
    )
    if find_value(payload, "eventKey") != event_key:
        raise SimulatorError("Phase 3 Event 응답의 eventKey가 요청값과 다릅니다.")
    return payload


def enrich_phase3_event(
    backend_url: str,
    event_key: str,
) -> dict[str, Any]:
    payload = json_request(
        "PUT",
        f"{backend_url}/api/ai/phase3/events/{event_key}/depth",
        body={
            "estimatedDepthM": 8.5,
            "sceneQ33M": 5.0,
            "sceneQ66M": 12.0,
            "depthBucket": "MID",
            "enrichmentLatencyMs": 14.5,
        },
    )
    if find_value(payload, "depthBucket") != "MID":
        raise SimulatorError("Phase 3 depth enrichment 결과가 MID가 아닙니다.")
    return payload


def verify_telemetry_history(
    backend_url: str,
    drone_id: int,
    session_id: str,
    operator_key: str,
    expected_samples: int,
    history_from: str,
) -> tuple[int, list[dict[str, Any]]]:
    query = urlencode(
        {
            "from": history_from,
            "limit": max(100, expected_samples * 4),
        }
    )
    payload = json_request(
        "GET",
        f"{backend_url}/api/drones/{drone_id}/telemetry/history?{query}",
        operator_key=operator_key,
    )

    matches: list[dict[str, Any]] = []
    for item in as_list(payload):
        if not isinstance(item, dict):
            continue
        if (
            item.get("flightSessionId") == session_id
            and item.get("sourceDeviceId") == SOURCE_DEVICE_ID
        ):
            matches.append(item)

    if len(matches) < expected_samples:
        raise SimulatorError(
            "Telemetry history 검증 실패: "
            f"예상 {expected_samples}건 이상, 실제 simulator correlation {len(matches)}건"
        )
    return len(matches), matches


def verify_phase3_event(
    backend_url: str,
    drone_id: int,
    event_key: str,
    operator_key: str,
) -> dict[str, Any]:
    query = urlencode({"droneId": drone_id, "limit": 100})
    payload = json_request(
        "GET",
        f"{backend_url}/api/ai/phase3/events?{query}",
        operator_key=operator_key,
    )
    for item in as_list(payload):
        if isinstance(item, dict) and item.get("eventKey") == event_key:
            return item
    raise SimulatorError(f"Phase 3 Event 조회에서 eventKey={event_key}를 찾지 못했습니다.")


def finish_session(
    backend_url: str,
    drone_id: int,
    session_id: str,
    operator_key: str,
) -> dict[str, Any]:
    return json_request(
        "POST",
        f"{backend_url}/api/drones/{drone_id}/flight-sessions/{session_id}/complete",
        operator_key=operator_key,
    )


def abort_session_best_effort(
    backend_url: str,
    drone_id: int,
    session_id: str | None,
    operator_key: str,
) -> None:
    if not session_id:
        return
    try:
        json_request(
            "POST",
            f"{backend_url}/api/drones/{drone_id}/flight-sessions/{session_id}/abort",
            operator_key=operator_key,
        )
        print("[RECOVERY] Simulator가 생성한 Flight Session을 ABORT 처리했습니다.")
    except SimulatorError as error:
        print(f"[WARN] Flight Session abort 실패: {error}", file=sys.stderr)


def write_evidence(
    evidence_dir: Path,
    run_id: str,
    evidence: dict[str, Any],
) -> Path:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    output = evidence_dir / f"{run_id}.json"
    output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "VisionFlow Phase 3 DJI software simulator: "
            "DJI_DEVICE telemetry + DJI_LIVE Phase 3 Event E2E"
        )
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8080")
    parser.add_argument("--drone-id", type=int, default=1)
    parser.add_argument("--samples", type=int, default=12)
    parser.add_argument("--interval", type=float, default=0.25)
    parser.add_argument("--latitude", type=float, default=37.5665)
    parser.add_argument("--longitude", type=float, default=126.9780)
    parser.add_argument("--altitude", type=float, default=18.0)
    parser.add_argument(
        "--evidence-dir",
        default="artifacts/phase3-dji-simulator",
    )
    parser.add_argument(
        "--require-new-session",
        action="store_true",
        help="ACTIVE Flight Session이 있으면 재사용하지 않고 실패합니다.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Backend/인증/droneId만 확인하고 DB 쓰기는 수행하지 않습니다.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.repo_root).resolve()
    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = root / env_file

    evidence_dir = Path(args.evidence_dir)
    if not evidence_dir.is_absolute():
        evidence_dir = root / evidence_dir

    backend_url = args.backend_url.rstrip("/")
    if args.drone_id < 1:
        print("[FAIL] --drone-id는 1 이상이어야 합니다.", file=sys.stderr)
        return 2
    if args.samples < 1:
        print("[FAIL] --samples는 1 이상이어야 합니다.", file=sys.stderr)
        return 2
    if args.interval < 0:
        print("[FAIL] --interval은 0 이상이어야 합니다.", file=sys.stderr)
        return 2

    created_session = False
    completed_session = False
    session_id: str | None = None

    try:
        operator_key = require_operator_key(root, env_file)

        print_step("Backend health")
        health = json_request("GET", f"{backend_url}/actuator/health")
        if not isinstance(health, dict) or health.get("status") != "UP":
            raise SimulatorError("Backend actuator health가 UP이 아닙니다.")
        print_pass("Backend health", "UP")

        print_step("Drone 조회", f"droneId={args.drone_id}")
        drone_payload = json_request(
            "GET",
            f"{backend_url}/api/drones/{args.drone_id}",
            operator_key=operator_key,
        )
        drone_id = find_value(drone_payload, "id")
        if drone_id is not None and int(drone_id) != args.drone_id:
            raise SimulatorError("Drone 조회 응답 ID가 요청값과 다릅니다.")
        print_pass("Drone 조회", f"droneId={args.drone_id}")

        if args.check_only:
            print("[PASS] CHECK-ONLY 완료 - DB write 없음")
            return 0

        run_id = (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "-"
            + uuid.uuid4().hex[:8]
        )

        print_step("Flight Session 확인")
        active = find_active_session(
            backend_url,
            args.drone_id,
            operator_key,
        )
        if active is not None:
            if args.require_new_session:
                raise SimulatorError(
                    "기존 ACTIVE Flight Session이 있습니다: "
                    f"{active.get('sessionId')}. "
                    "--require-new-session 없이 실행하면 기존 세션을 안전하게 재사용합니다."
                )
            session_id = str(active.get("sessionId", "")).strip()
            if not session_id:
                raise SimulatorError("ACTIVE Flight Session의 sessionId가 비어 있습니다.")
            print_pass(
                "Flight Session 재사용",
                f"sessionId={session_id} (기존 세션은 완료/중단하지 않음)",
            )
        else:
            session = create_session(
                backend_url,
                args.drone_id,
                operator_key,
                run_id,
            )
            session_id = str(find_value(session, "sessionId") or "").strip()
            if not session_id:
                raise SimulatorError("Flight Session 생성 응답에 sessionId가 없습니다.")
            created_session = True
            print_pass("Flight Session 생성", f"sessionId={session_id}")

        history_from = utc_local_datetime()
        print_step("DJI_DEVICE telemetry 송신", f"samples={args.samples}")
        sent = send_telemetry(
            backend_url,
            args.drone_id,
            session_id,
            operator_key,
            samples=args.samples,
            interval=args.interval,
            latitude=args.latitude,
            longitude=args.longitude,
            altitude=args.altitude,
        )
        print_pass("DJI_DEVICE telemetry 송신", f"{len(sent)}건")

        print_step("DJI_LIVE Phase 3 Event 생성")
        event = create_phase3_event(
            backend_url,
            args.drone_id,
            session_id,
            run_id,
            frame_index=max(args.samples - 1, 0),
        )
        event_key = str(find_value(event, "eventKey"))
        print_pass(
            "DJI_LIVE Phase 3 Event 생성",
            f"eventKey={event_key}",
        )

        print_step("Phase 3 depth enrichment")
        enriched = enrich_phase3_event(backend_url, event_key)
        print_pass(
            "Phase 3 depth enrichment",
            f"depthBucket={find_value(enriched, 'depthBucket')}",
        )

        print_step("Telemetry history correlation")
        history_count, _ = verify_telemetry_history(
            backend_url,
            args.drone_id,
            session_id,
            operator_key,
            args.samples,
            history_from,
        )
        print_pass(
            "Telemetry history correlation",
            f"matched={history_count}",
        )

        print_step("Phase 3 Event 조회 correlation")
        verified_event = verify_phase3_event(
            backend_url,
            args.drone_id,
            event_key,
            operator_key,
        )
        print_pass(
            "Phase 3 Event 조회 correlation",
            f"eventId={verified_event.get('id')}",
        )

        if created_session:
            print_step("Flight Session complete")
            completed = finish_session(
                backend_url,
                args.drone_id,
                session_id,
                operator_key,
            )
            completed_status = str(find_value(completed, "status") or "")
            if completed_status.upper() != "COMPLETED":
                raise SimulatorError(
                    f"Flight Session complete 응답 status={completed_status}"
                )
            completed_session = True
            print_pass(
                "Flight Session complete",
                f"sessionId={session_id}",
            )
        else:
            completed_status = "REUSED_ACTIVE"
            print("[INFO] 기존 ACTIVE Session을 재사용했으므로 complete하지 않습니다.")

        evidence = {
            "runId": run_id,
            "backendUrl": backend_url,
            "droneId": args.drone_id,
            "sessionId": session_id,
            "sessionCreatedBySimulator": created_session,
            "sessionFinalState": completed_status,
            "telemetrySource": "DJI_DEVICE",
            "sourceDeviceId": SOURCE_DEVICE_ID,
            "telemetrySamplesSent": len(sent),
            "telemetryHistoryMatched": history_count,
            "phase3SourceType": "DJI_LIVE",
            "phase3EventKey": event_key,
            "phase3EventId": verified_event.get("id"),
            "depthBucket": find_value(enriched, "depthBucket"),
            "estimatedDepthM": find_value(enriched, "estimatedDepthM"),
            "completedAt": utc_instant(),
        }
        evidence_path = write_evidence(
            evidence_dir,
            run_id,
            evidence,
        )
        print_pass("Evidence 저장", str(evidence_path))
        print("")
        print("=== PHASE 3 DJI SOFTWARE SIMULATOR: PASS ===")
        print(f"droneId={args.drone_id}")
        print(f"sessionId={session_id}")
        print(f"telemetrySamples={len(sent)}")
        print(f"eventKey={event_key}")
        print(f"evidence={evidence_path}")
        return 0

    except SimulatorError as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        if created_session and not completed_session:
            abort_session_best_effort(
                backend_url,
                args.drone_id,
                session_id,
                operator_key if "operator_key" in locals() else "",
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
