"""Read-only source/target acceptance gate for VisionFlow transfer day."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    from visionflow_hp_omen_transfer_day import (
        READY_STATUS as TRANSFER_DAY_READY_STATUS,
        TransferDayError,
        latest_checkpoint,
        verify_checkpoint,
    )
    from visionflow_release_evidence import (
        EvidenceBundleError,
        verify_bundle,
    )
    from visionflow_transfer_media import (
        MANIFEST_NAME as TRANSFER_MEDIA_MANIFEST_NAME,
        TransferMediaError,
        verify_media,
    )
    from visionflow_transfer_package import (
        TransferPackageError,
        verify_transfer_package_file,
    )
    from visionflow_transfer_rehearsal import (
        TransferRehearsalError,
        verify_report as verify_rehearsal_report,
    )
except ModuleNotFoundError:  # pragma: no cover - package import during tests
    from scripts.visionflow_hp_omen_transfer_day import (
        READY_STATUS as TRANSFER_DAY_READY_STATUS,
        TransferDayError,
        latest_checkpoint,
        verify_checkpoint,
    )
    from scripts.visionflow_release_evidence import (
        EvidenceBundleError,
        verify_bundle,
    )
    from scripts.visionflow_transfer_media import (
        MANIFEST_NAME as TRANSFER_MEDIA_MANIFEST_NAME,
        TransferMediaError,
        verify_media,
    )
    from scripts.visionflow_transfer_package import (
        TransferPackageError,
        verify_transfer_package_file,
    )
    from scripts.visionflow_transfer_rehearsal import (
        TransferRehearsalError,
        verify_report as verify_rehearsal_report,
    )


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
OPERATION = "TRANSFER_DAY_ACCEPTANCE_GATE"
REPORT_ROOT = Path("artifacts/transfer-day-gate")
SOURCE_ROLE = "SOURCE"
TARGET_ROLE = "TARGET"
SOURCE_READY_STATUS = "SOURCE_TRANSFER_DAY_GATE_READY_WITH_DEFERRED"
TARGET_READY_STATUS = "TARGET_TRANSFER_DAY_GATE_READY_WITH_DEFERRED"
SOURCE_BLOCKED_STATUS = "SOURCE_TRANSFER_DAY_GATE_BLOCKED"
TARGET_BLOCKED_STATUS = "TARGET_TRANSFER_DAY_GATE_BLOCKED"
ALLOWED_STATUSES = {
    SOURCE_READY_STATUS,
    TARGET_READY_STATUS,
    SOURCE_BLOCKED_STATUS,
    TARGET_BLOCKED_STATUS,
}
SOURCE_STEPS = (
    ("transfer-package", "최종 이관 패키지 무결성"),
    ("transfer-media", "외장 이관 매체 무결성"),
    ("offline-transfer-rehearsal", "오프라인 이관 리허설"),
    ("release-evidence", "최신 릴리스 증빙 번들"),
    ("source-lineage", "SOURCE 패키지·매체·리허설·증빙 동일성"),
)
TARGET_STEPS = (
    ("hp-transfer-day-checkpoint", "HP OMEN 이관 당일 READY 체크포인트"),
    ("release-evidence", "SOURCE 및 HP 활성화 후 릴리스 증빙 번들"),
    ("target-lineage", "SOURCE 리허설·TARGET 체크포인트 증빙 동일성"),
)


class TransferDayGateError(RuntimeError):
    """Raised when transfer-day evidence cannot be proven ready."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def write_text_atomic(path: Path, value: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding=encoding)
    os.replace(temporary, path)


