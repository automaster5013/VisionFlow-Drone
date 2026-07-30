"""Rehearse VisionFlow transfer media and fresh HP workspace preparation."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

try:
    from visionflow_hp_omen_restore import (
        PREPARE_CONFIRMATION,
        PREPARED_STATUS,
        HpOmenRestoreError,
        inspect_package,
        prepare_workspace,
        verify_prepare_report,
    )
    from visionflow_transfer_media import (
        CONFIRMATION as MEDIA_CONFIRMATION,
        READY_STATUS as MEDIA_READY_STATUS,
        TransferMediaError,
        resolve_package,
        stage_media,
        verify_media,
    )
    from visionflow_transfer_package import TransferPackageError
except ModuleNotFoundError:  # pragma: no cover - package import during tests
    from scripts.visionflow_hp_omen_restore import (
        PREPARE_CONFIRMATION,
        PREPARED_STATUS,
        HpOmenRestoreError,
        inspect_package,
        prepare_workspace,
        verify_prepare_report,
    )
    from scripts.visionflow_transfer_media import (
        CONFIRMATION as MEDIA_CONFIRMATION,
        READY_STATUS as MEDIA_READY_STATUS,
        TransferMediaError,
        resolve_package,
        stage_media,
        verify_media,
    )
    from scripts.visionflow_transfer_package import TransferPackageError


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
OPERATION = "OFFLINE_TRANSFER_REHEARSAL"
READY_STATUS = "OFFLINE_TRANSFER_REHEARSAL_READY_WITH_DEFERRED"
FAILED_STATUS = "OFFLINE_TRANSFER_REHEARSAL_FAILED"
CONFIRMATION = "REHEARSE_TRANSFER_MEDIA_TO_FRESH_WORKSPACE"
REPORT_ROOT = Path("artifacts/transfer-rehearsal")
STEP_DEFINITIONS = (
    ("package-verify", "최종 이관 패키지·sidecar·중첩 manifest 검증"),
    ("media-stage", "임시 오프라인 이관 매체 스테이징"),
    ("media-verify", "임시 매체 복사본 독립 재검증"),
    ("workspace-prepare", "존재하지 않는 새 HP 작업공간 준비"),
    ("workspace-verify", "추출 소스·증적·MySQL 백업 교차 재검증"),
    ("temporary-cleanup", "임시 매체와 작업공간 완전 정리"),
)

StageFunction = Callable[..., tuple[Path, dict[str, Any]]]
MediaVerifier = Callable[[str | Path], tuple[Path, dict[str, Any]]]
PrepareFunction = Callable[..., tuple[Path, dict[str, Any]]]
PrepareVerifier = Callable[[Path, str], tuple[Path, dict[str, Any]]]


class TransferRehearsalError(RuntimeError):
    """Raised when an offline transfer rehearsal cannot be trusted."""


def sha256_file(path: Path) -> str:
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
        raise TransferRehearsalError(
            f"{title} 파일을 찾을 수 없습니다: {path}"
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TransferRehearsalError(
            f"{title} JSON 형식이 올바르지 않습니다."
        ) from error
    if not isinstance(value, dict):
        raise TransferRehearsalError(f"{title} 최상위 값은 객체여야 합니다.")
    return value


def relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as error:
        raise TransferRehearsalError(
            f"경로가 프로젝트 밖에 있습니다: {path}"
        ) from error


def package_entry(root: Path, path: Path, status: str) -> dict[str, Any]:
    return {
        "path": relative_path(root, path),
        "fileName": path.name,
        "status": status,
        "sizeBytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def step_result(
    key: str,
    *,
    status: str,
    detail: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "title": dict(STEP_DEFINITIONS)[key],
        "status": status,
        "detail": detail,
    }


def build_plan() -> list[dict[str, Any]]:
    return [
        {
            "order": index,
            "mode": (
                "TEMPORARY"
                if key not in {"package-verify", "temporary-cleanup"}
                else "READ_ONLY" if key == "package-verify" else "CLEANUP"
            ),
            "key": key,
            "title": title,
        }
        for index, (key, title) in enumerate(STEP_DEFINITIONS, start=1)
    ]


def render_html(report: dict[str, Any]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{index}</td>"
        f"<td>{html.escape(str(item['title']))}</td>"
        f"<td>{html.escape(str(item['status']))}</td>"
        f"<td>{html.escape(str(item['detail']))}</td>"
        "</tr>"
        for index, item in enumerate(report["steps"], start=1)
    )
    ready = report["status"] == READY_STATUS
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VisionFlow 오프라인 이관 리허설</title><style>
body{{margin:0;background:#eef3f8;color:#0f172a;font-family:Arial,'Noto Sans KR',sans-serif}}main{{max-width:1080px;margin:32px auto;padding:0 20px}}
section{{background:#fff;border:1px solid #dbe4ee;border-radius:16px;padding:24px;margin:16px 0}}table{{width:100%;border-collapse:collapse}}
th,td{{padding:10px;border-bottom:1px solid #e2e8f0;text-align:left;vertical-align:top}}.ready{{color:#047857;font-weight:800}}.failed{{color:#b91c1c;font-weight:800}}</style></head>
<body><main><section><h1>VisionFlow 오프라인 이관 리허설</h1>
<p class="{'ready' if ready else 'failed'}">{html.escape(str(report['status']))}</p>
<p>{html.escape(str(report['generatedAt']))}</p></section>
<section><h2>검증 단계</h2><table><tr><th>#</th><th>단계</th><th>상태</th><th>결과</th></tr>{rows}</table></section>
<section><h2>안전</h2><p>DB 복원·Docker 기동·GPU 실행·외부 전송 없이 임시 작업공간을 완전히 정리했습니다.</p></section>
</main></body></html>"""


