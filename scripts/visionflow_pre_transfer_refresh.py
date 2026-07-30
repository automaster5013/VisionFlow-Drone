"""Orchestrate and verify the final VisionFlow pre-transfer refresh chain."""

from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

try:
    from visionflow_migration_handoff import (
        HandoffError,
        verify_handoff_file,
    )
    from visionflow_post_closeout_changes import (
        NO_CHANGES_STATUS,
        PostCloseoutChangesError,
        verify_changeset_file,
    )
    from visionflow_project_closeout import (
        CLOSEOUT_STATUS,
        ProjectCloseoutError,
        verify_closeout_file,
    )
    from visionflow_transfer_package import (
        READY_STATUS as TRANSFER_PACKAGE_STATUS,
        TransferPackageError,
        verify_transfer_package_file,
    )
    from visionflow_transfer_rehearsal import (
        READY_STATUS as TRANSFER_REHEARSAL_STATUS,
        TransferRehearsalError,
        verify_report as verify_transfer_rehearsal_report,
    )
except ModuleNotFoundError:  # pragma: no cover - package import during tests
    from scripts.visionflow_migration_handoff import (
        HandoffError,
        verify_handoff_file,
    )
    from scripts.visionflow_post_closeout_changes import (
        NO_CHANGES_STATUS,
        PostCloseoutChangesError,
        verify_changeset_file,
    )
    from scripts.visionflow_project_closeout import (
        CLOSEOUT_STATUS,
        ProjectCloseoutError,
        verify_closeout_file,
    )
    from scripts.visionflow_transfer_package import (
        READY_STATUS as TRANSFER_PACKAGE_STATUS,
        TransferPackageError,
        verify_transfer_package_file,
    )
    from scripts.visionflow_transfer_rehearsal import (
        READY_STATUS as TRANSFER_REHEARSAL_STATUS,
        TransferRehearsalError,
        verify_report as verify_transfer_rehearsal_report,
    )


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
READY_STATUS = "PRE_TRANSFER_REFRESH_READY"
FAILED_STATUS = "PRE_TRANSFER_REFRESH_FAILED"
CONFIRMATION = "REFRESH_TRANSFER_CHAIN_WITH_BACKUP"
REQUIRED_ACCEPTANCE_KEYS = (
    "VISIONFLOW_ACCEPTANCE_VIEWER_KEY",
    "VISIONFLOW_ACCEPTANCE_OPERATOR_KEY",
    "VISIONFLOW_ACCEPTANCE_ADMIN_KEY",
)


