"""Checkpointed HP OMEN transfer-day bootstrap and resume workflow."""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from visionflow_hp_omen_restore import (
        ACTIVATE_CONFIRMATION,
        ACTIVATED_STATUS,
        ACTIVATE_OPERATION,
        MODEL_DEFAULT,
        PREFLIGHT_BLOCKED_STATUS,
        PREFLIGHT_OPERATION,
        PREFLIGHT_STATUS,
        PREPARE_CONFIRMATION,
        CommandResult,
        HpOmenRestoreError,
        Runner,
        artifact_entry,
        create_activation_preflight,
        default_runner,
        execute_activation,
        inspect_package,
        latest_report_path,
        prepare_workspace,
        read_json,
        relative_path,
        resolve_report,
        sha256_file,
        validate_activation_start_lineage,
        validate_failed_activation_recovery_source,
        verify_activation_preflight_report,
        verify_activation_report,
        verify_multi_sidecar,
        verify_prepare_report,
        write_multi_sidecar,
        write_text_atomic,
    )
except ModuleNotFoundError:  # pragma: no cover - package import during tests
    from scripts.visionflow_hp_omen_restore import (
        ACTIVATE_CONFIRMATION,
        ACTIVATED_STATUS,
        ACTIVATE_OPERATION,
        MODEL_DEFAULT,
        PREFLIGHT_BLOCKED_STATUS,
        PREFLIGHT_OPERATION,
        PREFLIGHT_STATUS,
        PREPARE_CONFIRMATION,
        CommandResult,
        HpOmenRestoreError,
        Runner,
        artifact_entry,
        create_activation_preflight,
        default_runner,
        execute_activation,
        inspect_package,
        latest_report_path,
        prepare_workspace,
        read_json,
        relative_path,
        resolve_report,
        sha256_file,
        validate_activation_start_lineage,
        validate_failed_activation_recovery_source,
        verify_activation_preflight_report,
        verify_activation_report,
        verify_multi_sidecar,
        verify_prepare_report,
        write_multi_sidecar,
        write_text_atomic,
    )


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
OPERATION = "HP_OMEN_TRANSFER_DAY"
REPORT_ROOT = Path("artifacts/hp-omen-transfer-day")
MANUAL_STATUS = "TRANSFER_DAY_MANUAL_INPUT_REQUIRED"
CONFIRMATION_STATUS = "TRANSFER_DAY_ACTIVATION_CONFIRMATION_REQUIRED"
READY_STATUS = "TRANSFER_DAY_READY_WITH_DEFERRED"
RECOVERY_STATUS = "TRANSFER_DAY_RECOVERY_REQUIRED"
ALLOWED_STATUSES = {
    MANUAL_STATUS,
    CONFIRMATION_STATUS,
    READY_STATUS,
    RECOVERY_STATUS,
}
NEXT_ACTIONS = {
    MANUAL_STATUS: (
        "HP 전용 .env.docker, best.pt, VIEWER·OPERATOR·ADMIN 역할 키를 "
        "준비한 뒤 resume을 다시 실행하세요."
    ),
    CONFIRMATION_STATUS: (
        f"--confirm-activate {ACTIVATE_CONFIRMATION}을 지정해 resume을 "
        "다시 실행하세요."
    ),
    READY_STATUS: (
        "HP 기본 런타임 준비가 완료됐습니다. 모델 정확도·성능 검증으로 "
        "이동하세요."
    ),
    RECOVERY_STATUS: (
        "실패 활성화 보고서로 recover를 완료한 뒤 resume을 다시 "
        "실행하세요."
    ),
}


class TransferDayError(RuntimeError):
    """Raised when transfer-day progress cannot be proven safe."""


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_checkpoint(root: Path, value: str | Path) -> Path:
    candidate = Path(value)
    path = (
        candidate.resolve()
        if candidate.is_absolute()
        else (root / candidate).resolve()
    )
    allowed = (root / REPORT_ROOT).resolve()
    if (
        not is_within(path, allowed)
        or not path.is_file()
        or path.is_symlink()
        or path.name != "visionflow-hp-omen-transfer-day.json"
    ):
        raise TransferDayError(
            f"이관 당일 체크포인트 경로가 올바르지 않습니다: {path}"
        )
    return path