def write_report(
    root: Path,
    report: dict[str, Any],
    now: datetime,
) -> tuple[Path, Path, Path]:
    output = root / REPORT_ROOT
    output.mkdir(parents=True, exist_ok=True)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    base = output / f"visionflow-transfer-rehearsal-{timestamp}"
    if base.with_suffix(".json").exists():
        base = output / (
            f"visionflow-transfer-rehearsal-{timestamp}-"
            f"{uuid.uuid4().hex[:8]}"
        )
    json_path = base.with_suffix(".json")
    html_path = base.with_suffix(".html")
    sidecar = base.with_suffix(".sha256")
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
    expected: tuple[Path, Path],
) -> None:
    if not sidecar.is_file() or sidecar.is_symlink():
        raise TransferRehearsalError(
            f"리허설 보고서 sidecar가 없습니다: {sidecar}"
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
        raise TransferRehearsalError(
            "리허설 보고서 sidecar가 UTF-8이 아닙니다."
        ) from error
    if (
        len(lines) != len(expected)
        or any(len(parts) != 2 for parts in lines)
    ):
        raise TransferRehearsalError(
            "리허설 보고서 sidecar 형식이 올바르지 않습니다."
        )
    recorded = {parts[1]: parts[0].lower() for parts in lines}
    if set(recorded) != {path.name for path in expected}:
        raise TransferRehearsalError(
            "리허설 보고서 sidecar 파일 목록이 다릅니다."
        )
    for path in expected:
        if (
            not is_checksum(recorded[path.name])
            or recorded[path.name] != sha256_file(path)
        ):
            raise TransferRehearsalError(
                f"리허설 보고서 SHA-256이 다릅니다: {path.name}"
            )


def resolve_report(root: Path, value: str) -> Path:
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
        or path.suffix.lower() != ".json"
    ):
        raise TransferRehearsalError(
            f"리허설 보고서 경로가 허용 영역을 벗어났습니다: {path}"
        )
    return path


