from __future__ import annotations

import argparse
import ast
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


@dataclass(frozen=True, slots=True)
class Route:
    method: str
    path: str
    operation_id: str
    line: int


def route_decorator(node: ast.expr) -> tuple[str, str] | None:
    if not isinstance(node, ast.Call):
        return None
    function = node.func
    if not (
        isinstance(function, ast.Attribute)
        and isinstance(function.value, ast.Name)
        and function.value.id == "app"
        and function.attr.lower() in HTTP_METHODS
    ):
        return None
    if not node.args:
        raise ValueError(f"line {node.lineno}: @app.{function.attr} 경로가 없습니다.")
    path_node = node.args[0]
    if not isinstance(path_node, ast.Constant) or not isinstance(path_node.value, str):
        raise ValueError(
            f"line {node.lineno}: 동적 FastAPI 경로는 소스 snapshot에서 허용되지 않습니다."
        )
    path = path_node.value.strip()
    if not path.startswith("/"):
        raise ValueError(f"line {node.lineno}: FastAPI 경로는 '/'로 시작해야 합니다.")
    return function.attr.upper(), path


def collect_routes(source: Path) -> list[Route]:
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    routes: list[Route] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            parsed = route_decorator(decorator)
            if parsed is None:
                continue
            method, path = parsed
            routes.append(
                Route(
                    method=method,
                    path=path,
                    operation_id=node.name,
                    line=decorator.lineno,
                )
            )

    if not routes:
        raise ValueError(f"FastAPI route를 찾지 못했습니다: {source}")

    duplicates: dict[tuple[str, str], list[int]] = {}
    for route in routes:
        duplicates.setdefault((route.method, route.path), []).append(route.line)
    repeated = {key: lines for key, lines in duplicates.items() if len(lines) > 1}
    if repeated:
        details = ", ".join(
            f"{method} {path} (lines {lines})"
            for (method, path), lines in sorted(repeated.items())
        )
        raise ValueError(f"중복 FastAPI operation: {details}")

    return sorted(routes, key=lambda item: (item.path, item.method, item.operation_id))


def build_openapi(routes: list[Route], source: Path) -> dict[str, Any]:
    paths: dict[str, dict[str, Any]] = {}
    for route in routes:
        paths.setdefault(route.path, {})[route.method.lower()] = {
            "operationId": route.operation_id,
            "summary": route.operation_id.replace("_", " "),
            "x-visionflow-source-line": route.line,
        }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "VisionFlow AI source-derived API inventory",
            "version": "source-snapshot-v1",
        },
        "paths": paths,
        "x-visionflow-source": str(source).replace("\\", "/"),
        "x-visionflow-read-only": True,
    }


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="FastAPI 소스에서 읽기 전용 AI OpenAPI inventory snapshot 생성"
    )
    parser.add_argument("--root", type=Path, default=script_dir.parent)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    source = args.source or (
        root / "03_ai-server" / "visionflow-ai" / "app" / "streaming.py"
    )
    output = args.output or (
        root / "artifacts" / "api-audit-ci" / "ai-openapi.json"
    )
    if not source.is_absolute():
        source = (root / source).resolve()
    if not output.is_absolute():
        output = (root / output).resolve()

    try:
        routes = collect_routes(source)
        document = build_openapi(routes, source.relative_to(root))
        atomic_write_json(output, document)
    except (OSError, SyntaxError, ValueError) as error:
        print(f"[FAIL] AI OpenAPI source snapshot: {error}")
        return 2

    print("VisionFlow AI OpenAPI source snapshot: PASS")
    print(f"Operations: {len(routes)}")
    print(f"Source: {source}")
    print(f"Output: {output}")
    print("Safety: source read only; generated inventory only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
