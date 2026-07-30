from __future__ import annotations

import argparse
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_LATITUDE = 37.5665
DEFAULT_LONGITUDE = 126.9780
METERS_PER_LATITUDE_DEGREE = 111_320.0


@dataclass
class DroneSimState:
    drone_id: int
    drone_code: str
    center_latitude: float
    center_longitude: float
    base_altitude: float
    battery: float
    angle: float
    last_payload: dict[str, Any] = field(default_factory=dict)


def api_request(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    url = f"{base_url.rstrip('/')}{path}"
    body = (
        json.dumps(payload).encode("utf-8")
        if payload is not None
        else None
    )

    request = Request(
        url=url,
        data=body,
        method=method,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=5) as response:
            response_body = response.read().decode("utf-8")
            return json.loads(response_body) if response_body else None
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"HTTP {error.code} {method} {url}: {detail}"
        ) from error
    except URLError as error:
        raise RuntimeError(
            f"백엔드 연결 실패 {method} {url}: {error.reason}"
        ) from error


def extract_drone_list(payload: Any) -> list[dict[str, Any]]:
    current = payload

    for _ in range(4):
        if isinstance(current, list):
            return [item for item in current if isinstance(item, dict)]

        if not isinstance(current, dict):
            break

        for key in ("data", "content", "items"):
            if key in current:
                current = current[key]
                break
        else:
            break

    raise RuntimeError("GET /api/drones 응답에서 드론 배열을 찾지 못했습니다.")


def optional_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    return number if math.isfinite(number) else None


def create_states(
    drones: list[dict[str, Any]],
    selected_ids: set[int] | None,
) -> list[DroneSimState]:
    selected = []

    for drone in drones:
        drone_id = drone.get("id")

        if not isinstance(drone_id, int):
            continue

        if selected_ids is not None and drone_id not in selected_ids:
            continue

        selected.append(drone)

    selected.sort(key=lambda item: int(item["id"]))
    total = max(len(selected), 1)
    states: list[DroneSimState] = []

    for index, drone in enumerate(selected):
        drone_id = int(drone["id"])
        latitude = optional_float(drone.get("latitude"))
        longitude = optional_float(drone.get("longitude"))
        altitude = optional_float(drone.get("altitude"))
        battery = optional_float(drone.get("batteryLevel"))

        center_latitude = (
            latitude
            if latitude is not None
            else DEFAULT_LATITUDE + index * 0.0015
        )
        center_longitude = (
            longitude
            if longitude is not None
            else DEFAULT_LONGITUDE + index * 0.0015
        )

        states.append(
            DroneSimState(
                drone_id=drone_id,
                drone_code=str(
                    drone.get("droneCode") or f"DRONE-{drone_id:03d}"
                ),
                center_latitude=center_latitude,
                center_longitude=center_longitude,
                base_altitude=altitude if altitude is not None else 35.0,
                battery=battery if battery is not None else 100.0,
                angle=(2.0 * math.pi * index) / total,
            )
        )

    return states


def create_telemetry_payload(
    state: DroneSimState,
    radius_meters: float,
) -> dict[str, Any]:
    state.angle = (state.angle + 0.09) % (2.0 * math.pi)

    east_meters = radius_meters * math.sin(state.angle)
    north_meters = (
        radius_meters * 0.55 * math.sin(2.0 * state.angle)
    )

    latitude = (
        state.center_latitude
        + north_meters / METERS_PER_LATITUDE_DEGREE
    )

    longitude_scale = (
        METERS_PER_LATITUDE_DEGREE
        * math.cos(math.radians(state.center_latitude))
    )
    longitude = state.center_longitude + east_meters / longitude_scale

    altitude = max(
        5.0,
        state.base_altitude + 8.0 * math.sin(1.5 * state.angle),
    )

    state.battery = max(15.0, state.battery - 0.03)

    payload: dict[str, Any] = {
        "latitude": round(latitude, 7),
        "longitude": round(longitude, 7),
        "altitude": round(altitude, 2),
        "batteryLevel": int(round(state.battery)),
        "lastConnectedAt": datetime.now().isoformat(
            timespec="milliseconds"
        ),
    }

    state.last_payload = payload
    return payload


def update_status(
    base_url: str,
    drone_id: int,
    status: str,
) -> None:
    api_request(
        base_url,
        "PATCH",
        f"/api/drones/{drone_id}/status",
        {"status": status},
    )