class PreTransferRefreshError(RuntimeError):
    """Raised when pre-transfer refresh cannot proceed safely."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    output: str


Runner = Callable[[Sequence[str], Path, int], CommandResult]
StabilityChecker = Callable[[Path, str], tuple[Path, dict[str, Any]]]
ArtifactVerifier = Callable[
    [Path, str], tuple[Path, dict[str, Any]]
]


STEP_DEFINITIONS = (
    ("evidence-catalog", "기존 증적·SHA-256 무결성 사전 검사"),
    ("scripts-tests", "운영 스크립트 전체 단위 테스트"),
    ("integrated-acceptance", "Demo·RBAC·세션 통합 인수 테스트"),
    ("csp-evidence", "CSP Report-Only 관찰 증적"),
    ("consistent-backup", "MySQL·영속 증적 일관 백업"),
    ("storage-audit", "저장공간·DB 참조 감사"),
    ("retention-drill", "격리·복원 리허설"),
    ("ai-benchmark", "AI CPU 성능 기준선"),
    ("release-gate", "2차 프로젝트 릴리스 준비도"),
    ("release-evidence", "릴리스 증빙 번들"),
    ("source-release", "안전 소스 릴리스"),
    ("machine-baseline", "LG GRAM machine baseline"),
    ("migration-handoff", "HP OMEN 마이그레이션 핸드오프"),
    ("cold-start", "격리 콜드 스타트 리허설"),
    ("transfer-readiness", "최종 전송 준비도"),
    ("transfer-package", "MySQL 백업 포함 최종 이관 패키지"),
    ("transfer-rehearsal", "오프라인 매체·새 HP 작업공간 전체 리허설"),
    ("project-closeout", "2차 프로젝트 종결 보고서"),
    ("source-stability", "최종 패키지 이후 소스 무변경 확인"),
)


SCRIPT_FILES = {
    "evidence-catalog": "run-visionflow-evidence-catalog.bat",
    "integrated-acceptance": "run-visionflow-acceptance.bat",
    "csp-evidence": "run-visionflow-csp-evidence.bat",
    "consistent-backup": "run-visionflow-backup.bat",
    "storage-audit": "run-visionflow-storage-audit.bat",
    "retention-drill": "run-visionflow-retention-drill.bat",
    "ai-benchmark": "run-visionflow-ai-benchmark.bat",
    "release-gate": "run-visionflow-release-gate.bat",
    "release-evidence": "run-visionflow-release-evidence.bat",
    "source-release": "run-visionflow-source-release.bat",
    "machine-baseline": "run-visionflow-machine-profile.bat",
    "migration-handoff": "run-visionflow-migration-handoff.bat",
    "cold-start": "run-visionflow-cold-start-rehearsal.bat",
    "transfer-readiness": "run-visionflow-transfer-readiness.bat",
    "transfer-package": "run-visionflow-transfer-package.bat",
    "transfer-rehearsal": "run-visionflow-transfer-rehearsal.bat",
    "project-closeout": "run-visionflow-project-closeout.bat",
    "source-stability": "run-visionflow-post-closeout-changes.bat",
}

REQUIRED_SUPPORT_FILES = (
    "visionflow_evidence_catalog.py",
    "visionflow_checksum_retention.py",
)


ARTIFACT_PATTERNS = {
    "integrated-acceptance": (
        "artifacts/visionflow-acceptance/visionflow-acceptance-*.json"
    ),
    "csp-evidence": (
        "artifacts/csp-observability/visionflow-csp-observation-*.json"
    ),
    "consistent-backup": "backups/visionflow-backup-*.zip",
    "storage-audit": "artifacts/storage-audit/storage-audit-*/storage-audit.json",
    "retention-drill": (
        "artifacts/retention-drill/drill-*/retention-recovery-drill.json"
    ),
    "ai-benchmark": "artifacts/ai-benchmark/visionflow-ai-benchmark-*.json",
    "release-gate": (
        "artifacts/release-readiness/visionflow-release-readiness-*.json"
    ),
    "release-evidence": (
        "artifacts/release-evidence/visionflow-release-evidence-*.zip"
    ),
    "source-release": (
        "artifacts/source-release/visionflow-source-release-*.zip"
    ),
    "machine-baseline": (
        "artifacts/machine-readiness/visionflow-machine-baseline-*.json"
    ),
    "migration-handoff": (
        "artifacts/migration-handoff/visionflow-migration-handoff-*.zip"
    ),
    "cold-start": (
        "artifacts/cold-start-rehearsal/"
        "visionflow-cold-start-rehearsal-*.json"
    ),
    "transfer-readiness": (
        "artifacts/transfer-readiness/visionflow-transfer-readiness-*.json"
    ),
    "transfer-package": (
        "artifacts/transfer-package/visionflow-transfer-package-*.zip"
    ),
    "transfer-rehearsal": (
        "artifacts/transfer-rehearsal/"
        "visionflow-transfer-rehearsal-*.json"
    ),
    "project-closeout": (
        "artifacts/project-closeout/visionflow-project-closeout-*.json"
    ),
    "source-stability": (
        "artifacts/post-closeout-changes/"
        "visionflow-post-closeout-changes-*.zip"
    ),
}


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_checksum(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def write_text_atomic(
    path: Path,
    value: str,
    *,
    encoding: str = "utf-8",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding=encoding)
    os.replace(temporary, path)


def read_json(path: Path, title: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise PreTransferRefreshError(f"{title} 파일을 찾을 수 없습니다: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PreTransferRefreshError(
            f"{title} JSON 형식이 올바르지 않습니다."
        ) from error
    if not isinstance(value, dict):
        raise PreTransferRefreshError(f"{title} 최상위 값은 객체여야 합니다.")
    return value


def relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as error:
        raise PreTransferRefreshError(
            f"산출물 경로가 프로젝트 밖에 있습니다: {path}"
        ) from error


def resolve_report_path(root: Path, value: str) -> Path:
    candidate = Path(value)
    path = (
        candidate.resolve()
        if candidate.is_absolute()
        else (root / candidate).resolve()
    )
    allowed = (root / "artifacts/pre-transfer-refresh").resolve()
    if (
        not is_within(path, allowed)
        or not path.is_file()
        or path.is_symlink()
        or path.suffix.lower() != ".json"
    ):
        raise PreTransferRefreshError(
            f"이관 전 갱신 보고서 경로가 허용 영역을 벗어났습니다: {path}"
        )
    return path


def artifact_candidates(root: Path, pattern: str) -> set[Path]:
    return {
        path.resolve()
        for path in root.glob(pattern)
        if path.is_file() and not path.is_symlink()
    }


def newest_artifact(root: Path, pattern: str, title: str) -> Path:
    candidates = artifact_candidates(root, pattern)
    if not candidates:
        raise PreTransferRefreshError(f"{title} 산출물을 찾을 수 없습니다.")
    return max(
        candidates,
        key=lambda path: (path.stat().st_mtime_ns, path.name),
    )


def command_for_batch(
    root: Path,
    script_name: str,
    arguments: Sequence[str],
    *,
    platform_name: str,
) -> list[str]:
    script = (root / "scripts" / script_name).resolve()
    if platform_name == "nt":
        command_processor = os.environ.get("COMSPEC", "cmd.exe")
        return [
            command_processor,
            "/d",
            "/c",
            str(script),
            *arguments,
        ]
    return [str(script), *arguments]


def default_runner(
    command: Sequence[str],
    root: Path,
    timeout_seconds: int,
) -> CommandResult:
    try:
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
        output = completed.stdout
        if completed.stderr:
            output += "\n[stderr]\n" + completed.stderr
        return CommandResult(completed.returncode, output)
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout or ""
        stderr = error.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        output = stdout
        if stderr:
            output += "\n[stderr]\n" + stderr
        output += f"\n[TIMEOUT] {timeout_seconds} seconds\n"
        return CommandResult(124, output)


def build_plan(refresh_ai_benchmark: bool) -> list[dict[str, Any]]:
    plan = []
    for key, title in STEP_DEFINITIONS:
        mode = "RUN"
        detail = ""
        if key == "ai-benchmark" and not refresh_ai_benchmark:
            mode = "REUSE"
            detail = "30일 유효한 최신 AI CPU 기준선을 재사용"
        elif key == "evidence-catalog":
            detail = (
                "파일 생성 없이 기존 증적을 검사하고 "
                "REVIEW_REQUIRED이면 즉시 중단"
            )
        elif key == "consistent-backup":
            detail = "실행 중인 backend·AI를 잠시 멈춘 뒤 원래 상태로 재개"
        elif key == "retention-drill":
            detail = "후보를 격리하고 인수 테스트 후 원래 위치로 복원"
        elif key == "transfer-package":
            detail = "검증된 실제 MySQL 백업을 민감 이관 ZIP에 포함"
        elif key == "transfer-rehearsal":
            detail = (
                "시스템 임시 폴더에서 매체 복사와 새 HP 작업공간 준비 후 "
                "완전 정리"
            )
        elif key == "source-stability":
            detail = "최종 패키지 생성 후 소스 변경이 0개인지 확인"
        plan.append(
            {
                "order": len(plan) + 1,
                "key": key,
                "title": title,
                "mode": mode,
                "detail": detail,
            }
        )
    return plan


def validate_preflight(
    root: Path,
    *,
    confirmation: str,
    refresh_ai_benchmark: bool,
    environment: Mapping[str, str],
    platform_name: str,
) -> Path | None:
    if confirmation != CONFIRMATION:
        raise PreTransferRefreshError(
            f"전체 이관 증적 갱신에는 --confirm {CONFIRMATION}이 필요합니다."
        )
    if platform_name != "nt":
        raise PreTransferRefreshError(
            "전체 이관 증적 갱신 실행은 Windows 프로젝트 환경에서만 지원합니다."
        )
    if not root.is_dir():
        raise PreTransferRefreshError(
            f"프로젝트 루트를 찾을 수 없습니다: {root}"
        )
    compose = [
        root / name
        for name in (
            "compose.yaml",
            "compose.yml",
            "docker-compose.yaml",
            "docker-compose.yml",
        )
        if (root / name).is_file()
    ]
    if not compose:
        raise PreTransferRefreshError("프로젝트 Compose 파일이 없습니다.")
    if not (root / ".env.docker").is_file():
        raise PreTransferRefreshError(
            ".env.docker가 없습니다. 실제 값은 출력하지 않고 존재 여부만 확인합니다."
        )
    missing_scripts = [
        name
        for name in SCRIPT_FILES.values()
        if not (root / "scripts" / name).is_file()
    ]
    missing_scripts.extend(
        name
        for name in REQUIRED_SUPPORT_FILES
        if not (root / "scripts" / name).is_file()
    )
    if missing_scripts:
        raise PreTransferRefreshError(
            f"필수 실행 스크립트가 없습니다: {sorted(missing_scripts)}"
        )
    missing_keys = [
        name
        for name in REQUIRED_ACCEPTANCE_KEYS
        if not str(environment.get(name, "")).strip()
    ]
    if missing_keys:
        raise PreTransferRefreshError(
            "통합 인수 테스트용 역할 키 환경변수가 없습니다: "
            f"{missing_keys}"
        )
    if refresh_ai_benchmark:
        return None
    return newest_artifact(
        root,
        ARTIFACT_PATTERNS["ai-benchmark"],
        "재사용할 AI CPU 기준선",
    )


def run_command_step(
    root: Path,
    run_directory: Path,
    *,
    key: str,
    title: str,
    command: Sequence[str],
    pattern: str | None,
    timeout_seconds: int,
    runner: Runner,
) -> tuple[dict[str, Any], Path | None]:
    before = artifact_candidates(root, pattern) if pattern else set()
    started = time.monotonic()
    print(f"[RUN] {title}")
    result = runner(command, root, timeout_seconds)
    duration = round((time.monotonic() - started) * 1000)
    log_path = run_directory / f"{len(list(run_directory.glob('*.log'))) + 1:02d}-{key}.log"
    write_text_atomic(log_path, result.output)
    if result.output:
        print(result.output, end="" if result.output.endswith("\n") else "\n")
    artifact: Path | None = None
    error: str | None = None
    if result.returncode == 0 and pattern:
        after = artifact_candidates(root, pattern)
        created = sorted(
            after - before,
            key=lambda path: (path.stat().st_mtime_ns, path.name),
        )
        if len(created) != 1:
            error = (
                f"새 산출물이 정확히 1개여야 하지만 {len(created)}개입니다: "
                f"{pattern}"
            )
        else:
            artifact = created[0]
    elif result.returncode != 0:
        error = f"명령 종료 코드가 {result.returncode}입니다."
    step = {
        "key": key,
        "title": title,
        "status": "PASS" if error is None else "FAILED",
        "exitCode": result.returncode,
        "durationMs": duration,
        "logPath": relative_path(root, log_path),
        "artifactPath": relative_path(root, artifact) if artifact else None,
        "error": error,
    }
    return step, artifact


def artifact_entry(root: Path, path: Path) -> dict[str, Any]:
    return {
        "path": relative_path(root, path),
        "sizeBytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def render_html(report: dict[str, Any]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{item.get('order', index)}</td>"
        f"<td>{html.escape(str(item['title']))}</td>"
        f"<td>{html.escape(str(item['status']))}</td>"
        f"<td>{html.escape(str(item.get('artifactPath') or '-'))}</td>"
        "</tr>"
        for index, item in enumerate(report["steps"], start=1)
    )
    artifacts = "".join(
        "<li>"
        f"<code>{html.escape(str(item['path']))}</code> "
        f"<small>{html.escape(str(item['sha256']))}</small>"
        "</li>"
        for item in report.get("finalArtifacts", [])
    )
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VisionFlow 이관 전 전체 갱신</title><style>
body{{margin:0;background:#eef3f8;color:#0f172a;font-family:Arial,'Noto Sans KR',sans-serif}}
main{{max-width:1100px;margin:32px auto;padding:0 20px}}
section{{background:#fff;border:1px solid #dbe4ee;border-radius:16px;padding:24px;margin:16px 0}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid #e2e8f0;text-align:left}}
code,small{{word-break:break-all}}.ready{{color:#047857;font-weight:800}}.failed{{color:#b91c1c;font-weight:800}}
</style></head><body><main>
<section><h1>VisionFlow 이관 전 전체 갱신</h1>
<p class="{'ready' if report['status'] == READY_STATUS else 'failed'}">{html.escape(report['status'])}</p>
<p>{html.escape(report['generatedAt'])}</p></section>
<section><h2>단계</h2><table><tr><th>#</th><th>단계</th><th>상태</th><th>산출물</th></tr>{rows}</table></section>
<section><h2>최종 산출물</h2><ul>{artifacts}</ul></section>
<section><h2>안전</h2><p>영구 삭제와 외부 전송은 수행하지 않습니다. 통합 Demo는 검증 데이터를 추가하며 최종 ZIP은 실제 MySQL 백업을 포함합니다.</p></section>
</main></body></html>"""


