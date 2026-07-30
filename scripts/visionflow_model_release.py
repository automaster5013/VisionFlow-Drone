"""Prepare, activate, roll back, and verify a promoted VisionFlow AI model."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

try:
    from visionflow_model_promotion import (
        DEFAULT_MODEL,
        READY_STATUS,
        ModelPromotionError,
        artifact_entry,
        is_checksum,
        is_within,
        newest_artifact,
        parse_timestamp,
        read_json,
        relative_path,
        resolve_inside,
        sha256_file,
        verify_report as verify_promotion_report,
    )
except ModuleNotFoundError:  # pragma: no cover - package import during tests
    from scripts.visionflow_model_promotion import (
        DEFAULT_MODEL,
        READY_STATUS,
        ModelPromotionError,
        artifact_entry,
        is_checksum,
        is_within,
        newest_artifact,
        parse_timestamp,
        read_json,
        relative_path,
        resolve_inside,
        sha256_file,
        verify_report as verify_promotion_report,
    )

try:
    from visionflow_hp_omen_restore import (
        ACTIVATED_STATUS as HP_RUNTIME_READY_STATUS,
        HpOmenRestoreError,
        verify_activation_report as verify_hp_activation_report,
    )
except ModuleNotFoundError:  # pragma: no cover - package import during tests
    from scripts.visionflow_hp_omen_restore import (
        ACTIVATED_STATUS as HP_RUNTIME_READY_STATUS,
        HpOmenRestoreError,
        verify_activation_report as verify_hp_activation_report,
    )


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
PREPARE_OPERATION = "MODEL_RELEASE_PREPARE"
ACTIVATE_OPERATION = "MODEL_RELEASE_ACTIVATE"
PREPARED_STATUS = "MODEL_RELEASE_PREPARED"
ACTIVATED_STATUS = "MODEL_RELEASE_ACTIVATED"
ROLLED_BACK_STATUS = "MODEL_RELEASE_ROLLED_BACK"
FAILED_STATUS = "MODEL_RELEASE_ACTIVATION_FAILED"
ACTIVATION_CONFIRMATION = "ACTIVATE_PROMOTED_MODEL_WITH_ROLLBACK"
DEFAULT_OUTPUT = Path("artifacts/model-release")
PROMOTION_PATTERN = (
    "artifacts/model-promotion/promotion-*/visionflow-model-promotion.json"
)
RELEASE_PATTERN = (
    "artifacts/model-release/release-*/visionflow-model-release.json"
)
ACTIVATION_PATTERN = (
    "artifacts/model-release/activation-*/"
    "visionflow-model-release-activation.json"
)
HP_ACTIVATION_PATTERN = (
    "artifacts/hp-omen-restore/activation-*/"
    "visionflow-hp-omen-activation.json"
)
MODEL_DIRECTORY = DEFAULT_MODEL.parent
BASE_ENVIRONMENT = Path(".env.docker")
COMPOSE_FILE = Path("compose.yaml")
GPU_COMPOSE_FILE = Path("compose.gpu.yaml")
ACCEPTANCE_SCRIPT = Path("scripts/run-visionflow-acceptance.bat")


class ModelReleaseError(RuntimeError):
    """Raised when model release or rollback cannot be proven safe."""


class CommandResult:
    def __init__(
        self,
        exit_code: int,
        output: str = "",
        duration_ms: int = 0,
    ) -> None:
        self.exit_code = exit_code
        self.output = output
        self.duration_ms = duration_ms


Runner = Callable[[Sequence[str], Path, int], CommandResult]


def env_content(
    *,
    model_name: str,
    model_profile: str,
    model_sha256: str,
) -> str:
    return "\n".join(
        (
            f"AI_MODEL_PATH={model_name}",
            f"AI_MODEL_PROFILE={model_profile}",
            "AI_DEVICE=0",
            "AI_REQUIRE_CUDA=true",
            "AI_REQUIRE_LOCAL_MODEL=true",
            f"VISIONFLOW_MODEL_RELEASE_SHA256={model_sha256}",
            "",
        )
    )


def sha256_bytes(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def safe_model_name(value: object, title: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or Path(value).name != value
        or Path(value).suffix.lower() != ".pt"
    ):
        raise ModelReleaseError(f"{title} 파일명이 올바르지 않습니다.")
    return value


def promotion_comparison_path(
    root: Path,
    promotion: Mapping[str, Any],
) -> Path:
    inputs = promotion.get("inputs")
    if not isinstance(inputs, list):
        raise ModelReleaseError("모델 승격 입력 목록이 없습니다.")
    matches = [
        item
        for item in inputs
        if isinstance(item, Mapping)
        and item.get("key") == "performance-comparison"
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("path"), str):
        raise ModelReleaseError("A/B 성능 비교 입력이 정확히 하나가 아닙니다.")
    return resolve_inside(
        root,
        matches[0]["path"],
        "A/B 성능 비교",
    )


def resolve_models(
    root: Path,
    promotion: Mapping[str, Any],
    comparison_path: Path,
) -> tuple[Path, str, Path, str]:
    comparison = read_json(comparison_path, "A/B 성능 비교")
    baseline = comparison.get("baseline")
    candidate = comparison.get("candidate")
    if not isinstance(baseline, Mapping) or not isinstance(candidate, Mapping):
        raise ModelReleaseError("A/B 기준·후보 모델 정보가 없습니다.")

    active_name = safe_model_name(candidate.get("modelName"), "승격 모델")
    rollback_name = safe_model_name(baseline.get("modelName"), "롤백 모델")
    if active_name == rollback_name:
        raise ModelReleaseError("승격 모델과 롤백 모델이 동일합니다.")
    active_path = resolve_inside(
        root,
        MODEL_DIRECTORY / active_name,
        "승격 모델",
    )
    rollback_path = resolve_inside(
        root,
        MODEL_DIRECTORY / rollback_name,
        "롤백 모델",
    )
    active_sha = sha256_file(active_path)
    rollback_sha = sha256_file(rollback_path)
    promotion_model = promotion.get("model")
    if (
        not isinstance(promotion_model, Mapping)
        or promotion_model.get("fileName") != active_name
        or promotion_model.get("sizeBytes") != active_path.stat().st_size
        or promotion_model.get("sha256") != active_sha
        or candidate.get("modelSha256") != active_sha
    ):
        raise ModelReleaseError(
            "승격 보고서·성능 후보·현재 모델 동일성이 다릅니다."
        )
    if (
        not is_checksum(baseline.get("modelSha256"))
        or baseline.get("modelSha256") != rollback_sha
    ):
        raise ModelReleaseError(
            "A/B 기준 모델과 현재 롤백 모델 SHA-256이 다릅니다."
        )
    return active_path, active_sha, rollback_path, rollback_sha


def model_entry(
    root: Path,
    path: Path,
    sha256: str,
    profile: str,
) -> dict[str, Any]:
    return {
        "fileName": path.name,
        "path": relative_path(root, path),
        "profile": profile,
        "sizeBytes": path.stat().st_size,
        "sha256": sha256,
    }


def resolve_hp_runtime_activation(
    root: Path,
    value: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    try:
        path = (
            resolve_inside(root, value, "HP OMEN 기본 활성화 보고서")
            if value is not None
            else newest_artifact(
                root,
                HP_ACTIVATION_PATTERN,
                "HP OMEN 기본 활성화",
            )
        )
        verified_path, report = verify_hp_activation_report(
            root,
            relative_path(root, path),
        )
    except (ModelPromotionError, HpOmenRestoreError, OSError) as error:
        raise ModelReleaseError(
            "검증된 HP OMEN 기본 런타임 활성화가 필요합니다. "
            f"원인: {error}"
        ) from error
    if report.get("status") != HP_RUNTIME_READY_STATUS:
        raise ModelReleaseError(
            "HP OMEN 기본 런타임이 활성화 준비 상태가 아닙니다."
        )
    return verified_path, report


def build_release_report(
    *,
    root: Path,
    promotion_path: Path,
    now: datetime,
    release_id: str | None = None,
    hp_activation_path: Path | None = None,
) -> tuple[dict[str, Any], str, str]:
    root = root.resolve()
    hp_activation_path, _ = resolve_hp_runtime_activation(
        root,
        hp_activation_path,
    )
    try:
        promotion_path, promotion = verify_promotion_report(
            root=root,
            report_path=promotion_path,
        )
    except (ModelPromotionError, OSError) as error:
        raise ModelReleaseError(str(error)) from error
    if promotion.get("status") != READY_STATUS:
        raise ModelReleaseError(
            "MODEL_PROMOTION_READY 보고서만 릴리스할 수 있습니다."
        )
    comparison_path = promotion_comparison_path(root, promotion)
    (
        active_path,
        active_sha,
        rollback_path,
        rollback_sha,
    ) = resolve_models(root, promotion, comparison_path)
    activation_env = env_content(
        model_name=active_path.name,
        model_profile="best-gpu",
        model_sha256=active_sha,
    )
    rollback_env = env_content(
        model_name=rollback_path.name,
        model_profile=f"{rollback_path.stem}-gpu",
        model_sha256=rollback_sha,
    )
    report = {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "operation": PREPARE_OPERATION,
        "releaseId": release_id or str(uuid.uuid4()),
        "generatedAt": now.astimezone(timezone.utc).isoformat(),
        "status": PREPARED_STATUS,
        "hpRuntimeActivation": artifact_entry(
            root,
            "hp-runtime-activation",
            hp_activation_path,
        ),
        "promotion": artifact_entry(
            root,
            "model-promotion",
            promotion_path,
        ),
        "activeModel": model_entry(
            root,
            active_path,
            active_sha,
            "best-gpu",
        ),
        "rollbackModel": model_entry(
            root,
            rollback_path,
            rollback_sha,
            f"{rollback_path.stem}-gpu",
        ),
        "environmentOverlays": {
            "activation": {
                "fileName": "visionflow-model-release.env",
                "sha256": sha256_bytes(activation_env),
            },
            "rollback": {
                "fileName": "visionflow-model-rollback.env",
                "sha256": sha256_bytes(rollback_env),
            },
        },
        "activationPolicy": {
            "confirmation": ACTIVATION_CONFIRMATION,
            "composeFiles": [
                COMPOSE_FILE.as_posix(),
                GPU_COMPOSE_FILE.as_posix(),
            ],
            "healthWaitSeconds": 300,
            "acceptanceScript": ACCEPTANCE_SCRIPT.as_posix(),
            "automaticRollback": True,
        },
        "safety": {
            "baseEnvironmentModified": False,
            "modelWeightsCopied": False,
            "modelWeightsModified": False,
            "databaseMutation": False,
            "dockerMutationDuringPrepare": False,
            "secretsRecorded": False,
            "absolutePathsRecorded": False,
        },
    }
    return report, activation_env, rollback_env


def render_release_html(report: Mapping[str, Any]) -> str:
    active = report["activeModel"]
    rollback = report["rollbackModel"]
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VisionFlow 모델 릴리스 준비</title><style>
body{{margin:0;background:#eef3f8;color:#0f172a;font-family:Arial,'Noto Sans KR',sans-serif}}
main{{max-width:900px;margin:32px auto;padding:0 20px}}
section{{background:#fff;border:1px solid #dbe4ee;border-radius:16px;padding:24px;margin:16px 0}}
.ready{{color:#047857;font-weight:800}}code{{word-break:break-all}}
</style></head><body><main>
<section><h1>VisionFlow 모델 릴리스 준비</h1>
<p class="ready">{html.escape(str(report['status']))}</p>
<p>{html.escape(str(report['generatedAt']))}</p></section>
<section><h2>승격 모델</h2><p>{html.escape(str(active['fileName']))}</p>
<p><code>{html.escape(str(active['sha256']))}</code></p></section>
<section><h2>롤백 모델</h2><p>{html.escape(str(rollback['fileName']))}</p>
<p><code>{html.escape(str(rollback['sha256']))}</code></p></section>
<section><h2>안전 정책</h2>
<p>원본 환경파일과 모델 가중치를 변경하지 않는 Compose 오버레이 방식입니다.</p>
</section></main></body></html>"""


