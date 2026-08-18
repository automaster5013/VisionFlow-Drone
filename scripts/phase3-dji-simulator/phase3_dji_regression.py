#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import phase3_dji_simulator as sim


class RegressionError(RuntimeError):
    pass


def utc_instant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_json_bytes(payload: bytes) -> Any:
    if not payload:
        return None
    try:
        return json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError:
        return payload.decode("utf-8", errors="replace")


def raw_request(
    method: str,
    url: str,
    *,
    operator_key: str | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 8.0,
) -> tuple[int, Any]:
    headers = {"Accept": "application/json"}
    data: bytes | None = None

    if operator_key:
        headers[sim.OPERATOR_KEY_HEADER] = operator_key
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")

    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, parse_json_bytes(response.read())
    except HTTPError as error:
        return error.code, parse_json_bytes(error.read())
    except URLError as error:
        raise RegressionError(f"{method} {url} 연결 실패: {error}") from error


def require_status(
    label: str,
    actual: int,
    expected: tuple[int, ...],
) -> None:
    if actual not in expected:
        raise RegressionError(
            f"{label}: 예상 HTTP {expected}, 실제 HTTP {actual}"
        )


def record(
    results: list[dict[str, Any]],
    name: str,
    *,
    status: str = "PASS",
    detail: str = "",
) -> None:
    print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))
    results.append(
        {
            "name": name,
            "status": status,
            "detail": detail,
        }
    )


