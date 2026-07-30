"""Create and verify a non-sensitive VisionFlow second-project closeout report."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from visionflow_transfer_package import (
        READY_STATUS as READY_PACKAGE_STATUS,
        TransferPackageError,
        verify_transfer_package_file,
    )
except ModuleNotFoundError:  # pragma: no cover - package import during unit tests
    from scripts.visionflow_transfer_package import (
        READY_STATUS as READY_PACKAGE_STATUS,
        TransferPackageError,
        verify_transfer_package_file,
    )


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
CLOSEOUT_STATUS = "SECOND_PROJECT_CLOSED_WITH_DEFERRED"
MAX_JSON_BYTES = 5 * 1024 * 1024
FUTURE_TOLERANCE = timedelta(minutes=10)


class ProjectCloseoutError(RuntimeError):
    """Raised when closeout inputs or generated reports are inconsistent."""


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


def read_json(path: Path, title: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ProjectCloseoutError(f"{title} 파일을 찾을 수 없습니다: {path}")
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ProjectCloseoutError(f"{title} 크기가 허용 범위를 초과했습니다.")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProjectCloseoutError(f"{title} JSON 형식이 올바르지 않습니다.") from error
    if not isinstance(value, dict):
        raise ProjectCloseoutError(f"{title} 최상위 값은 객체여야 합니다.")
    return value


def parse_timestamp(value: Any, title: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ProjectCloseoutError(f"{title} 생성 시각이 없습니다.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ProjectCloseoutError(f"{title} 생성 시각 형식이 올바르지 않습니다.") from error
    if parsed.tzinfo is None:
        raise ProjectCloseoutError(f"{title} 생성 시각에 시간대가 없습니다.")
    return parsed.astimezone(timezone.utc)


def write_text_atomic(path: Path, value: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding=encoding)
    os.replace(temporary, path)


def newest_file(directory: Path, pattern: str, title: str) -> Path:
    if not directory.is_dir():
        raise ProjectCloseoutError(f"{title} 폴더가 없습니다: {directory}")
    candidates = [
        path.resolve()
        for path in directory.glob(pattern)
        if path.is_file() and not path.is_symlink()
    ]
    if not candidates:
        raise ProjectCloseoutError(f"{title} 파일이 없습니다.")
    return max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))


def resolve_input(
    root: Path,
    value: str | None,
    allowed: Path,
    pattern: str,
    title: str,
) -> Path:
    if value:
        candidate = Path(value)
        path = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    else:
        path = newest_file(allowed, pattern, title)
    if not is_within(path, allowed.resolve()) or not path.is_file() or path.is_symlink():
        raise ProjectCloseoutError(f"{title} 경로가 허용 영역을 벗어났습니다: {path}")
    return path


def completed_scope(
    package_manifest: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    completed = [
        {
            "key": "digital-twin-drone-control",
            "title": "스마트폰·브라우저 기반 가상 드론 관제",
            "status": "COMPLETED",
        },
        {
            "key": "realtime-fleet-telemetry-map",
            "title": "전체 드론 실시간 텔레메트리·관제 지도",
            "status": "COMPLETED",
        },
        {
            "key": "telemetry-history-replay",
            "title": "MySQL 텔레메트리 이력·과거 경로 재생",
            "status": "COMPLETED",
        },
        {
            "key": "geofence-incident-operations",
            "title": "지오펜스·인시던트·SLA 관제",
            "status": "COMPLETED",
        },
        {
            "key": "vision-ai-pipeline",
            "title": "브라우저 영상 입력·YOLO 추론·탐지 스냅샷",
            "status": "COMPLETED",
        },
        {
            "key": "operator-security",
            "title": "RBAC·브라우저 세션·CSRF·보안 헤더·CSP 관찰",
            "status": "COMPLETED",
        },
        {
            "key": "docker-operations",
            "title": "MySQL·Spring Boot·Next.js·AI 서버 통합 운영",
            "status": "COMPLETED",
        },
        {
            "key": "backup-recovery-release",
            "title": "백업·복구 리허설·릴리스·이관 무결성 체계",
            "status": "COMPLETED",
        },
    ]
    handoff = (
        package_manifest.get("handoff")
        if isinstance(package_manifest, dict)
        else None
    )
    if (
        isinstance(handoff, dict)
        and handoff.get("smartphoneE2eStatus") == "PASS"
    ):
        completed.append(
            {
                "key": "smartphone-real-sensor-e2e",
                "title": "신뢰된 HTTPS 스마트폰 GPS·방향 센서·카메라·AI E2E 검증",
                "status": "COMPLETED",
            }
        )
    return completed


def normalized_deferred(package_manifest: dict[str, Any]) -> list[dict[str, str]]:
    source = package_manifest.get("deferred")
    if not isinstance(source, list):
        raise ProjectCloseoutError("이관 패키지의 보류 항목이 없습니다.")
    reasons = {
        "hp-omen-runtime-restore": "HP OMEN 작업공간 이동 후 Docker·MySQL target 복원 검증",
        "gpu-best-model": "HP OMEN RTX 5060에서 파인튜닝 best.pt 이식·성능 검증",
        "hp-target-smartphone-https-revalidation": (
            "HP OMEN의 새 LAN IP·인증서에서 스마트폰 HTTPS 접속만 재검증"
        ),
        "dji-mini4-pro": "DJI Mini 4 Pro RTSP·기체 종속 연동은 3차 프로젝트 범위",
    }
    aliases = {
        "smartphone-real-sensor-https": (
            "hp-target-smartphone-https-revalidation"
        ),
    }
    result = []
    for item in source:
        if not isinstance(item, dict):
            raise ProjectCloseoutError("이관 패키지 보류 항목이 올바르지 않습니다.")
        source_key = str(item.get("key", ""))
        key = aliases.get(source_key, source_key)
        status = str(item.get("status", ""))
        if key not in reasons or status not in {"DEFERRED", "OUT_OF_SCOPE"}:
            raise ProjectCloseoutError(f"알 수 없는 보류 항목입니다: {source_key}")
        result.append(
            {
                "key": key,
                "status": status,
                "reason": reasons[key],
            }
        )
    return result


def build_report(
    root: Path,
    package_path: Path,
    package_manifest: dict[str, Any],
    *,
    max_package_age_hours: float,
    now: datetime,
) -> dict[str, Any]:
    if package_manifest.get("status") != READY_PACKAGE_STATUS:
        raise ProjectCloseoutError(
            f"최종 이관 패키지가 종결 조건을 충족하지 않습니다: {package_manifest.get('status')}"
        )
    generated = parse_timestamp(package_manifest.get("generatedAt"), "최종 이관 패키지")
    age = now.astimezone(timezone.utc) - generated
    if not timedelta(0) - FUTURE_TOLERANCE <= age <= timedelta(hours=max_package_age_hours):
        raise ProjectCloseoutError(
            f"최종 이관 패키지가 {max_package_age_hours:g}시간 유효 범위를 벗어났습니다: "
            f"{age.total_seconds() / 3600:.2f}시간"
        )
    handoff = package_manifest.get("handoff")
    readiness = package_manifest.get("transferReadiness")
    backup = package_manifest.get("databaseBackup")
    safety = package_manifest.get("safety")
    if not all(isinstance(item, dict) for item in (handoff, readiness, backup, safety)):
        raise ProjectCloseoutError("최종 이관 패키지 핵심 메타데이터가 없습니다.")
    smartphone_e2e_status = handoff.get("smartphoneE2eStatus", "DEFERRED")
    if smartphone_e2e_status not in {"PASS", "DEFERRED"}:
        raise ProjectCloseoutError("최종 이관 패키지 스마트폰 E2E 상태가 올바르지 않습니다.")
    checks = [
        {
            "key": "final-transfer-package",
            "status": "PASS",
            "detail": "최종 이관 패키지 바깥 SHA-256과 내부 전체 파일 무결성 검증",
        },
        {
            "key": "transfer-readiness",
            "status": "PASS",
            "detail": f"최종 전송 준비도: {readiness.get('status')}",
        },
        {
            "key": "release-readiness",
            "status": "PASS",
            "detail": f"2차 프로젝트 릴리스 준비도: {handoff.get('releaseReadinessStatus')}",
        },
        {
            "key": "lg-baseline",
            "status": "PASS",
            "detail": f"LG GRAM 기준 장비 상태: {handoff.get('baselineStatus')}",
        },
        {
            "key": "mysql-backup",
            "status": "PASS",
            "detail": (
                f"MySQL 백업 내부 검증: {backup.get('internalStatus')}, "
                f"{backup.get('fileCount')}개 payload"
            ),
        },
        {
            "key": "secret-separation",
            "status": "PASS",
            "detail": "환경파일·운영자 키·개인키·모델 가중치 분리 확인",
        },
    ]
    if smartphone_e2e_status == "PASS":
        checks.append(
            {
                "key": "smartphone-e2e-evidence",
                "status": "PASS",
                "detail": "스마트폰 실센서 HTTPS E2E PASS 증적이 최종 이관 계보에 포함됨",
            }
        )
    deferred = normalized_deferred(package_manifest)
    completed = completed_scope(package_manifest)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "scope": "SECOND_PROJECT_DIGITAL_TWIN",
        "operation": "PROJECT_CLOSEOUT",
        "closeoutId": str(uuid.uuid4()),
        "generatedAt": now.isoformat(),
        "status": CLOSEOUT_STATUS,
        "decision": {
            "phase": 2,
            "result": "COMPLETED_WITH_DEFERRED_VALIDATION",
            "nextExecutionEnvironment": "HP_OMEN_RTX_5060",
            "thirdProjectBoundaryPreserved": True,
        },
        "sourceArtifact": {
            "path": package_path.relative_to(root).as_posix(),
            "sizeBytes": package_path.stat().st_size,
            "sha256": sha256_file(package_path),
            "packageId": package_manifest.get("packageId"),
            "status": package_manifest.get("status"),
            "ageHours": round(age.total_seconds() / 3600, 3),
        },
        "checks": checks,
        "completedScope": completed,
        "deferred": deferred,
        "safety": {
            "containsDatabaseBackup": False,
            "containsEnvironmentValues": False,
            "containsOperatorKeys": False,
            "containsPrivateKeys": False,
            "containsModelWeights": False,
            "sourceArtifactModified": False,
            "externalTransferPerformed": False,
        },
        "summary": {
            "checks": len(checks),
            "passed": len(checks),
            "completedCapabilities": len(completed),
            "deferred": sum(item["status"] == "DEFERRED" for item in deferred),
            "outOfScope": sum(item["status"] == "OUT_OF_SCOPE" for item in deferred),
            "blocking": 0,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    checks = "\n".join(
        f"- [{item['status']}] {item['detail']}" for item in report["checks"]
    )
    completed = "\n".join(
        f"- {item['title']}" for item in report["completedScope"]
    )
    deferred = "\n".join(
        f"- **{item['status']}** `{item['key']}`: {item['reason']}"
        for item in report["deferred"]
    )
    artifact = report["sourceArtifact"]
    return f"""# VisionFlow-Drone 2차 프로젝트 종결 보고서