def write_report(
    run_directory: Path,
    report: dict[str, Any],
) -> tuple[Path, Path, Path]:
    json_path = run_directory / "visionflow-pre-transfer-refresh.json"
    html_path = run_directory / "visionflow-pre-transfer-refresh.html"
    sidecar = run_directory / "visionflow-pre-transfer-refresh.sha256"
    write_text_atomic(
        json_path,
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    write_text_atomic(html_path, render_html(report))
    write_text_atomic(
        sidecar,
        (
            f"{sha256_file(json_path)}  {json_path.name}\n"
            f"{sha256_file(html_path)}  {html_path.name}\n"
        ),
    )
    return json_path, html_path, sidecar


def verify_sidecar(
    sidecar: Path,
    expected: Sequence[Path],
) -> None:
    if not sidecar.is_file() or sidecar.is_symlink():
        raise PreTransferRefreshError(
            f"이관 전 갱신 sidecar를 찾을 수 없습니다: {sidecar}"
        )
    try:
        lines = [
            line.strip().split()
            for line in sidecar.read_text(
                encoding="utf-8-sig"
            ).splitlines()
            if line.strip()
        ]
    except UnicodeDecodeError as error:
        raise PreTransferRefreshError(
            "이관 전 갱신 sidecar가 UTF-8이 아닙니다."
        ) from error
    if len(lines) != len(expected) or any(len(parts) != 2 for parts in lines):
        raise PreTransferRefreshError(
            "이관 전 갱신 sidecar 형식이 올바르지 않습니다."
        )
    recorded = {parts[1]: parts[0].lower() for parts in lines}
    if set(recorded) != {path.name for path in expected}:
        raise PreTransferRefreshError(
            "이관 전 갱신 sidecar 파일 목록이 다릅니다."
        )
    for path in expected:
        if (
            not is_checksum(recorded[path.name])
            or recorded[path.name] != sha256_file(path)
        ):
            raise PreTransferRefreshError(
                f"이관 전 갱신 SHA-256이 다릅니다: {path.name}"
            )


def verify_refresh_report(
    root: Path,
    value: str,
    *,
    handoff_verifier: ArtifactVerifier = verify_handoff_file,
    transfer_verifier: ArtifactVerifier = verify_transfer_package_file,
    rehearsal_verifier: ArtifactVerifier = verify_transfer_rehearsal_report,
    closeout_verifier: ArtifactVerifier = verify_closeout_file,
    stability_verifier: StabilityChecker = verify_changeset_file,
) -> tuple[Path, dict[str, Any]]:
    report_path = resolve_report_path(root, value)
    html_path = report_path.with_suffix(".html")
    sidecar = report_path.with_suffix(".sha256")
    if not html_path.is_file() or html_path.is_symlink():
        raise PreTransferRefreshError(
            f"이관 전 갱신 HTML을 찾을 수 없습니다: {html_path}"
        )
    verify_sidecar(sidecar, [report_path, html_path])
    report = read_json(report_path, "이관 전 갱신 보고서")
    if (
        report.get("schemaVersion") != SCHEMA_VERSION
        or report.get("project") != PROJECT_NAME
        or report.get("operation") != "PRE_TRANSFER_REFRESH"
        or report.get("status") != READY_STATUS
    ):
        raise PreTransferRefreshError(
            "VisionFlow 이관 전 갱신 완료 보고서가 아닙니다."
        )
    steps = report.get("steps")
    summary = report.get("summary")
    safety = report.get("safety")
    artifacts = report.get("finalArtifacts")
    if (
        not isinstance(steps, list)
        or len(steps) != len(STEP_DEFINITIONS)
        or [
            item.get("key")
            for item in steps
            if isinstance(item, dict)
        ]
        != [key for key, _ in STEP_DEFINITIONS]
        or any(
            not isinstance(item, dict)
            or item.get("status") not in {"PASS", "REUSED"}
            for item in steps
        )
    ):
        raise PreTransferRefreshError(
            "이관 전 갱신 단계가 모두 완료되지 않았습니다."
        )
    expected_summary = {
        "total": len(steps),
        "passed": sum(item["status"] == "PASS" for item in steps),
        "reused": sum(item["status"] == "REUSED" for item in steps),
        "failed": 0,
        "blocking": 0,
    }
    if summary != expected_summary:
        raise PreTransferRefreshError(
            "이관 전 갱신 단계 집계가 올바르지 않습니다."
        )
    if (
        not isinstance(safety, dict)
        or safety.get("permanentDelete") is not False
        or safety.get("externalTransferPerformed") is not False
        or safety.get("databaseRestore") is not False
        or safety.get("actualDatabaseBackupIncluded") is not True
        or safety.get("demoDataMutation") is not True
        or safety.get("retentionCandidatesRestored") is not True
        or safety.get("evidenceIntegrityPrecheck") is not True
        or safety.get("offlineTransferRehearsal") is not True
    ):
        raise PreTransferRefreshError(
            "이관 전 갱신 안전 메타데이터가 올바르지 않습니다."
        )
    if not isinstance(artifacts, list):
        raise PreTransferRefreshError(
            "이관 전 갱신 최종 산출물 목록이 없습니다."
        )
    by_key: dict[str, Path] = {}
    for item in artifacts:
        if not isinstance(item, dict):
            raise PreTransferRefreshError(
                "이관 전 갱신 산출물 항목이 올바르지 않습니다."
            )
        key = item.get("key")
        relative = item.get("path")
        if (
            not isinstance(key, str)
            or key in by_key
            or not isinstance(relative, str)
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
        ):
            raise PreTransferRefreshError(
                "이관 전 갱신 산출물 경로가 올바르지 않습니다."
            )
        path = (root / relative).resolve()
        if (
            not is_within(path, root.resolve())
            or not path.is_file()
            or path.is_symlink()
            or path.stat().st_size != item.get("sizeBytes")
            or not is_checksum(item.get("sha256"))
            or sha256_file(path) != item.get("sha256")
        ):
            raise PreTransferRefreshError(
                f"이관 전 갱신 산출물 동일성이 다릅니다: {relative}"
            )
        by_key[key] = path
    required = {
        "source-release",
        "release-evidence",
        "machine-baseline",
        "migration-handoff",
        "cold-start",
        "transfer-readiness",
        "transfer-package",
        "transfer-rehearsal",
        "project-closeout",
        "source-stability",
    }
    if set(by_key) != required:
        raise PreTransferRefreshError(
            "이관 전 갱신 최종 산출물 종류가 다릅니다."
        )
    artifact_sha = {
        key: sha256_file(path)
        for key, path in by_key.items()
    }
    baseline = read_json(
        by_key["machine-baseline"],
        "LG machine baseline",
    )
    readiness = read_json(
        by_key["transfer-readiness"],
        "최종 전송 준비도",
    )
    _, handoff_manifest = handoff_verifier(
        root,
        str(by_key["migration-handoff"]),
    )
    _, package_manifest = transfer_verifier(
        root,
        str(by_key["transfer-package"]),
    )
    _, rehearsal = rehearsal_verifier(
        root,
        str(by_key["transfer-rehearsal"]),
    )
    _, closeout = closeout_verifier(
        root,
        str(by_key["project-closeout"]),
    )
    _, stability = stability_verifier(
        root,
        str(by_key["source-stability"]),
    )
    source_identity = baseline.get("sourceIdentity")
    handoff_source = handoff_manifest.get("source")
    handoff_evidence = handoff_manifest.get("evidence")
    handoff_baseline = handoff_manifest.get("baseline")
    readiness_handoff = readiness.get("handoff")
    readiness_cold_start = readiness.get("coldStart")
    package_handoff = package_manifest.get("handoff")
    package_readiness = package_manifest.get("transferReadiness")
    rehearsal_package = rehearsal.get("package")
    closeout_source = closeout.get("sourceArtifact")
    stability_baseline = stability.get("baseline")
    if not all(
        isinstance(item, dict)
        for item in (
            source_identity,
            handoff_source,
            handoff_evidence,
            handoff_baseline,
            readiness_handoff,
            readiness_cold_start,
            package_handoff,
            package_readiness,
            rehearsal_package,
            closeout_source,
            stability_baseline,
        )
    ):
        raise PreTransferRefreshError(
            "최종 산출물 교차 검증 메타데이터가 없습니다."
        )
    expected_links = (
        (
            source_identity.get("archiveSha256"),
            artifact_sha["source-release"],
            "LG machine baseline과 안전 소스 ZIP",
        ),
        (
            handoff_source.get("sha256"),
            artifact_sha["source-release"],
            "핸드오프와 안전 소스 ZIP",
        ),
        (
            handoff_evidence.get("sha256"),
            artifact_sha["release-evidence"],
            "핸드오프와 릴리스 증빙",
        ),
        (
            handoff_baseline.get("sha256"),
            artifact_sha["machine-baseline"],
            "핸드오프와 LG machine baseline",
        ),
        (
            readiness_handoff.get("sha256"),
            artifact_sha["migration-handoff"],
            "전송 준비도와 핸드오프",
        ),
        (
            readiness_cold_start.get("sha256"),
            artifact_sha["cold-start"],
            "전송 준비도와 콜드 스타트",
        ),
        (
            package_handoff.get("sha256"),
            artifact_sha["migration-handoff"],
            "최종 패키지와 핸드오프",
        ),
        (
            package_readiness.get("sha256"),
            artifact_sha["transfer-readiness"],
            "최종 패키지와 전송 준비도",
        ),
        (
            rehearsal_package.get("sha256"),
            artifact_sha["transfer-package"],
            "오프라인 이관 리허설과 최종 패키지",
        ),
        (
            closeout_source.get("sha256"),
            artifact_sha["transfer-package"],
            "종결 보고서와 최종 패키지",
        ),
        (
            stability_baseline.get("transferPackageSha256"),
            artifact_sha["transfer-package"],
            "소스 안정성 보고서와 최종 패키지",
        ),
    )
    for actual, expected, title in expected_links:
        if actual != expected:
            raise PreTransferRefreshError(
                f"{title} SHA-256 연결이 다릅니다."
            )
    expected_paths = (
        (
            readiness_handoff.get("path"),
            relative_path(root, by_key["migration-handoff"]),
            "전송 준비도 핸드오프",
        ),
        (
            readiness_cold_start.get("path"),
            relative_path(root, by_key["cold-start"]),
            "전송 준비도 콜드 스타트",
        ),
        (
            package_handoff.get("sourcePath"),
            relative_path(root, by_key["migration-handoff"]),
            "최종 패키지 핸드오프",
        ),
        (
            package_readiness.get("sourcePath"),
            relative_path(root, by_key["transfer-readiness"]),
            "최종 패키지 전송 준비도",
        ),
        (
            rehearsal_package.get("path"),
            relative_path(root, by_key["transfer-package"]),
            "오프라인 이관 리허설 최종 패키지",
        ),
        (
            closeout_source.get("path"),
            relative_path(root, by_key["transfer-package"]),
            "종결 보고서 최종 패키지",
        ),
        (
            stability_baseline.get("transferPackagePath"),
            relative_path(root, by_key["transfer-package"]),
            "소스 안정성 기준 패키지",
        ),
    )
    for actual, expected, title in expected_paths:
        if actual != expected:
            raise PreTransferRefreshError(
                f"{title} 경로 연결이 다릅니다."
            )
    if (
        package_manifest.get("status") != TRANSFER_PACKAGE_STATUS
        or rehearsal.get("status") != TRANSFER_REHEARSAL_STATUS
        or closeout.get("status") != CLOSEOUT_STATUS
        or stability.get("status") != NO_CHANGES_STATUS
        or stability.get("summary", {}).get("totalChanges") != 0
    ):
        raise PreTransferRefreshError(
            "최종 이관 패키지·종결·소스 안정성 상태가 일치하지 않습니다."
        )
    try:
        html_value = html_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise PreTransferRefreshError(
            "이관 전 갱신 HTML이 UTF-8이 아닙니다."
        ) from error
    lowered = html_value.lower()
    if any(
        token in lowered
        for token in ("<script", "<iframe", "<object", "<embed", "javascript:")
    ):
        raise PreTransferRefreshError(
            "이관 전 갱신 HTML에 실행 가능한 콘텐츠가 있습니다."
        )
    if html_value != render_html(report):
        raise PreTransferRefreshError(
            "이관 전 갱신 JSON과 HTML 내용이 일치하지 않습니다."
        )
    return report_path, report


def execute_refresh(
    root: Path,
    *,
    output_root: Path,
    confirmation: str,
    drone_id: int,
    refresh_ai_benchmark: bool,
    timeout_seconds: int,
    environment: Mapping[str, str],
    now: datetime,
    runner: Runner = default_runner,
    stability_checker: StabilityChecker = verify_changeset_file,
    rehearsal_checker: ArtifactVerifier = verify_transfer_rehearsal_report,
    platform_name: str = os.name,
) -> tuple[Path, dict[str, Any], int]:
    if drone_id <= 0:
        raise PreTransferRefreshError("드론 ID는 양수여야 합니다.")
    if timeout_seconds <= 0:
        raise PreTransferRefreshError("단계 제한 시간은 양수여야 합니다.")
    allowed_output = (root / "artifacts/pre-transfer-refresh").resolve()
    output = output_root.resolve()
    if not is_within(output, allowed_output):
        raise PreTransferRefreshError(
            "출력 폴더는 artifacts/pre-transfer-refresh 내부여야 합니다."
        )
    reused_benchmark = validate_preflight(
        root,
        confirmation=confirmation,
        refresh_ai_benchmark=refresh_ai_benchmark,
        environment=environment,
        platform_name=platform_name,
    )
    output.mkdir(parents=True, exist_ok=True)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    run_directory = output / f"refresh-{timestamp}"
    if run_directory.exists():
        run_directory = output / (
            f"refresh-{timestamp}-{uuid.uuid4().hex[:8]}"
        )
    run_directory.mkdir()
    report: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "scope": "SECOND_PROJECT_DIGITAL_TWIN",
        "operation": "PRE_TRANSFER_REFRESH",
        "refreshId": str(uuid.uuid4()),
        "generatedAt": now.isoformat(),
        "completedAt": None,
        "status": "RUNNING",
        "options": {
            "droneId": drone_id,
            "refreshAiBenchmark": refresh_ai_benchmark,
        },
        "steps": [],
        "finalArtifacts": [],
        "summary": {},
        "safety": {
            "permanentDelete": False,
            "externalTransferPerformed": False,
            "databaseRestore": False,
            "actualDatabaseBackupIncluded": False,
            "demoDataMutation": False,
            "retentionCandidatesRestored": False,
            "evidenceIntegrityPrecheck": False,
            "offlineTransferRehearsal": False,
        },
    }
    produced: dict[str, Path] = {}
    exit_code = 1

    def batch_command(key: str, arguments: Sequence[str]) -> list[str]:
        return command_for_batch(
            root,
            SCRIPT_FILES[key],
            arguments,
            platform_name=platform_name,
        )

    def run(
        key: str,
        arguments: Sequence[str],
        *,
        command: Sequence[str] | None = None,
    ) -> Path:
        title = dict(STEP_DEFINITIONS)[key]
        actual_command = (
            list(command)
            if command is not None
            else batch_command(key, arguments)
        )
        step, artifact = run_command_step(
            root,
            run_directory,
            key=key,
            title=title,
            command=actual_command,
            pattern=ARTIFACT_PATTERNS.get(key),
            timeout_seconds=timeout_seconds,
            runner=runner,
        )
        step["order"] = len(report["steps"]) + 1
        report["steps"].append(step)
        if step["status"] != "PASS":
            raise PreTransferRefreshError(
                f"{title} 실패: {step['error']}"
            )
        if artifact is None:
            raise PreTransferRefreshError(
                f"{title} 산출물이 없습니다."
            )
        produced[key] = artifact
        return artifact

    def run_check(key: str, arguments: Sequence[str]) -> None:
        title = dict(STEP_DEFINITIONS)[key]
        step, _ = run_command_step(
            root,
            run_directory,
            key=key,
            title=title,
            command=batch_command(key, arguments),
            pattern=None,
            timeout_seconds=timeout_seconds,
            runner=runner,
        )
        step["order"] = len(report["steps"]) + 1
        report["steps"].append(step)
        if step["status"] != "PASS":
            raise PreTransferRefreshError(
                f"{title} 실패: {step['error']}"
            )

    try:
        run_check("evidence-catalog", ["--check-only"])
        report["safety"]["evidenceIntegrityPrecheck"] = True

        tests_command = [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "scripts/tests",
            "-p",
            "test_*.py",
            "-v",
        ]
        title = dict(STEP_DEFINITIONS)["scripts-tests"]
        step, _ = run_command_step(
            root,
            run_directory,
            key="scripts-tests",
            title=title,
            command=tests_command,
            pattern=None,
            timeout_seconds=timeout_seconds,
            runner=runner,
        )
        step["order"] = len(report["steps"]) + 1
        report["steps"].append(step)
        if step["status"] != "PASS":
            raise PreTransferRefreshError(
                f"{title} 실패: {step['error']}"
            )

        acceptance = run(
            "integrated-acceptance",
            [
                "-RunDemo",
                "-RunRbac",
                "-RunSession",
                "-DroneId",
                str(drone_id),
            ],
        )
        report["safety"]["demoDataMutation"] = True
        csp = run("csp-evidence", [])
        backup = run("consistent-backup", ["--consistent"])
        audit = run("storage-audit", [])
        drill = run(
            "retention-drill",
            [
                "--audit",
                relative_path(root, audit),
                "--backup",
                relative_path(root, backup),
                "--execute",
                "--confirm",
                "RUN_RESTORE_DRILL",
            ],
        )
        report["safety"]["retentionCandidatesRestored"] = True
        if refresh_ai_benchmark:
            benchmark = run("ai-benchmark", [])
        else:
            assert reused_benchmark is not None
            benchmark = reused_benchmark
            produced["ai-benchmark"] = benchmark
            report["steps"].append(
                {
                    "order": len(report["steps"]) + 1,
                    "key": "ai-benchmark",
                    "title": dict(STEP_DEFINITIONS)["ai-benchmark"],
                    "status": "REUSED",
                    "exitCode": None,
                    "durationMs": 0,
                    "logPath": None,
                    "artifactPath": relative_path(root, benchmark),
                    "error": None,
                }
            )

        release = run(
            "release-gate",
            [
                "--acceptance",
                relative_path(root, acceptance),
                "--backup",
                relative_path(root, backup),
                "--audit",
                relative_path(root, audit),
                "--drill",
                relative_path(root, drill),
                "--benchmark",
                relative_path(root, benchmark),
                "--csp",
                relative_path(root, csp),
            ],
        )
        evidence = run(
            "release-evidence",
            ["--report", relative_path(root, release)],
        )
        source = run("source-release", [])
        baseline = run("machine-baseline", [])
        baseline_profile = read_json(baseline, "LG machine baseline")
        source_identity = baseline_profile.get("sourceIdentity")
        if (
            not isinstance(source_identity, dict)
            or source_identity.get("archiveSha256") != sha256_file(source)
        ):
            raise PreTransferRefreshError(
                "새 LG machine baseline이 이번 안전 소스 ZIP을 참조하지 않습니다."
            )
        handoff = run(
            "migration-handoff",
            [
                "--source",
                relative_path(root, source),
                "--evidence",
                relative_path(root, evidence),
                "--baseline",
                relative_path(root, baseline),
            ],
        )
        cold_start = run(
            "cold-start",
            ["--handoff", relative_path(root, handoff)],
        )
        transfer_readiness = run(
            "transfer-readiness",
            [
                "--handoff",
                relative_path(root, handoff),
                "--cold-start",
                relative_path(root, cold_start),
            ],
        )
        package = run(
            "transfer-package",
            [
                "--readiness",
                relative_path(root, transfer_readiness),
                "--handoff",
                relative_path(root, handoff),
                "--backup",
                relative_path(root, backup),
                "--confirm",
                "INCLUDE_VERIFIED_BACKUP",
            ],
        )
        report["safety"]["actualDatabaseBackupIncluded"] = True
        rehearsal = run(
            "transfer-rehearsal",
            [
                "execute",
                "--package",
                relative_path(root, package),
                "--confirm",
                "REHEARSE_TRANSFER_MEDIA_TO_FRESH_WORKSPACE",
            ],
        )
        try:
            _, rehearsal_manifest = rehearsal_checker(
                root,
                str(rehearsal),
            )
        except TransferRehearsalError as error:
            raise PreTransferRefreshError(str(error)) from error
        rehearsal_package = rehearsal_manifest.get("package")
        if (
            rehearsal_manifest.get("status") != TRANSFER_REHEARSAL_STATUS
            or not isinstance(rehearsal_package, dict)
            or rehearsal_package.get("path") != relative_path(root, package)
            or rehearsal_package.get("sha256") != sha256_file(package)
        ):
            raise PreTransferRefreshError(
                "오프라인 이관 리허설이 이번 최종 패키지를 검증하지 않았습니다."
            )
        report["safety"]["offlineTransferRehearsal"] = True
        closeout = run(
            "project-closeout",
            ["--package", relative_path(root, package)],
        )
        stability = run(
            "source-stability",
            ["--package", relative_path(root, package)],
        )
        _, stability_manifest = stability_checker(root, str(stability))
        if (
            stability_manifest.get("status") != NO_CHANGES_STATUS
            or stability_manifest.get("summary", {}).get("totalChanges") != 0
        ):
            raise PreTransferRefreshError(
                "최종 패키지 생성 중 소스가 다시 변경됐습니다. "
                "변경을 완료한 뒤 전체 갱신을 다시 실행하세요."
            )

        final_keys = (
            "source-release",
            "release-evidence",
            "machine-baseline",
            "migration-handoff",
            "cold-start",
            "transfer-readiness",
            "transfer-package",
            "transfer-rehearsal",
            "project-closeout",
            "source-stability",
        )
        report["finalArtifacts"] = [
            {"key": key, **artifact_entry(root, produced[key])}
            for key in final_keys
        ]
        report["status"] = READY_STATUS
        exit_code = 0
    except (PreTransferRefreshError, KeyboardInterrupt) as error:
        report["status"] = FAILED_STATUS
        report["error"] = (
            str(error)
            if not isinstance(error, KeyboardInterrupt)
            else "사용자에 의해 중단되었습니다."
        )
        exit_code = 130 if isinstance(error, KeyboardInterrupt) else 1
    finally:
        report["completedAt"] = datetime.now(timezone.utc).isoformat()
        report["summary"] = {
            "total": len(STEP_DEFINITIONS),
            "passed": sum(
                item["status"] == "PASS" for item in report["steps"]
            ),
            "reused": sum(
                item["status"] == "REUSED" for item in report["steps"]
            ),
            "failed": sum(
                item["status"] == "FAILED" for item in report["steps"]
            ),
            "blocking": 0 if exit_code == 0 else 1,
        }
        report_path, _, _ = write_report(run_directory, report)
    return report_path, report, exit_code


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="VisionFlow pre-transfer refresh orchestrator"
    )
    parser.add_argument("--root", default=str(default_root))
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser(
        "plan",
        help="변경 없이 실행 순서와 영향만 출력",
    )
    plan.add_argument("--refresh-ai-benchmark", action="store_true")
    execute = subparsers.add_parser(
        "execute",
        help="명시적 확인 후 전체 증적 체인 갱신",
    )
    execute.add_argument("--confirm", default="")
    execute.add_argument("--drone-id", type=int, default=1)
    execute.add_argument("--refresh-ai-benchmark", action="store_true")
    execute.add_argument("--timeout-seconds", type=int, default=1800)
    execute.add_argument(
        "--output",
        default="artifacts/pre-transfer-refresh",
    )
    verify = subparsers.add_parser(
        "verify",
        help="완료 보고서와 최종 산출물 독립 재검증",
    )
    verify.add_argument("--report", required=True)
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    args = build_parser(default_root).parse_args(arguments)
    root = Path(args.root).resolve()
    try:
        if args.command == "plan":
            print("VisionFlow pre-transfer refresh: PLAN")
            for item in build_plan(args.refresh_ai_benchmark):
                detail = f" - {item['detail']}" if item["detail"] else ""
                print(
                    f"{item['order']:02d}. [{item['mode']}] "
                    f"{item['title']}{detail}"
                )
            print("No command, database, Docker, or artifact was changed.")
            return 0
        if args.command == "execute":
            output_value = Path(args.output)
            output = (
                output_value.resolve()
                if output_value.is_absolute()
                else (root / output_value).resolve()
            )
            report_path, report, exit_code = execute_refresh(
                root,
                output_root=output,
                confirmation=args.confirm,
                drone_id=args.drone_id,
                refresh_ai_benchmark=args.refresh_ai_benchmark,
                timeout_seconds=args.timeout_seconds,
                environment=os.environ,
                now=datetime.now(timezone.utc),
            )
            print(f"VisionFlow pre-transfer refresh: {report['status']}")
            print(f"Report: {report_path}")
            return exit_code
        report_path, report = verify_refresh_report(root, args.report)
        print("VisionFlow pre-transfer refresh: VERIFIED")
        print(f"Status: {report['status']}")
        print(f"Report: {report_path}")
        return 0
    except (
        PreTransferRefreshError,
        HandoffError,
        TransferPackageError,
        TransferRehearsalError,
        ProjectCloseoutError,
        PostCloseoutChangesError,
        FileNotFoundError,
        OSError,
    ) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