def latest_checkpoint(root: Path) -> Path:
    candidates = [
        path.resolve()
        for path in (root / REPORT_ROOT).glob(
            "checkpoint-*/visionflow-hp-omen-transfer-day.json"
        )
        if path.is_file() and not path.is_symlink()
    ]
    if not candidates:
        raise TransferDayError(
            "이관 당일 체크포인트가 없습니다. bootstrap을 먼저 실행하세요."
        )
    return max(
        candidates,
        key=lambda path: (path.stat().st_mtime_ns, path.as_posix()),
    )


def resolve_report_entry(
    root: Path,
    value: object,
    key: str,
    title: str,
) -> Path:
    if (
        not isinstance(value, Mapping)
        or value.get("key") != key
        or not isinstance(value.get("path"), str)
    ):
        raise TransferDayError(f"{title} 연결이 없습니다.")
    try:
        path = resolve_report(root, str(value["path"]))
    except HpOmenRestoreError as error:
        raise TransferDayError(str(error)) from error
    if (
        value.get("sizeBytes") != path.stat().st_size
        or value.get("sha256") != sha256_file(path)
    ):
        raise TransferDayError(f"{title} 동일성이 다릅니다.")
    return path


def verify_preflight_any(
    root: Path,
    path: Path,
    *,
    environment: Mapping[str, str],
    platform_name: str,
) -> dict[str, Any]:
    report = read_json(path, "HP OMEN 활성화 사전점검 보고서")
    try:
        verify_multi_sidecar(
            path.with_suffix(".sha256"),
            [path, path.with_suffix(".html")],
            "HP OMEN 활성화 사전점검 보고서",
        )
    except HpOmenRestoreError as error:
        raise TransferDayError(str(error)) from error
    if (
        report.get("operation") != PREFLIGHT_OPERATION
        or report.get("status")
        not in {PREFLIGHT_STATUS, PREFLIGHT_BLOCKED_STATUS}
    ):
        raise TransferDayError(
            "HP OMEN 활성화 사전점검 상태가 올바르지 않습니다."
        )
    return report


