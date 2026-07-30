"""Run a non-destructive VisionFlow cold-start restore rehearsal."""

from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import os
import shutil
import stat
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
HANDOFF_ROOT = "VisionFlow-Handoff"
SOURCE_ROOT = "VisionFlow-Drone"
SOURCE_MANIFEST_PATH = f"{SOURCE_ROOT}/SOURCE_MANIFEST.json"
MAX_JSON_BYTES = 5 * 1024 * 1024
REQUIRED_MARKERS: dict[str, tuple[str, ...]] = {
    "compose": ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml"),
    "frontend-package": ("01_frontend/visionflow-web/package.json",),
    "frontend-lock": ("01_frontend/visionflow-web/package-lock.json",),
    "backend-build": (
        "02_backend/visionflow-api/build.gradle",
        "02_backend/visionflow-api/build.gradle.kts",
    ),
    "backend-wrapper": ("02_backend/visionflow-api/gradlew.bat",),
    "backend-wrapper-properties": (
        "02_backend/visionflow-api/gradle/wrapper/gradle-wrapper.properties",
    ),
    "backend-wrapper-jar": (
        "02_backend/visionflow-api/gradle/wrapper/gradle-wrapper.jar",
    ),
    "ai-dependencies": (
        "03_ai-server/visionflow-ai/requirements.txt",
        "03_ai-server/visionflow-ai/pyproject.toml",
    ),
    "acceptance-runner": ("scripts/run-visionflow-acceptance.bat",),
    "source-release-runner": ("scripts/run-visionflow-source-release.bat",),
    "machine-profile-runner": ("scripts/run-visionflow-machine-profile.bat",),
    "handoff-runner": ("scripts/run-visionflow-migration-handoff.bat",),
}
MODEL_SUFFIXES = {".pt", ".pth", ".onnx", ".engine"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif"}
VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv", ".webm"}


class RehearsalError(RuntimeError):
    """Raised when a cold-start rehearsal input is unsafe or incomplete."""


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
        raise RehearsalError(f"{title}가 비어 있습니다.")
    path = PurePosixPath(value)
    if value.startswith(("/", "\\")) or "\\" in value or ".." in path.parts:
        raise RehearsalError(f"안전하지 않은 {title}입니다: {value}")
    return path


def read_json_bytes(value: bytes, title: str) -> dict[str, Any]:
    if len(value) > MAX_JSON_BYTES:
        raise RehearsalError(f"{title} 크기가 허용 범위를 초과했습니다.")
    try:
        result = json.loads(value.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RehearsalError(f"{title} JSON 형식이 올바르지 않습니다.") from error
    if not isinstance(result, dict):
        raise RehearsalError(f"{title} 최상위 값은 객체여야 합니다.")
    return result


def write_text_atomic(path: Path, value: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding=encoding)
    os.replace(temporary, path)


def write_json(path: Path, value: dict[str, Any]) -> None:
    write_text_atomic(path, json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def parse_sidecar(path: Path, expected_name: str) -> str:
    if not path.is_file() or path.is_symlink():
        raise RehearsalError(f"SHA-256 sidecar를 찾을 수 없습니다: {path}")
    try:
        parts = path.read_text(encoding="utf-8-sig").strip().split()
    except UnicodeDecodeError as error:
        raise RehearsalError("핸드오프 sidecar가 UTF-8이 아닙니다.") from error
    if len(parts) != 2 or parts[1] != expected_name:
        raise RehearsalError("핸드오프 sidecar 형식이 올바르지 않습니다.")
    checksum = parts[0].lower()
    if len(checksum) != 64 or any(character not in "0123456789abcdef" for character in checksum):
        raise RehearsalError("핸드오프 sidecar SHA-256이 올바르지 않습니다.")
    return checksum


def safe_zip_infos(archive: zipfile.ZipFile, title: str) -> dict[str, zipfile.ZipInfo]:
    infos = [info for info in archive.infolist() if not info.is_dir()]
    names = [info.filename for info in infos]
    if len(names) != len(set(names)):
        raise RehearsalError(f"{title}에 중복 경로가 있습니다.")
    result: dict[str, zipfile.ZipInfo] = {}
    for info in infos:
        safe_path(info.filename, f"{title} 내부 경로")
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise RehearsalError(f"{title}에 심볼릭 링크가 있습니다: {info.filename}")
        result[info.filename] = info
    return result


def validate_manifest_entry(entry: Any, title: str) -> tuple[str, int, str]:
    if not isinstance(entry, dict):
        raise RehearsalError(f"{title} 파일 항목이 객체가 아닙니다.")
    path = safe_path(entry.get("archivePath") or entry.get("path"), title).as_posix()
    size = entry.get("sizeBytes")
    checksum = str(entry.get("sha256", "")).lower()
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise RehearsalError(f"{title} 파일 크기가 올바르지 않습니다: {path}")
    if len(checksum) != 64 or any(character not in "0123456789abcdef" for character in checksum):
        raise RehearsalError(f"{title} SHA-256이 올바르지 않습니다: {path}")
    return path, size, checksum


def verify_handoff(path: Path) -> tuple[dict[str, Any], bytes, str]:
    sidecar = path.with_suffix(".sha256")
    expected = parse_sidecar(sidecar, path.name)
    actual = sha256_file(path)
    if actual != expected:
        raise RehearsalError("핸드오프 ZIP SHA-256이 sidecar와 다릅니다.")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = safe_zip_infos(archive, "핸드오프 ZIP")
            manifest_name = f"{HANDOFF_ROOT}/HANDOFF_MANIFEST.json"
            manifest = read_json_bytes(archive.read(manifest_name), "핸드오프 manifest")
            if (
                manifest.get("schemaVersion") != SCHEMA_VERSION
                or manifest.get("project") != PROJECT_NAME
                or manifest.get("operation") != "MIGRATION_HANDOFF"
            ):
                raise RehearsalError("VisionFlow 마이그레이션 핸드오프가 아닙니다.")
            files = manifest.get("files")
            if not isinstance(files, list):
                raise RehearsalError("핸드오프 manifest 파일 목록이 없습니다.")
            expected_names = {manifest_name}
            for entry in files:
                archive_path, size, checksum = validate_manifest_entry(entry, "핸드오프 manifest")
                if not archive_path.startswith(f"{HANDOFF_ROOT}/") or archive_path in expected_names:
                    raise RehearsalError(f"핸드오프 manifest 경로가 올바르지 않습니다: {archive_path}")
                expected_names.add(archive_path)
                value = archive.read(archive_path)
                if len(value) != size or sha256_bytes(value) != checksum:
                    raise RehearsalError(f"핸드오프 내부 파일 무결성이 다릅니다: {archive_path}")
            if set(infos) != expected_names:
                raise RehearsalError("핸드오프 ZIP 파일 목록이 manifest와 다릅니다.")
            source = manifest.get("source")
            if not isinstance(source, dict):
                raise RehearsalError("핸드오프 소스 정보가 없습니다.")
            source_path = safe_path(source.get("archivePath"), "핸드오프 소스 경로").as_posix()
            if source_path not in infos:
                raise RehearsalError("핸드오프에 안전 소스 ZIP이 없습니다.")
            source_bytes = archive.read(source_path)
            if sha256_bytes(source_bytes) != source.get("sha256"):
                raise RehearsalError("핸드오프 소스 SHA-256 메타데이터가 다릅니다.")
            return manifest, source_bytes, actual
    except (zipfile.BadZipFile, KeyError) as error:
        raise RehearsalError("핸드오프 ZIP 또는 내부 manifest가 손상되었습니다.") from error


def validate_source_archive(value: bytes) -> tuple[dict[str, Any], dict[str, bytes], str]:
    try:
        with zipfile.ZipFile(io.BytesIO(value), "r") as archive:
            infos = safe_zip_infos(archive, "안전 소스 ZIP")
            manifest_bytes = archive.read(SOURCE_MANIFEST_PATH)
            manifest = read_json_bytes(manifest_bytes, "SOURCE_MANIFEST.json")
            if (
                manifest.get("schemaVersion") != SCHEMA_VERSION
                or manifest.get("project") != PROJECT_NAME
                or manifest.get("operation") != "PORTABLE_SOURCE_RELEASE"
            ):
                raise RehearsalError("VisionFlow 안전 소스 릴리스가 아닙니다.")
            files = manifest.get("files")
            summary = manifest.get("summary")
            if not isinstance(files, list) or not isinstance(summary, dict):
                raise RehearsalError("SOURCE_MANIFEST.json 파일 목록이 올바르지 않습니다.")
            if summary.get("includedFiles") != len(files):
                raise RehearsalError("SOURCE_MANIFEST.json 파일 개수가 일치하지 않습니다.")
            expected = {SOURCE_MANIFEST_PATH, f"{SOURCE_ROOT}/README-MIGRATION.md"}
            extracted: dict[str, bytes] = {
                "SOURCE_MANIFEST.json": manifest_bytes,
                "README-MIGRATION.md": archive.read(f"{SOURCE_ROOT}/README-MIGRATION.md"),
            }
            seen: set[str] = set()
            for entry in files:
                relative, size, checksum = validate_manifest_entry(entry, "소스 manifest")
                if relative in seen:
                    raise RehearsalError(f"소스 manifest에 중복 파일이 있습니다: {relative}")
                seen.add(relative)
                archive_path = f"{SOURCE_ROOT}/{relative}"
                expected.add(archive_path)
                data = archive.read(archive_path)
                if len(data) != size or sha256_bytes(data) != checksum:
                    raise RehearsalError(f"소스 ZIP 내부 파일 무결성이 다릅니다: {relative}")
                extracted[relative] = data
            if set(infos) != expected:
                raise RehearsalError("소스 ZIP 파일 목록이 SOURCE_MANIFEST.json과 다릅니다.")
            return manifest, extracted, sha256_bytes(manifest_bytes)
    except (zipfile.BadZipFile, KeyError) as error:
        raise RehearsalError("안전 소스 ZIP 또는 SOURCE_MANIFEST.json이 손상되었습니다.") from error


def check_forbidden_source(files: dict[str, bytes]) -> list[dict[str, str]]:
    findings = []
    for value, data in files.items():
        path = PurePosixPath(value)
        name = path.name.lower()
        suffix = path.suffix.lower()
        forbidden = None
        environment_template = name.endswith((".example", ".sample", ".template"))
        if name == ".env" or (name.startswith(".env.") and not environment_template):
            forbidden = "runtime environment file"
        elif suffix in MODEL_SUFFIXES:
            forbidden = "AI model weight"
        elif suffix in VIDEO_SUFFIXES:
            forbidden = "runtime video"
        elif suffix in IMAGE_SUFFIXES and not (
            value.lower().startswith("01_frontend/visionflow-web/public/")
            and len(data) <= 2 * 1024 * 1024
        ):
            forbidden = "runtime image"
        elif "backup" in (part.lower() for part in path.parts) and suffix in {".zip", ".sql"}:
            forbidden = "database backup"
        if forbidden:
            findings.append({"path": value, "reason": forbidden})
    return findings


def inspect_markers(workspace: Path) -> list[dict[str, Any]]:
    results = []
    for key, alternatives in REQUIRED_MARKERS.items():
        found = next((item for item in alternatives if (workspace / item).is_file()), None)
        results.append(
            {
                "key": key,
                "status": "PASS" if found else "MISSING",
                "path": found,
                "alternatives": list(alternatives),
            }
        )
    return results


def extract_verified_files(files: dict[str, bytes], workspace: Path) -> None:
    for relative, value in files.items():
        safe = safe_path(relative, "추출 경로")
        target = workspace.joinpath(*safe.parts).resolve()
        if not is_within(target, workspace.resolve()):
            raise RehearsalError(f"추출 경로가 격리 작업공간을 벗어났습니다: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)


def render_html(report: dict[str, Any]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(item['key'])}</td>"
        f"<td>{html.escape(item['status'])}</td>"
        f"<td>{html.escape(item.get('path') or '-')}</td>"
        "</tr>"
        for item in report["markers"]
    )
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>VisionFlow 콜드 스타트 복원 리허설</title><style>
body {{ font-family:Arial,sans-serif; background:#f1f5f9; color:#0f172a; margin:32px; }}
main {{ max-width:1050px; margin:auto; }} section {{ background:white; padding:22px; border-radius:14px; margin:16px 0; }}
table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:10px; border-bottom:1px solid #e2e8f0; text-align:left; }}
</style></head><body><main><section><h1>VisionFlow 콜드 스타트 복원 리허설</h1>
<p><strong>{html.escape(report['status'])}</strong></p><p>{html.escape(report['generatedAt'])}</p></section>
<section><h2>재구축 필수 파일</h2><table><tr><th>항목</th><th>상태</th><th>경로</th></tr>{rows}</table></section>
<section><h2>안전성</h2><pre>{html.escape(json.dumps(report['safety'], ensure_ascii=False, indent=2))}</pre></section>
</main></body></html>"""


def resolve_handoff(root: Path, value: str | None) -> Path:
    allowed = (root / "artifacts/migration-handoff").resolve()
    if value:
        candidate = Path(value)
        path = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    else:
        if not allowed.is_dir():
            raise RehearsalError("마이그레이션 핸드오프 폴더가 없습니다.")
        candidates = [
            item.resolve()
            for item in allowed.glob("visionflow-migration-handoff-*.zip")
            if item.is_file() and not item.is_symlink()
        ]
        if not candidates:
            raise RehearsalError("마이그레이션 핸드오프 ZIP이 없습니다.")
        path = max(candidates, key=lambda item: (item.stat().st_mtime_ns, item.name))
    if not is_within(path, allowed) or not path.is_file() or path.is_symlink():
        raise RehearsalError(f"핸드오프 ZIP 경로가 허용 영역을 벗어났습니다: {path}")
    return path


def run_rehearsal(
    root: Path,
    handoff_path: Path,
    *,
    output_root: Path,
    keep_workspace: bool,
    now: datetime,
) -> tuple[Path, Path, Path, dict[str, Any], int]:
    allowed = (root / "artifacts/cold-start-rehearsal").resolve()
    output = output_root.resolve()
    if not is_within(output, allowed):
        raise RehearsalError("출력 폴더는 artifacts/cold-start-rehearsal 내부여야 합니다.")
    output.mkdir(parents=True, exist_ok=True)
    handoff_before = sha256_file(handoff_path)
    manifest, source_bytes, handoff_sha = verify_handoff(handoff_path)
    source_manifest, source_files, source_manifest_sha = validate_source_archive(source_bytes)
    source_info = manifest["source"]
    if source_manifest_sha != source_info.get("manifestSha256"):
        raise RehearsalError("핸드오프와 안전 소스의 manifest SHA-256이 다릅니다.")
    forbidden = check_forbidden_source(source_files)
    if forbidden:
        raise RehearsalError(f"안전 소스에 런타임 또는 대용량 파일이 포함됐습니다: {forbidden[0]['path']}")

    run_id = uuid.uuid4().hex
    isolated = output / f".rehearsal-{run_id}"
    workspace = isolated / "workspace"
    workspace.mkdir(parents=True)
    retained_path: Path | None = None
    try:
        extract_verified_files(source_files, workspace)
        markers = inspect_markers(workspace)
        blocking = [item for item in markers if item["status"] != "PASS"]
        status_value = "BLOCKED" if blocking else "COLD_START_READY_WITH_DEFERRED"
        if sha256_file(handoff_path) != handoff_before:
            raise RehearsalError("리허설 중 원본 핸드오프 ZIP이 변경됐습니다.")
        if keep_workspace:
            retained_path = output / f"workspace-{now.strftime('%Y%m%dT%H%M%SZ')}-{run_id[:8]}"
            os.replace(workspace, retained_path)
        report = {
            "schemaVersion": SCHEMA_VERSION,
            "project": PROJECT_NAME,
            "operation": "COLD_START_REHEARSAL",
            "rehearsalId": str(uuid.uuid4()),
            "generatedAt": now.isoformat(),
            "status": status_value,
            "handoff": {
                "path": handoff_path.relative_to(root).as_posix(),
                "sha256": handoff_sha,
                "operation": manifest["operation"],
            },
            "source": {
                "sha256": source_info["sha256"],
                "manifestSha256": source_manifest_sha,
                "fileCount": len(source_manifest["files"]),
            },
            "markers": markers,
            "workspace": {
                "isolated": True,
                "retained": keep_workspace,
                "path": retained_path.relative_to(root).as_posix() if retained_path else None,
            },
            "safety": {
                "networkRequired": False,
                "dockerStarted": False,
                "databaseMutation": False,
                "originalHandoffModified": False,
                "runtimeSecretsIncluded": False,
                "modelWeightsIncluded": False,
                "runtimeMediaIncluded": False,
            },
            "deferred": [
                {"key": "runtime-build-and-service-start", "status": "DEFERRED", "reason": "HP OMEN 대상 환경에서 실행"},
                {"key": "mysql-restore", "status": "DEFERRED", "reason": "검증 백업 원본을 별도 이관한 뒤 실행"},
                {
                    "key": "hp-target-smartphone-https-revalidation",
                    "status": "DEFERRED",
                },
                {"key": "gpu-best-model", "status": "DEFERRED"},
                {"key": "dji-mini4-pro", "status": "OUT_OF_SCOPE"},
            ],
            "summary": {"blocking": len(blocking), "markers": len(markers)},
        }
        timestamp = now.strftime("%Y%m%dT%H%M%SZ")
        json_path = output / f"visionflow-cold-start-rehearsal-{timestamp}.json"
        html_path = output / f"visionflow-cold-start-rehearsal-{timestamp}.html"
        if json_path.exists() or html_path.exists():
            suffix = uuid.uuid4().hex[:8]
            json_path = output / f"visionflow-cold-start-rehearsal-{timestamp}-{suffix}.json"
            html_path = output / f"visionflow-cold-start-rehearsal-{timestamp}-{suffix}.html"
        write_json(json_path, report)
        write_text_atomic(html_path, render_html(report))
        sidecar = json_path.with_suffix(".sha256")
        write_text_atomic(sidecar, f"{sha256_file(json_path)}  {json_path.name}\n")
        return json_path, html_path, sidecar, report, 1 if blocking else 0
    finally:
        shutil.rmtree(isolated, ignore_errors=True)


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VisionFlow cold-start restore rehearsal")
    parser.add_argument("--root", default=str(default_root))
    parser.add_argument("--handoff")
    parser.add_argument("--output", default="artifacts/cold-start-rehearsal")
    parser.add_argument("--keep-workspace", action="store_true")
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    args = build_parser(default_root).parse_args(arguments)
    root = Path(args.root).resolve()
    try:
        if not root.is_dir():
            raise RehearsalError(f"프로젝트 루트를 찾을 수 없습니다: {root}")
        handoff = resolve_handoff(root, args.handoff)
        output_value = Path(args.output)
        output = output_value.resolve() if output_value.is_absolute() else (root / output_value).resolve()
        json_path, html_path, sidecar, report, exit_code = run_rehearsal(
            root,
            handoff,
            output_root=output,
            keep_workspace=args.keep_workspace,
            now=datetime.now(timezone.utc),
        )
        print(f"VisionFlow cold-start rehearsal: {report['status']}")
        print(f"JSON report: {json_path}")
        print(f"HTML report: {html_path}")
        print(f"SHA-256: {sidecar}")
        return exit_code
    except (RehearsalError, FileNotFoundError, OSError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
