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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_schema(openapi: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if not ref:
        return schema
    if not ref.startswith("#/"):
        raise RuntimeError(f"Unsupported OpenAPI ref: {ref}")
    value: Any = openapi
    for part in ref[2:].split("/"):
        value = value[part]
    if not isinstance(value, dict):
        raise RuntimeError(f"Resolved schema is not an object: {ref}")
    return value


def find_openapi(client: httpx.Client, candidates: list[str]) -> tuple[str, dict[str, Any]]:
    errors: list[str] = []
    for base in candidates:
        url = base.rstrip("/") + "/openapi.json"
        try:
            response = client.get(url)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and isinstance(payload.get("paths"), dict):
                return base.rstrip("/"), payload
        except Exception as error:
            errors.append(f"{url}: {error}")
    raise RuntimeError("OpenAPI discovery failed:\n" + "\n".join(errors))


def operation_score(
    openapi: dict[str, Any],
    path: str,
    operation: dict[str, Any],
) -> int:
    text = " ".join(
        [
            path,
            str(operation.get("operationId", "")),
            str(operation.get("summary", "")),
            str(operation.get("description", "")),
        ]
    ).lower()
    score = 0

    normalized_path = path.rstrip("/").lower()
    if normalized_path == "/api/ingest/frame":
        score += 100
    if "ingest" in text:
        score += 10
    if "frame" in text:
        score += 10
    if "upload" in text:
        score += 4

    request_body_raw = operation.get("requestBody", {})
    request_body = (
        resolve_schema(openapi, request_body_raw)
        if isinstance(request_body_raw, dict)
        else {}
    )
    content = (
        request_body.get("content", {})
        if isinstance(request_body, dict)
        else {}
    )
    if "multipart/form-data" in content:
        score += 20
    return score


def discover_endpoint(openapi: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    candidates: list[tuple[int, str, dict[str, Any]]] = []
    for path, path_item in openapi.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        operation = path_item.get("post")
        if not isinstance(operation, dict):
            continue
        score = operation_score(openapi, path, operation)
        if score > 0:
            candidates.append((score, path, operation))
    if not candidates:
        raise RuntimeError("No POST frame-ingest endpoint was found in OpenAPI.")
    candidates.sort(key=lambda item: (-item[0], item[1]))
    best = candidates[0]
    if best[0] < 20:
        details = [
            {
                "score": score,
                "path": path,
                "operationId": operation.get("operationId"),
            }
            for score, path, operation in candidates[:10]
        ]
        raise RuntimeError(
            "No confident multipart frame-ingest endpoint was found: "
            + json.dumps(details, ensure_ascii=False)
        )
    return best[1], best[2]


def normalize(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def value_for_field(
    name: str,
    schema: dict[str, Any],
    *,
    source_id: str,
    session_id: str,
    drone_id: int,
    frame_index: int,
    captured_at: str,
) -> str:
    key = normalize(name)
    mapping = {
        "sourceid": source_id,
        "sessionid": session_id,
        "droneid": str(drone_id),
        "frameindex": str(frame_index),
        "capturedat": captured_at,
        "sourcetype": "DUMMY_VIDEO",
        "contenttype": "image/jpeg",
        "mimetype": "image/jpeg",
    }
    if key in mapping:
        return mapping[key]

    if "source" in key and "id" in key:
        return source_id
    if "session" in key and "id" in key:
        return session_id
    if "drone" in key and "id" in key:
        return str(drone_id)
    if "frame" in key and ("index" in key or "number" in key):
        return str(frame_index)
    if "capture" in key and ("at" in key or "time" in key):
        return captured_at

    default = schema.get("default")
    if default is not None:
        return str(default)

    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return str(enum[0])

    field_type = schema.get("type")
    if field_type == "integer":
        return "0"
    if field_type == "number":
        return "0"
    if field_type == "boolean":
        return "false"
    return ""


def prepare_request(
    openapi: dict[str, Any],
    operation: dict[str, Any],
    jpeg: bytes,
    *,
    source_id: str,
    session_id: str,
    drone_id: int,
    frame_index: int,
) -> tuple[dict[str, Any], dict[str, str], dict[str, str]]:
    captured_at = utc_now()
    request_body_raw = operation.get("requestBody")
    if not isinstance(request_body_raw, dict):
        raise RuntimeError("Frame-ingest endpoint has no requestBody.")
    request_body = resolve_schema(openapi, request_body_raw)
    content = request_body.get("content")
    if not isinstance(content, dict) or "multipart/form-data" not in content:
        raise RuntimeError(
            "Frame-ingest endpoint is not multipart/form-data: "
            + json.dumps(list(content or {}), ensure_ascii=False)
        )

    media = content["multipart/form-data"]
    if not isinstance(media, dict):
        raise RuntimeError("Invalid multipart media schema.")
    raw_schema = media.get("schema", {})
    schema = resolve_schema(openapi, raw_schema)
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    if not isinstance(properties, dict):
        raise RuntimeError("Multipart schema has no properties.")

    files: dict[str, Any] = {}
    form_values: dict[str, str] = {}
    binary_fields: list[str] = []

    for name, prop_raw in properties.items():
        prop = resolve_schema(openapi, prop_raw) if isinstance(prop_raw, dict) else {}
        is_binary = prop.get("format") == "binary"
        if is_binary:
            binary_fields.append(name)
            files[name] = ("e2e-frame.jpg", jpeg, "image/jpeg")
            continue
        value = value_for_field(
            name,
            prop,
            source_id=source_id,
            session_id=session_id,
            drone_id=drone_id,
            frame_index=frame_index,
            captured_at=captured_at,
        )
        if value != "" or name in required:
            files[name] = (None, value)
            form_values[name] = value

    if not binary_fields:
        for likely in ("file", "frame", "image"):
            if likely in properties:
                files[likely] = ("e2e-frame.jpg", jpeg, "image/jpeg")
                binary_fields.append(likely)
                break
    if not binary_fields:
        raise RuntimeError(
            "Could not identify the binary JPEG field: "
            + json.dumps(properties, ensure_ascii=False)
        )

    params: dict[str, str] = {}
    headers: dict[str, str] = {}
    for parameter in operation.get("parameters", []):
        if not isinstance(parameter, dict):
            continue
        name = str(parameter.get("name", ""))
        location = parameter.get("in")
        prop = parameter.get("schema", {})
        value = value_for_field(
            name,
            prop if isinstance(prop, dict) else {},
            source_id=source_id,
            session_id=session_id,
            drone_id=drone_id,
            frame_index=frame_index,
            captured_at=captured_at,
        )
        if location == "query":
            params[name] = value
        elif location == "header":
            headers[name] = value

    return files, params, headers


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
        path, operation = discover_endpoint(openapi)
        url = base_url + path

        started = time.monotonic()
        interval = 1.0 / args.fps
        next_send = started

        for frame_index in range(1, args.frames + 1):
            files, params, headers = prepare_request(
                openapi,
                operation,
                jpeg,
                source_id=source_id,
                session_id=session_id,
                drone_id=args.drone_id,
                frame_index=frame_index,
            )
            response = client.post(
                url,
                files=files,
                params=params,
                headers=headers,
            )
            if response.status_code < 200 or response.status_code >= 300:
                raise RuntimeError(
                    f"Frame {frame_index} rejected: "
                    f"{response.status_code} {response.text[:1000]}"
                )
            if frame_index in (1, 5, args.frames):
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
