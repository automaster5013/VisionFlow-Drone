from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 최상위 값이 객체가 아닙니다: {path}")
    return value


def check_index(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = report.get("checks")
    if not isinstance(rows, list):
        raise ValueError("보고서 checks 값이 배열이 아닙니다.")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("key"), str):
            raise ValueError("보고서 check 형식이 올바르지 않습니다.")
        key = row["key"]
        if key in result:
            raise ValueError(f"중복 check key: {key}")
        result[key] = row
    return result


def report_counts(report: dict[str, Any]) -> dict[str, int]:
    summary = report.get("summary")
    counts = summary.get("counts") if isinstance(summary, dict) else None
    if not isinstance(counts, dict):
        raise ValueError("보고서 summary.counts 값이 없습니다.")
    return {name: int(counts.get(name, -1)) for name in ("backend", "frontend", "ai")}


def verify_read_only(report: dict[str, Any], label: str, failures: list[str]) -> None:
    if report.get("readOnly") is not True:
        failures.append(f"{label}: readOnly=true가 아닙니다.")
    safety = report.get("safety")
    if not isinstance(safety, dict):
        failures.append(f"{label}: safety 객체가 없습니다.")
        return
    for key in ("databaseMutation", "containerMutation", "serviceRestart"):
        if safety.get(key) is not False:
            failures.append(f"{label}: safety.{key}=false가 아닙니다.")
    if safety.get("writesOnlyReports") is not True:
        failures.append(f"{label}: safety.writesOnlyReports=true가 아닙니다.")
    if label == "security" and safety.get("credentialValueCollection") is not False:
        failures.append(f"{label}: safety.credentialValueCollection=false가 아닙니다.")
    if label == "traceability" and safety.get("secretValuesCollected") is not False:
        failures.append(f"{label}: safety.secretValuesCollected=false가 아닙니다.")


def verify_counts(
    report: dict[str, Any],
    expected: dict[str, Any],
    label: str,
    failures: list[str],
) -> None:
    actual = report_counts(report)
    normalized_expected = {
        name: int(expected.get(name, -1)) for name in ("backend", "frontend", "ai")
    }
    if actual != normalized_expected:
        failures.append(
            f"{label}: operation 수가 다릅니다. expected={normalized_expected}, actual={actual}"
        )


def allowed_contract_advisories(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = policy.get("allowedContractAdvisories", [])
    if not isinstance(rows, list):
        raise ValueError("allowedContractAdvisories 값이 배열이 아닙니다.")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("key"), str):
            raise ValueError("허용 계약 Advisory 형식이 올바르지 않습니다.")
        result[row["key"]] = row
    return result


def verify_contract(
    report: dict[str, Any],
    policy: dict[str, Any],
    failures: list[str],
) -> None:
    status = report.get("status")
    allowed = allowed_contract_advisories(policy)
    allowed_statuses = (
        {"API_CONTRACT_HEALTHY", "API_CONTRACT_ADVISORY"}
        if allowed
        else {"API_CONTRACT_HEALTHY"}
    )
    if status not in allowed_statuses:
        failures.append(f"contract: 허용되지 않은 전체 상태입니다: {status}")

    checks = check_index(report)
    advisory_keys = {
        key for key, row in checks.items() if row.get("status") == "ADVISORY"
    }
    unexpected_keys = advisory_keys - set(allowed)
    if unexpected_keys:
        failures.append(f"contract: 새 Advisory check가 있습니다: {sorted(unexpected_keys)}")

    for key, row in checks.items():
        row_status = row.get("status")
        if row_status not in {"PASS", "ADVISORY"}:
            failures.append(f"contract: {key} 상태가 {row_status}입니다.")

    for key in advisory_keys & set(allowed):
        row = checks[key]
        rule = allowed[key]
        unexpected = row.get("unexpected", [])
        if unexpected:
            failures.append(f"contract: {key} unexpected 항목이 있습니다: {unexpected}")
        advisory = row.get("advisory", [])
        if not isinstance(advisory, list):
            failures.append(f"contract: {key}.advisory가 배열이 아닙니다.")
            continue
        operations = {
            str(item.get("operation"))
            for item in advisory
            if isinstance(item, dict) and item.get("operation")
        }
        allowed_operations = {str(value) for value in rule.get("operations", [])}
        if not operations <= allowed_operations:
            failures.append(
                f"contract: {key}에 승인되지 않은 operation이 있습니다: "
                f"{sorted(operations - allowed_operations)}"
            )
        maximum = int(rule.get("maxFindings", len(allowed_operations)))
        if len(advisory) > maximum:
            failures.append(
                f"contract: {key} finding이 허용 수를 초과했습니다: "
                f"{len(advisory)} > {maximum}"
            )