def write_sidecar(sidecar: Path, paths: Sequence[Path]) -> None:
    sidecar.write_text(
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in paths),
        encoding="utf-8",
    )


def write_release(
    *,
    output_directory: Path,
    report: dict[str, Any],
    activation_env: str,
    rollback_env: str,
) -> tuple[Path, Path, Path]:
    timestamp = parse_timestamp(
        report["generatedAt"],
        "모델 릴리스",
    ).strftime("%Y%m%dT%H%M%SZ")
    run_directory = output_directory / f"release-{timestamp}"
    if run_directory.exists():
        run_directory = output_directory / (
            f"release-{timestamp}-{uuid.uuid4().hex[:8]}"
        )
    run_directory.mkdir(parents=True, exist_ok=False)
    report_path = run_directory / "visionflow-model-release.json"
    html_path = run_directory / "visionflow-model-release.html"
    activation_path = run_directory / "visionflow-model-release.env"
    rollback_path = run_directory / "visionflow-model-rollback.env"
    sidecar_path = run_directory / "visionflow-model-release.sha256"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    html_path.write_text(render_release_html(report), encoding="utf-8")
    activation_path.write_text(activation_env, encoding="utf-8")
    rollback_path.write_text(rollback_env, encoding="utf-8")
    write_sidecar(
        sidecar_path,
        [report_path, html_path, activation_path, rollback_path],
    )
    return report_path, html_path, sidecar_path