def verify_report(
    root: Path,
    value: str,
) -> tuple[Path, dict[str, Any]]:
    report_path = resolve_report(root, value)
    report = read_json(report_path, "오프라인 이관 리허설 보고서")
    html_path = report_path.with_suffix(".html")
    verify_sidecar(
        report_path.with_suffix(".sha256"),
        (report_path, html_path),
    )
    if (
        report.get("schemaVersion") != SCHEMA_VERSION
        or report.get("project") != PROJECT_NAME
        or report.get("operation") != OPERATION
        or report.get("status") != READY_STATUS
    ):
        raise TransferRehearsalError(
            "성공한 오프라인 이관 리허설 보고서가 아닙니다."
        )
    steps = report.get("steps")
    if (
        not isinstance(steps, list)
        or [item.get("key") for item in steps if isinstance(item, dict)]
        != [key for key, _ in STEP_DEFINITIONS]
        or any(
            not isinstance(item, dict) or item.get("status") != "PASS"
            for item in steps
        )
    ):
        raise TransferRehearsalError("리허설 단계가 모두 PASS가 아닙니다.")
    safety = report.get("safety")
    if (
        not isinstance(safety, dict)
        or safety.get("databaseMutation") is not False
        or safety.get("dockerStarted") is not False
        or safety.get("gpuExecuted") is not False
        or safety.get("externalTransferPerformed") is not False
        or safety.get("temporaryWorkspaceRemoved") is not True
        or safety.get("sourceFilesModified") is not False
    ):
        raise TransferRehearsalError(
            "리허설 안전 메타데이터가 올바르지 않습니다."
        )
    package = report.get("package")
    if not isinstance(package, dict):
        raise TransferRehearsalError("리허설 원본 패키지 정보가 없습니다.")
    path_value = package.get("path")
    if (
        not isinstance(path_value, str)
        or Path(path_value).is_absolute()
        or ".." in Path(path_value).parts
    ):
        raise TransferRehearsalError("리허설 원본 패키지 경로가 안전하지 않습니다.")
    package_path = (root / path_value).resolve()
    allowed = (root / "artifacts/transfer-package").resolve()
    if (
        not is_within(package_path, allowed)
        or not package_path.is_file()
        or package_path.is_symlink()
        or package_path.stat().st_size != package.get("sizeBytes")
        or not is_checksum(package.get("sha256"))
        or sha256_file(package_path) != package.get("sha256")
    ):
        raise TransferRehearsalError(
            "리허설 원본 패키지 크기 또는 SHA-256이 다릅니다."
        )
    try:
        _, package_manifest, checksum = inspect_package(str(package_path))
    except (
        HpOmenRestoreError,
        TransferPackageError,
        FileNotFoundError,
        OSError,
    ) as error:
        raise TransferRehearsalError(str(error)) from error
    if (
        package.get("status") != package_manifest.get("status")
        or package.get("sha256") != checksum
    ):
        raise TransferRehearsalError(
            "리허설 원본 패키지 상태가 보고서와 다릅니다."
        )
    source_identity = report.get("preparedSourceIdentity")
    if (
        not isinstance(source_identity, dict)
        or source_identity.get("status") != "PASS"
        or not is_checksum(source_identity.get("manifestSha256"))
        or not isinstance(source_identity.get("fileCount"), int)
        or source_identity.get("fileCount", 0) <= 0
    ):
        raise TransferRehearsalError(
            "준비된 HP 소스 동일성 기록이 올바르지 않습니다."
        )
    try:
        html_value = html_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise TransferRehearsalError(
            "리허설 HTML이 UTF-8이 아닙니다."
        ) from error
    if html_value != render_html(report):
        raise TransferRehearsalError(
            "리허설 JSON과 HTML 내용이 일치하지 않습니다."
        )
    return report_path, report