def send_telemetry(
    base_url: str,
    state: DroneSimState,
    radius_meters: float,
) -> dict[str, Any]:
    payload = create_telemetry_payload(state, radius_meters)

    api_request(
        base_url,
        "PATCH",
        f"/api/drones/{state.drone_id}/telemetry",
        payload,
    )

    return payload


def finish_simulation(
    base_url: str,
    states: list[DroneSimState],
) -> None:
    print("\n드론 상태를 OFFLINE으로 전환합니다.")

    for state in states:
        try:
            update_status(base_url, state.drone_id, "OFFLINE")

            if state.last_payload:
                final_payload = {
                    **state.last_payload,
                    "lastConnectedAt": datetime.now().isoformat(
                        timespec="milliseconds"
                    ),
                }
                api_request(
                    base_url,
                    "PATCH",
                    f"/api/drones/{state.drone_id}/telemetry",
                    final_payload,
                )
        except RuntimeError as error:
            print(f"[종료 경고] {state.drone_code}: {error}")


def run(args: argparse.Namespace) -> None:
    payload = api_request(args.base_url, "GET", "/api/drones")
    drones = extract_drone_list(payload)
    selected_ids = set(args.drone_ids) if args.drone_ids else None
    states = create_states(drones, selected_ids)

    if not states:
        raise RuntimeError("시뮬레이션할 드론이 없습니다.")

    print(
        f"시뮬레이션 시작: {len(states)}대, "
        f"주기 {args.interval:.1f}초, 반경 {args.radius_m:.0f}m"
    )
    print("중지하려면 Ctrl+C를 누르세요.\n")

    for state in states:
        try:
            update_status(args.base_url, state.drone_id, "FLYING")
        except RuntimeError as error:
            print(f"[상태 경고] {state.drone_code}: {error}")

    deadline = (
        time.monotonic() + args.duration
        if args.duration > 0
        else None
    )
    cycle = 0

    try:
        with ThreadPoolExecutor(
            max_workers=min(16, len(states))
        ) as executor:
            while deadline is None or time.monotonic() < deadline:
                started_at = time.monotonic()
                futures = {
                    executor.submit(
                        send_telemetry,
                        args.base_url,
                        state,
                        args.radius_m,
                    ): state
                    for state in states
                }

                successes = 0

                for future in as_completed(futures):
                    state = futures[future]

                    try:
                        telemetry = future.result()
                        successes += 1
                        print(
                            f"[{datetime.now():%H:%M:%S}] "
                            f"{state.drone_code} "
                            f"lat={telemetry['latitude']:.7f} "
                            f"lng={telemetry['longitude']:.7f} "
                            f"alt={telemetry['altitude']:.2f}m "
                            f"battery={telemetry['batteryLevel']}%"
                        )
                    except RuntimeError as error:
                        print(f"[전송 실패] {state.drone_code}: {error}")

                cycle += 1
                print(
                    f"-- cycle {cycle}: "
                    f"{successes}/{len(states)} 전송 성공 --"
                )

                elapsed = time.monotonic() - started_at
                time.sleep(max(0.0, args.interval - elapsed))
    except KeyboardInterrupt:
        print("\n사용자가 시뮬레이션을 중지했습니다.")
    finally:
        finish_simulation(args.base_url, states)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VisionFlow 다중 드론 텔레메트리 시뮬레이터"
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8080",
        help="Spring Boot 백엔드 주소",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="텔레메트리 전송 주기(초)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=120.0,
        help="실행 시간(초). 0이면 Ctrl+C까지 계속 실행",
    )
    parser.add_argument(
        "--radius-m",
        type=float,
        default=120.0,
        help="비행 경로 반경(미터)",
    )
    parser.add_argument(
        "--drone-ids",
        nargs="*",
        type=int,
        help="시뮬레이션할 드론 ID. 생략하면 전체 드론",
    )

    args = parser.parse_args()

    if args.interval < 0.2:
        parser.error("--interval은 0.2초 이상이어야 합니다.")

    if args.duration < 0:
        parser.error("--duration은 0 이상이어야 합니다.")

    if args.radius_m <= 0:
        parser.error("--radius-m은 0보다 커야 합니다.")

    return args


if __name__ == "__main__":
    try:
        run(parse_args())
    except RuntimeError as error:
        raise SystemExit(f"시뮬레이터 오류: {error}") from error