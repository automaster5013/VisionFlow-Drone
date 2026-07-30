"""Finalize a model release or roll it back from verified soak evidence."""

from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from visionflow_model_promotion import (
        ModelPromotionError,
        artifact_entry,
        is_within,
        newest_artifact,
        parse_timestamp,
        read_json,
        resolve_inside,
        sha256_file,
    )
    from visionflow_model_release import (
        ACCEPTANCE_SCRIPT,
        ACTIVATED_STATUS,
        CommandResult,
        ModelReleaseError,
        Runner,
        compose_command,
        default_runner,
        run_step,
        validate_runtime_files,
        verify_activation_report,
        verify_release_report,
        verify_sidecar,
        write_sidecar,
    )
    from visionflow_model_soak import (
        BLOCKED_STATUS,
        PASSED_STATUS,
        ModelSoakError,
        input_by_key,
        verify_report as verify_soak_report,
    )
except ModuleNotFoundError:  # pragma: no cover - package import during tests
    from scripts.visionflow_model_promotion import (
        ModelPromotionError,
        artifact_entry,
        is_within,
        newest_artifact,
        parse_timestamp,
        read_json,
        resolve_inside,
        sha256_file,
    )
    from scripts.visionflow_model_release import (
        ACCEPTANCE_SCRIPT,
        ACTIVATED_STATUS,
        CommandResult,
        ModelReleaseError,
        Runner,
        compose_command,
        default_runner,
        run_step,
        validate_runtime_files,
        verify_activation_report,
        verify_release_report,
        verify_sidecar,
        write_sidecar,
    )
    from scripts.visionflow_model_soak import (
        BLOCKED_STATUS,
        PASSED_STATUS,
        ModelSoakError,
        input_by_key,
        verify_report as verify_soak_report,
    )


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
OPERATION = "MODEL_POST_SOAK_RELEASE_DECISION"
STABILIZED_STATUS = "MODEL_RELEASE_STABILIZED"
ROLLED_BACK_STATUS = "MODEL_SOAK_ROLLED_BACK"
FAILED_STATUS = "MODEL_SOAK_ROLLBACK_FAILED"
ROLLBACK_CONFIRMATION = "ROLLBACK_BLOCKED_MODEL_SOAK"
DEFAULT_OUTPUT = Path("artifacts/model-soak-decision")
SOAK_PATTERN = "artifacts/model-soak/soak-*/visionflow-model-soak.json"


class ModelSoakDecisionError(RuntimeError):
    """Raised when a soak release decision cannot be proven safe."""


def linked_artifact_path(
    root: Path,
    value: object,
    title: str,
) -> Path:
    if not isinstance(value, Mapping) or not isinstance(
        value.get("path"),
        str,
    ):
        raise ModelSoakDecisionError(f"{title} 연결 경로가 없습니다.")
    path = resolve_inside(root, value["path"], title)
    if (
        value.get("sizeBytes") != path.stat().st_size
        or value.get("sha256") != sha256_file(path)
    ):
        raise ModelSoakDecisionError(f"{title} 동일성이 다릅니다.")
    return path


def resolve_context(
    *,
    root: Path,
    soak_path: Path,
) -> tuple[
    Path,
    dict[str, Any],
    Path,
    dict[str, Any],
    Path,
    dict[str, Any],
    Path,
]:
    root = root.resolve()
    try:
        soak_path, soak = verify_soak_report(
            root=root,
            report_path=soak_path,
        )
    except (ModelSoakError, ModelReleaseError, OSError) as error:
        raise ModelSoakDecisionError(str(error)) from error
    activation_path = linked_artifact_path(
        root,
        input_by_key(soak, "model-release-activation"),
        "모델 릴리스 실행",
    )
    try:
        activation_path, activation = verify_activation_report(
            root=root,
            report_path=activation_path,
        )
    except (ModelReleaseError, OSError) as error:
        raise ModelSoakDecisionError(str(error)) from error
    if activation.get("status") != ACTIVATED_STATUS:
        raise ModelSoakDecisionError(
            "MODEL_RELEASE_ACTIVATED 실행에 대한 소크만 확정할 수 있습니다."
        )
    release_path = linked_artifact_path(
        root,
        activation.get("release"),
        "모델 릴리스 준비",
    )
    try:
        release_path, release = verify_release_report(
            root=root,
            report_path=release_path,
        )
    except (ModelReleaseError, OSError) as error:
        raise ModelSoakDecisionError(str(error)) from error
    rollback_env = release_path.parent / "visionflow-model-rollback.env"
    if not rollback_env.is_file() or rollback_env.is_symlink():
        raise ModelSoakDecisionError("검증된 모델 롤백 오버레이가 없습니다.")
    return (
        soak_path,
        soak,
        activation_path,
        activation,
        release_path,
        release,
        rollback_env,
    )