def render_html(report: Mapping[str, Any]) -> str:
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VisionFlow HP OMEN 이관 당일 체크포인트</title><style>
body{{margin:0;background:#eef3f8;color:#0f172a;font-family:Arial,'Noto Sans KR',sans-serif}}
main{{max-width:920px;margin:32px auto;padding:0 20px}}
section{{background:#fff;border:1px solid #dbe4ee;border-radius:16px;padding:24px;margin:16px 0}}
.status{{font-weight:800}}code{{word-break:break-all}}</style></head>
<body><main><section><h1>HP OMEN 이관 당일 체크포인트</h1>
<p class="status">{html.escape(str(report['status']))}</p>
<p>전환 #{html.escape(str(report['transitionNumber']))}</p>
<p>{html.escape(str(report['generatedAt']))}</p></section>
<section><h2>다음 작업</h2>
<p>{html.escape(str(report['nextAction']))}</p></section>
<section><h2>안전</h2>
<p>체크포인트에는 환경값·운영자 키·모델 원본·절대 경로를 기록하지 않습니다.</p>
</section></main></body></html>"""


def write_checkpoint(
    root: Path,
    report: dict[str, Any],
    now: datetime,
) -> Path:
    output = root / REPORT_ROOT
    output.mkdir(parents=True, exist_ok=True)
    timestamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    directory = output / f"checkpoint-{timestamp}"
    if directory.exists():
        directory = output / (
            f"checkpoint-{timestamp}-{uuid.uuid4().hex[:8]}"
        )
    directory.mkdir()
    json_path = directory / "visionflow-hp-omen-transfer-day.json"
    html_path = directory / "visionflow-hp-omen-transfer-day.html"
    sidecar_path = directory / "visionflow-hp-omen-transfer-day.sha256"
    write_text_atomic(
        json_path,
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    write_text_atomic(html_path, render_html(report))
    write_multi_sidecar(sidecar_path, [json_path, html_path])
    return json_path


def checkpoint_report(
    root: Path,
    *,
    status: str,
    prepare_path: Path,
    now: datetime,
    previous_path: Path | None = None,
    previous: Mapping[str, Any] | None = None,
    preflight_path: Path | None = None,
    activation_path: Path | None = None,
) -> dict[str, Any]:
    if status not in ALLOWED_STATUSES:
        raise TransferDayError(f"지원하지 않는 체크포인트 상태입니다: {status}")
    if (previous_path is None) != (previous is None):
        raise TransferDayError("이전 체크포인트 연결이 불완전합니다.")
    transition = (
        1
        if previous is None
        else int(previous.get("transitionNumber", 0)) + 1
    )
    day_id = (
        str(uuid.uuid4())
        if previous is None
        else str(previous.get("transferDayId"))
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "scope": "HP_OMEN_TRANSFER_DAY",
        "operation": OPERATION,
        "transferDayId": day_id,
        "generatedAt": now.astimezone(timezone.utc).isoformat(),
        "transitionNumber": transition,
        "status": status,
        "nextAction": NEXT_ACTIONS[status],
        "previousCheckpoint": (
            artifact_entry(
                root,
                "previous-transfer-day-checkpoint",
                previous_path,
            )
            if previous_path is not None
            else None
        ),
        "prepareReport": artifact_entry(
            root,
            "hp-workspace-prepare",
            prepare_path,
        ),
        "preflightReport": (
            artifact_entry(
                root,
                "hp-activation-preflight",
                preflight_path,
            )
            if preflight_path is not None
            else None
        ),
        "activationReport": (
            artifact_entry(
                root,
                "hp-runtime-activation",
                activation_path,
            )
            if activation_path is not None
            else None
        ),
        "deferred": [
            "hp-target-smartphone-https-revalidation",
            "hp-omen-model-accuracy-performance",
        ],
        "outOfScope": ["dji-mini4-pro-integration"],
        "safety": {
            "permanentDelete": False,
            "environmentValuesRecorded": False,
            "operatorKeysRecorded": False,
            "modelWeightsIncluded": False,
            "absolutePathsRecorded": False,
            "activationRequiresExplicitConfirmation": True,
        },
    }


def verify_checkpoint(
    root: Path,
    value: str | Path,
    *,
    environment: Mapping[str, str],
    platform_name: str,
) -> tuple[Path, dict[str, Any]]:
    root = root.resolve()
    path = resolve_checkpoint(root, value)
    html_path = path.with_suffix(".html")
    try:
        verify_multi_sidecar(
            path.with_suffix(".sha256"),
            [path, html_path],
            "HP OMEN 이관 당일 체크포인트",
        )
    except HpOmenRestoreError as error:
        raise TransferDayError(str(error)) from error
    report = read_json(path, "HP OMEN 이관 당일 체크포인트")
    if (
        report.get("schemaVersion") != SCHEMA_VERSION
        or report.get("project") != PROJECT_NAME
        or report.get("operation") != OPERATION
        or report.get("status") not in ALLOWED_STATUSES
        or report.get("nextAction") != NEXT_ACTIONS.get(report.get("status"))
        or not isinstance(report.get("transitionNumber"), int)
        or isinstance(report.get("transitionNumber"), bool)
        or report.get("transitionNumber", 0) <= 0
    ):
        raise TransferDayError(
            "HP OMEN 이관 당일 체크포인트 형식이 올바르지 않습니다."
        )
    try:
        uuid.UUID(str(report.get("transferDayId")))
    except (ValueError, AttributeError) as error:
        raise TransferDayError(
            "HP OMEN 이관 당일 ID가 올바르지 않습니다."
        ) from error
    prepare_path = resolve_report_entry(
        root,
        report.get("prepareReport"),
        "hp-workspace-prepare",
        "HP 작업공간 준비 보고서",
    )
    try:
        verify_prepare_report(root, relative_path(root, prepare_path))
    except HpOmenRestoreError as error:
        raise TransferDayError(str(error)) from error

    previous_meta = report.get("previousCheckpoint")
    transition = report["transitionNumber"]
    if transition == 1:
        if previous_meta is not None:
            raise TransferDayError("최초 체크포인트에 이전 연결이 있습니다.")
    else:
        if (
            not isinstance(previous_meta, Mapping)
            or previous_meta.get("key")
            != "previous-transfer-day-checkpoint"
            or not isinstance(previous_meta.get("path"), str)
        ):
            raise TransferDayError("이전 체크포인트 연결이 없습니다.")
        previous_path = resolve_checkpoint(
            root,
            str(previous_meta["path"]),
        )
        if (
            previous_meta.get("sizeBytes")
            != previous_path.stat().st_size
            or previous_meta.get("sha256")
            != sha256_file(previous_path)
        ):
            raise TransferDayError("이전 체크포인트 동일성이 다릅니다.")
        previous_html = previous_path.with_suffix(".html")
        try:
            verify_multi_sidecar(
                previous_path.with_suffix(".sha256"),
                [previous_path, previous_html],
                "이전 HP OMEN 이관 당일 체크포인트",
            )
        except HpOmenRestoreError as error:
            raise TransferDayError(str(error)) from error
        previous = read_json(
            previous_path,
            "이전 HP OMEN 이관 당일 체크포인트",
        )
        if (
            previous.get("operation") != OPERATION
            or previous.get("transferDayId") != report.get("transferDayId")
            or previous.get("transitionNumber") != transition - 1
            or previous_html.read_text(encoding="utf-8-sig")
            != render_html(previous)
        ):
            raise TransferDayError("이전 체크포인트 연결이 다릅니다.")

    preflight_path: Path | None = None
    preflight: dict[str, Any] | None = None
    if report.get("preflightReport") is not None:
        preflight_path = resolve_report_entry(
            root,
            report.get("preflightReport"),
            "hp-activation-preflight",
            "HP 활성화 사전점검 보고서",
        )
        preflight = verify_preflight_any(
            root,
            preflight_path,
            environment=environment,
            platform_name=platform_name,
        )

    activation_path: Path | None = None
    activation: dict[str, Any] | None = None
    if report.get("activationReport") is not None:
        activation_path = resolve_report_entry(
            root,
            report.get("activationReport"),
            "hp-runtime-activation",
            "HP 런타임 활성화 보고서",
        )
        raw = read_json(activation_path, "HP 런타임 활성화 보고서")
        try:
            if raw.get("status") == ACTIVATED_STATUS:
                _, activation = verify_activation_report(
                    root,
                    relative_path(root, activation_path),
                )
            else:
                _, activation, _ = (
                    validate_failed_activation_recovery_source(
                        root,
                        relative_path(root, activation_path),
                    )
                )
        except HpOmenRestoreError as error:
            raise TransferDayError(str(error)) from error

    status = report["status"]
    if (
        (
            status == MANUAL_STATUS
            and (
                activation is not None
                or (
                    preflight is not None
                    and preflight.get("status") != PREFLIGHT_BLOCKED_STATUS
                )
            )
        )
        or (
            status == CONFIRMATION_STATUS
            and (
                preflight is None
                or preflight.get("status") != PREFLIGHT_STATUS
                or activation is not None
            )
        )
        or (
            status == READY_STATUS
            and (
                activation is None
                or activation.get("status") != ACTIVATED_STATUS
            )
        )
        or (
            status == RECOVERY_STATUS
            and (
                activation is None
                or activation.get("status") == ACTIVATED_STATUS
            )
        )
    ):
        raise TransferDayError(
            "체크포인트 상태와 연결 보고서 상태가 다릅니다."
        )
    safety = report.get("safety")
    if (
        not isinstance(safety, Mapping)
        or safety.get("permanentDelete") is not False
        or safety.get("environmentValuesRecorded") is not False
        or safety.get("operatorKeysRecorded") is not False
        or safety.get("modelWeightsIncluded") is not False
        or safety.get("absolutePathsRecorded") is not False
        or safety.get("activationRequiresExplicitConfirmation") is not True
    ):
        raise TransferDayError("체크포인트 안전 메타데이터가 다릅니다.")
    if html_path.read_text(encoding="utf-8-sig") != render_html(report):
        raise TransferDayError("체크포인트 JSON과 HTML이 일치하지 않습니다.")
    return path, report


def bootstrap_day(
    *,
    package: str,
    workspace: str,
    confirmation: str,
    now: datetime,
) -> tuple[Path, dict[str, Any]]:
    root = Path(workspace).resolve()
    if confirmation != PREPARE_CONFIRMATION:
        raise TransferDayError(
            f"작업공간 준비에는 --confirm {PREPARE_CONFIRMATION}이 "
            "필요합니다."
        )
    if root.exists() or root.is_symlink():
        if not root.is_dir() or root.is_symlink():
            raise TransferDayError(
                f"기존 HP 작업공간 경로가 일반 폴더가 아닙니다: {root}"
            )
        existing_checkpoints = [
            path
            for path in (root / REPORT_ROOT).glob(
                "checkpoint-*/visionflow-hp-omen-transfer-day.json"
            )
            if path.is_file() and not path.is_symlink()
        ]
        if existing_checkpoints:
            return verify_checkpoint(
                root,
                latest_checkpoint(root),
                environment={},
                platform_name="nt",
            )
        prepare_path = latest_report_path(
            root,
            "visionflow-hp-omen-prepare-*.json",
            "HP OMEN 작업공간 준비 보고서",
        )
        if prepare_path is None:
            raise TransferDayError(
                "기존 작업공간에 검증 가능한 준비 보고서가 없습니다. "
                "자동 덮어쓰기를 중단합니다."
            )
        try:
            prepare_path, prepared = verify_prepare_report(
                root,
                relative_path(root, prepare_path),
            )
            source_package, _, source_sha = inspect_package(package)
        except HpOmenRestoreError as error:
            raise TransferDayError(str(error)) from error
        source_meta = prepared.get("sourcePackage")
        if (
            not isinstance(source_meta, Mapping)
            or source_meta.get("fileName") != source_package.name
            or source_meta.get("sizeBytes") != source_package.stat().st_size
            or source_meta.get("sha256") != source_sha
        ):
            raise TransferDayError(
                "기존 작업공간의 준비 원본과 지정한 이관 패키지가 "
                "일치하지 않습니다."
            )
    else:
        prepare_path, _ = prepare_workspace(
            package,
            workspace,
            confirmation=confirmation,
            now=now,
        )
    report = checkpoint_report(
        root,
        status=MANUAL_STATUS,
        prepare_path=prepare_path,
        now=now,
    )
    path = write_checkpoint(root, report, now)
    return verify_checkpoint(
        root,
        path,
        environment={},
        platform_name="nt",
    )


def discover_activation(
    root: Path,
) -> tuple[Path, dict[str, Any]] | None:
    path = latest_report_path(
        root,
        "activation-*/visionflow-hp-omen-activation.json",
        "최신 HP OMEN 활성화 보고서",
    )
    if path is None:
        return None
    report = read_json(path, "최신 HP OMEN 활성화 보고서")
    try:
        if report.get("status") == ACTIVATED_STATUS:
            return verify_activation_report(
                root,
                relative_path(root, path),
            )
        failed_path, failed, _ = validate_failed_activation_recovery_source(
            root,
            relative_path(root, path),
        )
        return failed_path, failed
    except HpOmenRestoreError as error:
        raise TransferDayError(str(error)) from error


def transition(
    root: Path,
    current_path: Path,
    current: Mapping[str, Any],
    *,
    status: str,
    prepare_path: Path,
    now: datetime,
    preflight_path: Path | None = None,
    activation_path: Path | None = None,
    environment: Mapping[str, str],
    platform_name: str,
) -> tuple[Path, dict[str, Any]]:
    report = checkpoint_report(
        root,
        status=status,
        prepare_path=prepare_path,
        preflight_path=preflight_path,
        activation_path=activation_path,
        previous_path=current_path,
        previous=current,
        now=now,
    )
    path = write_checkpoint(root, report, now)
    return verify_checkpoint(
        root,
        path,
        environment=environment,
        platform_name=platform_name,
    )


def resume_day(
    *,
    workspace: Path,
    confirmation: str,
    run_benchmark: bool,
    timeout_seconds: int,
    environment: Mapping[str, str],
    now: datetime,
    runner: Runner,
    platform_name: str,
) -> tuple[Path, dict[str, Any], int]:
    root = workspace.resolve()
    current_path, current = verify_checkpoint(
        root,
        latest_checkpoint(root),
        environment=environment,
        platform_name=platform_name,
    )
    prepare_path = resolve_report_entry(
        root,
        current["prepareReport"],
        "hp-workspace-prepare",
        "HP 작업공간 준비 보고서",
    )

    existing_activation = discover_activation(root)
    if existing_activation is not None:
        activation_path, activation = existing_activation
        if activation.get("status") == ACTIVATED_STATUS:
            if current.get("status") == READY_STATUS:
                return current_path, current, 0
            path, report = transition(
                root,
                current_path,
                current,
                status=READY_STATUS,
                prepare_path=prepare_path,
                preflight_path=(
                    resolve_report_entry(
                        root,
                        current["preflightReport"],
                        "hp-activation-preflight",
                        "HP 활성화 사전점검 보고서",
                    )
                    if current.get("preflightReport") is not None
                    else None
                ),
                activation_path=activation_path,
                environment=environment,
                platform_name=platform_name,
                now=now,
            )
            return path, report, 0
        try:
            lineage = validate_activation_start_lineage(root)
        except HpOmenRestoreError:
            lineage = None
        if (
            isinstance(lineage, Mapping)
            and lineage.get("status") == "RECOVERED_RETRY_READY"
        ):
            if current.get("status") == RECOVERY_STATUS:
                path, report = transition(
                    root,
                    current_path,
                    current,
                    status=MANUAL_STATUS,
                    prepare_path=prepare_path,
                    environment=environment,
                    platform_name=platform_name,
                    now=now,
                )
                return path, report, 0
        else:
            if current.get("status") == RECOVERY_STATUS:
                return current_path, current, 1
            path, report = transition(
                root,
                current_path,
                current,
                status=RECOVERY_STATUS,
                prepare_path=prepare_path,
                preflight_path=(
                    resolve_report_entry(
                        root,
                        current["preflightReport"],
                        "hp-activation-preflight",
                        "HP 활성화 사전점검 보고서",
                    )
                    if current.get("preflightReport") is not None
                    else None
                ),
                activation_path=activation_path,
                environment=environment,
                platform_name=platform_name,
                now=now,
            )
            return path, report, 1

    status = current["status"]
    if status == READY_STATUS:
        return current_path, current, 0
    if status == RECOVERY_STATUS:
        return current_path, current, 1

    preflight_path: Path | None = None
    if current.get("preflightReport") is not None:
        preflight_path = resolve_report_entry(
            root,
            current["preflightReport"],
            "hp-activation-preflight",
            "HP 활성화 사전점검 보고서",
        )

    if status == MANUAL_STATUS:
        preflight_path, preflight, preflight_code = (
            create_activation_preflight(
                root,
                prepare_report_value=relative_path(root, prepare_path),
                model_value=MODEL_DEFAULT.as_posix(),
                environment=environment,
                platform_name=platform_name,
                now=now,
            )
        )
        next_status = (
            CONFIRMATION_STATUS
            if preflight_code == 0
            else MANUAL_STATUS
        )
        path, report = transition(
            root,
            current_path,
            current,
            status=next_status,
            prepare_path=prepare_path,
            preflight_path=preflight_path,
            environment=environment,
            platform_name=platform_name,
            now=now,
        )
        return path, report, 0

    if confirmation != ACTIVATE_CONFIRMATION:
        return current_path, current, 0
    activation_path, activation, exit_code = execute_activation(
        root,
        prepare_report_value=relative_path(root, prepare_path),
        model_value=MODEL_DEFAULT.as_posix(),
        confirmation=confirmation,
        drone_id=1,
        run_benchmark=run_benchmark,
        timeout_seconds=timeout_seconds,
        environment=environment,
        now=now,
        runner=runner,
        platform_name=platform_name,
    )
    path, report = transition(
        root,
        current_path,
        current,
        status=(
            READY_STATUS if exit_code == 0 else RECOVERY_STATUS
        ),
        prepare_path=prepare_path,
        preflight_path=preflight_path,
        activation_path=activation_path,
        environment=environment,
        platform_name=platform_name,
        now=now,
    )
    return path, report, exit_code


def build_plan() -> list[dict[str, str | int]]:
    return [
        {
            "order": 1,
            "mode": "CONFIRM_PREPARE",
            "title": "최종 패키지 검증과 새 HP 작업공간 준비",
        },
        {
            "order": 2,
            "mode": "CHECKPOINT",
            "title": "준비 보고서와 첫 이관 당일 체크포인트 봉인",
        },
        {
            "order": 3,
            "mode": "MANUAL",
            "title": "HP 전용 환경파일·best.pt·역할 키 준비",
        },
        {
            "order": 4,
            "mode": "READ_ONLY_PREFLIGHT",
            "title": "DB·Docker 변경 없는 활성화 사전점검",
        },
        {
            "order": 5,
            "mode": "CONFIRM_ACTIVATE",
            "title": "명시적 확인 후 DB 복원·GPU 스택·통합 인수",
        },
        {
            "order": 6,
            "mode": "RESUME",
            "title": "중단 지점 검증 후 성공 단계 재실행 없이 재개",
        },
        {
            "order": 7,
            "mode": "DEFERRED",
            "title": "실제 GPU 모델 정확도·성능과 스마트폰 E2E 후속 검증",
        },
    ]


def print_status(path: Path, report: Mapping[str, Any]) -> None:
    print(f"VisionFlow HP OMEN transfer day: {report['status']}")
    print(f"Checkpoint: {path}")
    print(f"Next      : {report['nextAction']}")


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="VisionFlow HP OMEN transfer-day checkpoint orchestrator"
    )
    subparsers = value.add_subparsers(dest="command", required=True)
    subparsers.add_parser("plan")
    bootstrap = subparsers.add_parser("bootstrap")
    bootstrap.add_argument("--package", required=True)
    bootstrap.add_argument("--workspace", required=True)
    bootstrap.add_argument("--confirm", default="")
    resume = subparsers.add_parser("resume")
    resume.add_argument("--workspace", required=True)
    resume.add_argument("--confirm-activate", default="")
    resume.add_argument("--run-benchmark", action="store_true")
    resume.add_argument("--timeout-seconds", type=int, default=900)
    status = subparsers.add_parser("status")
    status.add_argument("--workspace", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--workspace", required=True)
    verify.add_argument("--report", required=True)
    return value


def main(arguments: Sequence[str] | None = None) -> int:
    args = parser().parse_args(arguments)
    try:
        if args.command == "plan":
            print("VisionFlow HP OMEN transfer day: PLAN")
            for item in build_plan():
                print(
                    f"{item['order']:02d}. [{item['mode']}] "
                    f"{item['title']}"
                )
            print("No file, database, Docker, or service was changed.")
            return 0
        if args.command == "bootstrap":
            path, report = bootstrap_day(
                package=args.package,
                workspace=args.workspace,
                confirmation=args.confirm,
                now=datetime.now(timezone.utc),
            )
            print_status(path, report)
            return 0
        root = Path(args.workspace).resolve()
        if args.command == "verify":
            path, report = verify_checkpoint(
                root,
                args.report,
                environment=os.environ,
                platform_name=os.name,
            )
            print("VisionFlow HP OMEN transfer day: VERIFIED")
            print_status(path, report)
            return 0
        if args.command == "status":
            path, report = verify_checkpoint(
                root,
                latest_checkpoint(root),
                environment=os.environ,
                platform_name=os.name,
            )
            print_status(path, report)
            return 0
        if args.timeout_seconds <= 0:
            raise TransferDayError("실행 제한 시간은 양수여야 합니다.")
        path, report, exit_code = resume_day(
            workspace=root,
            confirmation=args.confirm_activate,
            run_benchmark=args.run_benchmark,
            timeout_seconds=args.timeout_seconds,
            environment=os.environ,
            now=datetime.now(timezone.utc),
            runner=default_runner,
            platform_name=os.name,
        )
        print_status(path, report)
        return exit_code
    except (
        TransferDayError,
        HpOmenRestoreError,
        OSError,
        ValueError,
    ) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