def verify_sidecar(sidecar: Path, paths: Sequence[Path]) -> None:
    if not sidecar.is_file() or sidecar.is_symlink():
        raise ModelReleaseError("모델 릴리스 SHA-256 sidecar가 없습니다.")
    values: dict[str, str] = {}
    for line in sidecar.read_text(encoding="utf-8-sig").splitlines():
        parts = line.strip().split()
        if len(parts) != 2 or not is_checksum(parts[0]):
            raise ModelReleaseError("모델 릴리스 SHA-256 형식이 잘못되었습니다.")
        values[parts[1]] = parts[0].lower()
    if set(values) != {path.name for path in paths}:
        raise ModelReleaseError("모델 릴리스 SHA-256 파일 목록이 다릅니다.")
    for path in paths:
        if not path.is_file() or path.is_symlink():
            raise ModelReleaseError(f"모델 릴리스 파일이 없습니다: {path.name}")
        if values[path.name] != sha256_file(path):
            raise ModelReleaseError(
                f"모델 릴리스 SHA-256이 다릅니다: {path.name}"
            )


def verify_model_entry(
    root: Path,
    value: object,
    title: str,
) -> Path:
    if not isinstance(value, Mapping):
        raise ModelReleaseError(f"{title} 메타데이터가 없습니다.")
    path_value = value.get("path")
    if not isinstance(path_value, str):
        raise ModelReleaseError(f"{title} 경로가 없습니다.")
    path = resolve_inside(root, path_value, title)
    if (
        value.get("fileName") != path.name
        or value.get("sizeBytes") != path.stat().st_size
        or value.get("sha256") != sha256_file(path)
    ):
        raise ModelReleaseError(f"{title} 동일성이 다릅니다.")
    return path