def read_json(path: Path, title: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise TransferDayGateError(f"{title} JSON 형식이 올바르지 않습니다.") from error
    if not isinstance(value, dict):
        raise TransferDayGateError(f"{title} JSON 최상위 값은 객체여야 합니다.")
    return value


def relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as error:
        raise TransferDayGateError(
            "프로젝트 내부 증적 경로를 상대경로로 기록할 수 없습니다."
        ) from error


def artifact_entry(root: Path, key: str, path: Path) -> dict[str, Any]:
    return {
        "key": key,
        "path": relative_path(root, path),
        "fileName": path.name,
        "sizeBytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def media_entry(path: Path) -> dict[str, Any]:
    manifest = path / TRANSFER_MEDIA_MANIFEST_NAME
    return {
        "key": "transfer-media",
        "folderName": path.name,
        "manifestSizeBytes": manifest.stat().st_size,
        "manifestSha256": sha256_file(manifest),
    }


def external_file_entry(key: str, path: Path) -> dict[str, Any]:
    return {
        "key": key,
        "fileName": path.name,
        "sizeBytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def resolve_project_file(
    root: Path,
    value: str | None,
    *,
    directory: Path,
    pattern: str,
    title: str,
) -> Path:
    allowed = (root / directory).resolve()
    if value:
        candidate = Path(value)
        path = (
            candidate.resolve()
            if candidate.is_absolute()
            else (root / candidate).resolve()
        )
    else:
        candidates = [
            item.resolve()
            for item in allowed.glob(pattern)
            if item.is_file() and not item.is_symlink()
        ]
        if not candidates:
            raise TransferDayGateError(f"{title} 파일이 없습니다: {directory.as_posix()}")
        path = max(
            candidates,
            key=lambda item: (item.stat().st_mtime_ns, item.as_posix()),
        )
    if (
        not is_within(path, allowed)
        or not path.is_file()
        or path.is_symlink()
    ):
        raise TransferDayGateError(f"{title} 경로가 허용 영역을 벗어났습니다.")
    return path


def resolve_media(value: str) -> Path:
    path = Path(value).resolve()
    if not path.is_dir() or path.is_symlink() or path.parent == path:
        raise TransferDayGateError("외장 이관 매체 폴더를 찾을 수 없습니다.")
    return path


def verify_release_evidence_bundle(
    root: Path,
    value: str | None,
) -> tuple[Path, dict[str, Any]]:
    bundle = resolve_project_file(
        root,
        value,
        directory=Path("artifacts/release-evidence"),
        pattern="visionflow-release-evidence-*.zip",
        title="릴리스 증빙 번들",
    )
    return verify_release_evidence_file(bundle)


def verify_release_evidence_file(
    bundle: Path,
) -> tuple[Path, dict[str, Any]]:
    bundle = bundle.resolve()
    if (
        not bundle.is_file()
        or bundle.is_symlink()
        or not bundle.name.startswith("visionflow-release-evidence-")
        or bundle.suffix.lower() != ".zip"
    ):
        raise TransferDayGateError("릴리스 증빙 ZIP 경로가 올바르지 않습니다.")
    sidecar = bundle.with_suffix(".sha256")
    if not sidecar.is_file() or sidecar.is_symlink():
        raise TransferDayGateError("릴리스 증빙 SHA-256 sidecar가 없습니다.")
    parts = sidecar.read_text(encoding="utf-8-sig").strip().split()
    if (
        len(parts) != 2
        or parts[1] != bundle.name
        or len(parts[0]) != 64
        or any(character not in "0123456789abcdefABCDEF" for character in parts[0])
        or parts[0].lower() != sha256_file(bundle)
    ):
        raise TransferDayGateError("릴리스 증빙 SHA-256이 일치하지 않습니다.")
    try:
        with zipfile.ZipFile(bundle, "r") as archive:
            manifest = json.loads(
                archive.read("evidence-manifest.json").decode("utf-8-sig")
            )
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as error:
        raise TransferDayGateError(
            "릴리스 증빙 ZIP 또는 manifest가 손상되었습니다."
        ) from error
    if (
        not isinstance(manifest, dict)
        or manifest.get("schemaVersion") != SCHEMA_VERSION
        or manifest.get("project") != PROJECT_NAME
        or manifest.get("operation") != "RELEASE_EVIDENCE_BUNDLE"
        or not isinstance(manifest.get("evidence"), list)
        or not isinstance(manifest.get("supplementalEvidence"), list)
        or not isinstance(manifest.get("includedFiles"), list)
    ):
        raise TransferDayGateError("VisionFlow 릴리스 증빙 manifest가 아닙니다.")
    try:
        verify_bundle(bundle, manifest)
    except (EvidenceBundleError, KeyError, TypeError) as error:
        raise TransferDayGateError(str(error)) from error
    return bundle, manifest


def supplemental_entry(
    manifest: Mapping[str, Any],
    key: str,
    expected_archive: str,
) -> Mapping[str, Any]:
    entries = manifest.get("supplementalEvidence")
    if not isinstance(entries, list):
        raise TransferDayGateError("릴리스 증빙에 보조 증적 목록이 없습니다.")
    matches = [
        item
        for item in entries
        if isinstance(item, Mapping) and item.get("key") == key
    ]
    if len(matches) != 1:
        raise TransferDayGateError(f"릴리스 보조 증적이 없거나 중복됐습니다: {key}")
    entry = matches[0]
    if (
        entry.get("status") != "PASS"
        or entry.get("included") is not True
        or entry.get("archivePath") != expected_archive
        or not isinstance(entry.get("sourceSha256"), str)
    ):
        raise TransferDayGateError(f"릴리스 보조 증적이 PASS 포함 상태가 아닙니다: {key}")
    return entry


def step_result(
    key: str,
    title: str,
    status: str,
    detail: str,
) -> dict[str, str]:
    return {
        "key": key,
        "title": title,
        "status": status,
        "detail": detail,
    }


def sanitize_error(
    error: Exception,
    *,
    root: Path,
    media: Path | None,
) -> str:
    detail = str(error)
    replacements = [(str(root), "<PROJECT_ROOT>")]
    if media is not None:
        replacements.append((str(media), "<TRANSFER_MEDIA>"))
    for original, replacement in replacements:
        detail = detail.replace(original, replacement)
        detail = detail.replace(original.replace("\\", "/"), replacement)
    return detail


def build_report(
    *,
    role: str,
    status: str,
    now: datetime,
    checks: list[dict[str, str]],
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    expected = len(SOURCE_STEPS if role == SOURCE_ROLE else TARGET_STEPS)
    passed = sum(item["status"] == "PASS" for item in checks)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "scope": "LG_GRAM_TO_HP_OMEN_TRANSFER_DAY",
        "operation": OPERATION,
        "gateId": str(uuid.uuid4()),
        "generatedAt": now.astimezone(timezone.utc).isoformat(),
        "role": role,
        "status": status,
        "checks": checks,
        "artifacts": artifacts,
        "summary": {
            "total": expected,
            "passed": passed,
            "blocking": 0 if status in {SOURCE_READY_STATUS, TARGET_READY_STATUS} else 1,
        },
        "deferred": [
            "hp-target-smartphone-https-revalidation",
            "hp-omen-model-accuracy-performance",
        ],
        "outOfScope": ["dji-mini4-pro-integration"],
        "safety": {
            "readOnly": True,
            "databaseMutation": False,
            "dockerStarted": False,
            "gpuExecuted": False,
            "externalMediaModified": False,
            "environmentValuesRecorded": False,
            "operatorKeysRecorded": False,
            "absolutePathsRecorded": False,
        },
    }


def render_html(report: Mapping[str, Any]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{index}</td>"
        f"<td>{html.escape(str(item['title']))}</td>"
        f"<td>{html.escape(str(item['status']))}</td>"
        f"<td>{html.escape(str(item['detail']))}</td>"
        "</tr>"
        for index, item in enumerate(report["checks"], start=1)
    )
    ready = str(report["status"]).endswith("READY_WITH_DEFERRED")
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VisionFlow 이관 당일 최종 합격 게이트</title><style>
body{{margin:0;background:#eef3f8;color:#0f172a;font-family:Arial,'Noto Sans KR',sans-serif}}
main{{max-width:1080px;margin:32px auto;padding:0 20px}}section{{background:#fff;border:1px solid #dbe4ee;border-radius:16px;padding:24px;margin:16px 0}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid #e2e8f0;text-align:left;vertical-align:top}}
.ready{{color:#047857;font-weight:800}}.blocked{{color:#b91c1c;font-weight:800}}</style></head>
<body><main><section><h1>VisionFlow 이관 당일 최종 합격 게이트</h1>
<p>역할: {html.escape(str(report['role']))}</p>
<p class="{'ready' if ready else 'blocked'}">{html.escape(str(report['status']))}</p>
<p>{html.escape(str(report['generatedAt']))}</p></section>
<section><h2>검증 항목</h2><table><tr><th>#</th><th>항목</th><th>상태</th><th>결과</th></tr>{rows}</table></section>
<section><h2>안전</h2><p>읽기 전용 검사이며 DB·Docker·GPU·외장 매체를 변경하지 않았습니다.</p></section>
</main></body></html>"""


def write_report(
    root: Path,
    report: dict[str, Any],
    now: datetime,
) -> Path:
    output = root / REPORT_ROOT
    output.mkdir(parents=True, exist_ok=True)
    timestamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    role = str(report["role"]).lower()
    base = output / f"visionflow-transfer-day-{role}-gate-{timestamp}"
    if base.with_suffix(".json").exists():
        base = output / (
            f"visionflow-transfer-day-{role}-gate-{timestamp}-"
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
    return json_path


def run_source_gate(
    root: Path,
    *,
    media_value: str,
    package_value: str | None,
    rehearsal_value: str | None,
    release_evidence_value: str | None,
    now: datetime,
) -> tuple[Path, dict[str, Any], int]:
    checks: list[dict[str, str]] = []
    artifacts: list[dict[str, Any]] = []
    media: Path | None = None
    current_key, current_title = SOURCE_STEPS[0]
    try:
        package = resolve_project_file(
            root,
            package_value,
            directory=Path("artifacts/transfer-package"),
            pattern="visionflow-transfer-package-*.zip",
            title=current_title,
        )
        _, package_manifest = verify_transfer_package_file(
            root,
            relative_path(root, package),
        )
        package_sha = sha256_file(package)
        artifacts.append(artifact_entry(root, current_key, package))
        checks.append(step_result(current_key, current_title, "PASS", "패키지와 sidecar·내부 manifest가 유효함"))

        current_key, current_title = SOURCE_STEPS[1]
        media = resolve_media(media_value)
        _, media_manifest = verify_media(media)
        artifacts.append(media_entry(media))
        checks.append(step_result(current_key, current_title, "PASS", "외장 매체 파일 구성과 패키지 복사본이 유효함"))

        current_key, current_title = SOURCE_STEPS[2]
        rehearsal = resolve_project_file(
            root,
            rehearsal_value,
            directory=Path("artifacts/transfer-rehearsal"),
            pattern="visionflow-transfer-rehearsal-*.json",
            title=current_title,
        )
        _, rehearsal_report = verify_rehearsal_report(
            root,
            relative_path(root, rehearsal),
        )
        artifacts.append(artifact_entry(root, current_key, rehearsal))
        checks.append(step_result(current_key, current_title, "PASS", "비파괴 오프라인 이관 리허설이 유효함"))

        current_key, current_title = SOURCE_STEPS[3]
        release_bundle, release_manifest = verify_release_evidence_bundle(
            root,
            release_evidence_value,
        )
        artifacts.append(artifact_entry(root, current_key, release_bundle))
        checks.append(step_result(current_key, current_title, "PASS", "릴리스 증빙 ZIP과 내부 manifest가 유효함"))

        current_key, current_title = SOURCE_STEPS[4]
        media_package = media_manifest.get("package")
        media_release = media_manifest.get("releaseEvidence")
        rehearsal_package = rehearsal_report.get("package")
        offline_entry = supplemental_entry(
            release_manifest,
            "offline-transfer-rehearsal",
            "supplemental/offline-transfer-rehearsal.json",
        )
        if (
            package_manifest.get("status") != "TRANSFER_PACKAGE_READY_WITH_DEFERRED"
            or not isinstance(media_package, Mapping)
            or media_package.get("sha256") != package_sha
            or not isinstance(rehearsal_package, Mapping)
            or rehearsal_package.get("sha256") != package_sha
            or not isinstance(media_release, Mapping)
            or media_release.get("sha256") != sha256_file(release_bundle)
            or offline_entry.get("sourceSha256") != sha256_file(rehearsal)
        ):
            raise TransferDayGateError(
                "SOURCE 패키지·매체·리허설·릴리스 증빙의 SHA-256 연결이 다릅니다."
            )
        checks.append(step_result(current_key, current_title, "PASS", "네 증적이 동일 패키지·리허설 해시로 연결됨"))
        report = build_report(
            role=SOURCE_ROLE,
            status=SOURCE_READY_STATUS,
            now=now,
            checks=checks,
            artifacts=artifacts,
        )
        report_path = write_report(root, report, now)
        verify_gate_report(root, relative_path(root, report_path))
        return report_path, report, 0
    except (
        TransferDayGateError,
        TransferPackageError,
        TransferMediaError,
        TransferRehearsalError,
        EvidenceBundleError,
        FileNotFoundError,
        OSError,
    ) as error:
        checks.append(
            step_result(
                current_key,
                current_title,
                "FAILED",
                sanitize_error(error, root=root, media=media),
            )
        )
        report = build_report(
            role=SOURCE_ROLE,
            status=SOURCE_BLOCKED_STATUS,
            now=now,
            checks=checks,
            artifacts=artifacts,
        )
        return write_report(root, report, now), report, 1


def run_target_gate(
    root: Path,
    *,
    checkpoint_value: str | None,
    source_release_evidence_value: str,
    release_evidence_value: str | None,
    now: datetime,
) -> tuple[Path, dict[str, Any], int]:
    checks: list[dict[str, str]] = []
    artifacts: list[dict[str, Any]] = []
    current_key, current_title = TARGET_STEPS[0]
    try:
        checkpoint = (
            resolve_project_file(
                root,
                checkpoint_value,
                directory=Path("artifacts/hp-omen-transfer-day"),
                pattern="checkpoint-*/visionflow-hp-omen-transfer-day.json",
                title=current_title,
            )
            if checkpoint_value
            else latest_checkpoint(root)
        )
        _, checkpoint_report = verify_checkpoint(
            root,
            relative_path(root, checkpoint),
            environment={},
            platform_name=sys.platform,
        )
        if checkpoint_report.get("status") != TRANSFER_DAY_READY_STATUS:
            raise TransferDayGateError(
                f"HP 이관 당일 체크포인트가 READY가 아닙니다: {checkpoint_report.get('status')}"
            )
        artifacts.append(artifact_entry(root, current_key, checkpoint))
        checks.append(step_result(current_key, current_title, "PASS", "준비·사전점검·활성화 증적 체인이 READY임"))

        current_key, current_title = TARGET_STEPS[1]
        source_release_bundle, source_release_manifest = (
            verify_release_evidence_file(
                Path(source_release_evidence_value),
            )
        )
        release_bundle, release_manifest = verify_release_evidence_bundle(
            root,
            release_evidence_value,
        )
        artifacts.append(
            external_file_entry(
                "source-release-evidence",
                source_release_bundle,
            )
        )
        artifacts.append(artifact_entry(root, current_key, release_bundle))
        checks.append(step_result(current_key, current_title, "PASS", "외장 SOURCE 및 HP TARGET 릴리스 증빙 ZIP이 유효함"))

        current_key, current_title = TARGET_STEPS[2]
        offline_entry = supplemental_entry(
            source_release_manifest,
            "offline-transfer-rehearsal",
            "supplemental/offline-transfer-rehearsal.json",
        )
        hp_entry = supplemental_entry(
            release_manifest,
            "hp-omen-transfer-day",
            "supplemental/hp-omen-transfer-day.json",
        )
        if (
            not isinstance(offline_entry.get("sourceSha256"), str)
            or hp_entry.get("sourceSha256") != sha256_file(checkpoint)
        ):
            raise TransferDayGateError(
                "TARGET 체크포인트와 릴리스 증빙의 SHA-256 연결이 다릅니다."
            )
        checks.append(step_result(current_key, current_title, "PASS", "SOURCE 번들은 리허설, TARGET 번들은 READY 체크포인트를 포함함"))
        report = build_report(
            role=TARGET_ROLE,
            status=TARGET_READY_STATUS,
            now=now,
            checks=checks,
            artifacts=artifacts,
        )
        report_path = write_report(root, report, now)
        verify_gate_report(root, relative_path(root, report_path))
        return report_path, report, 0
    except (
        TransferDayGateError,
        TransferDayError,
        EvidenceBundleError,
        FileNotFoundError,
        OSError,
    ) as error:
        checks.append(
            step_result(
                current_key,
                current_title,
                "FAILED",
                sanitize_error(error, root=root, media=None),
            )
        )
        report = build_report(
            role=TARGET_ROLE,
            status=TARGET_BLOCKED_STATUS,
            now=now,
            checks=checks,
            artifacts=artifacts,
        )
        return write_report(root, report, now), report, 1


def resolve_gate_report(root: Path, value: str) -> Path:
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
        raise TransferDayGateError("이관 당일 게이트 보고서 경로가 올바르지 않습니다.")
    return path


def verify_gate_report(
    root: Path,
    value: str,
) -> tuple[Path, dict[str, Any]]:
    path = resolve_gate_report(root, value)
    html_path = path.with_suffix(".html")
    sidecar = path.with_suffix(".sha256")
    if not sidecar.is_file() or sidecar.is_symlink():
        raise TransferDayGateError("이관 당일 게이트 sidecar가 없습니다.")
    lines = [
        line.strip().split()
        for line in sidecar.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    recorded = {
        parts[1]: parts[0].lower()
        for parts in lines
        if len(parts) == 2
    }
    expected = {path.name, html_path.name}
    if len(lines) != 2 or set(recorded) != expected:
        raise TransferDayGateError("이관 당일 게이트 sidecar 형식이 올바르지 않습니다.")
    for item in (path, html_path):
        checksum = recorded[item.name]
        if (
            len(checksum) != 64
            or any(character not in "0123456789abcdef" for character in checksum)
            or not item.is_file()
            or item.is_symlink()
            or checksum != sha256_file(item)
        ):
            raise TransferDayGateError(
                f"이관 당일 게이트 SHA-256이 다릅니다: {item.name}"
            )
    report = read_json(path, "이관 당일 게이트")
    role = report.get("role")
    status = report.get("status")
    expected_total = len(SOURCE_STEPS if role == SOURCE_ROLE else TARGET_STEPS)
    summary = report.get("summary")
    safety = report.get("safety")
    if (
        report.get("schemaVersion") != SCHEMA_VERSION
        or report.get("project") != PROJECT_NAME
        or report.get("operation") != OPERATION
        or role not in {SOURCE_ROLE, TARGET_ROLE}
        or status not in ALLOWED_STATUSES
        or (
            role == SOURCE_ROLE
            and status not in {SOURCE_READY_STATUS, SOURCE_BLOCKED_STATUS}
        )
        or (
            role == TARGET_ROLE
            and status not in {TARGET_READY_STATUS, TARGET_BLOCKED_STATUS}
        )
        or not isinstance(summary, Mapping)
        or summary.get("total") != expected_total
        or not isinstance(report.get("checks"), list)
        or not isinstance(report.get("artifacts"), list)
    ):
        raise TransferDayGateError("이관 당일 게이트 보고서 형식이 올바르지 않습니다.")
    ready = status in {SOURCE_READY_STATUS, TARGET_READY_STATUS}
    if (
        summary.get("blocking") != (0 if ready else 1)
        or summary.get("passed")
        != sum(item.get("status") == "PASS" for item in report["checks"] if isinstance(item, Mapping))
        or (ready and len(report["checks"]) != expected_total)
        or (ready and any(item.get("status") != "PASS" for item in report["checks"]))
    ):
        raise TransferDayGateError("이관 당일 게이트 집계가 검사 결과와 다릅니다.")
    if (
        not isinstance(safety, Mapping)
        or safety.get("readOnly") is not True
        or safety.get("databaseMutation") is not False
        or safety.get("dockerStarted") is not False
        or safety.get("gpuExecuted") is not False
        or safety.get("externalMediaModified") is not False
        or safety.get("environmentValuesRecorded") is not False
        or safety.get("operatorKeysRecorded") is not False
        or safety.get("absolutePathsRecorded") is not False
    ):
        raise TransferDayGateError("이관 당일 게이트 안전 정보가 올바르지 않습니다.")
    serialized = json.dumps(report, ensure_ascii=False)
    root_text = str(root.resolve())
    if root_text in serialized or root_text.replace("\\", "/") in serialized:
        raise TransferDayGateError("게이트 보고서에 프로젝트 절대경로가 기록됐습니다.")
    if html_path.read_text(encoding="utf-8-sig") != render_html(report):
        raise TransferDayGateError("게이트 JSON과 HTML이 일치하지 않습니다.")
    return path, report


def build_plan(role: str) -> list[dict[str, Any]]:
    definitions = SOURCE_STEPS if role == SOURCE_ROLE else TARGET_STEPS
    return [
        {
            "order": index,
            "mode": "READ_ONLY",
            "key": key,
            "title": title,
        }
        for index, (key, title) in enumerate(definitions, start=1)
    ]


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="VisionFlow transfer-day source/target acceptance gate"
    )
    parser.add_argument("--root", default=str(default_root))
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan", help="읽기 전용 검사 계획 출력")
    plan.add_argument("--role", choices=("source", "target"), required=True)
    source = subparsers.add_parser("source", help="LG 출발 전 SOURCE 게이트")
    source.add_argument("--media", required=True)
    source.add_argument("--package")
    source.add_argument("--rehearsal")
    source.add_argument("--release-evidence")
    target = subparsers.add_parser("target", help="HP 활성화 후 TARGET 게이트")
    target.add_argument("--checkpoint")
    target.add_argument("--source-release-evidence", required=True)
    target.add_argument("--release-evidence")
    verify = subparsers.add_parser("verify", help="게이트 보고서 독립 검증")
    verify.add_argument("--report", required=True)
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    args = build_parser(default_root).parse_args(arguments)
    root = Path(args.root).resolve()
    try:
        if not root.is_dir():
            raise TransferDayGateError(f"프로젝트 루트를 찾을 수 없습니다: {root}")
        if args.command == "plan":
            role = SOURCE_ROLE if args.role == "source" else TARGET_ROLE
            print(f"VisionFlow transfer-day {role} gate: PLAN")
            for step in build_plan(role):
                print(
                    f"{step['order']:02d}. [{step['mode']}] "
                    f"{step['title']}"
                )
            print("No file, database, Docker, GPU, or external media was changed.")
            return 0
        if args.command == "verify":
            path, report = verify_gate_report(root, args.report)
            print("VisionFlow transfer-day gate: VERIFIED")
            print(f"Role  : {report['role']}")
            print(f"Status: {report['status']}")
            print(f"Report: {path}")
            return (
                0
                if report["status"] in {
                    SOURCE_READY_STATUS,
                    TARGET_READY_STATUS,
                }
                else 1
            )
        if args.command == "source":
            path, report, exit_code = run_source_gate(
                root,
                media_value=args.media,
                package_value=args.package,
                rehearsal_value=args.rehearsal,
                release_evidence_value=args.release_evidence,
                now=datetime.now(timezone.utc),
            )
        else:
            path, report, exit_code = run_target_gate(
                root,
                checkpoint_value=args.checkpoint,
                source_release_evidence_value=args.source_release_evidence,
                release_evidence_value=args.release_evidence,
                now=datetime.now(timezone.utc),
            )
        print(f"VisionFlow transfer-day {report['role']} gate: {report['status']}")
        print(f"Report: {path}")
        return exit_code
    except (
        TransferDayGateError,
        TransferDayError,
        TransferPackageError,
        TransferMediaError,
        TransferRehearsalError,
        EvidenceBundleError,
        FileNotFoundError,
        OSError,
    ) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
