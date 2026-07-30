#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


TARGET_PATH = "/api/ingest/frame"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_ref(openapi: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    ref = value.get("$ref")
    if not ref:
        return value
    if not ref.startswith("#/"):
        raise RuntimeError(f"Unsupported OpenAPI ref: {ref}")
    current: Any = openapi
    for part in ref[2:].split("/"):
        current = current[part]
    if not isinstance(current, dict):
        raise RuntimeError(f"Resolved OpenAPI ref is not an object: {ref}")
    return current


def find_openapi(
    client: httpx.Client,
    candidates: list[str],
) -> tuple[str, dict[str, Any]]:
    errors: list[str] = []
    for base in candidates:
        normalized = base.rstrip("/")
        url = normalized + "/openapi.json"
        try:
            response = client.get(url)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and isinstance(payload.get("paths"), dict):
                return normalized, payload
        except Exception as error:
            errors.append(f"{url}: {error}")
    raise RuntimeError("OpenAPI discovery failed:\n" + "\n".join(errors))


def find_operation(openapi: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    paths = openapi.get("paths", {})
    direct = paths.get(TARGET_PATH)
    if isinstance(direct, dict) and isinstance(direct.get("post"), dict):
        return TARGET_PATH, direct["post"]

    candidates: list[tuple[int, str, dict[str, Any]]] = []
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        operation = path_item.get("post")
        if not isinstance(operation, dict):
            continue
        searchable = " ".join(
            [
                path,
                str(operation.get("operationId", "")),
                str(operation.get("summary", "")),
            ]
        ).lower()
        score = int("ingest" in searchable) * 10 + int("frame" in searchable) * 10
        if score:
            candidates.append((score, path, operation))

    if not candidates:
        raise RuntimeError("POST frame-ingest endpoint was not found.")
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][1], candidates[0][2]


def normalize(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def metadata_values(
    *,
    source_id: str,
    session_id: str,
    drone_id: int,
    frame_index: int,
    captured_at: str,
) -> dict[str, str]:
    return {
        "sourceid": source_id,
        "sessionid": session_id,
        "droneid": str(drone_id),
        "frameindex": str(frame_index),
        "capturedat": captured_at,
        "sourcetype": "DUMMY_VIDEO",
    }


def value_for(
    name: str,
    schema: dict[str, Any],
    values: dict[str, str],
) -> str:
    key = normalize(name)
    if key in values:
        return values[key]

    if "source" in key and "id" in key:
        return values["sourceid"]
    if "session" in key and "id" in key:
        return values["sessionid"]
    if "drone" in key and "id" in key:
        return values["droneid"]
    if "frame" in key and ("index" in key or "number" in key):
        return values["frameindex"]
    if "capture" in key and ("at" in key or "time" in key):
        return values["capturedat"]
    if "source" in key and "type" in key:
        return values["sourcetype"]

    default = schema.get("default")
    if default is not None:
        return str(default)
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return str(enum[0])
    value_type = schema.get("type")
    if value_type in {"integer", "number"}:
        return "0"
    if value_type == "boolean":
        return "false"
    return ""


def declared_parameters(
    openapi: dict[str, Any],
    operation: dict[str, Any],
    *,
    source_id: str,
    session_id: str,
    drone_id: int,
    frame_index: int,
    captured_at: str,
) -> tuple[dict[str, str], dict[str, str]]:
    query: dict[str, str] = {}
    headers: dict[str, str] = {}
    values = metadata_values(
        source_id=source_id,
        session_id=session_id,
        drone_id=drone_id,
        frame_index=frame_index,
        captured_at=captured_at,
    )

    for raw in operation.get("parameters", []):
        if not isinstance(raw, dict):
            continue
        parameter = resolve_ref(openapi, raw)
        name = str(parameter.get("name", ""))
        location = parameter.get("in")
        raw_schema = parameter.get("schema", {})
        schema = resolve_ref(openapi, raw_schema) if isinstance(raw_schema, dict) else {}
        value = value_for(name, schema, values)
        if location == "query":
            query[name] = value
        elif location == "header":
            headers[name] = value

    return query, headers


def conventional_metadata(
    *,
    source_id: str,
    session_id: str,
    drone_id: int,
    frame_index: int,
    captured_at: str,
) -> tuple[dict[str, str], dict[str, str]]:
    query = {
        "sourceId": source_id,
        "sessionId": session_id,
        "droneId": str(drone_id),
        "frameIndex": str(frame_index),
        "capturedAt": captured_at,
        "sourceType": "DUMMY_VIDEO",
        "source_id": source_id,
        "session_id": session_id,
        "drone_id": str(drone_id),
        "frame_index": str(frame_index),
        "captured_at": captured_at,
        "source_type": "DUMMY_VIDEO",
    }
    headers = {
        "X-Source-Id": source_id,
        "X-Session-Id": session_id,
        "X-Drone-Id": str(drone_id),
        "X-Frame-Index": str(frame_index),
        "X-Captured-At": captured_at,
        "X-Source-Type": "DUMMY_VIDEO",
    }
    return query, headers


def request_body_contract(
    openapi: dict[str, Any],
    operation: dict[str, Any],
) -> dict[str, Any] | None:
    raw = operation.get("requestBody")
    if not isinstance(raw, dict):
        return None
    return resolve_ref(openapi, raw)


def multipart_from_openapi(
    openapi: dict[str, Any],
    operation: dict[str, Any],
    jpeg: bytes,
    *,
    source_id: str,
    session_id: str,
    drone_id: int,
    frame_index: int,
    captured_at: str,
) -> dict[str, Any] | None:
    body = request_body_contract(openapi, operation)
    if body is None:
        return None
    content = body.get("content", {})
    if not isinstance(content, dict) or "multipart/form-data" not in content:
        return None

    media = content["multipart/form-data"]
    if not isinstance(media, dict):
        return None
    raw_schema = media.get("schema", {})
    schema = resolve_ref(openapi, raw_schema) if isinstance(raw_schema, dict) else {}
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return None

    values = metadata_values(
        source_id=source_id,
        session_id=session_id,
        drone_id=drone_id,
        frame_index=frame_index,
        captured_at=captured_at,
    )
    files: dict[str, Any] = {}
    binary_found = False

    for name, raw_prop in properties.items():
        prop = resolve_ref(openapi, raw_prop) if isinstance(raw_prop, dict) else {}
        if prop.get("format") == "binary":
            files[name] = ("e2e-frame.jpg", jpeg, "image/jpeg")
            binary_found = True
        else:
            files[name] = (None, value_for(name, prop, values))

    return files if binary_found else None


def strategies_for_frame(
    openapi: dict[str, Any],
    operation: dict[str, Any],
    jpeg: bytes,
    *,
    source_id: str,
    session_id: str,
    drone_id: int,
    frame_index: int,
) -> list[dict[str, Any]]:
    captured_at = utc_now()
    declared_query, declared_headers = declared_parameters(
        openapi,
        operation,
        source_id=source_id,
        session_id=session_id,
        drone_id=drone_id,
        frame_index=frame_index,
        captured_at=captured_at,
    )
    conventional_query, conventional_headers = conventional_metadata(
        source_id=source_id,
        session_id=session_id,
        drone_id=drone_id,
        frame_index=frame_index,
        captured_at=captured_at,
    )

    combined_query = {**conventional_query, **declared_query}
    combined_headers = {**conventional_headers, **declared_headers}
    multipart = multipart_from_openapi(
        openapi,
        operation,
        jpeg,
        source_id=source_id,
        session_id=session_id,
        drone_id=drone_id,
        frame_index=frame_index,
        captured_at=captured_at,
    )

    strategies: list[dict[str, Any]] = []

    if multipart is not None:
        strategies.append(
            {
                "name": "openapi-multipart",
                "files": multipart,
                "params": declared_query,
                "headers": declared_headers,
            }
        )

    # Expected contract for a Request-based FastAPI endpoint:
    # raw JPEG bytes plus metadata in declared query/header parameters.
    strategies.extend(
        [
            {
                "name": "raw-jpeg-declared-and-conventional-metadata",
                "content": jpeg,
                "params": combined_query,
                "headers": {
                    **combined_headers,
                    "Content-Type": "image/jpeg",
                },
            },
            {
                "name": "raw-jpeg-declared-metadata",
                "content": jpeg,
                "params": declared_query,
                "headers": {
                    **declared_headers,
                    "Content-Type": "image/jpeg",
                },
            },
            {
                "name": "conventional-multipart",
                "files": {
                    "file": ("e2e-frame.jpg", jpeg, "image/jpeg"),
                    "frame": ("e2e-frame.jpg", jpeg, "image/jpeg"),
                    "image": ("e2e-frame.jpg", jpeg, "image/jpeg"),
                    **{
                        key: (None, value)
                        for key, value in conventional_query.items()
                    },
                },
                "params": declared_query,
                "headers": declared_headers,
            },
        ]
    )
    return strategies


def send(
    client: httpx.Client,
    url: str,
    strategy: dict[str, Any],
) -> httpx.Response:
    kwargs: dict[str, Any] = {
        "params": strategy.get("params", {}),
        "headers": strategy.get("headers", {}),
    }
    if "files" in strategy:
        kwargs["files"] = strategy["files"]
    else:
        kwargs["content"] = strategy.get("content", b"")
    return client.post(url, **kwargs)


def choose_strategy(
    client: httpx.Client,
    url: str,
    openapi: dict[str, Any],
    operation: dict[str, Any],
    jpeg: bytes,
    *,
    source_id: str,
    session_id: str,
    drone_id: int,
) -> tuple[dict[str, Any], httpx.Response, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    for strategy in strategies_for_frame(
        openapi,
        operation,
        jpeg,
        source_id=source_id,
        session_id=session_id,
        drone_id=drone_id,
        frame_index=1,
    ):
        response = send(client, url, strategy)
        attempts.append(
            {
                "strategy": strategy["name"],
                "statusCode": response.status_code,
                "response": response.text[:1000],
            }
        )
        if 200 <= response.status_code < 300:
            return strategy, response, attempts

    raise RuntimeError(
        "All frame-ingest request strategies failed: "
        + json.dumps(attempts, ensure_ascii=False)
    )


def rebuild_strategy(
    selected_name: str,
    openapi: dict[str, Any],
    operation: dict[str, Any],
    jpeg: bytes,
    *,
    source_id: str,
    session_id: str,
    drone_id: int,
    frame_index: int,
) -> dict[str, Any]:
    strategies = strategies_for_frame(
        openapi,
        operation,
        jpeg,
        source_id=source_id,
        session_id=session_id,
        drone_id=drone_id,
        frame_index=frame_index,
    )
    for strategy in strategies:
        if strategy["name"] == selected_name:
            return strategy
    raise RuntimeError(f"Selected strategy disappeared: {selected_name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default="/app/data/dummy/test-input.jpg")
    parser.add_argument("--frames", type=int, default=30)
    parser.add_argument("--fps", type=float, default=5.0)
    parser.add_argument("--drone-id", type=int, default=1)
    parser.add_argument("--source-id")
    parser.add_argument("--session-id")
    parser.add_argument("--base-url", action="append")
    args = parser.parse_args()

    if args.frames < 5:
        raise RuntimeError("--frames must be at least 5.")
    if args.fps <= 0 or args.fps > 10:
        raise RuntimeError("--fps must be greater than 0 and at most 10.")

    fixture = Path(args.fixture)
    if not fixture.is_file():
        raise RuntimeError(f"Fixture was not found: {fixture}")
    jpeg = fixture.read_bytes()
    if len(jpeg) < 100:
        raise RuntimeError(f"Fixture is too small: {fixture}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    source_id = args.source_id or f"visionflow-e2e-gate-{stamp}"
    session_id = args.session_id or str(uuid.uuid4())
    base_candidates = args.base_url or [
        "http://127.0.0.1:8000",
        "http://127.0.0.1:8001",
    ]

    timeout = httpx.Timeout(20.0, connect=5.0)
    responses: list[dict[str, Any]] = []
    with httpx.Client(timeout=timeout) as client:
        base_url, openapi = find_openapi(client, base_candidates)
        path, operation = find_operation(openapi)
        url = base_url + path

        started = time.monotonic()
        interval = 1.0 / args.fps
        next_send = started

        selected, first_response, attempts = choose_strategy(
            client,
            url,
            openapi,
            operation,
            jpeg,
            source_id=source_id,
            session_id=session_id,
            drone_id=args.drone_id,
        )
        selected_name = str(selected["name"])
        responses.append(
            {
                "frameIndex": 1,
                "statusCode": first_response.status_code,
                "body": first_response.text[:500],
            }
        )
        next_send += interval
        remaining = next_send - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)

        for frame_index in range(2, args.frames + 1):
            strategy = rebuild_strategy(
                selected_name,
                openapi,
                operation,
                jpeg,
                source_id=source_id,
                session_id=session_id,
                drone_id=args.drone_id,
                frame_index=frame_index,
            )
            response = send(client, url, strategy)
            if not 200 <= response.status_code < 300:
                raise RuntimeError(
                    f"Frame {frame_index} rejected using {selected_name}: "
                    f"{response.status_code} {response.text[:1000]}"
                )

            if frame_index in (5, args.frames):
                responses.append(
                    {
                        "frameIndex": frame_index,
                        "statusCode": response.status_code,
                        "body": response.text[:500],
                    }
                )

            next_send += interval
            remaining = next_send - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)

    result = {
        "sourceId": source_id,
        "sessionId": session_id,
        "droneId": args.drone_id,
        "framesSubmitted": args.frames,
        "fps": args.fps,
        "durationSeconds": round(time.monotonic() - started, 3),
        "fixture": str(fixture),
        "fixtureBytes": len(jpeg),
        "baseUrl": base_url,
        "endpoint": path,
        "operationId": operation.get("operationId"),
        "requestBodyPresent": isinstance(operation.get("requestBody"), dict),
        "selectedStrategy": selected_name,
        "strategyAttempts": attempts,
        "declaredParameters": operation.get("parameters", []),
        "responses": responses,
    }
    print("E2E_FEEDER_RESULT=" + json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"E2E_FEEDER_ERROR={error}", file=sys.stderr)
        raise SystemExit(2)