def execute_rehearsal(
    root: Path,
    *,
    package_value: str | None,
    confirmation: str,
    now: datetime,
    temporary_parent: Path | None = None,
    stage_function: StageFunction = stage_media,
    media_verifier: MediaVerifier = verify_media,
    prepare_function: PrepareFunction = prepare_workspace,
    prepare_verifier: PrepareVerifier = verify_prepare_report,
) -> tuple[Path, dict[str, Any], int]:
    root = root.resolve()
    if confirmation != CONFIRMATION:
        raise TransferRehearsalError(
            f"전체 이관 리허설에는 --confirm {CONFIRMATION}이 필요합니다."
        )
    package = resolve_package(root, package_value)
    try:
        _, package_manifest, _ = inspect_package(str(package))
    except (
        HpOmenRestoreError,
        TransferPackageError,
        FileNotFoundError,
        OSError,
    ) as error:
        raise TransferRehearsalError(str(error)) from error
    if temporary_parent is not None:
        temporary_parent = temporary_parent.resolve()
        if (
            not temporary_parent.is_dir()
            or temporary_parent.is_symlink()
            or is_within(temporary_parent, root)
        ):
            raise TransferRehearsalError(
                "리허설 임시 상위 폴더는 프로젝트 밖의 기존 폴더여야 합니다."
            )

    steps: list[dict[str, Any]] = [
        step_result(
            "package-verify",
            status="PASS",
            detail="원본 최종 이관 패키지 전체 검증 완료",
        )
    ]
    prepared_source_identity: dict[str, Any] | None = None
    temporary_root = Path(
        tempfile.mkdtemp(
            prefix="visionflow-transfer-rehearsal-",
            dir=str(temporary_parent) if temporary_parent else None,
        )
    ).resolve()
    failed = False
    try:
        media_root = temporary_root / "offline-media"
        try:
            _, media_manifest = stage_function(
                root,
                package_value=str(package),
                release_evidence_value=None,
                destination_value=str(media_root),
                confirmation=MEDIA_CONFIRMATION,
                now=now,
            )
            if media_manifest.get("status") != MEDIA_READY_STATUS:
                raise TransferRehearsalError(
                    "임시 이관 매체가 준비 완료 상태가 아닙니다."
                )
            steps.append(
                step_result(
                    "media-stage",
                    status="PASS",
                    detail="임시 매체에 패키지와 부트스트랩 도구 복사 완료",
                )
            )
        except Exception as error:
            failed = True
            steps.append(
                step_result(
                    "media-stage",
                    status="FAILED",
                    detail=str(error),
                )
            )

        if not failed:
            try:
                _, verified_media = media_verifier(media_root)
                if verified_media.get("status") != MEDIA_READY_STATUS:
                    raise TransferRehearsalError(
                        "임시 매체 독립 검증 상태가 올바르지 않습니다."
                    )
                steps.append(
                    step_result(
                        "media-verify",
                        status="PASS",
                        detail="복사본 크기·SHA-256·중첩 구조 검증 완료",
                    )
                )
            except Exception as error:
                failed = True
                steps.append(
                    step_result(
                        "media-verify",
                        status="FAILED",
                        detail=str(error),
                    )
                )
        else:
            steps.append(
                step_result(
                    "media-verify",
                    status="SKIPPED",
                    detail="앞 단계 실패로 실행하지 않음",
                )
            )

        prepared_root = temporary_root / "fresh-hp-workspace"
        prepare_report_path: Path | None = None
        if not failed:
            copied_package = media_root / "package" / package.name
            try:
                prepare_report_path, prepare_report = prepare_function(
                    str(copied_package),
                    str(prepared_root),
                    confirmation=PREPARE_CONFIRMATION,
                    now=now,
                )
                if prepare_report.get("status") != PREPARED_STATUS:
                    raise TransferRehearsalError(
                        "임시 HP 작업공간이 준비 완료 상태가 아닙니다."
                    )
                source_identity = prepare_report.get("sourceIdentity")
                if not isinstance(source_identity, dict):
                    raise TransferRehearsalError(
                        "임시 HP 작업공간 소스 동일성이 없습니다."
                    )
                prepared_source_identity = dict(source_identity)
                steps.append(
                    step_result(
                        "workspace-prepare",
                        status="PASS",
                        detail="안전 소스와 검증 증적을 새 작업공간에 추출 완료",
                    )
                )
            except Exception as error:
                failed = True
                steps.append(
                    step_result(
                        "workspace-prepare",
                        status="FAILED",
                        detail=str(error),
                    )
                )
        else:
            steps.append(
                step_result(
                    "workspace-prepare",
                    status="SKIPPED",
                    detail="앞 단계 실패로 실행하지 않음",
                )
            )

        if not failed and prepare_report_path is not None:
            try:
                relative_report = prepare_report_path.relative_to(
                    prepared_root
                ).as_posix()
                _, verified_prepare = prepare_verifier(
                    prepared_root,
                    relative_report,
                )
                if verified_prepare.get("status") != PREPARED_STATUS:
                    raise TransferRehearsalError(
                        "임시 HP 준비 보고서 검증 상태가 올바르지 않습니다."
                    )
                steps.append(
                    step_result(
                        "workspace-verify",
                        status="PASS",
                        detail="소스·기준선·백업·증적 교차 검증 완료",
                    )
                )
            except Exception as error:
                failed = True
                steps.append(
                    step_result(
                        "workspace-verify",
                        status="FAILED",
                        detail=str(error),
                    )
                )
        else:
            steps.append(
                step_result(
                    "workspace-verify",
                    status="SKIPPED",
                    detail="앞 단계 실패로 실행하지 않음",
                )
            )
    finally:
        cleanup_error: str | None = None
        try:
            shutil.rmtree(temporary_root)
        except OSError as error:
            cleanup_error = str(error)
        removed = not temporary_root.exists()
        if cleanup_error is not None or not removed:
            failed = True
            steps.append(
                step_result(
                    "temporary-cleanup",
                    status="FAILED",
                    detail=cleanup_error or "임시 폴더가 남아 있습니다.",
                )
            )
        else:
            steps.append(
                step_result(
                    "temporary-cleanup",
                    status="PASS",
                    detail="임시 매체와 새 작업공간을 완전히 제거함",
                )
            )

    if prepared_source_identity is None:
        prepared_source_identity = {
            "status": "UNAVAILABLE",
            "manifestSha256": None,
            "fileCount": 0,
        }
    status = FAILED_STATUS if failed else READY_STATUS
    report: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "scope": "LG_GRAM_PRE_HP_OMEN_TRANSFER",
        "operation": OPERATION,
        "rehearsalId": str(uuid.uuid4()),
        "generatedAt": now.isoformat(),
        "completedAt": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "package": package_entry(
            root,
            package,
            str(package_manifest.get("status")),
        ),
        "preparedSourceIdentity": prepared_source_identity,
        "steps": steps,
        "deferred": [
            "hp-target-smartphone-https-revalidation",
            "hp-omen-gpu-best-model-benchmark",
        ],
        "outOfScope": ["dji-mini4-pro-integration"],
        "safety": {
            "databaseMutation": False,
            "dockerStarted": False,
            "gpuExecuted": False,
            "externalTransferPerformed": False,
            "temporaryWorkspaceRemoved": not temporary_root.exists(),
            "sourceFilesModified": False,
        },
    }
    report_path, _, _ = write_report(root, report, now)
    if not failed:
        verify_report(root, relative_path(root, report_path))
    return report_path, report, 1 if failed else 0


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rehearse VisionFlow offline transfer and HP preparation"
    )
    parser.add_argument("--root", default=str(default_root))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "plan",
        help="변경 없이 오프라인 이관 리허설 순서 출력",
    )
    execute = subparsers.add_parser(
        "execute",
        help="시스템 임시 폴더에서 전체 이관 준비 리허설",
    )
    execute.add_argument("--package")
    execute.add_argument("--confirm", default="")
    verify = subparsers.add_parser(
        "verify",
        help="리허설 성공 보고서 독립 재검증",
    )
    verify.add_argument("--report", required=True)
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    args = build_parser(default_root).parse_args(arguments)
    root = Path(args.root).resolve()
    try:
        if args.command == "plan":
            print("VisionFlow offline transfer rehearsal: PLAN")
            for item in build_plan():
                print(
                    f"{item['order']:02d}. [{item['mode']}] {item['title']}"
                )
            print("No database, Docker, GPU, or external media was changed.")
            return 0
        if args.command == "execute":
            report_path, report, exit_code = execute_rehearsal(
                root,
                package_value=args.package,
                confirmation=args.confirm,
                now=datetime.now(timezone.utc),
            )
            print(
                "VisionFlow offline transfer rehearsal: "
                f"{report['status']}"
            )
            print(f"Report: {report_path}")
            return exit_code
        report_path, report = verify_report(root, args.report)
        print("VisionFlow offline transfer rehearsal: VERIFIED")
        print(f"Status: {report['status']}")
        print(f"Report: {report_path}")
        return 0
    except (
        TransferRehearsalError,
        TransferMediaError,
        HpOmenRestoreError,
        TransferPackageError,
        FileNotFoundError,
        OSError,
    ) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