def render_html(report: Mapping[str, Any]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['title']))}</td>"
        f"<td>{html.escape(str(item['status']))}</td>"
        f"<td>{html.escape(str(item['exitCode']))}</td>"
        "</tr>"
        for item in report["steps"]
    )
    if not rows:
        rows = (
            "<tr><td>소크 통과</td><td>PASS</td>"
            "<td>Docker 변경 없음</td></tr>"
        )
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VisionFlow 모델 소크 릴리스 결정</title><style>
body{{margin:0;background:#eef3f8;color:#0f172a;font-family:Arial,'Noto Sans KR',sans-serif}}
main{{max-width:980px;margin:32px auto;padding:0 20px}}
section{{background:#fff;border:1px solid #dbe4ee;border-radius:16px;padding:24px;margin:16px 0}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid #e2e8f0;text-align:left}}
</style></head><body><main><section>
<h1>VisionFlow 모델 소크 릴리스 결정</h1>
<p>{html.escape(str(report['status']))}</p>
<p>{html.escape(str(report['generatedAt']))}</p></section>
<section><table><tr><th>단계</th><th>상태</th><th>종료 코드</th></tr>
{rows}</table></section></main></body></html>"""


def write_report(
    *,
    output_directory: Path,
    report: dict[str, Any],
) -> tuple[Path, Path, Path]:
    timestamp = parse_timestamp(
        report["generatedAt"],
        "모델 소크 릴리스 결정",
    ).strftime("%Y%m%dT%H%M%SZ")
    run_directory = output_directory / f"decision-{timestamp}"
    if run_directory.exists():
        run_directory = output_directory / (
            f"decision-{timestamp}-{uuid.uuid4().hex[:8]}"
        )
    run_directory.mkdir(parents=True, exist_ok=False)
    report_path = run_directory / "visionflow-model-soak-decision.json"
    html_path = run_directory / "visionflow-model-soak-decision.html"
    sidecar_path = run_directory / "visionflow-model-soak-decision.sha256"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    html_path.write_text(render_html(report), encoding="utf-8")
    write_sidecar(sidecar_path, [report_path, html_path])
    return report_path, html_path, sidecar_path


def build_decision_report(
    *,
    root: Path,
    soak_path: Path,
    soak: Mapping[str, Any],
    activation_path: Path,
    activation: Mapping[str, Any],
    release_path: Path,
    release: Mapping[str, Any],
    steps: list[dict[str, Any]],
    status: str,
    now: datetime,
    rollback_required: bool,
    rollback_attempted: bool,
    rollback_succeeded: bool,
    confirmation_matched: bool,
    decision_id: str | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "operation": OPERATION,
        "decisionId": decision_id or str(uuid.uuid4()),
        "generatedAt": now.astimezone(timezone.utc).isoformat(),
        "status": status,
        "inputs": [
            artifact_entry(root, "model-soak", soak_path),
            artifact_entry(
                root,
                "model-release-activation",
                activation_path,
            ),
            artifact_entry(root, "model-release", release_path),
        ],
        "soakStatus": soak.get("status"),
        "activeModel": activation.get("activeModel"),
        "rollbackModel": release.get("rollbackModel"),
        "steps": steps,
        "summary": {
            "releaseStabilized": status == STABILIZED_STATUS,
            "rollbackRequired": rollback_required,
            "rollbackSucceeded": rollback_succeeded,
        },
        "safety": {
            "confirmationMatched": confirmation_matched,
            "rollbackRequired": rollback_required,
            "rollbackAttempted": rollback_attempted,
            "rollbackSucceeded": rollback_succeeded,
            "baseEnvironmentModified": False,
            "modelWeightsModified": False,
            "databaseMutation": False,
            "commandOutputRecorded": False,
            "environmentValuesRecorded": False,
            "operatorKeysRecorded": False,
            "absolutePathsRecorded": False,
        },
    }


def execute_decision(
    *,
    root: Path,
    soak_path: Path,
    confirmation: str,
    timeout_seconds: int,
    now: datetime,
    output_directory: Path | None = None,
    runner: Runner = default_runner,
    platform_name: str = os.name,
) -> tuple[Path, dict[str, Any], int]:
    root = root.resolve()
    (
        soak_path,
        soak,
        activation_path,
        activation,
        release_path,
        release,
        rollback_env,
    ) = resolve_context(root=root, soak_path=soak_path)
    soak_status = soak.get("status")
    if soak_status not in {PASSED_STATUS, BLOCKED_STATUS}:
        raise ModelSoakDecisionError("지원하지 않는 모델 소크 상태입니다.")
    steps: list[dict[str, Any]] = []
    rollback_required = soak_status == BLOCKED_STATUS
    rollback_attempted = False
    rollback_succeeded = False
    confirmation_matched = False

    if rollback_required:
        if confirmation != ROLLBACK_CONFIRMATION:
            raise ModelSoakDecisionError(
                f"--confirm {ROLLBACK_CONFIRMATION} 확인이 필요합니다."
            )
        confirmation_matched = True
        if platform_name != "nt":
            raise ModelSoakDecisionError(
                "모델 소크 롤백 실행은 Windows HP OMEN 전용입니다."
            )
        if timeout_seconds <= 0:
            raise ModelSoakDecisionError("실행 제한 시간은 양수여야 합니다.")
        try:
            validate_runtime_files(root)
        except ModelReleaseError as error:
            raise ModelSoakDecisionError(str(error)) from error
        rollback_compose = compose_command(root, rollback_env)
        config_step, config_result = run_step(
            key="rollback-compose-config",
            title="기준 모델 롤백 Compose 구성 검증",
            command=rollback_compose + ["config", "-q"],
            root=root,
            timeout_seconds=timeout_seconds,
            runner=runner,
        )
        steps.append(config_step)
        start_result = CommandResult(1)
        acceptance_result = CommandResult(1)
        if config_result.exit_code == 0:
            rollback_attempted = True
            start_step, start_result = run_step(
                key="rollback-start",
                title="검증된 기준 모델 자동 롤백",
                command=rollback_compose
                + [
                    "up",
                    "--detach",
                    "--build",
                    "--wait",
                    "--wait-timeout",
                    "300",
                ],
                root=root,
                timeout_seconds=timeout_seconds,
                runner=runner,
            )
            steps.append(start_step)
        if start_result.exit_code == 0:
            acceptance_step, acceptance_result = run_step(
                key="rollback-acceptance",
                title="롤백 모델 기본 인수 테스트",
                command=[
                    "cmd.exe",
                    "/d",
                    "/c",
                    str(root / ACCEPTANCE_SCRIPT),
                ],
                root=root,
                timeout_seconds=timeout_seconds,
                runner=runner,
            )
            steps.append(acceptance_step)
        rollback_succeeded = (
            config_result.exit_code == 0
            and start_result.exit_code == 0
            and acceptance_result.exit_code == 0
        )
        status = (
            ROLLED_BACK_STATUS if rollback_succeeded else FAILED_STATUS
        )
    else:
        status = STABILIZED_STATUS

    report = build_decision_report(
        root=root,
        soak_path=soak_path,
        soak=soak,
        activation_path=activation_path,
        activation=activation,
        release_path=release_path,
        release=release,
        steps=steps,
        status=status,
        now=now,
        rollback_required=rollback_required,
        rollback_attempted=rollback_attempted,
        rollback_succeeded=rollback_succeeded,
        confirmation_matched=confirmation_matched,
    )
    report_path, _, _ = write_report(
        output_directory=output_directory or root / DEFAULT_OUTPUT,
        report=report,
    )
    return (
        report_path,
        report,
        0 if status == STABILIZED_STATUS else 1,
    )


def report_input(
    report: Mapping[str, Any],
    key: str,
) -> Mapping[str, Any]:
    inputs = report.get("inputs")
    if not isinstance(inputs, list):
        raise ModelSoakDecisionError("소크 릴리스 결정 입력이 없습니다.")
    matches = [
        item
        for item in inputs
        if isinstance(item, Mapping) and item.get("key") == key
    ]
    if len(matches) != 1:
        raise ModelSoakDecisionError(
            f"소크 릴리스 결정 입력이 정확히 하나가 아닙니다: {key}"
        )
    return matches[0]


def validate_steps(
    *,
    soak_status: str,
    steps: object,
) -> tuple[str, bool, bool, bool]:
    if not isinstance(steps, list):
        raise ModelSoakDecisionError("소크 릴리스 결정 단계가 없습니다.")
    keys: list[str] = []
    by_key: dict[str, Mapping[str, Any]] = {}
    for item in steps:
        if not isinstance(item, Mapping) or not isinstance(
            item.get("key"),
            str,
        ):
            raise ModelSoakDecisionError("소크 릴리스 결정 단계가 올바르지 않습니다.")
        key = str(item["key"])
        if key in by_key:
            raise ModelSoakDecisionError("중복된 소크 릴리스 결정 단계가 있습니다.")
        exit_code = item.get("exitCode")
        duration_ms = item.get("durationMs")
        if (
            isinstance(exit_code, bool)
            or not isinstance(exit_code, int)
            or isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or duration_ms < 0
            or item.get("status")
            != ("PASS" if exit_code == 0 else "FAILED")
        ):
            raise ModelSoakDecisionError("소크 릴리스 단계 결과가 다릅니다.")
        keys.append(key)
        by_key[key] = item

    if soak_status == PASSED_STATUS:
        if keys:
            raise ModelSoakDecisionError(
                "통과한 소크에는 롤백 실행 단계가 없어야 합니다."
            )
        return STABILIZED_STATUS, False, False, False
    if soak_status != BLOCKED_STATUS:
        raise ModelSoakDecisionError("지원하지 않는 모델 소크 상태입니다.")

    allowed = (
        "rollback-compose-config",
        "rollback-start",
        "rollback-acceptance",
    )
    if not keys or any(key not in allowed for key in keys):
        raise ModelSoakDecisionError("알 수 없는 소크 롤백 단계가 있습니다.")
    if keys[0] != "rollback-compose-config":
        raise ModelSoakDecisionError("소크 롤백 단계 순서가 다릅니다.")
    config_passed = by_key["rollback-compose-config"].get("status") == "PASS"
    if not config_passed and len(keys) != 1:
        raise ModelSoakDecisionError("실패한 Compose 검증 이후 단계가 있습니다.")
    if config_passed and (
        len(keys) < 2 or keys[1] != "rollback-start"
    ):
        raise ModelSoakDecisionError("롤백 기동 단계가 없습니다.")
    start_passed = (
        "rollback-start" in by_key
        and by_key["rollback-start"].get("status") == "PASS"
    )
    if "rollback-start" in by_key and not start_passed and len(keys) != 2:
        raise ModelSoakDecisionError("실패한 롤백 기동 이후 단계가 있습니다.")
    if start_passed and (
        len(keys) != 3 or keys[2] != "rollback-acceptance"
    ):
        raise ModelSoakDecisionError("롤백 인수 테스트 단계가 없습니다.")
    rollback_succeeded = (
        start_passed
        and "rollback-acceptance" in by_key
        and by_key["rollback-acceptance"].get("status") == "PASS"
    )
    return (
        ROLLED_BACK_STATUS if rollback_succeeded else FAILED_STATUS,
        True,
        "rollback-start" in by_key,
        rollback_succeeded,
    )


def verify_decision_report(
    *,
    root: Path,
    report_path: Path,
) -> tuple[Path, dict[str, Any]]:
    root = root.resolve()
    report_path = resolve_inside(
        root,
        report_path,
        "모델 소크 릴리스 결정 보고서",
    )
    html_path = report_path.with_suffix(".html")
    sidecar_path = report_path.with_suffix(".sha256")
    verify_sidecar(sidecar_path, [report_path, html_path])
    report = read_json(report_path, "모델 소크 릴리스 결정 보고서")
    if (
        report.get("schemaVersion") != SCHEMA_VERSION
        or report.get("project") != PROJECT_NAME
        or report.get("operation") != OPERATION
        or report.get("status")
        not in {STABILIZED_STATUS, ROLLED_BACK_STATUS, FAILED_STATUS}
    ):
        raise ModelSoakDecisionError(
            "VisionFlow 모델 소크 릴리스 결정 보고서가 아닙니다."
        )
    try:
        uuid.UUID(str(report.get("decisionId")))
    except (ValueError, AttributeError) as error:
        raise ModelSoakDecisionError(
            "모델 소크 릴리스 결정 ID가 올바르지 않습니다."
        ) from error

    soak_path = linked_artifact_path(
        root,
        report_input(report, "model-soak"),
        "모델 소크",
    )
    activation_path = linked_artifact_path(
        root,
        report_input(report, "model-release-activation"),
        "모델 릴리스 실행",
    )
    release_path = linked_artifact_path(
        root,
        report_input(report, "model-release"),
        "모델 릴리스 준비",
    )
    (
        expected_soak_path,
        soak,
        expected_activation_path,
        activation,
        expected_release_path,
        release,
        _,
    ) = resolve_context(root=root, soak_path=soak_path)
    if (
        activation_path != expected_activation_path
        or release_path != expected_release_path
        or soak_path != expected_soak_path
        or report.get("soakStatus") != soak.get("status")
        or report.get("activeModel") != activation.get("activeModel")
        or report.get("rollbackModel") != release.get("rollbackModel")
    ):
        raise ModelSoakDecisionError(
            "소크·활성화·릴리스 연결 또는 모델 동일성이 다릅니다."
        )
    (
        expected_status,
        rollback_required,
        rollback_attempted,
        rollback_succeeded,
    ) = validate_steps(
        soak_status=str(soak.get("status")),
        steps=report.get("steps"),
    )
    expected_summary = {
        "releaseStabilized": expected_status == STABILIZED_STATUS,
        "rollbackRequired": rollback_required,
        "rollbackSucceeded": rollback_succeeded,
    }
    expected_safety = {
        "confirmationMatched": rollback_required,
        "rollbackRequired": rollback_required,
        "rollbackAttempted": rollback_attempted,
        "rollbackSucceeded": rollback_succeeded,
        "baseEnvironmentModified": False,
        "modelWeightsModified": False,
        "databaseMutation": False,
        "commandOutputRecorded": False,
        "environmentValuesRecorded": False,
        "operatorKeysRecorded": False,
        "absolutePathsRecorded": False,
    }
    if (
        report.get("status") != expected_status
        or report.get("summary") != expected_summary
        or report.get("safety") != expected_safety
    ):
        raise ModelSoakDecisionError(
            "소크 릴리스 결정 상태 계산이 다릅니다."
        )
    parse_timestamp(report.get("generatedAt"), "소크 릴리스 결정")
    if html_path.read_text(encoding="utf-8-sig") != render_html(report):
        raise ModelSoakDecisionError(
            "모델 소크 릴리스 결정 JSON과 HTML이 다릅니다."
        )
    return report_path, report


def build_plan() -> list[str]:
    return [
        "MODEL_SOAK_PASSED 또는 MODEL_SOAK_BLOCKED 증적 재검증",
        "소크 통과 시 MODEL_RELEASE_STABILIZED 확정",
        "소크 차단 시 명시적 확인 토큰 검사",
        "검증된 yolo26n.pt 롤백 Compose 구성 적용",
        "롤백 스택 기동 후 기본 인수 테스트",
        "JSON·HTML·SHA-256 결정 증적 생성 및 독립 검증",
    ]


def output_path(root: Path, value: str) -> Path:
    output = resolve_inside(
        root,
        value,
        "모델 소크 결정 출력",
        require_file=False,
    )
    if not is_within(output, (root / DEFAULT_OUTPUT).resolve()):
        raise ModelSoakDecisionError(
            "모델 소크 결정 출력은 artifacts/model-soak-decision "
            "안에 있어야 합니다."
        )
    return output


def parser(default_root: Path) -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="VisionFlow model post-soak release decision"
    )
    value.add_argument("--root", default=str(default_root))
    subparsers = value.add_subparsers(dest="command", required=True)
    subparsers.add_parser("plan")
    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("--soak")
    apply_parser.add_argument("--confirm", default="")
    apply_parser.add_argument("--timeout-seconds", type=int, default=900)
    apply_parser.add_argument("--output", default=DEFAULT_OUTPUT.as_posix())
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--report", required=True)
    return value


def main(argv: Sequence[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    arguments = parser(default_root).parse_args(argv)
    root = Path(arguments.root).resolve()
    try:
        if arguments.command == "plan":
            print("VisionFlow model soak decision: PLAN")
            for index, item in enumerate(build_plan(), start=1):
                print(f"{index:02d}. {item}")
            print("No model, database, Docker, or service was changed.")
            return 0
        if arguments.command == "verify":
            path, report = verify_decision_report(
                root=root,
                report_path=Path(arguments.report),
            )
            print("VisionFlow model soak decision: VERIFIED")
            print(f"Status: {report['status']}")
            print(f"Report: {path}")
            return 0

        soak_path = (
            resolve_inside(root, arguments.soak, "모델 소크 보고서")
            if arguments.soak
            else newest_artifact(root, SOAK_PATTERN, "모델 소크")
        )
        report_path, report, exit_code = execute_decision(
            root=root,
            soak_path=soak_path,
            confirmation=arguments.confirm,
            timeout_seconds=arguments.timeout_seconds,
            now=datetime.now(timezone.utc),
            output_directory=output_path(root, arguments.output),
        )
        verify_decision_report(root=root, report_path=report_path)
        print(f"VisionFlow model soak decision: {report['status']}")
        print(f"Report: {report_path}")
        return exit_code
    except (
        ModelSoakDecisionError,
        ModelSoakError,
        ModelReleaseError,
        ModelPromotionError,
        OSError,
        subprocess.SubprocessError,
    ) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