def verify_release_report(
    *,
    root: Path,
    report_path: Path,
) -> tuple[Path, dict[str, Any]]:
    root = root.resolve()
    report_path = resolve_inside(root, report_path, "모델 릴리스 보고서")
    html_path = report_path.with_suffix(".html")
    sidecar_path = report_path.with_suffix(".sha256")
    activation_path = report_path.parent / "visionflow-model-release.env"
    rollback_path = report_path.parent / "visionflow-model-rollback.env"
    verify_sidecar(
        sidecar_path,
        [report_path, html_path, activation_path, rollback_path],
    )
    report = read_json(report_path, "모델 릴리스 보고서")
    if (
        report.get("schemaVersion") != SCHEMA_VERSION
        or report.get("project") != PROJECT_NAME
        or report.get("operation") != PREPARE_OPERATION
        or report.get("status") != PREPARED_STATUS
    ):
        raise ModelReleaseError("VisionFlow 모델 릴리스 준비 보고서가 아닙니다.")
    try:
        uuid.UUID(str(report.get("releaseId")))
    except (ValueError, AttributeError) as error:
        raise ModelReleaseError("모델 릴리스 ID가 올바르지 않습니다.") from error
    hp_activation = report.get("hpRuntimeActivation")
    if not isinstance(hp_activation, Mapping) or not isinstance(
        hp_activation.get("path"),
        str,
    ):
        raise ModelReleaseError("HP OMEN 기본 활성화 보고서 연결이 없습니다.")
    hp_activation_path = resolve_inside(
        root,
        hp_activation["path"],
        "HP OMEN 기본 활성화 보고서",
    )
    if (
        hp_activation.get("key") != "hp-runtime-activation"
        or hp_activation.get("sizeBytes")
        != hp_activation_path.stat().st_size
        or hp_activation.get("sha256")
        != sha256_file(hp_activation_path)
    ):
        raise ModelReleaseError(
            "HP OMEN 기본 활성화 보고서 동일성이 다릅니다."
        )
    resolve_hp_runtime_activation(root, hp_activation_path)
    promotion = report.get("promotion")
    if not isinstance(promotion, Mapping) or not isinstance(
        promotion.get("path"),
        str,
    ):
        raise ModelReleaseError("모델 승격 보고서 연결이 없습니다.")
    promotion_path = resolve_inside(
        root,
        promotion["path"],
        "모델 승격 보고서",
    )
    if (
        promotion.get("sizeBytes") != promotion_path.stat().st_size
        or promotion.get("sha256") != sha256_file(promotion_path)
    ):
        raise ModelReleaseError("모델 승격 보고서 동일성이 다릅니다.")
    active = verify_model_entry(root, report.get("activeModel"), "승격 모델")
    rollback = verify_model_entry(
        root,
        report.get("rollbackModel"),
        "롤백 모델",
    )
    rebuilt, expected_activation, expected_rollback = build_release_report(
        root=root,
        promotion_path=promotion_path,
        now=parse_timestamp(report.get("generatedAt"), "모델 릴리스"),
        release_id=str(report.get("releaseId")),
        hp_activation_path=hp_activation_path,
    )
    if rebuilt != report:
        raise ModelReleaseError(
            "현재 승격 증적·모델로 재계산한 릴리스 내용이 다릅니다."
        )
    if activation_path.read_text(encoding="utf-8-sig") != expected_activation:
        raise ModelReleaseError("승격 모델 환경 오버레이 내용이 다릅니다.")
    if rollback_path.read_text(encoding="utf-8-sig") != expected_rollback:
        raise ModelReleaseError("롤백 모델 환경 오버레이 내용이 다릅니다.")
    if html_path.read_text(encoding="utf-8-sig") != render_release_html(report):
        raise ModelReleaseError("모델 릴리스 JSON과 HTML이 다릅니다.")
    if active == rollback:
        raise ModelReleaseError("승격 모델과 롤백 모델 경로가 동일합니다.")
    return report_path, report


def default_runner(
    command: Sequence[str],
    root: Path,
    timeout_seconds: int,
) -> CommandResult:
    started = time.monotonic()
    completed = subprocess.run(
        list(command),
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        check=False,
    )
    return CommandResult(
        completed.returncode,
        (completed.stdout or "") + (completed.stderr or ""),
        round((time.monotonic() - started) * 1000),
    )


def run_step(
    *,
    key: str,
    title: str,
    command: Sequence[str],
    root: Path,
    timeout_seconds: int,
    runner: Runner,
) -> tuple[dict[str, Any], CommandResult]:
    print(f"[RUN] {title}")
    try:
        result = runner(command, root, timeout_seconds)
    except Exception as error:  # fail closed; rollback may still be required
        result = CommandResult(124, f"{type(error).__name__}: {error}")
    if result.output:
        print(result.output.rstrip())
    return (
        {
            "key": key,
            "title": title,
            "status": "PASS" if result.exit_code == 0 else "FAILED",
            "exitCode": result.exit_code,
            "durationMs": result.duration_ms,
        },
        result,
    )