def verify_security(
    report: dict[str, Any],
    policy: dict[str, Any],
    failures: list[str],
) -> None:
    status = report.get("status")
    if status != "API_SECURITY_HEALTHY":
        failures.append(f"security: API_SECURITY_HEALTHY가 아닙니다: {status}")

    allowed_skipped = {
        str(value) for value in policy.get("allowedSecuritySkippedChecks", [])
    }
    checks = check_index(report)
    for key, row in checks.items():
        row_status = row.get("status")
        if row_status == "PASS":
            continue
        if row_status == "SKIPPED" and key in allowed_skipped:
            continue
        failures.append(f"security: {key} 상태가 {row_status}입니다.")


def traceability_counts(report: dict[str, Any]) -> dict[str, int]:
    summary = report.get("summary")
    counts = summary.get("counts") if isinstance(summary, dict) else None
    if not isinstance(counts, dict):
        raise ValueError("추적성 보고서 summary.counts 값이 없습니다.")
    result = {
        name: int(counts.get(name, -1))
        for name in (
            "backend",
            "frontend",
            "ai",
            "tables",
            "entities",
            "repositories",
            "foreignKeys",
        )
    }
    result["flows"] = int(summary.get("flows", -1))
    result["softCorrelations"] = int(summary.get("softCorrelations", -1))
    return result


def verify_traceability(
    report: dict[str, Any],
    policy: dict[str, Any],
    failures: list[str],
) -> None:
    status = report.get("status")
    if status != "SYSTEM_TRACEABILITY_HEALTHY":
        failures.append(
            "traceability: SYSTEM_TRACEABILITY_HEALTHY가 아닙니다: "
            f"{status}"
        )

    expected = policy.get("expectedTraceabilityCounts")
    if not isinstance(expected, dict):
        raise ValueError("정책 expectedTraceabilityCounts 값이 없습니다.")
    actual = traceability_counts(report)
    normalized_expected = {name: int(expected.get(name, -1)) for name in actual}
    if actual != normalized_expected:
        failures.append(
            "traceability: 기준 수량이 다릅니다. "
            f"expected={normalized_expected}, actual={actual}"
        )

    expected_checks_value = policy.get("expectedTraceabilityChecks")
    if not isinstance(expected_checks_value, list):
        raise ValueError("정책 expectedTraceabilityChecks 값이 배열이 아닙니다.")
    expected_checks = {str(value) for value in expected_checks_value}
    checks = check_index(report)
    actual_checks = set(checks)
    if actual_checks != expected_checks:
        failures.append(
            "traceability: 검사키 구성이 다릅니다. "
            f"missing={sorted(expected_checks - actual_checks)}, "
            f"unexpected={sorted(actual_checks - expected_checks)}"
        )
    for key, row in checks.items():
        if row.get("status") != "PASS":
            failures.append(f"traceability: {key} 상태가 {row.get('status')}입니다.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="VisionFlow API 계약·보안 CI 정책 게이트"
    )
    parser.add_argument("--contract-report", type=Path, required=True)
    parser.add_argument("--security-report", type=Path, required=True)
    parser.add_argument("--traceability-report", type=Path, required=True)
    parser.add_argument(
        "--policy",
        type=Path,
        default=script_dir / "visionflow_ci_api_audit_policy.json",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        policy = read_object(args.policy)
        contract = read_object(args.contract_report)
        security = read_object(args.security_report)
        traceability = read_object(args.traceability_report)
        expected_counts = policy.get("expectedCounts")
        if not isinstance(expected_counts, dict):
            raise ValueError("정책 expectedCounts 값이 없습니다.")

        failures: list[str] = []
        verify_counts(contract, expected_counts, "contract", failures)
        verify_counts(security, expected_counts, "security", failures)
        verify_read_only(contract, "contract", failures)
        verify_read_only(security, "security", failures)
        verify_read_only(traceability, "traceability", failures)
        verify_contract(contract, policy, failures)
        verify_security(security, policy, failures)
        verify_traceability(traceability, policy, failures)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"VisionFlow API audit CI gate: BLOCKED\n[FAIL] {error}")
        return 2

    if failures:
        print("VisionFlow API audit CI gate: BLOCKED")
        for failure in failures:
            print(f"[FAIL] {failure}")
        return 1

    counts = report_counts(contract)
    print("VisionFlow API audit CI gate: PASS")
    print(
        "Operations: "
        f"Backend={counts['backend']}, Frontend={counts['frontend']}, AI={counts['ai']}"
    )
    print(f"Contract: {contract.get('status')}")
    print("Security: API_SECURITY_HEALTHY")
    trace_counts = traceability_counts(traceability)
    print(
        "Traceability: SYSTEM_TRACEABILITY_HEALTHY; "
        f"Tables={trace_counts['tables']}, Entities={trace_counts['entities']}, "
        f"Repositories={trace_counts['repositories']}, "
        f"ForeignKeys={trace_counts['foreignKeys']}"
    )
    print("Safety: read-only reports; no runtime or secret access")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
