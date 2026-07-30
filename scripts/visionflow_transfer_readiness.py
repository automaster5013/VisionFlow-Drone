"""Evaluate the final LG-to-HP VisionFlow transfer readiness gate."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import stat
import sys
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
HANDOFF_ROOT = "VisionFlow-Handoff"
READY_BASELINES = {"BASELINE_READY", "BASELINE_READY_WITH_DEFERRED"}
READY_RELEASES = {"READY", "READY_WITH_DEFERRED", "READY_WITH_WARNINGS"}
READY_REHEARSALS = {"COLD_START_READY_WITH_DEFERRED", "COLD_START_READY"}
SMARTPHONE_E2E_STATUSES = {"PASS", "DEFERRED"}
MAX_JSON_BYTES = 5 * 1024 * 1024
FUTURE_TOLERANCE = timedelta(minutes=10)


class TransferReadinessError(RuntimeError):
    """Raised when transfer readiness inputs are unsafe or malformed."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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


def safe_path(value: Any, title: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise TransferReadinessError(f"{title}가 비어 있습니다.")
    path = PurePosixPath(value)
    if value.startswith(("/", "\\")) or "\\" in value or ".." in path.parts:
        raise TransferReadinessError(f"안전하지 않은 {title}입니다: {value}")
    return path


def read_json_bytes(value: bytes, title: str) -> dict[str, Any]:
    if len(value) > MAX_JSON_BYTES:
        raise TransferReadinessError(f"{title} 크기가 허용 범위를 초과했습니다.")
    try:
        result = json.loads(value.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TransferReadinessError(f"{title} JSON 형식이 올바르지 않습니다.") from error
    if not isinstance(result, dict):
        raise TransferReadinessError(f"{title} 최상위 값은 객체여야 합니다.")
    return result


def write_text_atomic(path: Path, value: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding=encoding)
    os.replace(temporary, path)


def write_json(path: Path, value: dict[str, Any]) -> None:
    write_text_atomic(path, json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def parse_sidecar(path: Path, expected_name: str, title: str) -> str:
    if not path.is_file() or path.is_symlink():
        raise TransferReadinessError(f"{title} sidecar를 찾을 수 없습니다: {path}")
    try:
        parts = path.read_text(encoding="utf-8-sig").strip().split()
    except UnicodeDecodeError as error:
        raise TransferReadinessError(f"{title} sidecar가 UTF-8이 아닙니다.") from error
    if len(parts) != 2 or parts[1] != expected_name:
        raise TransferReadinessError(f"{title} sidecar 형식이 올바르지 않습니다.")
    checksum = parts[0].lower()
    if len(checksum) != 64 or any(character not in "0123456789abcdef" for character in checksum):
        raise TransferReadinessError(f"{title} sidecar SHA-256이 올바르지 않습니다.")
    return checksum


def verify_sidecar(path: Path, title: str) -> str:
    expected = parse_sidecar(path.with_suffix(".sha256"), path.name, title)
    actual = sha256_file(path)
    if actual != expected:
        raise TransferReadinessError(f"{title} SHA-256이 sidecar와 다릅니다.")
    return actual


def validate_entry(entry: Any) -> tuple[str, int, str]:
    if not isinstance(entry, dict):
        raise TransferReadinessError("핸드오프 파일 항목이 객체가 아닙니다.")
    path = safe_path(entry.get("archivePath"), "핸드오프 파일 경로").as_posix()
    size = entry.get("sizeBytes")
    checksum = str(entry.get("sha256", "")).lower()
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise TransferReadinessError(f"핸드오프 파일 크기가 올바르지 않습니다: {path}")
    if len(checksum) != 64 or any(character not in "0123456789abcdef" for character in checksum):
        raise TransferReadinessError(f"핸드오프 파일 SHA-256이 올바르지 않습니다: {path}")
    return path, size, checksum


def verify_handoff(path: Path) -> tuple[dict[str, Any], str]:
    checksum = verify_sidecar(path, "마이그레이션 핸드오프 ZIP")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = [item for item in archive.infolist() if not item.is_dir()]
            names = [item.filename for item in infos]
            if len(names) != len(set(names)):
                raise TransferReadinessError("핸드오프 ZIP에 중복 경로가 있습니다.")
            for info in infos:
                safe_path(info.filename, "핸드오프 ZIP 내부 경로")
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise TransferReadinessError(f"핸드오프 ZIP에 심볼릭 링크가 있습니다: {info.filename}")
            manifest_name = f"{HANDOFF_ROOT}/HANDOFF_MANIFEST.json"
            manifest = read_json_bytes(archive.read(manifest_name), "HANDOFF_MANIFEST.json")
            if (
                manifest.get("schemaVersion") != SCHEMA_VERSION
                or manifest.get("project") != PROJECT_NAME
                or manifest.get("operation") != "MIGRATION_HANDOFF"
            ):
                raise TransferReadinessError("VisionFlow 마이그레이션 핸드오프가 아닙니다.")
            files = manifest.get("files")
            if not isinstance(files, list):
                raise TransferReadinessError("핸드오프 파일 목록이 없습니다.")
            expected = {manifest_name}
            for entry in files:
                archive_path, size, item_sha = validate_entry(entry)
                if not archive_path.startswith(f"{HANDOFF_ROOT}/") or archive_path in expected:
                    raise TransferReadinessError(f"핸드오프 파일 경로가 올바르지 않습니다: {archive_path}")
                expected.add(archive_path)
                value = archive.read(archive_path)
                if len(value) != size or sha256_bytes(value) != item_sha:
                    raise TransferReadinessError(f"핸드오프 내부 파일 무결성이 다릅니다: {archive_path}")
            if set(names) != expected:
                raise TransferReadinessError("핸드오프 ZIP 파일 목록이 manifest와 다릅니다.")
            for key in ("source", "evidence", "baseline", "verifiedMySqlBackup"):
                if not isinstance(manifest.get(key), dict):
                    raise TransferReadinessError(f"핸드오프 {key} 정보가 없습니다.")
            return manifest, checksum
    except (zipfile.BadZipFile, KeyError) as error:
        raise TransferReadinessError("핸드오프 ZIP 또는 manifest가 손상되었습니다.") from error


def validate_rehearsal_html(path: Path, status_value: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise TransferReadinessError(f"콜드 스타트 HTML을 찾을 수 없습니다: {path}")
    if path.stat().st_size > 2 * 1024 * 1024:
        raise TransferReadinessError("콜드 스타트 HTML 크기가 허용 범위를 초과했습니다.")
    try:
        value = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise TransferReadinessError("콜드 스타트 HTML이 UTF-8이 아닙니다.") from error
    lowered = value.lower()
    if any(token in lowered for token in ("<script", "<iframe", "<object", "<embed", "javascript:")):
        raise TransferReadinessError("콜드 스타트 HTML에 실행 가능한 콘텐츠가 있습니다.")
    if status_value not in value:
        raise TransferReadinessError("콜드 스타트 JSON과 HTML 상태가 일치하지 않습니다.")


def verify_rehearsal(path: Path) -> tuple[dict[str, Any], str]:
    checksum = verify_sidecar(path, "콜드 스타트 JSON")
    report = read_json_bytes(path.read_bytes(), "콜드 스타트 JSON")
    if (
        report.get("schemaVersion") != SCHEMA_VERSION
        or report.get("project") != PROJECT_NAME
        or report.get("operation") != "COLD_START_REHEARSAL"
    ):
        raise TransferReadinessError("VisionFlow 콜드 스타트 보고서가 아닙니다.")
    if not isinstance(report.get("handoff"), dict) or not isinstance(report.get("source"), dict):
        raise TransferReadinessError("콜드 스타트 교차 검증 정보가 없습니다.")
    if not isinstance(report.get("summary"), dict) or not isinstance(report.get("safety"), dict):
        raise TransferReadinessError("콜드 스타트 요약 또는 안전 정보가 없습니다.")
    validate_rehearsal_html(path.with_suffix(".html"), str(report.get("status", "")))
    return report, checksum


def parse_timestamp(value: Any, title: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise TransferReadinessError(f"{title} 생성 시각이 없습니다.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise TransferReadinessError(f"{title} 생성 시각 형식이 올바르지 않습니다.") from error
    if parsed.tzinfo is None:
        raise TransferReadinessError(f"{title} 생성 시각에 시간대가 없습니다.")
    return parsed.astimezone(timezone.utc)


def check(key: str, passed: bool, detail: str, *, expected: Any = None, actual: Any = None) -> dict[str, Any]:
    return {
        "key": key,
        "status": "PASS" if passed else "BLOCKED",
        "detail": detail,
        "expected": expected,
        "actual": actual,
    }


def evaluate(
    handoff: dict[str, Any],
    handoff_path: Path,
    handoff_sha: str,
    rehearsal: dict[str, Any],
    rehearsal_path: Path,
    rehearsal_sha: str,
    *,
    max_age_hours: float,
    now: datetime,
) -> dict[str, Any]:
    generated = parse_timestamp(rehearsal.get("generatedAt"), "콜드 스타트")
    age = now.astimezone(timezone.utc) - generated
    rehearsal_handoff = rehearsal["handoff"]
    rehearsal_source = rehearsal["source"]
    handoff_source = handoff["source"]
    handoff_evidence = handoff["evidence"]
    handoff_baseline = handoff["baseline"]
    backup = handoff["verifiedMySqlBackup"]
    backup_sha = str(backup.get("sha256", "")).lower()
    safety = rehearsal["safety"]
    checks = [
        check(
            "handoff-identity",
            rehearsal_handoff.get("sha256") == handoff_sha,
            "콜드 스타트가 최신 핸드오프 ZIP을 검증했는지 확인",
            expected=handoff_sha,
            actual=rehearsal_handoff.get("sha256"),
        ),
        check(
            "handoff-path",
            Path(str(rehearsal_handoff.get("path", ""))).name == handoff_path.name,
            "콜드 스타트 보고서의 핸드오프 파일명 확인",
            expected=handoff_path.name,
            actual=Path(str(rehearsal_handoff.get("path", ""))).name,
        ),
        check(
            "source-archive-identity",
            rehearsal_source.get("sha256") == handoff_source.get("sha256"),
            "콜드 스타트와 핸드오프의 안전 소스 ZIP 확인",
            expected=handoff_source.get("sha256"),
            actual=rehearsal_source.get("sha256"),
        ),
        check(
            "source-manifest-identity",
            rehearsal_source.get("manifestSha256") == handoff_source.get("manifestSha256"),
            "콜드 스타트와 핸드오프의 SOURCE_MANIFEST 확인",
            expected=handoff_source.get("manifestSha256"),
            actual=rehearsal_source.get("manifestSha256"),
        ),
        check(
            "cold-start-status",
            rehearsal.get("status") in READY_REHEARSALS and rehearsal["summary"].get("blocking") == 0,
            "콜드 스타트 차단 항목 확인",
            expected=sorted(READY_REHEARSALS),
            actual=rehearsal.get("status"),
        ),
        check(
            "cold-start-age",
            timedelta(0) - FUTURE_TOLERANCE <= age <= timedelta(hours=max_age_hours),
            f"콜드 스타트 보고서가 {max_age_hours:g}시간 이내인지 확인",
            expected=f"0..{max_age_hours:g} hours",
            actual=round(age.total_seconds() / 3600, 3),
        ),
        check(
            "baseline-status",
            handoff_baseline.get("status") in READY_BASELINES,
            "LG baseline 준비 상태 확인",
            expected=sorted(READY_BASELINES),
            actual=handoff_baseline.get("status"),
        ),
        check(
            "release-evidence-status",
            handoff_evidence.get("readinessStatus") in READY_RELEASES,
            "릴리스 증빙 준비 상태 확인",
            expected=sorted(READY_RELEASES),
            actual=handoff_evidence.get("readinessStatus"),
        ),
        check(
            "smartphone-e2e-lineage",
            handoff_evidence.get("smartphoneE2eStatus")
            in SMARTPHONE_E2E_STATUSES,
            "스마트폰 실센서 HTTPS E2E 증적 계보 확인",
            expected=sorted(SMARTPHONE_E2E_STATUSES),
            actual=handoff_evidence.get("smartphoneE2eStatus"),
        ),
        check(
            "mysql-backup-metadata",
            backup.get("included") is False
            and isinstance(backup.get("sizeBytes"), int)
            and not isinstance(backup.get("sizeBytes"), bool)
            and backup.get("sizeBytes") >= 0
            and len(backup_sha) == 64
            and all(character in "0123456789abcdef" for character in backup_sha),
            "MySQL 백업 원본 제외 및 체크섬 메타데이터 확인",
            expected="metadata-only",
            actual=backup.get("included"),
        ),
        check(
            "non-destructive-rehearsal",
            safety.get("databaseMutation") is False
            and safety.get("dockerStarted") is False
            and safety.get("originalHandoffModified") is False,
            "콜드 스타트가 비파괴 방식으로 수행됐는지 확인",
            expected=True,
            actual=safety,
        ),
    ]
    blocking = [item for item in checks if item["status"] == "BLOCKED"]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "scope": "SECOND_PROJECT_DIGITAL_TWIN",
        "operation": "TRANSFER_READINESS_GATE",
        "gateId": str(uuid.uuid4()),
        "generatedAt": now.isoformat(),
        "status": "BLOCKED" if blocking else "TRANSFER_READY_WITH_DEFERRED",
        "handoff": {
            "path": handoff_path.as_posix(),
            "sha256": handoff_sha,
            "sourceSha256": handoff_source.get("sha256"),
            "sourceManifestSha256": handoff_source.get("manifestSha256"),
            "smartphoneE2eStatus": handoff_evidence.get("smartphoneE2eStatus"),
        },
        "coldStart": {
            "path": rehearsal_path.as_posix(),
            "sha256": rehearsal_sha,
            "status": rehearsal.get("status"),
            "generatedAt": rehearsal.get("generatedAt"),
            "ageHours": round(age.total_seconds() / 3600, 3),
        },
        "checks": checks,
        "deferred": [
            {"key": "hp-omen-runtime-restore", "status": "DEFERRED"},
            {"key": "gpu-best-model", "status": "DEFERRED"},
            {
                "key": "hp-target-smartphone-https-revalidation",
                "status": "DEFERRED",
            },
            {"key": "dji-mini4-pro", "status": "OUT_OF_SCOPE"},
        ],
        "safety": {
            "readOnlyInputs": True,
            "databaseMutation": False,
            "dockerStarted": False,
            "externalTransferPerformed": False,
        },
        "summary": {"checks": len(checks), "passed": len(checks) - len(blocking), "blocking": len(blocking)},
    }


def render_html(report: dict[str, Any]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(item['key'])}</td>"
        f"<td>{html.escape(item['status'])}</td>"
        f"<td>{html.escape(item['detail'])}</td>"
        "</tr>"
        for item in report["checks"]
    )
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>VisionFlow 최종 이관 준비도</title><style>
body {{ font-family:Arial,sans-serif; background:#f1f5f9; color:#0f172a; margin:32px; }}
main {{ max-width:1100px; margin:auto; }} section {{ background:white; padding:22px; border-radius:14px; margin:16px 0; }}
table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:10px; border-bottom:1px solid #e2e8f0; text-align:left; }}
</style></head><body><main><section><h1>VisionFlow 최종 이관 준비도</h1>
<p><strong>{html.escape(report['status'])}</strong></p><p>{html.escape(report['generatedAt'])}</p></section>
<section><h2>Go/No-Go 검사</h2><table><tr><th>검사</th><th>상태</th><th>내용</th></tr>{rows}</table></section>
<section><h2>보류 항목</h2><pre>{html.escape(json.dumps(report['deferred'], ensure_ascii=False, indent=2))}</pre></section>
</main></body></html>"""


def newest_file(directory: Path, pattern: str, title: str) -> Path:
    if not directory.is_dir():
        raise TransferReadinessError(f"{title} 폴더가 없습니다: {directory}")
    candidates = [item.resolve() for item in directory.glob(pattern) if item.is_file() and not item.is_symlink()]
    if not candidates:
        raise TransferReadinessError(f"{title} 파일이 없습니다.")
    return max(candidates, key=lambda item: (item.stat().st_mtime_ns, item.name))


def resolve_input(root: Path, value: str | None, allowed: Path, pattern: str, title: str) -> Path:
    if value:
        candidate = Path(value)
        path = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    else:
        path = newest_file(allowed, pattern, title)
    if not is_within(path, allowed.resolve()) or not path.is_file() or path.is_symlink():
        raise TransferReadinessError(f"{title} 경로가 허용 영역을 벗어났습니다: {path}")
    return path


def run_gate(
    root: Path,
    handoff_path: Path,
    rehearsal_path: Path,
    *,
    output_root: Path,
    max_age_hours: float,
    now: datetime,
) -> tuple[Path, Path, Path, dict[str, Any], int]:
    if max_age_hours <= 0:
        raise TransferReadinessError("최대 보고서 유효 시간은 양수여야 합니다.")
    allowed = (root / "artifacts/transfer-readiness").resolve()
    output = output_root.resolve()
    if not is_within(output, allowed):
        raise TransferReadinessError("출력 폴더는 artifacts/transfer-readiness 내부여야 합니다.")
    handoff, handoff_sha = verify_handoff(handoff_path)
    rehearsal, rehearsal_sha = verify_rehearsal(rehearsal_path)
    report = evaluate(
        handoff,
        handoff_path.relative_to(root),
        handoff_sha,
        rehearsal,
        rehearsal_path.relative_to(root),
        rehearsal_sha,
        max_age_hours=max_age_hours,
        now=now,
    )
    output.mkdir(parents=True, exist_ok=True)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    json_path = output / f"visionflow-transfer-readiness-{timestamp}.json"
    html_path = output / f"visionflow-transfer-readiness-{timestamp}.html"
    if json_path.exists() or html_path.exists():
        suffix = uuid.uuid4().hex[:8]
        json_path = output / f"visionflow-transfer-readiness-{timestamp}-{suffix}.json"
        html_path = output / f"visionflow-transfer-readiness-{timestamp}-{suffix}.html"
    write_json(json_path, report)
    write_text_atomic(html_path, render_html(report))
    sidecar = json_path.with_suffix(".sha256")
    write_text_atomic(sidecar, f"{sha256_file(json_path)}  {json_path.name}\n")
    return json_path, html_path, sidecar, report, 1 if report["status"] == "BLOCKED" else 0


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VisionFlow final transfer readiness gate")
    parser.add_argument("--root", default=str(default_root))
    parser.add_argument("--handoff")
    parser.add_argument("--cold-start")
    parser.add_argument("--output", default="artifacts/transfer-readiness")
    parser.add_argument("--max-age-hours", type=float, default=24.0)
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    args = build_parser(default_root).parse_args(arguments)
    root = Path(args.root).resolve()
    try:
        if not root.is_dir():
            raise TransferReadinessError(f"프로젝트 루트를 찾을 수 없습니다: {root}")
        handoff = resolve_input(
            root,
            args.handoff,
            root / "artifacts/migration-handoff",
            "visionflow-migration-handoff-*.zip",
            "마이그레이션 핸드오프",
        )
        cold_start = resolve_input(
            root,
            args.cold_start,
            root / "artifacts/cold-start-rehearsal",
            "visionflow-cold-start-rehearsal-*.json",
            "콜드 스타트 보고서",
        )
        output_value = Path(args.output)
        output = output_value.resolve() if output_value.is_absolute() else (root / output_value).resolve()
        json_path, html_path, sidecar, report, exit_code = run_gate(
            root,
            handoff,
            cold_start,
            output_root=output,
            max_age_hours=args.max_age_hours,
            now=datetime.now(timezone.utc),
        )
        print(f"VisionFlow transfer readiness: {report['status']}")
        print(f"JSON report: {json_path}")
        print(f"HTML report: {html_path}")
        print(f"SHA-256: {sidecar}")
        return exit_code
    except (TransferReadinessError, FileNotFoundError, OSError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
