#!/usr/bin/env python3
"""Read-only API security and authorization audit for VisionFlow-Drone.

The audit reads Spring Security rules, Backend Controller mappings, Next.js
Route Handlers, FastAPI OpenAPI metadata, selected non-secret container
environment values, and Compose defaults. It only writes JSON, HTML, and
Markdown reports.
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
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


CONTRACT_IMPORT_ERROR: Exception | None = None
try:
    from visionflow_api_contract_audit import (
        Operation,
        Target,
        baseline_entries,
        current_git_commit,
        load_ai_openapi,
        load_special_mappings,
        method_counts,
        normalize_path,
        operation_key,
        operation_key_text,
        parse_backend_operations,
        parse_frontend_operations,
        parse_openapi_operations,
        read_json,
    )
except ImportError as error:  # pragma: no cover - deployment prerequisite path
    CONTRACT_IMPORT_ERROR = error


MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
PUBLIC_ACCESS = "PUBLIC"
DENY_ACCESS = "DENY_ALL"
SECURITY_RULE_PATTERN = re.compile(
    r"\.requestMatchers\s*\((.*?)\)\s*\."
    r"(permitAll|authenticated|denyAll|hasRole|hasAnyRole)\s*\((.*?)\)",
    re.DOTALL,
)
ANY_REQUEST_PATTERN = re.compile(
    r"\.anyRequest\s*\(\s*\)\s*\."
    r"(permitAll|authenticated|denyAll)\s*\(\s*\)",
    re.DOTALL,
)
HTTP_METHOD_PATTERN = re.compile(
    r"HttpMethod\.(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)"
)
QUOTED_PATTERN = re.compile(r'"([^"]+)"')
AI_AUTH_SIGNAL_PATTERN = re.compile(
    r"APIKeyHeader|HTTPBearer|OAuth2|Security\s*\(|"
    r"Depends\s*\([^)]*(?:auth|token|key)|Authorization",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SecurityRule:
    order: int
    method: str | None
    patterns: tuple[str, ...]
    access: str
    expression: str

    def report_dict(self) -> dict[str, Any]:
        return asdict(self)


def configure_console() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def access_label(kind: str, arguments: str) -> str:
    if kind == "permitAll":
        return PUBLIC_ACCESS
    if kind == "authenticated":
        return "AUTHENTICATED"
    if kind == "denyAll":
        return DENY_ACCESS
    roles = QUOTED_PATTERN.findall(arguments)
    if kind == "hasRole":
        return f"ROLE_{roles[0]}" if roles else "ROLE_UNKNOWN"
    return "ROLES_" + "_".join(roles) if roles else "ROLES_UNKNOWN"


def parse_rule_block(block: str) -> tuple[list[SecurityRule], str]:
    rules: list[SecurityRule] = []
    for order, match in enumerate(SECURITY_RULE_PATTERN.finditer(block), start=1):
        matcher_arguments = match.group(1)
        access_kind = match.group(2)
        access_arguments = match.group(3)
        method_match = HTTP_METHOD_PATTERN.search(matcher_arguments)
        method = method_match.group(1) if method_match else None
        patterns = tuple(QUOTED_PATTERN.findall(matcher_arguments))
        if not patterns:
            raise ValueError("SecurityConfig requestMatchers 경로를 해석하지 못했습니다.")
        rules.append(
            SecurityRule(
                order=order,
                method=method,
                patterns=patterns,
                access=access_label(access_kind, access_arguments),
                expression=match.group(0).strip(),
            )
        )
    fallback_matches = list(ANY_REQUEST_PATTERN.finditer(block))
    if not fallback_matches:
        raise ValueError("SecurityConfig anyRequest fallback을 찾지 못했습니다.")
    fallback_match = fallback_matches[-1]
    fallback = access_label(fallback_match.group(1), "")
    return rules, fallback


def parse_security_config(root: Path) -> dict[str, Any]:
    path = (
        root
        / "02_backend"
        / "visionflow-api"
        / "src"
        / "main"
        / "java"
        / "com"
        / "visionflow"
        / "api"
        / "common"
        / "config"
        / "SecurityConfig.java"
    )
    text = path.read_text(encoding="utf-8")
    branch_start = text.find("if (!credentialRegistry.isEnabled())")
    if branch_start < 0:
        raise ValueError("SecurityConfig의 보안 비활성 분기를 찾지 못했습니다.")
    branch_return = text.find("return;", branch_start)
    if branch_return < 0:
        raise ValueError("SecurityConfig의 보안 비활성 분기 종료를 찾지 못했습니다.")
    disabled_rules, disabled_fallback = parse_rule_block(
        text[branch_start:branch_return]
    )
    enabled_rules, enabled_fallback = parse_rule_block(text[branch_return:])
    return {
        "path": str(path.relative_to(root)).replace("\\", "/"),
        "csrfDisabled": ".csrf(csrf -> csrf.disable())" in text,
        "sessionCreationPolicy": (
            "STATELESS" if "SessionCreationPolicy.STATELESS" in text else "UNKNOWN"
        ),
        "enabledRules": enabled_rules,
        "enabledFallback": enabled_fallback,
        "disabledRules": disabled_rules,
        "disabledFallback": disabled_fallback,
    }


def ant_matches(pattern: str, path: str) -> bool:
    normalized_pattern = normalize_path(pattern)
    normalized_value = normalize_path(path)
    if normalized_pattern.endswith("/**"):
        base = normalized_pattern[:-3]
        if normalized_value == base or normalized_value.startswith(base + "/"):
            return True
    expression: list[str] = []
    index = 0
    while index < len(normalized_pattern):
        if normalized_pattern.startswith("**", index):
            expression.append(".*")
            index += 2
        elif normalized_pattern[index] == "*":
            expression.append("[^/]*")
            index += 1
        else:
            expression.append(re.escape(normalized_pattern[index]))
            index += 1
    return re.fullmatch("".join(expression), normalized_value) is not None


def evaluate_access(
    operation: Operation | Target,
    rules: Iterable[SecurityRule],
    fallback: str,
) -> tuple[str, str]:
    for rule in rules:
        if rule.method is not None and rule.method != operation.method:
            continue
        if any(ant_matches(pattern, operation.normalized_path) for pattern in rule.patterns):
            matcher = ", ".join(rule.patterns)
            method = rule.method or "ANY"
            return rule.access, f"#{rule.order} {method} {matcher}"
    return fallback, "anyRequest"


def baseline_operation_map(
    baseline: dict[str, Any],
    key: str,
) -> dict[tuple[str, str], dict[str, Any]]:
    raw = baseline.get(key, [])
    if not isinstance(raw, list):
        raise ValueError(f"기준선 {key} 값이 배열이 아닙니다.")
    values: dict[tuple[str, str], dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"기준선 {key} 항목이 객체가 아닙니다.")
        operation = operation_key(str(item.get("method", "")), str(item.get("path", "")))
        values[operation] = item
    return values


def analyze_backend(
    operations: list[Operation],
    security: dict[str, Any],
    baseline: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for operation in operations:
        enabled_access, enabled_rule = evaluate_access(
            operation,
            security["enabledRules"],
            security["enabledFallback"],
        )
        disabled_access, disabled_rule = evaluate_access(
            operation,
            security["disabledRules"],
            security["disabledFallback"],
        )
        row = {
            "operation": operation_key_text(operation.key),
            "method": operation.method,
            "path": operation.path,
            "normalizedPath": operation.normalized_path,
            "source": operation.source,
            "enabledAccess": enabled_access,
            "enabledRule": enabled_rule,
            "disabledAccess": disabled_access,
            "disabledRule": disabled_rule,
        }
        rows.append(row)
        by_key[operation.key] = row

    required_access = baseline_operation_map(baseline, "requiredBackendAccess")
    protection_failures: list[dict[str, Any]] = []
    for key, policy in required_access.items():
        row = by_key.get(key)
        allowed = [str(value) for value in policy.get("allowedAccess", [])]
        if row is None:
            protection_failures.append(
                {
                    "operation": operation_key_text(key),
                    "actual": "MISSING_OPERATION",
                    "expected": allowed,
                    "reason": str(policy.get("reason", "")),
                }
            )
        elif row["enabledAccess"] not in allowed:
            protection_failures.append(
                {
                    "operation": operation_key_text(key),
                    "actual": row["enabledAccess"],
                    "expected": allowed,
                    "reason": str(policy.get("reason", "")),
                }
            )

    expected_public_writes = baseline_operation_map(
        baseline,
        "expectedBackendPublicWrites",
    )
    public_writes = {
        key: row
        for key, row in by_key.items()
        if key[0] in MUTATION_METHODS and row["enabledAccess"] == PUBLIC_ACCESS
    }
    unexpected_public_writes = [
        row for key, row in sorted(public_writes.items()) if key not in expected_public_writes
    ]
    changed_expected_public_writes: list[dict[str, Any]] = []
    for key, policy in expected_public_writes.items():
        row = by_key.get(key)
        actual = "MISSING_OPERATION" if row is None else row["enabledAccess"]
        if actual != PUBLIC_ACCESS:
            changed_expected_public_writes.append(
                {
                    "operation": operation_key_text(key),
                    "actual": actual,
                    "reason": str(policy.get("reason", "")),
                }
            )

    sensitive_policies = baseline.get("sensitiveBackendPublicReads", [])
    if not isinstance(sensitive_policies, list):
        raise ValueError("sensitiveBackendPublicReads 값이 배열이 아닙니다.")
    sensitive_public_reads: list[dict[str, Any]] = []
    for row in rows:
        if row["method"] != "GET" or row["enabledAccess"] != PUBLIC_ACCESS:
            continue
        for policy in sensitive_policies:
            if not isinstance(policy, dict):
                continue
            pattern = str(policy.get("path", ""))
            if pattern and ant_matches(pattern, row["normalizedPath"]):
                sensitive_public_reads.append(
                    {
                        "operation": row["operation"],
                        "severity": str(policy.get("severity", "MEDIUM")),
                        "reason": str(policy.get("reason", "")),
                        "source": row["source"],
                    }
                )
                break

    disabled_non_public = [
        row for row in rows if row["disabledAccess"] != PUBLIC_ACCESS
    ]
    denied_enabled = [row for row in rows if row["enabledAccess"] == DENY_ACCESS]
    summary = {
        "enabledAccessCounts": dict(Counter(row["enabledAccess"] for row in rows)),
        "disabledAccessCounts": dict(Counter(row["disabledAccess"] for row in rows)),
        "protectionFailures": protection_failures,
        "unexpectedPublicWrites": unexpected_public_writes,
        "changedExpectedPublicWrites": changed_expected_public_writes,
        "sensitivePublicReads": sensitive_public_reads,
        "disabledNonPublic": disabled_non_public,
        "deniedEnabled": denied_enabled,
    }
    return rows, summary


def helper_auth_modules(root: Path) -> set[str]:
    server_root = root / "01_frontend" / "visionflow-web" / "src" / "lib" / "server"
    modules: set[str] = set()
    for path in server_root.glob("*.ts"):
        text = path.read_text(encoding="utf-8")
        if path.name != "operator-auth.ts" and "withBackendOperatorAuth" in text:
            modules.add(path.stem)
    return modules


def route_auth_mechanism(text: str, auth_modules: set[str]) -> str:
    if "withBackendOperatorAuth" in text:
        return "DIRECT_OPERATOR_AUTH"
    imports = set(re.findall(r"@/lib/server/([\w-]+)", text))
    matched = sorted(imports & auth_modules)
    if matched:
        return "HELPER_OPERATOR_AUTH:" + ",".join(matched)
    return "NONE"


def route_mutation_guard(operation: Operation, text: str) -> str:
    if operation.method not in MUTATION_METHODS:
        return "NOT_APPLICABLE"
    if "rejectCrossOriginOperatorMutation" in text:
        return "SAME_ORIGIN_GUARD"
    if "isSameOriginRequest(request)" in text and "CROSS_ORIGIN" in text:
        return "SAME_ORIGIN_MANUAL"
    if operation.normalized_path == "/api/operator/session":
        if operation.method == "POST" and "CROSS_ORIGIN_OPERATOR_LOGIN_DENIED" in text:
            return "SAME_ORIGIN_MANUAL"
        if operation.method == "DELETE" and "CROSS_ORIGIN_OPERATOR_LOGOUT_DENIED" in text:
            return "SAME_ORIGIN_MANUAL"
    return "NONE"


def analyze_frontend(
    root: Path,
    operations: list[Operation],
    contract_baseline: dict[str, Any],
    security_baseline: dict[str, Any],
    backend_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    backend_access = {
        operation_key(row["method"], row["normalizedPath"]): row["enabledAccess"]
        for row in backend_rows
    }
    local_operations = baseline_entries(contract_baseline, "frontendLocalOperations")
    special_mappings = load_special_mappings(contract_baseline)
    expected_unguarded = baseline_operation_map(
        security_baseline,
        "expectedFrontendUnguardedMutations",
    )
    advisory_unguarded = baseline_operation_map(
        security_baseline,
        "advisoryFrontendUnguardedMutations",
    )
    auth_modules = helper_auth_modules(root)
    rows: list[dict[str, Any]] = []
    missing_auth: list[dict[str, Any]] = []
    unexpected_unguarded: list[dict[str, Any]] = []
    advisory_guard_findings: list[dict[str, Any]] = []

    for operation in operations:
        text = (root / operation.source).read_text(encoding="utf-8")
        local = operation.key in local_operations
        targets = [] if local else special_mappings.get(
            operation.key,
            [Target("backend", operation.method, operation.normalized_path)],
        )
        mechanism = route_auth_mechanism(text, auth_modules)
        guard = route_mutation_guard(operation, text)
        target_rows: list[dict[str, str]] = []
        protected_targets: list[dict[str, str]] = []
        for target in targets:
            access = (
                backend_access.get(target.key, "UNKNOWN")
                if target.service == "backend"
                else PUBLIC_ACCESS
            )
            target_row = {
                "service": target.service,
                "operation": operation_key_text(target.key),
                "access": access,
            }
            target_rows.append(target_row)
            if target.service == "backend" and access not in {PUBLIC_ACCESS, "UNKNOWN"}:
                protected_targets.append(target_row)
        auth_state = "NOT_REQUIRED"
        if protected_targets:
            auth_state = "PASS" if mechanism != "NONE" else "MISSING"
            if auth_state == "MISSING":
                missing_auth.append(
                    {
                        "operation": operation_key_text(operation.key),
                        "source": operation.source,
                        "targets": protected_targets,
                    }
                )

        guard_state = guard
        if operation.method in MUTATION_METHODS and guard == "NONE":
            if operation.key in expected_unguarded:
                guard_state = "EXPECTED_UNGUARDED"
            elif operation.key in advisory_unguarded:
                guard_state = "ADVISORY_UNGUARDED"
                advisory_guard_findings.append(
                    {
                        "operation": operation_key_text(operation.key),
                        "source": operation.source,
                        "reason": str(advisory_unguarded[operation.key].get("reason", "")),
                    }
                )
            else:
                guard_state = "MISSING"
                unexpected_unguarded.append(
                    {
                        "operation": operation_key_text(operation.key),
                        "source": operation.source,
                    }
                )
        rows.append(
            {
                "operation": operation_key_text(operation.key),
                "method": operation.method,
                "path": operation.path,
                "normalizedPath": operation.normalized_path,
                "source": operation.source,
                "local": local,
                "targets": target_rows,
                "authMechanism": mechanism,
                "protectedTargetAuth": auth_state,
                "mutationGuard": guard_state,
            }
        )
    return rows, {
        "missingProtectedTargetAuth": missing_auth,
        "unexpectedUnguardedMutations": unexpected_unguarded,
        "advisoryUnguardedMutations": advisory_guard_findings,
        "guardCounts": dict(Counter(row["mutationGuard"] for row in rows)),
        "authMechanismCounts": dict(Counter(row["authMechanism"] for row in rows)),
    }


def analyze_ai(
    root: Path,
    operations: list[Operation],
    baseline: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    streaming_path = root / "03_ai-server" / "visionflow-ai" / "app" / "streaming.py"
    text = streaming_path.read_text(encoding="utf-8")
    signals = sorted(set(match.group(0) for match in AI_AUTH_SIGNAL_PATTERN.finditer(text)))
    access = "AUTH_REVIEW" if signals else PUBLIC_ACCESS
    sensitive = baseline_operation_map(baseline, "sensitiveAiPublicOperations")
    rows: list[dict[str, Any]] = []
    exposures: list[dict[str, Any]] = []
    for operation in operations:
        policy = sensitive.get(operation.key)
        row = {
            "operation": operation_key_text(operation.key),
            "method": operation.method,
            "path": operation.path,
            "source": operation.source,
            "access": access,
            "severity": str(policy.get("severity", "INFO")) if policy else "INFO",
            "reason": str(policy.get("reason", "")) if policy else "health endpoint",
        }
        rows.append(row)
        if policy is not None and access == PUBLIC_ACCESS:
            exposures.append(row)
    return rows, {
        "authSignals": signals,
        "sensitivePublicOperations": exposures,
        "publicOperationCount": len(operations) if access == PUBLIC_ACCESS else 0,
    }


def parse_compose_defaults(root: Path, keys: Iterable[str]) -> dict[str, str | None]:
    text = (root / "compose.yaml").read_text(encoding="utf-8")
    values: dict[str, str | None] = {}
    for key in keys:
        match = re.search(
            rf"^\s*{re.escape(key)}:\s*\$\{{[^}}]*:-([^}}]+)\}}\s*$",
            text,
            re.MULTILINE,
        )
        values[key] = match.group(1).strip() if match else None
    return values


def inspect_container_env(container: str, allowed_keys: Iterable[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [
                "docker",
                "inspect",
                container,
                "--format",
                "{{range .Config.Env}}{{println .}}{{end}}",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return {"available": False, "error": str(error), "values": {}}
    if completed.returncode != 0:
        return {
            "available": False,
            "error": completed.stderr.strip()[:500],
            "values": {},
        }
    allowed = set(allowed_keys)
    values: dict[str, str | None] = {key: None for key in allowed}
    for line in completed.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in allowed:
            values[key] = value
    return {"available": True, "error": None, "values": values}


def analyze_runtime(args: argparse.Namespace, baseline: dict[str, Any]) -> dict[str, Any]:
    if args.skip_runtime:
        return {"skipped": True, "status": "SKIPPED", "issues": []}
    backend = inspect_container_env(
        args.backend_container,
        ["VISIONFLOW_OPERATOR_SECURITY_ENABLED"],
    )
    frontend = inspect_container_env(
        args.frontend_container,
        ["VISIONFLOW_WEB_AUTH_MODE", "VISIONFLOW_WEB_SECURE_COOKIES"],
    )
    expected = baseline.get("runtimeExpectations", {})
    issues: list[dict[str, str]] = []
    if not backend["available"] or not frontend["available"]:
        status = "ADVISORY"
    else:
        mappings = [
            (
                "backendSecurityEnabled",
                backend["values"].get("VISIONFLOW_OPERATOR_SECURITY_ENABLED"),
                str(expected.get("backendSecurityEnabled", "true")),
                "BLOCKED",
            ),
            (
                "frontendAuthMode",
                frontend["values"].get("VISIONFLOW_WEB_AUTH_MODE"),
                str(expected.get("frontendAuthMode", "session")),
                "BLOCKED",
            ),
            (
                "frontendSecureCookies",
                frontend["values"].get("VISIONFLOW_WEB_SECURE_COOKIES"),
                str(expected.get("frontendSecureCookies", "true")),
                "ADVISORY",
            ),
        ]
        for name, actual, wanted, severity in mappings:
            if (actual or "").lower() != wanted.lower():
                issues.append(
                    {
                        "key": name,
                        "expected": wanted,
                        "actual": actual or "MISSING",
                        "severity": severity,
                    }
                )
        status = "PASS"
        if any(item["severity"] == "BLOCKED" for item in issues):
            status = "BLOCKED"
        elif issues:
            status = "ADVISORY"
    return {
        "skipped": False,
        "status": status,
        "issues": issues,
        "backend": backend,
        "frontend": frontend,
    }


def make_check(
    status: str,
    key: str,
    title: str,
    detail: str,
    **extra: Any,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "status": status,
        "key": key,
        "title": title,
        "detail": detail,
    }
    value.update(extra)
    return value


def audit(args: argparse.Namespace) -> tuple[dict[str, Any], Path]:
    if CONTRACT_IMPORT_ERROR is not None:
        raise ValueError(
            "visionflow_api_contract_audit.py를 불러오지 못했습니다. "
            "API 계약 감사 도구를 먼저 적용하세요: "
            f"{CONTRACT_IMPORT_ERROR}"
        )
    root = args.root.resolve()
    baseline = read_json(args.baseline.resolve())
    contract_baseline = read_json(args.contract_baseline.resolve())
    if baseline.get("schemaVersion") != 1:
        raise ValueError("지원하지 않는 보안 기준선 schemaVersion입니다.")

    backend_operations, backend_parse_issues = parse_backend_operations(root)
    frontend_operations = parse_frontend_operations(root)
    ai_document, ai_source, ai_http_status = load_ai_openapi(
        args.ai_openapi_file.resolve() if args.ai_openapi_file else None,
        args.ai_openapi_url,
        args.timeout_seconds,
    )
    ai_operations = parse_openapi_operations(ai_document, ai_source)
    security = parse_security_config(root)
    backend_rows, backend_summary = analyze_backend(
        backend_operations,
        security,
        baseline,
    )
    frontend_rows, frontend_summary = analyze_frontend(
        root,
        frontend_operations,
        contract_baseline,
        baseline,
        backend_rows,
    )
    ai_rows, ai_summary = analyze_ai(root, ai_operations, baseline)

    expected_counts = baseline.get("expectedCounts", {})
    actual_counts = {
        "backend": len(backend_operations),
        "frontend": len(frontend_operations),
        "ai": len(ai_operations),
    }
    count_drift = {
        name: {"expected": int(expected_counts.get(name, -1)), "actual": actual}
        for name, actual in actual_counts.items()
        if int(expected_counts.get(name, -1)) != actual
    }
    compose_expected = baseline.get("composeDefaultExpectations", {})
    compose_actual = parse_compose_defaults(root, compose_expected.keys())
    compose_drift = {
        key: {"expected": str(expected), "actual": compose_actual.get(key)}
        for key, expected in compose_expected.items()
        if (compose_actual.get(key) or "").lower() != str(expected).lower()
    }
    runtime = analyze_runtime(args, baseline)

    checks: list[dict[str, Any]] = []
    checks.append(
        make_check(
            "BLOCKED" if backend_parse_issues else "PASS",
            "source-inventory",
            "API 및 보안 규칙 수집",
            (
                "Controller 파싱 문제가 있습니다."
                if backend_parse_issues
                else "Backend·Frontend·AI operation과 Spring Security 규칙을 해석했습니다."
            ),
            issues=backend_parse_issues,
        )
    )
    checks.append(
        make_check(
            "ADVISORY" if count_drift else "PASS",
            "baseline-counts",
            "API 기준 수",
            (
                "operation 수가 보안 기준선과 다릅니다."
                if count_drift
                else "Backend 70, Frontend 69, AI 9 기준과 일치합니다."
            ),
            drift=count_drift,
        )
    )
    protection_failures = backend_summary["protectionFailures"]
    checks.append(
        make_check(
            "BLOCKED" if protection_failures else "PASS",
            "backend-critical-protections",
            "Backend 핵심 보호 규칙",
            (
                "ADMIN·인증 전용 API의 보호 규칙이 기준과 다릅니다."
                if protection_failures
                else (
                    "세션 관리·감사·Incident·AI 이벤트와 "
                    "경보 API의 역할별 보호 규칙이 유지됩니다."
                )
            ),
            failures=protection_failures,
        )
    )
    unexpected_writes = backend_summary["unexpectedPublicWrites"]
    changed_writes = backend_summary["changedExpectedPublicWrites"]
    checks.append(
        make_check(
            "BLOCKED" if unexpected_writes else ("ADVISORY" if changed_writes else "PASS"),
            "backend-public-writes",
            "Backend 공개 변경 API",
            (
                "기준선에 없는 공개 변경 API가 있습니다."
                if unexpected_writes
                else (
                    "승인된 공개 수집 API의 접근 규칙이 변경됐습니다."
                    if changed_writes
                    else "공개 변경 API는 승인된 장치·AI·세션 진입점 5개뿐입니다."
                )
            ),
            unexpected=unexpected_writes,
            changedExpected=changed_writes,
        )
    )
    sensitive_reads = backend_summary["sensitivePublicReads"]
    checks.append(
        make_check(
            "ADVISORY" if sensitive_reads else "PASS",
            "backend-sensitive-public-reads",
            "Backend 민감 GET 공개 범위",
            (
                f"민감 운영 데이터를 인증 없이 읽을 수 있는 API가 {len(sensitive_reads)}개입니다."
                if sensitive_reads
                else "민감 GET API가 인증으로 보호됩니다."
            ),
            findings=sensitive_reads,
        )
    )
    disabled_non_public = backend_summary["disabledNonPublic"]
    checks.append(
        make_check(
            "ADVISORY" if disabled_non_public else "PASS",
            "security-disabled-consistency",
            "보안 비활성 모드 일관성",
            (
                f"보안 비활성 모드에서도 접근되지 않는 API가 {len(disabled_non_public)}개입니다."
                if disabled_non_public
                else "보안 비활성 모드의 API 허용 범위가 일관됩니다."
            ),
            findings=disabled_non_public,
        )
    )
    missing_auth = frontend_summary["missingProtectedTargetAuth"]
    checks.append(
        make_check(
            "BLOCKED" if missing_auth else "PASS",
            "frontend-auth-propagation",
            "Frontend 보호 대상 인증 전달",
            (
                "보호된 Backend 대상에 운영자 인증을 전달하지 않는 Proxy가 있습니다."
                if missing_auth
                else "모든 보호 대상 Frontend Proxy가 운영자 인증을 전달합니다."
            ),
            findings=missing_auth,
        )
    )
    missing_guards = frontend_summary["unexpectedUnguardedMutations"]
    advisory_guards = frontend_summary["advisoryUnguardedMutations"]
    checks.append(
        make_check(
            "BLOCKED" if missing_guards else ("ADVISORY" if advisory_guards else "PASS"),
            "frontend-same-origin",
            "Frontend 변경 요청 same-origin 방어",
            (
                "기준선에 없는 same-origin 방어 누락이 있습니다."
                if missing_guards
                else (
                    "기준선에 등록된 same-origin 방어 예외를 검토하세요."
                    if advisory_guards
                    else "브라우저 변경 요청의 same-origin 방어가 일치합니다."
                )
            ),
            unexpected=missing_guards,
            advisory=advisory_guards,
        )
    )
    ai_exposures = ai_summary["sensitivePublicOperations"]
    checks.append(
        make_check(
            "ADVISORY" if ai_exposures or ai_summary["authSignals"] else "PASS",
            "ai-auth-exposure",
            "AI API 인증·노출",
            (
                f"인증 없이 노출되는 민감 AI API가 {len(ai_exposures)}개입니다."
                if ai_exposures
                else (
                    "AI 인증 단서가 발견되어 수동 검토가 필요합니다."
                    if ai_summary["authSignals"]
                    else "AI 민감 API가 공개되지 않습니다."
                )
            ),
            findings=ai_exposures,
            authSignals=ai_summary["authSignals"],
        )
    )
    checks.append(
        make_check(
            "ADVISORY" if compose_drift else "PASS",
            "compose-security-defaults",
            "Compose 보안 기본값",
            (
                "Compose 기본값이 운영 권장 보안 모드보다 느슨합니다."
                if compose_drift
                else "Compose 기본값이 운영 권장 보안 모드입니다."
            ),
            drift=compose_drift,
        )
    )
    runtime_status = runtime["status"]
    checks.append(
        make_check(
            runtime_status,
            "runtime-security-mode",
            "현재 컨테이너 보안 모드",
            (
                "런타임 검사를 생략했습니다."
                if runtime_status == "SKIPPED"
                else (
                    "현재 Backend RBAC·Frontend 세션·Secure Cookie 설정이 권장값입니다."
                    if runtime_status == "PASS"
                    else "현재 컨테이너의 선택된 비밀 제외 보안 설정을 검토하세요."
                )
            ),
            runtime=runtime,
        )
    )

    status = "API_SECURITY_HEALTHY"
    if any(item["status"] == "BLOCKED" for item in checks):
        status = "API_SECURITY_BLOCKED"
    elif any(item["status"] == "ADVISORY" for item in checks):
        status = "API_SECURITY_ADVISORY"

    generated_at = datetime.now(timezone.utc)
    if args.output is not None:
        output_dir = args.output if args.output.is_absolute() else root / args.output
        output_dir = output_dir.resolve()
    else:
        output_dir = (
            root
            / "artifacts"
            / "api-security-audit"
            / generated_at.strftime("audit-%Y%m%dT%H%M%SZ")
        )
    report = {
        "schemaVersion": 1,
        "project": "visionflow",
        "scope": "API_SECURITY_AUTHORIZATION",
        "generatedAt": generated_at.isoformat(),
        "status": status,
        "readOnly": True,
        "git": {
            "commit": current_git_commit(root),
            "baselineCommit": baseline.get("baselineCommit"),
        },
        "sources": {
            "root": str(root),
            "securityBaseline": str(args.baseline.resolve()),
            "contractBaseline": str(args.contract_baseline.resolve()),
            "aiOpenapi": ai_source,
            "aiOpenapiHttpStatus": ai_http_status,
            "securityConfig": security["path"],
        },
        "summary": {
            "counts": actual_counts,
            "methods": {
                "backend": method_counts(backend_operations),
                "frontend": method_counts(frontend_operations),
                "ai": method_counts(ai_operations),
            },
            "backendEnabledAccess": backend_summary["enabledAccessCounts"],
            "backendSensitivePublicReads": len(sensitive_reads),
            "backendDisabledModeMismatches": len(disabled_non_public),
            "frontendMissingAuthPropagation": len(missing_auth),
            "frontendUnguardedAdvisories": len(advisory_guards),
            "aiSensitivePublicOperations": len(ai_exposures),
        },
        "checks": checks,
        "securityRules": {
            "csrfDisabled": security["csrfDisabled"],
            "sessionCreationPolicy": security["sessionCreationPolicy"],
            "enabled": {
                "rules": [item.report_dict() for item in security["enabledRules"]],
                "fallback": security["enabledFallback"],
            },
            "disabled": {
                "rules": [item.report_dict() for item in security["disabledRules"]],
                "fallback": security["disabledFallback"],
            },
        },
        "matrix": {
            "backend": backend_rows,
            "frontend": frontend_rows,
            "ai": ai_rows,
        },
        "compose": {
            "selectedDefaults": compose_actual,
            "drift": compose_drift,
        },
        "runtime": runtime,
        "safety": {
            "databaseMutation": False,
            "containerMutation": False,
            "serviceRestart": False,
            "credentialValueCollection": False,
            "externalWrite": False,
            "writesOnlyReports": True,
        },
    }
    return report, output_dir


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    def clean(value: str) -> str:
        return value.replace("|", "\\|").replace("\n", " ")
    lines = [
        "| " + " | ".join(clean(value) for value in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend(
        "| " + " | ".join(clean(str(value)) for value in row) + " |"
        for row in rows
    )
    return "\n".join(lines)


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    check_rows = [
        [item["status"], item["title"], item["detail"]]
        for item in report["checks"]
    ]
    backend_rows = [
        [row["method"], row["path"], row["enabledAccess"], row["disabledAccess"], row["source"]]
        for row in report["matrix"]["backend"]
    ]
    frontend_rows = [
        [
            row["method"],
            row["path"],
            row["protectedTargetAuth"],
            row["mutationGuard"],
            row["source"],
        ]
        for row in report["matrix"]["frontend"]
    ]
    ai_rows = [
        [row["method"], row["path"], row["access"], row["severity"], row["reason"]]
        for row in report["matrix"]["ai"]
    ]
    return "\n".join(
        [
            "# VisionFlow API 보안·권한 감사",
            "",
            f"> 생성 시각: {report['generatedAt']}<br>",
            f"> 상태: **{report['status']}**<br>",
            f"> Git: `{report['git']['commit'] or 'UNKNOWN'}`",
            "",
            "## 요약",
            "",
            f"- Backend: {summary['counts']['backend']}개",
            f"- Frontend: {summary['counts']['frontend']}개",
            f"- AI: {summary['counts']['ai']}개",
            f"- Backend 민감 공개 GET: {summary['backendSensitivePublicReads']}개",
            f"- Frontend 보호 대상 인증 전달 누락: {summary['frontendMissingAuthPropagation']}개",
            f"- AI 민감 공개 API: {summary['aiSensitivePublicOperations']}개",
            "",
            "## 검사 결과",
            "",
            markdown_table(["상태", "검사", "설명"], check_rows),
            "",
            "## Backend 권한 매트릭스",
            "",
            markdown_table(
                ["Method", "Path", "RBAC 활성", "RBAC 비활성", "Source"],
                backend_rows,
            ),
            "",
            "## Frontend Proxy 보안 매트릭스",
            "",
            markdown_table(
                ["Method", "Path", "보호 대상 인증", "same-origin", "Source"],
                frontend_rows,
            ),
            "",
            "## AI API 노출 매트릭스",
            "",
            markdown_table(["Method", "Path", "접근", "심각도", "근거"], ai_rows),
            "",
            "## 안전 속성",
            "",
            "DB 변경 없음 · 컨테이너 변경 없음 · 서비스 재시작 없음 · 비밀값 수집 없음 · 보고서만 생성",
            "",
        ]
    )


def html_table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{html.escape(value)}</th>" for value in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_html(report: dict[str, Any]) -> str:
    summary = report["summary"]
    checks = html_table(
        ["상태", "검사", "설명"],
        [[item["status"], item["title"], item["detail"]] for item in report["checks"]],
    )
    backend = html_table(
        ["Method", "Path", "RBAC 활성", "RBAC 비활성", "Source"],
        [
            [row["method"], row["path"], row["enabledAccess"], row["disabledAccess"], row["source"]]
            for row in report["matrix"]["backend"]
        ],
    )
    frontend = html_table(
        ["Method", "Path", "보호 대상 인증", "same-origin", "Source"],
        [
            [row["method"], row["path"], row["protectedTargetAuth"], row["mutationGuard"], row["source"]]
            for row in report["matrix"]["frontend"]
        ],
    )
    ai = html_table(
        ["Method", "Path", "접근", "심각도", "근거"],
        [[row["method"], row["path"], row["access"], row["severity"], row["reason"]] for row in report["matrix"]["ai"]],
    )
    status_class = report["status"].replace("API_SECURITY_", "").lower()
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VisionFlow API Security Audit</title><style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f4f7fb;color:#172033}}main{{max-width:1320px;margin:auto;padding:28px}}
.hero{{background:#071126;color:white;padding:28px;border-radius:18px}}.status{{display:inline-block;padding:8px 12px;border-radius:999px;font-weight:700}}
.healthy,.pass{{background:#d1fae5;color:#065f46}}.advisory{{background:#fef3c7;color:#92400e}}.blocked{{background:#fee2e2;color:#991b1b}}
.card{{background:white;border:1px solid #dbe3ef;border-radius:14px;padding:20px;margin-top:18px;overflow:auto}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}}
.metric{{background:#eef4ff;border-radius:12px;padding:16px}}.metric strong{{display:block;font-size:28px}}table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{border-bottom:1px solid #e5eaf2;padding:8px;text-align:left;vertical-align:top}}th{{background:#f8fafc;position:sticky;top:0}}details{{margin-top:14px}}summary{{cursor:pointer;font-weight:700}}
</style></head><body><main><section class="hero"><h1>VisionFlow API 보안·권한 감사</h1><p>{html.escape(report['generatedAt'])}</p><span class="status {status_class}">{html.escape(report['status'])}</span></section>
<section class="card"><h2>요약</h2><div class="grid"><div class="metric">Backend<strong>{summary['counts']['backend']}</strong></div><div class="metric">Frontend<strong>{summary['counts']['frontend']}</strong></div><div class="metric">AI<strong>{summary['counts']['ai']}</strong></div><div class="metric">민감 공개 GET<strong>{summary['backendSensitivePublicReads']}</strong></div><div class="metric">AI 공개 민감 API<strong>{summary['aiSensitivePublicOperations']}</strong></div></div></section>
<section class="card"><h2>검사 결과</h2>{checks}</section><section class="card"><h2>전체 매트릭스</h2><details open><summary>Backend</summary>{backend}</details><details><summary>Frontend</summary>{frontend}</details><details><summary>AI</summary>{ai}</details></section>
<section class="card"><h2>안전 속성</h2><p>DB 변경 없음 · 컨테이너 변경 없음 · 서비스 재시작 없음 · 비밀값 수집 없음 · 보고서만 생성</p></section></main></body></html>"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="VisionFlow Backend·Frontend·AI 읽기 전용 API 보안·권한 감사"
    )
    parser.add_argument("--root", type=Path, default=script_dir.parent)
    parser.add_argument(
        "--baseline",
        type=Path,
        default=script_dir / "visionflow_api_security_baseline.json",
    )
    parser.add_argument(
        "--contract-baseline",
        type=Path,
        default=script_dir / "visionflow_api_contract_baseline.json",
    )
    parser.add_argument("--ai-openapi-url", default="http://localhost:8000/openapi.json")
    parser.add_argument("--ai-openapi-file", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--backend-container", default="visionflow-backend")
    parser.add_argument("--frontend-container", default="visionflow-frontend")
    parser.add_argument("--skip-runtime", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds는 0보다 커야 합니다.")
    return args


def main(argv: list[str] | None = None) -> int:
    configure_console()
    args = parse_args(argv)
    try:
        report, output_dir = audit(args)
        json_path = output_dir / "visionflow-api-security-audit.json"
        html_path = output_dir / "visionflow-api-security-audit.html"
        markdown_path = output_dir / "visionflow-api-security-matrix.md"
        atomic_write_text(json_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        atomic_write_text(html_path, render_html(report))
        atomic_write_text(markdown_path, render_markdown(report))
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError) as error:
        print(f"[FAIL] API 보안 감사를 실행하지 못했습니다: {error}", file=sys.stderr)
        return 2

    print(f"VisionFlow API security audit: {report['status']}")
    counts = report["summary"]["counts"]
    print(f"Operations: Backend={counts['backend']}, Frontend={counts['frontend']}, AI={counts['ai']}")
    for item in report["checks"]:
        print(f"[{item['status']}] {item['key']}: {item['detail']}")
    print(f"JSON report: {json_path}")
    print(f"HTML report: {html_path}")
    print(f"Markdown matrix: {markdown_path}")
    print("Safety: read-only; reports only; no credential values collected")
    if report["status"] == "API_SECURITY_BLOCKED":
        return 1
    if args.strict and report["status"] == "API_SECURITY_ADVISORY":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