def ensure_session(
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
            raise RegressionError(
                "ACTIVE Flight Session 응답의 sessionId가 비어 있습니다."
            )
        return session_id, False

    created = sim.create_session(
        backend_url,
        drone_id,
        operator_key,
        f"reg-{run_id}",
    )
    session_id = str(sim.find_value(created, "sessionId") or "").strip()
    if not session_id:
        raise RegressionError(
            "Regression 전용 Flight Session 생성 응답에 sessionId가 없습니다."
        )
    return session_id, True


def test_invalid_drone(
    backend_url: str,
    operator_key: str,
    results: list[dict[str, Any]],
) -> None:
    invalid_id = 2147483647
    status, _ = raw_request(
        "GET",
        f"{backend_url}/api/drones/{invalid_id}",
        operator_key=operator_key,
    )
    require_status("존재하지 않는 droneId", status, (404,))
    record(
        results,
        "존재하지 않는 droneId 거부",
        detail=f"HTTP {status}",
    )


def test_invalid_coordinate_pair(
    backend_url: str,
    drone_id: int,
    session_id: str,
    operator_key: str,
    results: list[dict[str, Any]],
) -> None:
    status, _ = raw_request(
        "PATCH",
        f"{backend_url}/api/drones/{drone_id}/telemetry",
        operator_key=operator_key,
        body={
            "latitude": 37.5665,
            "telemetrySource": "DJI_DEVICE",
            "sourceDeviceId": "phase3-dji-regression",
            "flightSessionId": session_id,
            "lastConnectedAt": datetime.now(timezone.utc)
                .replace(tzinfo=None)
                .isoformat(timespec="milliseconds"),
        },
    )
    require_status("좌표 pair validation", status, (400,))
    record(
        results,
        "불완전 좌표 telemetry 거부",
        detail=f"HTTP {status}; DB write 없음",
    )


def test_missing_depth_event(
    backend_url: str,
    results: list[dict[str, Any]],
) -> None:
    missing_key = f"phase3-regression-missing-{uuid.uuid4().hex}"
    status, _ = raw_request(
        "PUT",
        f"{backend_url}/api/ai/phase3/events/{missing_key}/depth",
        body={
            "estimatedDepthM": 8.5,
            "sceneQ33M": 5.0,
            "sceneQ66M": 12.0,
            "depthBucket": "MID",
            "enrichmentLatencyMs": 10.0,
        },
    )
    require_status("존재하지 않는 Phase3 event depth", status, (404,))
    record(
        results,
        "존재하지 않는 Event depth 거부",
        detail=f"HTTP {status}",
    )


def test_duplicate_event_idempotency(
    backend_url: str,
    drone_id: int,
    session_id: str,
    run_id: str,
    results: list[dict[str, Any]],
) -> tuple[str, Any]:
    duplicate_run_id = f"reg-{run_id}"
    first = sim.create_phase3_event(
        backend_url,
        drone_id,
        session_id,
        duplicate_run_id,
        frame_index=100,
    )
    second = sim.create_phase3_event(
        backend_url,
        drone_id,
        session_id,
        duplicate_run_id,
        frame_index=101,
    )

    first_id = sim.find_value(first, "id")
    second_id = sim.find_value(second, "id")
    first_key = str(sim.find_value(first, "eventKey") or "")
    second_key = str(sim.find_value(second, "eventKey") or "")

    if not first_key or first_key != second_key:
        raise RegressionError(
            "Duplicate Event idempotency: eventKey가 일치하지 않습니다."
        )
    if first_id is None or first_id != second_id:
        raise RegressionError(
            "Duplicate Event idempotency: 동일 eventKey가 다른 eventId를 반환했습니다. "
            f"first={first_id}, second={second_id}"
        )

    record(
        results,
        "Duplicate eventKey idempotency",
        detail=f"eventKey={first_key}; eventId={first_id}",
    )
    return first_key, first_id


def test_duplicate_readback(
    backend_url: str,
    drone_id: int,
    event_key: str,
    expected_event_id: Any,
    operator_key: str,
    results: list[dict[str, Any]],
) -> None:
    event = sim.verify_phase3_event(
        backend_url,
        drone_id,
        event_key,
        operator_key,
    )
    actual_id = event.get("id")
    if actual_id != expected_event_id:
        raise RegressionError(
            "Duplicate Event readback ID 불일치: "
            f"expected={expected_event_id}, actual={actual_id}"
        )
    record(
        results,
        "Duplicate Event readback correlation",
        detail=f"eventId={actual_id}",
    )


def write_evidence(
    evidence_dir: Path,
    run_id: str,
    payload: dict[str, Any],
) -> Path:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / f"regression-{run_id}.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "VisionFlow Phase 3 DJI simulator regression suite: "
            "validation + negative path + duplicate event idempotency"
        )
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8080")
    parser.add_argument("--drone-id", type=int, default=1)
    parser.add_argument(
        "--evidence-dir",
        default="artifacts/phase3-dji-simulator",
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

    results: list[dict[str, Any]] = []
    created_session = False
    completed_session = False
    session_id: str | None = None

    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex[:8]
    )

    try:
        operator_key = sim.require_operator_key(root, env_file)

        print("[STEP] Regression preflight")
        health = sim.json_request(
            "GET",
            f"{backend_url}/actuator/health",
        )
        if not isinstance(health, dict) or health.get("status") != "UP":
            raise RegressionError("Backend actuator health가 UP이 아닙니다.")
        record(results, "Backend health", detail="UP")

        drone = sim.json_request(
            "GET",
            f"{backend_url}/api/drones/{args.drone_id}",
            operator_key=operator_key,
        )
        response_id = sim.find_value(drone, "id")
        if response_id is not None and int(response_id) != args.drone_id:
            raise RegressionError("Drone 조회 응답 ID가 요청값과 다릅니다.")
        record(
            results,
            "Drone 조회",
            detail=f"droneId={args.drone_id}",
        )

        session_id, created_session = ensure_session(
            backend_url,
            args.drone_id,
            operator_key,
            run_id,
        )
        record(
            results,
            "Flight Session 준비",
            detail=(
                f"sessionId={session_id}; "
                + ("REGRESSION_CREATED" if created_session else "REUSED_ACTIVE")
            ),
        )

        print("[STEP] Negative-path validation")
        test_invalid_drone(
            backend_url,
            operator_key,
            results,
        )
        test_invalid_coordinate_pair(
            backend_url,
            args.drone_id,
            session_id,
            operator_key,
            results,
        )
        test_missing_depth_event(
            backend_url,
            results,
        )

        print("[STEP] Idempotency validation")
        event_key, event_id = test_duplicate_event_idempotency(
            backend_url,
            args.drone_id,
            session_id,
            run_id,
            results,
        )
        test_duplicate_readback(
            backend_url,
            args.drone_id,
            event_key,
            event_id,
            operator_key,
            results,
        )

        if created_session:
            completed = sim.finish_session(
                backend_url,
                args.drone_id,
                session_id,
                operator_key,
            )
            status = str(sim.find_value(completed, "status") or "")
            if status.upper() != "COMPLETED":
                raise RegressionError(
                    f"Regression 전용 Flight Session complete status={status}"
                )
            completed_session = True
            session_state = "COMPLETED"
            record(
                results,
                "Regression Flight Session complete",
                detail=f"sessionId={session_id}",
            )
        else:
            session_state = "REUSED_ACTIVE"
            print(
                "[INFO] 기존 ACTIVE Session을 재사용했으므로 "
                "complete/abort하지 않습니다."
            )

        evidence = {
            "runId": run_id,
            "suite": "phase3-dji-simulator-regression",
            "backendUrl": backend_url,
            "droneId": args.drone_id,
            "sessionId": session_id,
            "sessionCreatedByRegression": created_session,
            "sessionFinalState": session_state,
            "duplicateEventKey": event_key,
            "duplicateEventId": event_id,
            "tests": results,
            "passed": sum(1 for item in results if item["status"] == "PASS"),
            "failed": sum(1 for item in results if item["status"] != "PASS"),
            "completedAt": utc_instant(),
        }
        evidence_path = write_evidence(
            evidence_dir,
            run_id,
            evidence,
        )
        record(
            results,
            "Regression Evidence 저장",
            detail=str(evidence_path),
        )

        print("")
        print("=== PHASE 3 DJI SIMULATOR REGRESSION: PASS ===")
        print(f"testsPassed={evidence['passed']}")
        print("testsFailed=0")
        print(f"eventKey={event_key}")
        print(f"evidence={evidence_path}")
        return 0

    except (RegressionError, sim.SimulatorError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        if created_session and not completed_session:
            sim.abort_session_best_effort(
                backend_url,
                args.drone_id,
                session_id,
                operator_key if "operator_key" in locals() else "",
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
