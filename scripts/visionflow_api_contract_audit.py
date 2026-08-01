#!/usr/bin/env python3
"""Read-only API contract audit for VisionFlow-Drone.

The audit compares:
* Spring Controller request mappings.
* Next.js app/api Route Handler methods.
* FastAPI AI OpenAPI operations.

It only reads source files and HTTP metadata. Its only writes are JSON/HTML
reports beneath the selected output directory.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD")
JAVA_MAPPING_METHODS = {
    "GetMapping": "GET",
    "PostMapping": "POST",
    "PutMapping": "PUT",
    "PatchMapping": "PATCH",
    "DeleteMapping": "DELETE",
}
JAVA_ANNOTATION_PATTERN = re.compile(
    r"@(RequestMapping|GetMapping|PostMapping|PutMapping|PatchMapping|DeleteMapping)\b"
)
FRONTEND_HANDLER_PATTERN = re.compile(
    r"export\s+(?:async\s+)?function\s+"
    r"(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s*\("
)
DYNAMIC_SEGMENT_PATTERN = re.compile(r"(?:\[[^\]]+\]|\{[^}]+\})")


@dataclass(frozen=True)
class Operation:
    method: str
    path: str
    source: str
    handler: str = ""
    summary: str = ""

    @property
    def normalized_path(self) -> str:
        return normalize_path(self.path)

    @property
    def key(self) -> tuple[str, str]:
        return self.method, self.normalized_path

    def report_dict(self) -> dict[str, str]:
        value = asdict(self)
        value["normalizedPath"] = self.normalized_path
        return value


@dataclass(frozen=True)
class Target:
    service: str
    method: str
    path: str

    @property
    def key(self) -> tuple[str, str]:
        return self.method, normalize_path(self.path)

    def report_dict(self) -> dict[str, str]:
        return {
            "service": self.service,
            "method": self.method,
            "path": self.path,
            "normalizedPath": normalize_path(self.path),
        }


def configure_console() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def normalize_path(value: str) -> str:
    path = value.strip()
    if not path.startswith("/"):
        path = "/" + path
    path = re.sub(r"/{2,}", "/", path)
    if len(path) > 1:
        path = path.rstrip("/")
    return DYNAMIC_SEGMENT_PATTERN.sub("{}", path)


def operation_key(method: str, path: str) -> tuple[str, str]:
    return method.upper(), normalize_path(path)


def operation_key_text(key: tuple[str, str]) -> str:
    return f"{key[0]} {key[1]}"


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"JSON 최상위 값이 객체가 아닙니다: {path}")
    return value


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def capture_annotation(lines: list[str], start: int) -> tuple[str, str, int]:
    match = JAVA_ANNOTATION_PATTERN.search(lines[start])
    if match is None:
        raise ValueError("매핑 어노테이션 시작점을 찾지 못했습니다.")
    name = match.group(1)
    block = lines[start].strip()
    end = start
    if "(" in block:
        balance = block.count("(") - block.count(")")
        while balance > 0 and end + 1 < len(lines):
            end += 1
            block += " " + lines[end].strip()
            balance += lines[end].count("(") - lines[end].count(")")
        if balance != 0:
            raise ValueError(f"닫히지 않은 Java 매핑 어노테이션: line {start + 1}")
    return name, block, end


def extract_mapping_path(annotation: str) -> str:
    if "(" not in annotation:
        return ""
    arguments = annotation.split("(", 1)[1].rsplit(")", 1)[0].strip()
    named = re.search(r"\b(?:path|value)\s*=\s*\"([^\"]*)\"", arguments)
    if named is not None:
        return named.group(1)
    positional = re.match(r"\s*\"([^\"]*)\"", arguments)
    if positional is not None:
        return positional.group(1)
    return ""


def find_java_handler(lines: list[str], start: int) -> str:
    snippet = " ".join(line.strip() for line in lines[start : start + 16])
    match = re.search(
        r"\bpublic\s+[\w<>,.?\[\] ]+?\s+(\w+)\s*\(",
        snippet,
    )
    return match.group(1) if match is not None else ""


def parse_backend_operations(root: Path) -> tuple[list[Operation], list[str]]:
    java_root = (
        root
        / "02_backend"
        / "visionflow-api"
        / "src"
        / "main"
        / "java"
    )
    controller_files = sorted(java_root.rglob("*Controller.java"))
    if not controller_files:
        raise FileNotFoundError(f"Backend Controller를 찾지 못했습니다: {java_root}")

    operations: list[Operation] = []
    issues: list[str] = []
    for path in controller_files:
        lines = path.read_text(encoding="utf-8").splitlines()
        class_line = next(
            (index for index, line in enumerate(lines) if re.search(r"\bclass\s+\w+", line)),
            len(lines),
        )
        annotations: list[tuple[str, str, int, int]] = []
        index = 0
        while index < len(lines):
            if JAVA_ANNOTATION_PATTERN.search(lines[index]) is None:
                index += 1
                continue
            try:
                name, block, end = capture_annotation(lines, index)
            except ValueError as error:
                issues.append(f"{path.relative_to(root)}: {error}")
                index += 1
                continue
            annotations.append((name, block, index, end))
            index = end + 1

        class_request_mappings = [
            item for item in annotations
            if item[0] == "RequestMapping" and item[2] < class_line
        ]
        if len(class_request_mappings) > 1:
            issues.append(
                f"{path.relative_to(root)}: class-level RequestMapping이 여러 개입니다."
            )
        base_path = (
            extract_mapping_path(class_request_mappings[0][1])
            if class_request_mappings
            else ""
        )

        for name, block, start, end in annotations:
            if name == "RequestMapping":
                if start >= class_line:
                    issues.append(
                        f"{path.relative_to(root)}:{start + 1}: "
                        "method-level RequestMapping은 자동 해석 대상이 아닙니다."
                    )
                continue
            method = JAVA_MAPPING_METHODS[name]
            child_path = extract_mapping_path(block)
            full_path = normalize_path(
                base_path.rstrip("/") + "/" + child_path.lstrip("/")
            )
            operations.append(
                Operation(
                    method=method,
                    path=full_path,
                    source=str(path.relative_to(root)).replace("\\", "/"),
                    handler=find_java_handler(lines, end + 1),
                )
            )
    return sorted(operations, key=lambda item: item.key), issues


def parse_frontend_operations(root: Path) -> list[Operation]:
    api_root = (
        root
        / "01_frontend"
        / "visionflow-web"
        / "src"
        / "app"
        / "api"
    )
    route_files = sorted(api_root.rglob("route.ts"))
    if not route_files:
        raise FileNotFoundError(f"Frontend route.ts를 찾지 못했습니다: {api_root}")

    operations: list[Operation] = []
    for path in route_files:
        text = path.read_text(encoding="utf-8")
        route_path = "/api/" + "/".join(path.relative_to(api_root).parts[:-1])
        for match in FRONTEND_HANDLER_PATTERN.finditer(text):
            operations.append(
                Operation(
                    method=match.group(1),
                    path=route_path,
                    source=str(path.relative_to(root)).replace("\\", "/"),
                    handler=match.group(1),
                )
            )
    return sorted(operations, key=lambda item: item.key)


def open_json_url(url: str, timeout_seconds: float) -> tuple[dict[str, Any], int]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "VisionFlow-API-Audit/1"},
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        status = int(response.status)
        data = json.loads(response.read().decode("utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("OpenAPI 최상위 값이 객체가 아닙니다.")
    return data, status


def parse_openapi_operations(document: dict[str, Any], source: str) -> list[Operation]:
    paths = document.get("paths")
    if not isinstance(paths, dict):
        raise ValueError("OpenAPI paths 객체가 없습니다.")
    operations: list[Operation] = []
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        for raw_method, operation in path_item.items():
            method = str(raw_method).upper()
            if method not in HTTP_METHODS:
                continue
            details = operation if isinstance(operation, dict) else {}
            operations.append(
                Operation(
                    method=method,
                    path=normalize_path(path),
                    source=source,
                    handler=str(details.get("operationId", "")),
                    summary=str(details.get("summary", "")),
                )
            )
    return sorted(operations, key=lambda item: item.key)


def load_ai_openapi(
    file_path: Path | None,
    url: str,
    timeout_seconds: float,
) -> tuple[dict[str, Any], str, int | None]:
    if file_path is not None:
        return read_json(file_path), str(file_path), None
    document, status = open_json_url(url, timeout_seconds)
    return document, url, status


def probe_backend_openapi(url: str, timeout_seconds: float) -> dict[str, Any]:
    try:
        document, status = open_json_url(url, timeout_seconds)
        return {"status": status, "available": True, "document": document}
    except urllib.error.HTTPError as error:
        return {
            "status": int(error.code),
            "available": False,
            "error": str(error),
        }
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return {"status": None, "available": False, "error": str(error)}


def duplicate_keys(operations: Iterable[Operation]) -> list[str]:
    counts = Counter(item.key for item in operations)
    return sorted(operation_key_text(key) for key, count in counts.items() if count > 1)


def baseline_entries(
    baseline: dict[str, Any],
    name: str,
) -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    raw_entries = baseline.get(name, [])
    if not isinstance(raw_entries, list):
        raise ValueError(f"기준선 {name} 값이 배열이 아닙니다.")
    for entry in raw_entries:
        if not isinstance(entry, dict):
            raise ValueError(f"기준선 {name} 항목이 객체가 아닙니다.")
        key = operation_key(str(entry.get("method", "")), str(entry.get("path", "")))
        result[key] = str(entry.get("reason", ""))
    return result


def load_special_mappings(
    baseline: dict[str, Any],
) -> dict[tuple[str, str], list[Target]]:
    result: dict[tuple[str, str], list[Target]] = {}
    raw_entries = baseline.get("frontendSpecialMappings", [])
    if not isinstance(raw_entries, list):
        raise ValueError("frontendSpecialMappings 값이 배열이 아닙니다.")
    for entry in raw_entries:
        if not isinstance(entry, dict):
            raise ValueError("frontendSpecialMappings 항목이 객체가 아닙니다.")
        key = operation_key(str(entry.get("method", "")), str(entry.get("path", "")))
        targets: list[Target] = []
        for raw_target in entry.get("targets", []):
            if not isinstance(raw_target, dict):
                raise ValueError(f"잘못된 target: {entry}")
            target = Target(
                service=str(raw_target.get("service", "")),
                method=str(raw_target.get("method", "")).upper(),
                path=normalize_path(str(raw_target.get("path", ""))),
            )
            if target.service not in {"backend", "ai"}:
                raise ValueError(f"지원하지 않는 target service: {target.service}")
            targets.append(target)
        if not targets:
            raise ValueError(f"target이 없는 special mapping: {operation_key_text(key)}")
        result[key] = targets
    return result


def scan_direct_url_advisories(
    root: Path,
    baseline: dict[str, Any],
) -> list[dict[str, Any]]:
    source_root = root / "01_frontend" / "visionflow-web" / "src"
    results: list[dict[str, Any]] = []
    extensions = {".ts", ".tsx", ".js", ".jsx"}
    entries = baseline.get("browserDirectUrlAdvisories", [])
    if not isinstance(entries, list):
        raise ValueError("browserDirectUrlAdvisories 값이 배열이 아닙니다.")
    source_files = [
        path for path in source_root.rglob("*")
        if path.is_file() and path.suffix.lower() in extensions
    ]
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        pattern = str(entry.get("pattern", ""))
        if not pattern:
            continue
        matches: list[dict[str, Any]] = []
        for path in source_files:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for line_number, line in enumerate(lines, start=1):
                if pattern in line:
                    matches.append(
                        {
                            "source": str(path.relative_to(root)).replace("\\", "/"),
                            "line": line_number,
                        }
                    )
        if matches:
            results.append(
                {
                    "pattern": pattern,
                    "reason": str(entry.get("reason", "")),
                    "matches": matches,
                }
            )
    return results


def method_counts(operations: Iterable[Operation]) -> dict[str, int]:
    counts = Counter(item.method for item in operations)
    return {method: counts.get(method, 0) for method in HTTP_METHODS if counts.get(method, 0)}


def check(status: str, key: str, title: str, detail: str, **extra: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "key": key,
        "title": title,
        "status": status,
        "detail": detail,
    }
    value.update(extra)
    return value


def classify_uncovered(
    uncovered: set[tuple[str, str]],
    expected: dict[tuple[str, str], str],
    advisory: dict[tuple[str, str], str],
) -> dict[str, list[dict[str, str]]]:
    value = {"expected": [], "advisory": [], "unexpected": []}
    for key in sorted(uncovered):
        item = {"operation": operation_key_text(key), "reason": ""}
        if key in expected:
            item["reason"] = expected[key]
            value["expected"].append(item)
        elif key in advisory:
            item["reason"] = advisory[key]
            value["advisory"].append(item)
        else:
            item["reason"] = "기준선에 없는 미중계 operation"
            value["unexpected"].append(item)
    return value


def current_git_commit(root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return completed.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def audit(args: argparse.Namespace) -> tuple[dict[str, Any], Path]:
    root = args.root.resolve()
    baseline_path = args.baseline.resolve()
    baseline = read_json(baseline_path)
    if baseline.get("schemaVersion") != 1:
        raise ValueError("지원하지 않는 API 계약 기준선 schemaVersion입니다.")

    backend, backend_parse_issues = parse_backend_operations(root)
    frontend = parse_frontend_operations(root)
    ai_document, ai_source, ai_http_status = load_ai_openapi(
        args.ai_openapi_file.resolve() if args.ai_openapi_file else None,
        args.ai_openapi_url,
        args.timeout_seconds,
    )
    ai = parse_openapi_operations(ai_document, ai_source)

    backend_keys = {item.key for item in backend}
    frontend_keys = {item.key for item in frontend}
    ai_keys = {item.key for item in ai}
    duplicate_backend = duplicate_keys(backend)
    duplicate_frontend = duplicate_keys(frontend)
    duplicate_ai = duplicate_keys(ai)

    local_operations = baseline_entries(baseline, "frontendLocalOperations")
    special_mappings = load_special_mappings(baseline)
    expected_backend_only = baseline_entries(baseline, "expectedBackendOnlyOperations")
    advisory_backend_only = baseline_entries(baseline, "advisoryBackendOnlyOperations")
    expected_ai_only = baseline_entries(baseline, "expectedAiOnlyOperations")
    advisory_ai_only = baseline_entries(baseline, "advisoryAiOnlyOperations")

    mappings: list[dict[str, Any]] = []
    covered_backend: set[tuple[str, str]] = set()
    covered_ai: set[tuple[str, str]] = set()
    missing_targets: list[dict[str, Any]] = []
    for operation in frontend:
        key = operation.key
        if key in local_operations:
            mappings.append(
                {
                    "frontend": operation.report_dict(),
                    "kind": "local",
                    "reason": local_operations[key],
                    "targets": [],
                }
            )
            continue
        targets = special_mappings.get(
            key,
            [Target("backend", operation.method, operation.normalized_path)],
        )
        mapping = {
            "frontend": operation.report_dict(),
            "kind": "proxy",
            "targets": [target.report_dict() for target in targets],
        }
        mappings.append(mapping)
        for target in targets:
            available = backend_keys if target.service == "backend" else ai_keys
            if target.service == "backend":
                covered_backend.add(target.key)
            else:
                covered_ai.add(target.key)
            if target.key not in available:
                missing_targets.append(
                    {
                        "frontend": operation_key_text(key),
                        "targetService": target.service,
                        "target": operation_key_text(target.key),
                    }
                )

    uncovered_backend = classify_uncovered(
        backend_keys - covered_backend,
        expected_backend_only,
        advisory_backend_only,
    )
    uncovered_ai = classify_uncovered(
        ai_keys - covered_ai,
        expected_ai_only,
        advisory_ai_only,
    )
    direct_url_advisories = scan_direct_url_advisories(root, baseline)

    expected_counts = baseline.get("expectedCounts", {})
    actual_counts = {
        "backend": len(backend),
        "frontend": len(frontend),
        "ai": len(ai),
    }
    count_drift = {
        name: {"expected": int(expected_counts.get(name, -1)), "actual": actual}
        for name, actual in actual_counts.items()
        if int(expected_counts.get(name, -1)) != actual
    }

    checks: list[dict[str, Any]] = []
    parse_blockers = backend_parse_issues + [
        f"Backend duplicate: {value}" for value in duplicate_backend
    ] + [
        f"Frontend duplicate: {value}" for value in duplicate_frontend
    ] + [
        f"AI duplicate: {value}" for value in duplicate_ai
    ]
    checks.append(
        check(
            "BLOCKED" if parse_blockers else "PASS",
            "source-inventory",
            "소스 operation 수집",
            (
                "파싱 또는 중복 문제가 있습니다."
                if parse_blockers
                else "Backend Controller와 Frontend Route Handler를 정상 해석했습니다."
            ),
            issues=parse_blockers,
        )
    )
    checks.append(
        check(
            "ADVISORY" if count_drift else "PASS",
            "baseline-counts",
            "기준 operation 수",
            (
                "operation 수가 기준선과 달라 검토가 필요합니다."
                if count_drift
                else "Backend 70, Frontend 69, AI 9 기준과 일치합니다."
            ),
            drift=count_drift,
        )
    )
    checks.append(
        check(
            "BLOCKED" if missing_targets else "PASS",
            "frontend-targets",
            "Frontend proxy target",
            (
                "실제 Backend 또는 AI operation이 없는 Frontend proxy가 있습니다."
                if missing_targets
                else "모든 Frontend 업무 proxy의 대상 operation이 존재합니다."
            ),
            missingTargets=missing_targets,
        )
    )
    backend_advisory_count = (
        len(uncovered_backend["advisory"])
        + len(uncovered_backend["unexpected"])
    )
    checks.append(
        check(
            "ADVISORY" if backend_advisory_count else "PASS",
            "backend-coverage",
            "Backend proxy coverage",
            (
                "Frontend에서 중계하지 않는 Backend 업무 operation을 검토하세요."
                if backend_advisory_count
                else "의도된 내부·직접 Backend operation만 Frontend 중계에서 제외됐습니다."
            ),
            **uncovered_backend,
        )
    )
    ai_advisory_count = len(uncovered_ai["advisory"]) + len(uncovered_ai["unexpected"])
    checks.append(
        check(
            "ADVISORY" if ai_advisory_count else "PASS",
            "ai-coverage",
            "AI proxy coverage",
            (
                "Frontend에서 중계하지 않는 AI 업무 operation을 검토하세요."
                if ai_advisory_count
                else "의도된 운영·직접 AI operation만 Frontend 중계에서 제외됐습니다."
            ),
            **uncovered_ai,
        )
    )
    checks.append(
        check(
            "ADVISORY" if direct_url_advisories else "PASS",
            "browser-direct-urls",
            "브라우저 직접 URL",
            (
                "HTTPS·스마트폰에 부적합할 수 있는 직접 URL이 있습니다."
                if direct_url_advisories
                else "기준선의 위험 직접 URL이 발견되지 않았습니다."
            ),
            findings=direct_url_advisories,
        )
    )

    backend_probe: dict[str, Any] | None = None
    if not args.skip_backend_openapi_probe:
        backend_probe = probe_backend_openapi(
            args.backend_openapi_url,
            args.timeout_seconds,
        )
        accepted_statuses = {
            int(value) for value in baseline.get("backendOpenapiAcceptedStatuses", [])
        }
        probe_status = backend_probe.get("status")
        probe_advisory = probe_status not in accepted_statuses
        probe_detail = (
            f"Backend OpenAPI HTTP {probe_status}; 현재 정책 범위입니다."
            if not probe_advisory
            else "Backend OpenAPI 상태를 확인하지 못했거나 예상 상태가 아닙니다."
        )
        checks.append(
            check(
                "ADVISORY" if probe_advisory else "PASS",
                "backend-openapi-probe",
                "Backend OpenAPI probe",
                probe_detail,
                probe={key: value for key, value in backend_probe.items() if key != "document"},
            )
        )
        if backend_probe.get("available") and isinstance(backend_probe.get("document"), dict):
            openapi_backend = parse_openapi_operations(
                backend_probe["document"],
                args.backend_openapi_url,
            )
            openapi_keys = {item.key for item in openapi_backend}
            missing_in_openapi = sorted(operation_key_text(key) for key in backend_keys - openapi_keys)
            extra_in_openapi = sorted(operation_key_text(key) for key in openapi_keys - backend_keys)
            mismatch = missing_in_openapi or extra_in_openapi
            checks.append(
                check(
                    "BLOCKED" if mismatch else "PASS",
                    "backend-openapi-contract",
                    "Backend Controller와 OpenAPI",
                    (
                        "Controller와 OpenAPI operation이 다릅니다."
                        if mismatch
                        else "Controller와 OpenAPI operation이 일치합니다."
                    ),
                    missingInOpenapi=missing_in_openapi,
                    extraInOpenapi=extra_in_openapi,
                )
            )

    status = "API_CONTRACT_HEALTHY"
    if any(item["status"] == "BLOCKED" for item in checks):
        status = "API_CONTRACT_BLOCKED"
    elif any(item["status"] == "ADVISORY" for item in checks):
        status = "API_CONTRACT_ADVISORY"

    generated_at = datetime.now(timezone.utc)
    if args.output is not None:
        output_dir = args.output
        if not output_dir.is_absolute():
            output_dir = root / output_dir
        output_dir = output_dir.resolve()
    else:
        output_dir = (
            root
            / "artifacts"
            / "api-contract-audit"
            / generated_at.strftime("audit-%Y%m%dT%H%M%SZ")
        )
    backend_probe_summary = (
        None
        if backend_probe is None
        else {key: value for key, value in backend_probe.items() if key != "document"}
    )
    report = {
        "schemaVersion": 1,
        "project": "visionflow",
        "scope": "API_CONTRACT",
        "generatedAt": generated_at.isoformat(),
        "status": status,
        "readOnly": True,
        "git": {
            "commit": current_git_commit(root),
            "baselineCommit": baseline.get("baselineCommit"),
        },
        "sources": {
            "root": str(root),
            "baseline": str(baseline_path),
            "aiOpenapi": ai_source,
            "aiOpenapiHttpStatus": ai_http_status,
            "backendOpenapi": backend_probe_summary,
        },
        "summary": {
            "counts": actual_counts,
            "methods": {
                "backend": method_counts(backend),
                "frontend": method_counts(frontend),
                "ai": method_counts(ai),
            },
            "frontendTargetMappings": len(mappings),
            "missingTargets": len(missing_targets),
            "backendAdvisories": backend_advisory_count,
            "aiAdvisories": ai_advisory_count,
            "browserDirectUrlAdvisories": len(direct_url_advisories),
        },
        "checks": checks,
        "inventory": {
            "backend": [item.report_dict() for item in backend],
            "frontend": [item.report_dict() for item in frontend],
            "ai": [item.report_dict() for item in ai],
        },
        "mappings": mappings,
        "safety": {
            "databaseMutation": False,
            "containerMutation": False,
            "serviceRestart": False,
            "externalWrite": False,
            "writesOnlyReports": True,
        },
    }
    return report, output_dir


def render_items(items: list[dict[str, str]]) -> str:
    if not items:
        return "<p class='muted'>없음</p>"
    rows = "".join(
        "<tr><td><code>{}</code></td><td>{}</td></tr>".format(
            html.escape(item.get("operation", "")),
            html.escape(item.get("reason", "")),
        )
        for item in items
    )
    return f"<table><thead><tr><th>Operation</th><th>판정 근거</th></tr></thead><tbody>{rows}</tbody></table>"


def render_inventory(operations: list[dict[str, Any]]) -> str:
    rows = "".join(
        "<tr><td>{}</td><td><code>{}</code></td><td>{}</td></tr>".format(
            html.escape(str(item.get("method", ""))),
            html.escape(str(item.get("path", ""))),
            html.escape(str(item.get("source", ""))),
        )
        for item in operations
    )
    return f"<table><thead><tr><th>Method</th><th>Path</th><th>Source</th></tr></thead><tbody>{rows}</tbody></table>"


def render_html(report: dict[str, Any]) -> str:
    summary = report["summary"]
    check_rows = "".join(
        "<tr><td><span class='badge {}'>{}</span></td><td>{}</td><td>{}</td></tr>".format(
            html.escape(item["status"].lower()),
            html.escape(item["status"]),
            html.escape(item["title"]),
            html.escape(item["detail"]),
        )
        for item in report["checks"]
    )
    coverage_sections: list[str] = []
    for key, title in (("backend-coverage", "Backend 미중계"), ("ai-coverage", "AI 미중계")):
        item = next(value for value in report["checks"] if value["key"] == key)
        coverage_sections.append(f"<h3>{html.escape(title)} — 예상</h3>{render_items(item['expected'])}")
        coverage_sections.append(f"<h3>{html.escape(title)} — 검토</h3>{render_items(item['advisory'] + item['unexpected'])}")

    direct_check = next(
        value for value in report["checks"] if value["key"] == "browser-direct-urls"
    )
    direct_rows = "".join(
        "<tr><td><code>{}</code></td><td>{}</td><td>{}</td></tr>".format(
            html.escape(item["pattern"]),
            html.escape(item["reason"]),
            "<br>".join(
                html.escape(f"{match['source']}:{match['line']}")
                for match in item["matches"]
            ),
        )
        for item in direct_check["findings"]
    )
    direct_table = (
        "<p class='muted'>없음</p>"
        if not direct_rows
        else "<table><thead><tr><th>URL</th><th>위험</th><th>위치</th></tr></thead>"
             f"<tbody>{direct_rows}</tbody></table>"
    )
    status_class = report["status"].replace("API_CONTRACT_", "").lower()
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VisionFlow API Contract Audit</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f4f7fb;color:#172033}}
main{{max-width:1180px;margin:auto;padding:28px}}
.hero{{background:#071126;color:#fff;border-radius:18px;padding:28px}}
.status{{display:inline-block;margin-top:12px;padding:8px 12px;border-radius:999px;font-weight:700}}
.healthy,.pass{{background:#d1fae5;color:#065f46}} .advisory{{background:#fef3c7;color:#92400e}}
.blocked{{background:#fee2e2;color:#991b1b}} .card{{background:#fff;border:1px solid #dbe3ef;border-radius:14px;padding:20px;margin-top:18px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}}
.metric{{background:#eef4ff;border-radius:12px;padding:16px}} .metric strong{{display:block;font-size:28px}}
table{{border-collapse:collapse;width:100%;margin-top:10px}} th,td{{border-bottom:1px solid #e5eaf2;padding:9px;text-align:left;vertical-align:top}}
th{{background:#f8fafc}} code{{font-family:Consolas,monospace}} .badge{{display:inline-block;padding:4px 8px;border-radius:999px;font-weight:700}}
.muted{{color:#667085}} details{{margin-top:16px}} summary{{cursor:pointer;font-weight:700}}
</style>
</head>
<body><main>
<section class="hero"><h1>VisionFlow API Contract Audit</h1><p>{html.escape(report['generatedAt'])}</p>
<span class="status {status_class}">{html.escape(report['status'])}</span></section>
<section class="card"><h2>요약</h2><div class="grid">
<div class="metric">Backend<strong>{summary['counts']['backend']}</strong></div>
<div class="metric">Frontend<strong>{summary['counts']['frontend']}</strong></div>
<div class="metric">AI<strong>{summary['counts']['ai']}</strong></div>
<div class="metric">Missing target<strong>{summary['missingTargets']}</strong></div>
</div></section>
<section class="card"><h2>검사 결과</h2><table><thead><tr><th>상태</th><th>검사</th><th>설명</th></tr></thead><tbody>{check_rows}</tbody></table></section>
<section class="card"><h2>미중계 operation</h2>{''.join(coverage_sections)}</section>
<section class="card"><h2>브라우저 직접 URL</h2>{direct_table}</section>
<section class="card"><h2>전체 Inventory</h2>
<details><summary>Backend</summary>{render_inventory(report['inventory']['backend'])}</details>
<details><summary>Frontend</summary>{render_inventory(report['inventory']['frontend'])}</details>
<details><summary>AI</summary>{render_inventory(report['inventory']['ai'])}</details>
</section>
<section class="card"><h2>안전 속성</h2><p>DB 변경 없음 · 컨테이너 변경 없음 · 서비스 재시작 없음 · 보고서만 생성</p></section>
</main></body></html>"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="VisionFlow Backend·Frontend·AI 읽기 전용 API 계약 감사"
    )
    parser.add_argument("--root", type=Path, default=script_dir.parent)
    parser.add_argument(
        "--baseline",
        type=Path,
        default=script_dir / "visionflow_api_contract_baseline.json",
    )
    parser.add_argument(
        "--ai-openapi-url",
        default="http://localhost:8000/openapi.json",
    )
    parser.add_argument("--ai-openapi-file", type=Path)
    parser.add_argument(
        "--backend-openapi-url",
        default="http://localhost:8080/v3/api-docs",
    )
    parser.add_argument("--skip-backend-openapi-probe", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="ADVISORY도 실패 종료 코드로 처리",
    )
    args = parser.parse_args(argv)
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds는 0보다 커야 합니다.")
    return args


def main(argv: list[str] | None = None) -> int:
    configure_console()
    args = parse_args(argv)
    try:
        report, output_dir = audit(args)
        json_path = output_dir / "visionflow-api-contract-audit.json"
        html_path = output_dir / "visionflow-api-contract-audit.html"
        atomic_write_text(
            json_path,
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        )
        atomic_write_text(html_path, render_html(report))
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError) as error:
        print(f"[FAIL] API 계약 감사를 실행하지 못했습니다: {error}", file=sys.stderr)
        return 2

    print(f"VisionFlow API contract audit: {report['status']}")
    counts = report["summary"]["counts"]
    print(
        "Operations: "
        f"Backend={counts['backend']}, "
        f"Frontend={counts['frontend']}, "
        f"AI={counts['ai']}"
    )
    for item in report["checks"]:
        print(f"[{item['status']}] {item['key']}: {item['detail']}")
    print(f"JSON report: {json_path}")
    print(f"HTML report: {html_path}")
    print("Safety: read-only; reports only")

    if report["status"] == "API_CONTRACT_BLOCKED":
        return 1
    if args.strict and report["status"] == "API_CONTRACT_ADVISORY":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