def compose_command(root: Path, overlay: Path) -> list[str]:
    return [
        "docker",
        "compose",
        "--env-file",
        str(root / BASE_ENVIRONMENT),
        "--env-file",
        str(overlay),
        "-f",
        str(root / COMPOSE_FILE),
        "-f",
        str(root / GPU_COMPOSE_FILE),
    ]


def render_activation_html(report: Mapping[str, Any]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['title']))}</td>"
        f"<td>{html.escape(str(item['status']))}</td>"
        f"<td>{html.escape(str(item['exitCode']))}</td>"
        "</tr>"
        for item in report["steps"]
    )
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VisionFlow 모델 릴리스 실행</title><style>
body{{margin:0;background:#eef3f8;color:#0f172a;font-family:Arial,'Noto Sans KR',sans-serif}}
main{{max-width:950px;margin:32px auto;padding:0 20px}}
section{{background:#fff;border:1px solid #dbe4ee;border-radius:16px;padding:24px;margin:16px 0}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid #e2e8f0;text-align:left}}
</style></head><body><main><section>
<h1>VisionFlow 모델 릴리스 실행</h1>
<p>{html.escape(str(report['status']))}</p>
<p>{html.escape(str(report['generatedAt']))}</p></section>
<section><table><tr><th>단계</th><th>상태</th><th>종료 코드</th></tr>
{rows}</table></section></main></body></html>"""


def write_activation_report(
    *,
    output_directory: Path,
    report: dict[str, Any],
) -> tuple[Path, Path, Path]:
    timestamp = parse_timestamp(
        report["generatedAt"],
        "모델 릴리스 실행",
    ).strftime("%Y%m%dT%H%M%SZ")
    run_directory = output_directory / f"activation-{timestamp}"
    if run_directory.exists():
        run_directory = output_directory / (
            f"activation-{timestamp}-{uuid.uuid4().hex[:8]}"
        )
    run_directory.mkdir(parents=True, exist_ok=False)
    report_path = run_directory / "visionflow-model-release-activation.json"
    html_path = run_directory / "visionflow-model-release-activation.html"
    sidecar_path = run_directory / "visionflow-model-release-activation.sha256"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    html_path.write_text(render_activation_html(report), encoding="utf-8")
    write_sidecar(sidecar_path, [report_path, html_path])
    return report_path, html_path, sidecar_path


def validate_runtime_files(root: Path) -> None:
    for path, title in (
        (root / BASE_ENVIRONMENT, "Docker 환경파일"),
        (root / COMPOSE_FILE, "기본 Compose"),
        (root / GPU_COMPOSE_FILE, "GPU Compose"),
        (root / ACCEPTANCE_SCRIPT, "인수 테스트"),
    ):
        if not path.is_file() or path.is_symlink():
            raise ModelReleaseError(f"{title} 파일이 없습니다: {path.name}")


def verify_activation_guard(
    root: Path,
    value: object,
    release_report_path: Path,
) -> None:
    if not isinstance(value, Mapping):
        raise ModelReleaseError("모델 릴리스 실행 이력 게이트가 없습니다.")
    status = value.get("status")
    previous = value.get("previousActivation")
    if status == "FIRST_ATTEMPT":
        if previous is not None or value.get("previousStatus") is not None:
            raise ModelReleaseError(
                "최초 모델 릴리스 실행 이력 값이 올바르지 않습니다."
            )
        return
    allowed = {
        ACTIVATED_STATUS: "NEW_RELEASE_AFTER_ACTIVATED",
        ROLLED_BACK_STATUS: "NEW_RELEASE_AFTER_ROLLED_BACK",
    }
    previous_status = value.get("previousStatus")
    if (
        not isinstance(previous, Mapping)
        or previous.get("key") != "previous-model-release-activation"
        or not isinstance(previous_status, str)
        or previous_status not in allowed
        or status != allowed[previous_status]
        or not isinstance(previous.get("path"), str)
    ):
        raise ModelReleaseError(
            "이전 모델 릴리스 실행 이력 값이 올바르지 않습니다."
        )
    previous_path = resolve_inside(
        root,
        previous["path"],
        "이전 모델 릴리스 실행 보고서",
    )
    if (
        previous.get("sizeBytes") != previous_path.stat().st_size
        or previous.get("sha256") != sha256_file(previous_path)
    ):
        raise ModelReleaseError(
            "이전 모델 릴리스 실행 보고서 동일성이 다릅니다."
        )
    previous_html = previous_path.with_suffix(".html")
    verify_sidecar(
        previous_path.with_suffix(".sha256"),
        [previous_path, previous_html],
    )
    previous_report = read_json(
        previous_path,
        "이전 모델 릴리스 실행 보고서",
    )
    previous_release = previous_report.get("release")
    if (
        previous_report.get("operation") != ACTIVATE_OPERATION
        or previous_report.get("status") != previous_status
        or not isinstance(previous_release, Mapping)
        or previous_release.get("path")
        == relative_path(root, release_report_path)
        or previous_html.read_text(encoding="utf-8-sig")
        != render_activation_html(previous_report)
    ):
        raise ModelReleaseError(
            "이전 모델 릴리스 실행 보고서 연결이 다릅니다."
        )


def validate_activation_history(
    root: Path,
    release_report_path: Path,
) -> dict[str, Any]:
    candidates = [
        path.resolve()
        for path in root.glob(ACTIVATION_PATTERN)
        if path.is_file() and not path.is_symlink()
    ]
    if not candidates:
        return {
            "status": "FIRST_ATTEMPT",
            "previousStatus": None,
            "previousActivation": None,
        }
    latest = max(
        candidates,
        key=lambda path: (path.stat().st_mtime_ns, path.as_posix()),
    )
    try:
        latest, report = verify_activation_report(
            root=root,
            report_path=latest,
        )
    except (ModelReleaseError, ModelPromotionError, OSError) as error:
        raise ModelReleaseError(
            f"최신 모델 릴리스 실행 이력을 검증할 수 없습니다: {error}"
        ) from error
    previous_release = report.get("release")
    if not isinstance(previous_release, Mapping):
        raise ModelReleaseError(
            "최신 모델 릴리스 실행의 준비 보고서 연결이 없습니다."
        )
    same_release = (
        previous_release.get("path")
        == relative_path(root, release_report_path)
        and previous_release.get("sha256")
        == sha256_file(release_report_path)
    )
    if same_release:
        raise ModelReleaseError(
            "이 모델 릴리스 준비 보고서는 이미 실행되었습니다. "
            "원인을 반영해 prepare로 새 릴리스 보고서를 생성하세요."
        )
    previous_status = report.get("status")
    if previous_status == FAILED_STATUS:
        raise ModelReleaseError(
            "이전 모델 릴리스의 자동 롤백이 실패했습니다. "
            "운영 스택을 수동 복구하고 증적을 검토하기 전에는 "
            "새 릴리스를 실행할 수 없습니다."
        )
    guard = {
        "status": (
            "NEW_RELEASE_AFTER_ACTIVATED"
            if previous_status == ACTIVATED_STATUS
            else "NEW_RELEASE_AFTER_ROLLED_BACK"
        ),
        "previousStatus": previous_status,
        "previousActivation": artifact_entry(
            root,
            "previous-model-release-activation",
            latest,
        ),
    }
    verify_activation_guard(root, guard, release_report_path)
    return guard


def execute_activation(
    *,
    root: Path,
    release_report_path: Path,
    confirmation: str,
    timeout_seconds: int,
    now: datetime,
    runner: Runner = default_runner,
    platform_name: str = os.name,
) -> tuple[Path, dict[str, Any], int]:
    if confirmation != ACTIVATION_CONFIRMATION:
        raise ModelReleaseError(
            f"--confirm {ACTIVATION_CONFIRMATION} 확인이 필요합니다."
        )
    if platform_name != "nt":
        raise ModelReleaseError("모델 릴리스 실행은 Windows HP OMEN 전용입니다.")
    root = root.resolve()
    release_report_path, release = verify_release_report(
        root=root,
        report_path=release_report_path,
    )
    activation_guard = validate_activation_history(
        root,
        release_report_path,
    )
    validate_runtime_files(root)
    release_env = release_report_path.parent / "visionflow-model-release.env"
    rollback_env = release_report_path.parent / "visionflow-model-rollback.env"
    promoted_compose = compose_command(root, release_env)
    rollback_compose = compose_command(root, rollback_env)
    steps: list[dict[str, Any]] = []
    rollback_attempted = False
    rollback_succeeded = False
    stack_mutation_attempted = False

    config_step, config_result = run_step(
        key="compose-config",
        title="승격 모델 Compose 구성 검증",
        command=promoted_compose + ["config", "-q"],
        root=root,
        timeout_seconds=timeout_seconds,
        runner=runner,
    )
    steps.append(config_step)
    start_result = CommandResult(1)
    acceptance_result = CommandResult(1)
    if config_result.exit_code == 0:
        stack_mutation_attempted = True
        start_step, start_result = run_step(
            key="promoted-start",
            title="승격 모델 전체 스택 기동",
            command=promoted_compose
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
            key="acceptance",
            title="승격 모델 기본 인수 테스트",
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

    activation_succeeded = (
        config_result.exit_code == 0
        and start_result.exit_code == 0
        and acceptance_result.exit_code == 0
    )
    rollback_attempted = not activation_succeeded and stack_mutation_attempted
    if rollback_attempted:
        rollback_step, rollback_result = run_step(
            key="automatic-rollback",
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
        steps.append(rollback_step)
        rollback_succeeded = rollback_result.exit_code == 0

    status = (
        ACTIVATED_STATUS
        if activation_succeeded
        else (
            ROLLED_BACK_STATUS
            if rollback_attempted and rollback_succeeded
            else FAILED_STATUS
        )
    )
    report = {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "operation": ACTIVATE_OPERATION,
        "activationId": str(uuid.uuid4()),
        "generatedAt": now.astimezone(timezone.utc).isoformat(),
        "status": status,
        "release": artifact_entry(
            root,
            "model-release",
            release_report_path,
        ),
        "activationGuard": activation_guard,
        "activeModel": release["activeModel"],
        "rollbackModel": release["rollbackModel"],
        "steps": steps,
        "safety": {
            "confirmationMatched": True,
            "baseEnvironmentModified": False,
            "modelWeightsModified": False,
            "rollbackAttempted": rollback_attempted,
            "rollbackSucceeded": rollback_succeeded,
            "commandOutputRecorded": False,
            "environmentValuesRecorded": False,
            "operatorKeysRecorded": False,
        },
    }
    report_path, _, _ = write_activation_report(
        output_directory=root / DEFAULT_OUTPUT,
        report=report,
    )
    return report_path, report, 0 if activation_succeeded else 1


def verify_activation_report(
    *,
    root: Path,
    report_path: Path,
) -> tuple[Path, dict[str, Any]]:
    root = root.resolve()
    report_path = resolve_inside(root, report_path, "모델 릴리스 실행 보고서")
    html_path = report_path.with_suffix(".html")
    sidecar_path = report_path.with_suffix(".sha256")
    verify_sidecar(sidecar_path, [report_path, html_path])
    report = read_json(report_path, "모델 릴리스 실행 보고서")
    if (
        report.get("schemaVersion") != SCHEMA_VERSION
        or report.get("project") != PROJECT_NAME
        or report.get("operation") != ACTIVATE_OPERATION
        or report.get("status")
        not in {ACTIVATED_STATUS, ROLLED_BACK_STATUS, FAILED_STATUS}
    ):
        raise ModelReleaseError("VisionFlow 모델 릴리스 실행 보고서가 아닙니다.")
    try:
        uuid.UUID(str(report.get("activationId")))
    except (ValueError, AttributeError) as error:
        raise ModelReleaseError("모델 릴리스 실행 ID가 올바르지 않습니다.") from error
    release = report.get("release")
    if not isinstance(release, Mapping) or not isinstance(
        release.get("path"),
        str,
    ):
        raise ModelReleaseError("모델 릴리스 준비 보고서 연결이 없습니다.")
    release_path = resolve_inside(root, release["path"], "모델 릴리스 준비")
    if (
        release.get("sizeBytes") != release_path.stat().st_size
        or release.get("sha256") != sha256_file(release_path)
    ):
        raise ModelReleaseError("모델 릴리스 준비 보고서 동일성이 다릅니다.")
    _, prepared = verify_release_report(root=root, report_path=release_path)
    verify_activation_guard(
        root,
        report.get("activationGuard"),
        release_path,
    )
    if (
        report.get("activeModel") != prepared.get("activeModel")
        or report.get("rollbackModel") != prepared.get("rollbackModel")
    ):
        raise ModelReleaseError("모델 릴리스 실행 모델 정보가 다릅니다.")
    steps = report.get("steps")
    safety = report.get("safety")
    if not isinstance(steps, list) or not isinstance(safety, Mapping):
        raise ModelReleaseError("모델 릴리스 실행 단계가 없습니다.")
    by_key = {
        item.get("key"): item
        for item in steps
        if isinstance(item, Mapping) and isinstance(item.get("key"), str)
    }
    if len(by_key) != len(steps) or "compose-config" not in by_key:
        raise ModelReleaseError("모델 릴리스 실행 단계가 올바르지 않습니다.")
    keys = [str(item.get("key")) for item in steps]
    allowed_keys = {
        "compose-config",
        "promoted-start",
        "acceptance",
        "automatic-rollback",
    }
    if any(key not in allowed_keys for key in keys):
        raise ModelReleaseError("알 수 없는 모델 릴리스 실행 단계가 있습니다.")
    for item in steps:
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
            raise ModelReleaseError("모델 릴리스 실행 단계 결과가 다릅니다.")
    config_passed = by_key["compose-config"].get("status") == "PASS"
    start_passed = (
        "promoted-start" in by_key
        and by_key["promoted-start"].get("status") == "PASS"
    )
    acceptance_present = "acceptance" in by_key
    rollback_present = "automatic-rollback" in by_key
    if (
        (not config_passed and keys != ["compose-config"])
        or (
            config_passed
            and (
                "promoted-start" not in by_key
                or len(keys) < 2
                or keys[1] != "promoted-start"
            )
        )
        or (
            "promoted-start" in by_key
            and not start_passed
            and acceptance_present
        )
        or (
            start_passed
            and (
                not acceptance_present
                or len(keys) < 3
                or keys[2] != "acceptance"
            )
        )
        or (
            rollback_present
            and keys[-1] != "automatic-rollback"
        )
    ):
        raise ModelReleaseError("모델 릴리스 실행 단계 순서가 다릅니다.")
    all_primary_passed = all(
        key in by_key and by_key[key].get("status") == "PASS"
        for key in ("compose-config", "promoted-start", "acceptance")
    )
    rollback_passed = (
        "automatic-rollback" in by_key
        and by_key["automatic-rollback"].get("status") == "PASS"
    )
    expected_status = (
        ACTIVATED_STATUS
        if all_primary_passed
        else (ROLLED_BACK_STATUS if rollback_passed else FAILED_STATUS)
    )
    if (
        report.get("status") != expected_status
        or rollback_present != (config_passed and not all_primary_passed)
        or safety.get("rollbackAttempted")
        is not rollback_present
        or safety.get("rollbackSucceeded") is not rollback_passed
    ):
        raise ModelReleaseError("모델 릴리스 실행 상태 계산이 다릅니다.")
    if html_path.read_text(encoding="utf-8-sig") != render_activation_html(
        report
    ):
        raise ModelReleaseError("모델 릴리스 실행 JSON과 HTML이 다릅니다.")
    return report_path, report


def build_plan() -> list[str]:
    return [
        "검증된 HP OMEN 기본 런타임 활성화와 실행 이력 확인",
        "MODEL_PROMOTION_READY 보고서와 현재 best.pt 재검증",
        "A/B 기준 yolo26n.pt를 검증된 롤백 모델로 고정",
        "원본 .env.docker를 수정하지 않는 승격·롤백 오버레이 생성",
        "HP OMEN에서 승격 모델 GPU 스택 기동과 기본 인수 테스트",
        "기동·인수 실패 시 yolo26n.pt로 자동 롤백",
        "JSON·HTML·SHA-256 실행 증적 생성 및 독립 검증",
    ]


def parser(default_root: Path) -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="VisionFlow promoted model release and rollback gate"
    )
    value.add_argument("--root", default=str(default_root))
    subparsers = value.add_subparsers(dest="command", required=True)
    subparsers.add_parser("plan")
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--promotion")
    prepare.add_argument("--output", default=DEFAULT_OUTPUT.as_posix())
    activate = subparsers.add_parser("activate")
    activate.add_argument("--report")
    activate.add_argument("--confirm", default="")
    activate.add_argument("--timeout-seconds", type=int, default=900)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--report", required=True)
    return value


def resolve_output(root: Path, value: str) -> Path:
    output = resolve_inside(
        root,
        value,
        "모델 릴리스 출력",
        require_file=False,
    )
    if not is_within(output, (root / DEFAULT_OUTPUT).resolve()):
        raise ModelReleaseError(
            "모델 릴리스 출력은 artifacts/model-release 안에 있어야 합니다."
        )
    return output


def main(argv: Sequence[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    arguments = parser(default_root).parse_args(argv)
    root = Path(arguments.root).resolve()
    try:
        if arguments.command == "plan":
            print("VisionFlow model release: PLAN")
            for index, item in enumerate(build_plan(), start=1):
                print(f"{index:02d}. {item}")
            print("No environment, model, database, Docker, or service was changed.")
            return 0

        if arguments.command == "verify":
            report = read_json(
                resolve_inside(root, arguments.report, "검증 보고서"),
                "검증 보고서",
            )
            if report.get("operation") == PREPARE_OPERATION:
                path, verified = verify_release_report(
                    root=root,
                    report_path=Path(arguments.report),
                )
            elif report.get("operation") == ACTIVATE_OPERATION:
                path, verified = verify_activation_report(
                    root=root,
                    report_path=Path(arguments.report),
                )
            else:
                raise ModelReleaseError("지원하지 않는 모델 릴리스 보고서입니다.")
            print("VisionFlow model release: VERIFIED")
            print(f"Status: {verified['status']}")
            print(f"Report: {path}")
            return 0

        output = resolve_output(root, getattr(arguments, "output", str(DEFAULT_OUTPUT)))
        if arguments.command == "prepare":
            promotion_path = (
                resolve_inside(root, arguments.promotion, "모델 승격 보고서")
                if arguments.promotion
                else newest_artifact(root, PROMOTION_PATTERN, "모델 승격")
            )
            report, activation_env, rollback_env = build_release_report(
                root=root,
                promotion_path=promotion_path,
                now=datetime.now(timezone.utc),
            )
            report_path, html_path, sidecar_path = write_release(
                output_directory=output,
                report=report,
                activation_env=activation_env,
                rollback_env=rollback_env,
            )
            verify_release_report(root=root, report_path=report_path)
            print(f"VisionFlow model release: {report['status']}")
            print(f"JSON report: {report_path}")
            print(f"HTML report: {html_path}")
            print(f"SHA-256   : {sidecar_path}")
            return 0

        if arguments.timeout_seconds <= 0:
            raise ModelReleaseError("실행 제한 시간은 양수여야 합니다.")
        release_path = (
            resolve_inside(root, arguments.report, "모델 릴리스 보고서")
            if arguments.report
            else newest_artifact(root, RELEASE_PATTERN, "모델 릴리스")
        )
        report_path, report, exit_code = execute_activation(
            root=root,
            release_report_path=release_path,
            confirmation=arguments.confirm,
            timeout_seconds=arguments.timeout_seconds,
            now=datetime.now(timezone.utc),
        )
        verify_activation_report(root=root, report_path=report_path)
        print(f"VisionFlow model release: {report['status']}")
        print(f"Report: {report_path}")
        return exit_code
    except (
        ModelReleaseError,
        ModelPromotionError,
        OSError,
        subprocess.SubprocessError,
    ) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