## 최종 판정

**{report['status']}**

- 종결 시각: `{report['generatedAt']}`
- 최종 이관 세트: `{artifact['path']}`
- SHA-256: `{artifact['sha256']}`
- HP OMEN 이동 후속 검증은 보류 목록에 따라 별도로 수행

## 완료 검증

{checks}

## 구현 완료 범위

{completed}

## 보류·범위 외 항목

{deferred}

## 보안

이 종결 보고서에는 MySQL 백업 원본, 환경변수 값, 운영자 키, 인증서 개인키, 모델 가중치가
포함되지 않습니다. 실제 최종 이관 ZIP은 민감 데이터로 취급합니다.
"""


def render_html(report: dict[str, Any]) -> str:
    check_rows = "".join(
        "<tr>"
        f"<td>{html.escape(item['key'])}</td>"
        f"<td>{html.escape(item['status'])}</td>"
        f"<td>{html.escape(item['detail'])}</td>"
        "</tr>"
        for item in report["checks"]
    )
    capability_rows = "".join(
        "<tr>"
        f"<td>{html.escape(item['title'])}</td>"
        f"<td>{html.escape(item['status'])}</td>"
        "</tr>"
        for item in report["completedScope"]
    )
    deferred_rows = "".join(
        "<tr>"
        f"<td>{html.escape(item['key'])}</td>"
        f"<td>{html.escape(item['status'])}</td>"
        f"<td>{html.escape(item['reason'])}</td>"
        "</tr>"
        for item in report["deferred"]
    )
    artifact = report["sourceArtifact"]
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VisionFlow-Drone 2차 프로젝트 종결 보고서</title><style>
body {{ margin:0; background:#eef3f8; color:#0f172a; font-family:Arial,'Noto Sans KR',sans-serif; }}
main {{ max-width:1100px; margin:32px auto; padding:0 20px; }}
section {{ background:#fff; border:1px solid #dbe4ee; border-radius:16px; padding:24px; margin:16px 0; }}
h1,h2 {{ margin-top:0; }} .status {{ color:#047857; font-size:1.25rem; font-weight:700; }}
table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:10px; border-bottom:1px solid #e2e8f0; text-align:left; }}
code {{ word-break:break-all; }}
</style></head><body><main>
<section><h1>VisionFlow-Drone 2차 프로젝트 종결 보고서</h1>
<p class="status">{html.escape(report['status'])}</p>
<p>{html.escape(report['generatedAt'])}</p></section>
<section><h2>최종 증빙</h2>
<p>이관 세트: <code>{html.escape(artifact['path'])}</code></p>
<p>SHA-256: <code>{html.escape(artifact['sha256'])}</code></p></section>
<section><h2>완료 검증</h2><table><tr><th>검사</th><th>상태</th><th>내용</th></tr>{check_rows}</table></section>
<section><h2>구현 완료 범위</h2><table><tr><th>기능</th><th>상태</th></tr>{capability_rows}</table></section>
<section><h2>보류·범위 외 항목</h2><table><tr><th>항목</th><th>상태</th><th>사유</th></tr>{deferred_rows}</table></section>
<section><h2>보안</h2><p>이 보고서에는 DB 백업 원본, 환경변수 값, 인증 키, 개인키, 모델 가중치가 포함되지 않습니다.</p></section>
</main></body></html>"""


def write_sidecar(path: Path, files: list[Path]) -> None:
    value = "".join(f"{sha256_file(item)}  {item.name}\n" for item in files)
    write_text_atomic(path, value)


def parse_sidecar(path: Path, expected: list[Path]) -> None:
    if not path.is_file() or path.is_symlink():
        raise ProjectCloseoutError(f"종결 보고서 sidecar를 찾을 수 없습니다: {path}")
    try:
        lines = [
            line.strip().split()
            for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
    except UnicodeDecodeError as error:
        raise ProjectCloseoutError("종결 보고서 sidecar가 UTF-8이 아닙니다.") from error
    expected_names = {item.name for item in expected}
    if len(lines) != len(expected) or any(len(parts) != 2 for parts in lines):
        raise ProjectCloseoutError("종결 보고서 sidecar 형식이 올바르지 않습니다.")
    recorded = {parts[1]: parts[0].lower() for parts in lines}
    if set(recorded) != expected_names:
        raise ProjectCloseoutError("종결 보고서 sidecar 파일 목록이 다릅니다.")
    for item in expected:
        if not is_checksum(recorded[item.name]) or recorded[item.name] != sha256_file(item):
            raise ProjectCloseoutError(f"종결 보고서 SHA-256이 다릅니다: {item.name}")


def create_closeout(
    root: Path,
    package_path: Path,
    *,
    output_root: Path,
    max_package_age_hours: float,
    now: datetime,
) -> tuple[Path, Path, Path, Path, dict[str, Any]]:
    if max_package_age_hours <= 0:
        raise ProjectCloseoutError("최종 이관 패키지 최대 유효시간은 양수여야 합니다.")
    allowed = (root / "artifacts/project-closeout").resolve()
    output = output_root.resolve()
    if not is_within(output, allowed):
        raise ProjectCloseoutError("출력 폴더는 artifacts/project-closeout 내부여야 합니다.")
    try:
        verified_path, package_manifest = verify_transfer_package_file(
            root,
            str(package_path),
        )
    except TransferPackageError as error:
        raise ProjectCloseoutError(str(error)) from error
    report = build_report(
        root,
        verified_path,
        package_manifest,
        max_package_age_hours=max_package_age_hours,
        now=now,
    )
    output.mkdir(parents=True, exist_ok=True)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    base = output / f"visionflow-project-closeout-{timestamp}"
    if any(base.with_suffix(suffix).exists() for suffix in (".json", ".html", ".md")):
        base = output / f"visionflow-project-closeout-{timestamp}-{uuid.uuid4().hex[:8]}"
    json_path = base.with_suffix(".json")
    html_path = base.with_suffix(".html")
    markdown_path = base.with_suffix(".md")
    sidecar = base.with_suffix(".sha256")
    write_text_atomic(
        json_path,
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    write_text_atomic(html_path, render_html(report))
    write_text_atomic(markdown_path, render_markdown(report))
    write_sidecar(sidecar, [json_path, html_path, markdown_path])
    verify_closeout_file(root, str(json_path))
    return json_path, html_path, markdown_path, sidecar, report


def verify_closeout_file(root: Path, value: str) -> tuple[Path, dict[str, Any]]:
    candidate = Path(value)
    json_path = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    allowed = (root / "artifacts/project-closeout").resolve()
    if not is_within(json_path, allowed) or not json_path.is_file() or json_path.is_symlink():
        raise ProjectCloseoutError(f"종결 보고서 경로가 허용 영역을 벗어났습니다: {json_path}")
    html_path = json_path.with_suffix(".html")
    markdown_path = json_path.with_suffix(".md")
    sidecar = json_path.with_suffix(".sha256")
    for path, title in ((html_path, "HTML"), (markdown_path, "Markdown")):
        if not path.is_file() or path.is_symlink():
            raise ProjectCloseoutError(f"종결 보고서 {title} 파일을 찾을 수 없습니다: {path}")
    parse_sidecar(sidecar, [json_path, html_path, markdown_path])
    report = read_json(json_path, "종결 보고서")
    if (
        report.get("schemaVersion") != SCHEMA_VERSION
        or report.get("project") != PROJECT_NAME
        or report.get("scope") != "SECOND_PROJECT_DIGITAL_TWIN"
        or report.get("operation") != "PROJECT_CLOSEOUT"
        or report.get("status") != CLOSEOUT_STATUS
    ):
        raise ProjectCloseoutError("VisionFlow 2차 프로젝트 종결 보고서가 아닙니다.")
    summary = report.get("summary")
    safety = report.get("safety")
    source = report.get("sourceArtifact")
    checks = report.get("checks")
    completed = report.get("completedScope")
    deferred = report.get("deferred")
    if (
        not isinstance(summary, dict)
        or summary.get("blocking") != 0
        or summary.get("checks") != summary.get("passed")
    ):
        raise ProjectCloseoutError("종결 보고서 완료 집계가 올바르지 않습니다.")
    if (
        not isinstance(checks, list)
        or not checks
        or any(
            not isinstance(item, dict) or item.get("status") != "PASS"
            for item in checks
        )
    ):
        raise ProjectCloseoutError("종결 보고서 완료 검사가 올바르지 않습니다.")
    if (
        not isinstance(safety, dict)
        or safety.get("containsDatabaseBackup") is not False
        or safety.get("containsEnvironmentValues") is not False
        or safety.get("containsOperatorKeys") is not False
        or safety.get("containsPrivateKeys") is not False
        or safety.get("containsModelWeights") is not False
        or safety.get("sourceArtifactModified") is not False
        or safety.get("externalTransferPerformed") is not False
    ):
        raise ProjectCloseoutError("종결 보고서 안전 메타데이터가 올바르지 않습니다.")
    if not isinstance(source, dict) or not is_checksum(source.get("sha256")):
        raise ProjectCloseoutError("종결 보고서 원본 이관 패키지 메타데이터가 없습니다.")
    package_path = resolve_input(
        root,
        str(source.get("path")),
        root / "artifacts/transfer-package",
        "visionflow-transfer-package-*.zip",
        "최종 이관 패키지",
    )
    if package_path.stat().st_size != source.get("sizeBytes") or sha256_file(package_path) != source.get("sha256"):
        raise ProjectCloseoutError("종결 보고서와 최종 이관 패키지 동일성이 다릅니다.")
    try:
        _, package_manifest = verify_transfer_package_file(root, str(package_path))
    except TransferPackageError as error:
        raise ProjectCloseoutError(str(error)) from error
    if (
        package_manifest.get("packageId") != source.get("packageId")
        or package_manifest.get("status") != source.get("status")
    ):
        raise ProjectCloseoutError("종결 보고서가 다른 최종 이관 패키지를 참조합니다.")
    expected_completed = completed_scope(package_manifest)
    if completed != expected_completed:
        raise ProjectCloseoutError("종결 보고서 구현 완료 범위가 올바르지 않습니다.")
    expected_deferred = normalized_deferred(package_manifest)
    if deferred != expected_deferred:
        raise ProjectCloseoutError("종결 보고서 보류·범위 외 항목이 이관 패키지와 다릅니다.")
    expected_summary = {
        "checks": len(checks),
        "passed": len(checks),
        "completedCapabilities": len(expected_completed),
        "deferred": sum(
            item["status"] == "DEFERRED" for item in expected_deferred
        ),
        "outOfScope": sum(
            item["status"] == "OUT_OF_SCOPE" for item in expected_deferred
        ),
        "blocking": 0,
    }
    if summary != expected_summary:
        raise ProjectCloseoutError("종결 보고서 집계가 상세 항목과 일치하지 않습니다.")
    try:
        html_value = html_path.read_text(encoding="utf-8-sig")
        markdown_value = markdown_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise ProjectCloseoutError("종결 보고서 HTML 또는 Markdown이 UTF-8이 아닙니다.") from error
    lowered = html_value.lower()
    if any(token in lowered for token in ("<script", "<iframe", "<object", "<embed", "javascript:")):
        raise ProjectCloseoutError("종결 보고서 HTML에 실행 가능한 콘텐츠가 있습니다.")
    if html_value != render_html(report) or markdown_value != render_markdown(report):
        raise ProjectCloseoutError("종결 보고서 JSON·HTML·Markdown 내용이 일치하지 않습니다.")
    return json_path, report


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VisionFlow second-project closeout")
    parser.add_argument("--root", default=str(default_root))
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create", help="2차 프로젝트 종결 보고서 생성")
    create.add_argument("--package")
    create.add_argument("--output", default="artifacts/project-closeout")
    create.add_argument("--max-package-age-hours", type=float, default=24.0)
    verify = subparsers.add_parser("verify", help="기존 종결 보고서 독립 재검증")
    verify.add_argument("--report", required=True)
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    args = build_parser(default_root).parse_args(arguments)
    root = Path(args.root).resolve()
    try:
        if not root.is_dir():
            raise ProjectCloseoutError(f"프로젝트 루트를 찾을 수 없습니다: {root}")
        if args.command == "create":
            package = resolve_input(
                root,
                args.package,
                root / "artifacts/transfer-package",
                "visionflow-transfer-package-*.zip",
                "최종 이관 패키지",
            )
            output_value = Path(args.output)
            output = (
                output_value.resolve()
                if output_value.is_absolute()
                else (root / output_value).resolve()
            )
            json_path, html_path, markdown_path, sidecar, report = create_closeout(
                root,
                package,
                output_root=output,
                max_package_age_hours=args.max_package_age_hours,
                now=datetime.now(timezone.utc),
            )
            print(f"VisionFlow project closeout: {report['status']}")
            print(f"JSON report: {json_path}")
            print(f"HTML report: {html_path}")
            print(f"Markdown report: {markdown_path}")
            print(f"SHA-256: {sidecar}")
        else:
            report_path, report = verify_closeout_file(root, args.report)
            print("VisionFlow project closeout: VERIFIED")
            print(f"Status: {report['status']}")
            print(f"Report: {report_path}")
        return 0
    except (
        ProjectCloseoutError,
        TransferPackageError,
        FileNotFoundError,
        OSError,
    ) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
