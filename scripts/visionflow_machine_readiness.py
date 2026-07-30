"""Capture and compare sanitized VisionFlow machine readiness profiles."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
PROFILE_OPERATION = "MACHINE_READINESS_PROFILE"
MOBILE_EVIDENCE_OPERATION = "SMARTPHONE_E2E_VERIFICATION"
MOBILE_EVIDENCE_MAX_AGE = timedelta(days=30)
REQUIRED_MOBILE_EVIDENCE_CHECKS = frozenset(
    {
        "trusted-https-endpoint",
        "browser-permission-policy",
        "completed-flight-session",
        "mobile-source-identity",
        "telemetry-minimum",
        "mobile-sensor-source",
        "gps-values",
        "orientation-values",
        "ai-events",
        "ai-detections",
    }
)
SERVICE_PORTS = (
    ("frontend", "Next.js", "127.0.0.1", 3000),
    ("backend", "Spring Boot", "127.0.0.1", 8080),
    ("ai-server", "Python AI", "127.0.0.1", 8000),
    ("mysql", "MySQL", "127.0.0.1", 3306),
)
PROJECT_MARKERS = {
    "compose": ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml"),
    "frontend": ("01_frontend/visionflow-web/package.json",),
    "backend": (
        "02_backend/visionflow-api/build.gradle",
        "02_backend/visionflow-api/build.gradle.kts",
    ),
    "ai-server": (
        "03_ai-server/visionflow-ai/requirements.txt",
        "03_ai-server/visionflow-ai/pyproject.toml",
    ),
}
CommandRunner = Callable[[tuple[str, ...], int], dict[str, Any]]
PortProbe = Callable[[str, int, float], bool]


class MachineReadinessError(RuntimeError):
    """Raised when a machine profile or comparison is unsafe or invalid."""


def command_specs(
    platform_name: str | None = None,
    python_executable: str | None = None,
) -> tuple[tuple[str, str, tuple[str, ...], bool], ...]:
    effective_platform = platform_name or os.name
    npm_executable = "npm.cmd" if effective_platform == "nt" else "npm"
    effective_python = python_executable or sys.executable
    return (
        ("git", "Git", ("git", "--version"), True),
        ("docker-cli", "Docker CLI", ("docker", "--version"), True),
        (
            "docker-compose",
            "Docker Compose",
            ("docker", "compose", "version"),
            True,
        ),
        (
            "docker-engine",
            "Docker Engine",
            ("docker", "info", "--format", "{{.ServerVersion}}"),
            True,
        ),
        ("java", "Java", ("java", "-version"), True),
        ("node", "Node.js", ("node", "--version"), True),
        ("npm", "npm", (npm_executable, "--version"), True),
        ("python", "Python", (effective_python, "--version"), True),
        (
            "nvidia-smi",
            "NVIDIA GPU",
            (
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader,nounits",
            ),
            False,
        ),
    )


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


def write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    os.replace(temporary, path)


def decode_output(value: bytes) -> str:
    for encoding in ("utf-8", "cp949"):
        try:
            return value.decode(encoding)
        except UnicodeDecodeError:
            continue
    return value.decode("utf-8", errors="replace")


def normalize_command_output(stdout: bytes, stderr: bytes) -> str:
    output = decode_output(stdout)
    if stderr:
        output += ("\n" if output else "") + decode_output(stderr)
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return " | ".join(lines[:4])[:1000]


def run_command(arguments: tuple[str, ...], timeout_seconds: int) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            list(arguments),
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "status": "PASS" if completed.returncode == 0 else "FAILED",
            "exitCode": completed.returncode,
            "version": normalize_command_output(completed.stdout, completed.stderr),
            "durationMs": round((time.monotonic() - started) * 1000),
        }
    except FileNotFoundError:
        return {
            "status": "MISSING",
            "exitCode": None,
            "version": "",
            "durationMs": round((time.monotonic() - started) * 1000),
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "TIMED_OUT",
            "exitCode": None,
            "version": "",
            "durationMs": round((time.monotonic() - started) * 1000),
        }


def probe_port(host: str, port: int, timeout_seconds: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def parse_sidecar(path: Path, expected_name: str) -> str:
    if not path.is_file() or path.is_symlink():
        raise MachineReadinessError(f"SHA-256 sidecar를 찾을 수 없습니다: {path}")
    parts = path.read_text(encoding="utf-8-sig").strip().split()
    if len(parts) != 2 or parts[1] != expected_name:
        raise MachineReadinessError(f"SHA-256 sidecar 형식이 올바르지 않습니다: {path}")
    checksum = parts[0].lower()
    if len(checksum) != 64 or any(character not in "0123456789abcdef" for character in checksum):
        raise MachineReadinessError(f"SHA-256 값이 올바르지 않습니다: {path}")
    return checksum


def newest_mobile_evidence(root: Path) -> Path | None:
    evidence_root = root / "artifacts/mobile-readiness"
    if not evidence_root.is_dir():
        return None
    candidates = [
        path.resolve()
        for path in evidence_root.glob("visionflow-smartphone-e2e-*.json")
        if path.is_file() and not path.is_symlink()
    ]
    return max(candidates, key=lambda path: path.stat().st_mtime, default=None)


def inspect_mobile_evidence(root: Path, now: datetime) -> dict[str, Any]:
    path = newest_mobile_evidence(root)
    deferred = {
        "key": "smartphone-real-sensor-https",
        "status": "DEFERRED",
        "reason": "스마트폰 실센서·카메라 HTTPS E2E 증거 생성 후 검증",
    }
    if path is None:
        return deferred
    try:
        expected = parse_sidecar(path.with_suffix(".sha256"), path.name)
        actual = sha256_file(path)
        if actual != expected:
            raise MachineReadinessError("스마트폰 증거 SHA-256이 sidecar와 다릅니다.")
        report = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(report, dict):
            raise MachineReadinessError("스마트폰 증거 최상위 값이 객체가 아닙니다.")
        if (
            report.get("schemaVersion") != SCHEMA_VERSION
            or report.get("project") != PROJECT_NAME
            or report.get("operation") != MOBILE_EVIDENCE_OPERATION
        ):
            raise MachineReadinessError("VisionFlow 스마트폰 E2E 증거가 아닙니다.")
        if report.get("status") != "SMARTPHONE_E2E_PASS":
            raise MachineReadinessError("스마트폰 E2E 검증이 PASS가 아닙니다.")
        generated_value = report.get("generatedAt")
        if not isinstance(generated_value, str) or not generated_value:
            raise MachineReadinessError("스마트폰 증거 생성 시각이 없습니다.")
        generated = datetime.fromisoformat(generated_value.replace("Z", "+00:00"))
        if generated.tzinfo is None:
            raise MachineReadinessError("스마트폰 증거 생성 시각에 시간대가 없습니다.")
        age = now.astimezone(timezone.utc) - generated.astimezone(timezone.utc)
        if age < timedelta(minutes=-10) or age > MOBILE_EVIDENCE_MAX_AGE:
            raise MachineReadinessError("스마트폰 E2E 증거가 너무 오래됐거나 미래 시각입니다.")
        checks = report.get("checks")
        if (
            not isinstance(checks, list)
            or not checks
            or any(
                not isinstance(item, dict) or item.get("status") != "PASS"
                for item in checks
            )
        ):
            raise MachineReadinessError("스마트폰 E2E 세부 검증에 미통과 항목이 있습니다.")
        checks_by_key = {
            item.get("key"): item
            for item in checks
            if isinstance(item, dict) and isinstance(item.get("key"), str)
        }
        missing_checks = REQUIRED_MOBILE_EVIDENCE_CHECKS - checks_by_key.keys()
        if missing_checks:
            missing = ", ".join(sorted(missing_checks))
            raise MachineReadinessError(
                f"스마트폰 E2E 필수 검증 항목이 없습니다: {missing}"
            )
        privacy = report.get("privacy")
        if not isinstance(privacy, dict) or any(
            privacy.get(key) is not False
            for key in (
                "exactCoordinatesRecorded",
                "operatorKeyRecorded",
                "sessionTokenRecorded",
                "rawImageRecorded",
                "rawVideoRecorded",
            )
        ):
            raise MachineReadinessError("스마트폰 E2E 증거 개인정보 정책이 올바르지 않습니다.")
        safety = report.get("safety")
        if (
            not isinstance(safety, dict)
            or safety.get("readOnly") is not True
            or safety.get("databaseMutation") is not False
            or safety.get("externalMessagesSent") is not False
        ):
            raise MachineReadinessError("스마트폰 E2E 증거가 읽기 전용 검증이 아닙니다.")
        return {
            "key": "smartphone-real-sensor-https",
            "status": "PASS",
            "reason": "신뢰된 HTTPS에서 GPS·방향 센서·카메라·AI 세션 E2E 검증 완료",
            "evidence": {
                "path": path.relative_to(root).as_posix(),
                "sha256": actual,
                "generatedAt": generated.isoformat(),
                "sessionId": report.get("evidence", {}).get("sessionId")
                if isinstance(report.get("evidence"), dict)
                else None,
            },
        }
    except (MachineReadinessError, OSError, ValueError, json.JSONDecodeError) as error:
        return {
            **deferred,
            "reason": f"스마트폰 E2E 증거 확인 필요: {error}",
        }


def validate_source_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schemaVersion") != SCHEMA_VERSION:
        raise MachineReadinessError("지원하지 않는 소스 manifest 스키마입니다.")
    if manifest.get("project") != PROJECT_NAME:
        raise MachineReadinessError("VisionFlow 소스 manifest가 아닙니다.")
    if manifest.get("operation") != "PORTABLE_SOURCE_RELEASE":
        raise MachineReadinessError("안전 소스 릴리스 manifest가 아닙니다.")
    files = manifest.get("files")
    summary = manifest.get("summary")
    if not isinstance(files, list) or not isinstance(summary, dict):
        raise MachineReadinessError("소스 manifest 파일 목록이 올바르지 않습니다.")
    if summary.get("includedFiles") != len(files):
        raise MachineReadinessError("소스 manifest 파일 개수가 일치하지 않습니다.")


def safe_manifest_path(value: Any) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise MachineReadinessError("소스 manifest 경로가 비어 있습니다.")
    path = PurePosixPath(value)
    if value.startswith(("/", "\\")) or "\\" in value or ".." in path.parts:
        raise MachineReadinessError(f"안전하지 않은 소스 manifest 경로입니다: {value}")
    return path


def verify_extracted_source(root: Path, manifest_path: Path) -> dict[str, Any]:
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8-sig"))
    if not isinstance(manifest, dict):
        raise MachineReadinessError("소스 manifest 최상위 값이 객체가 아닙니다.")
    validate_source_manifest(manifest)
    for entry in manifest["files"]:
        if not isinstance(entry, dict):
            raise MachineReadinessError("소스 manifest 파일 항목이 올바르지 않습니다.")
        relative = safe_manifest_path(entry.get("path"))
        path = root.joinpath(*relative.parts).resolve()
        if not is_within(path, root) or not path.is_file() or path.is_symlink():
            raise MachineReadinessError(f"추출된 소스 파일이 없습니다: {relative}")
        if path.stat().st_size != entry.get("sizeBytes"):
            raise MachineReadinessError(f"추출된 소스 크기가 다릅니다: {relative}")
        if sha256_file(path) != str(entry.get("sha256", "")).lower():
            raise MachineReadinessError(f"추출된 소스 SHA-256이 다릅니다: {relative}")
    return {
        "status": "PASS",
        "mode": "EXTRACTED",
        "manifestPath": "SOURCE_MANIFEST.json",
        "manifestSha256": sha256_bytes(manifest_bytes),
        "fileCount": len(manifest["files"]),
    }


def newest_source_archive(root: Path) -> Path | None:
    archive_root = root / "artifacts/source-release"
    if not archive_root.is_dir():
        return None
    candidates = [
        path.resolve()
        for path in archive_root.glob("visionflow-source-release-*.zip")
        if path.is_file() and not path.is_symlink()
    ]
    return max(candidates, key=lambda path: path.stat().st_mtime, default=None)


def verify_source_archive(root: Path) -> dict[str, Any]:
    extracted_manifest = root / "SOURCE_MANIFEST.json"
    if extracted_manifest.is_file() and not extracted_manifest.is_symlink():
        return verify_extracted_source(root, extracted_manifest)
    archive_path = newest_source_archive(root)
    if archive_path is None:
        raise MachineReadinessError("안전 소스 릴리스 ZIP 또는 SOURCE_MANIFEST.json이 없습니다.")
    sidecar = archive_path.with_suffix(".sha256")
    expected = parse_sidecar(sidecar, archive_path.name)
    actual = sha256_file(archive_path)
    if actual != expected:
        raise MachineReadinessError("안전 소스 릴리스 ZIP SHA-256이 sidecar와 다릅니다.")
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            manifest_name = "VisionFlow-Drone/SOURCE_MANIFEST.json"
            manifest_bytes = archive.read(manifest_name)
            manifest = json.loads(manifest_bytes.decode("utf-8-sig"))
            if not isinstance(manifest, dict):
                raise MachineReadinessError("ZIP 내부 소스 manifest가 객체가 아닙니다.")
            validate_source_manifest(manifest)
            return {
                "status": "PASS",
                "mode": "ARCHIVE",
                "archivePath": archive_path.relative_to(root).as_posix(),
                "archiveSha256": actual,
                "manifestSha256": sha256_bytes(manifest_bytes),
                "fileCount": len(manifest["files"]),
            }
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as error:
        raise MachineReadinessError("안전 소스 릴리스 ZIP 또는 manifest가 손상되었습니다.") from error


def inspect_project_markers(root: Path) -> list[dict[str, Any]]:
    results = []
    for key, alternatives in PROJECT_MARKERS.items():
        matched = next((value for value in alternatives if (root / value).is_file()), None)
        results.append(
            {
                "key": key,
                "status": "PASS" if matched else "MISSING",
                "path": matched,
                "alternatives": list(alternatives),
            }
        )
    return results


def inspect_model(root: Path, value: str | None, required: bool) -> dict[str, Any]:
    if not value:
        return {
            "status": "MISSING" if required else "DEFERRED",
            "required": required,
            "path": None,
            "sizeBytes": None,
            "sha256": None,
        }
    path = Path(value)
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    if not is_within(resolved, root):
        raise MachineReadinessError("모델 파일은 프로젝트 루트 내부 경로여야 합니다.")
    if resolved.suffix.lower() not in {".pt", ".pth", ".onnx", ".engine"}:
        raise MachineReadinessError("지원하지 않는 모델 파일 확장자입니다.")
    if not resolved.is_file() or resolved.is_symlink():
        return {
            "status": "MISSING",
            "required": required,
            "path": resolved.relative_to(root).as_posix(),
            "sizeBytes": None,
            "sha256": None,
        }
    return {
        "status": "PASS",
        "required": required,
        "path": resolved.relative_to(root).as_posix(),
        "sizeBytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def platform_snapshot(root: Path) -> dict[str, Any]:
    usage = shutil.disk_usage(root)
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "disk": {
            "totalBytes": usage.total,
            "freeBytes": usage.free,
            "usedBytes": usage.used,
        },
        "privacy": {
            "hostnameRecorded": False,
            "usernameRecorded": False,
            "environmentValuesRecorded": False,
            "gpuSerialRecorded": False,
        },
    }


def render_profile_html(profile: dict[str, Any]) -> str:
    tool_rows = "".join(
        "<tr>"
        f"<td>{html.escape(item['title'])}</td>"
        f"<td>{html.escape(item['status'])}</td>"
        f"<td>{html.escape(item.get('version') or '-')}</td>"
        "</tr>"
        for item in profile["tools"]
    )
    port_rows = "".join(
        "<tr>"
        f"<td>{html.escape(item['title'])}</td>"
        f"<td>{item['port']}</td>"
        f"<td>{html.escape(item['status'])}</td>"
        "</tr>"
        for item in profile["services"]
    )
    deferred_rows = "".join(
        "<tr>"
        f"<td>{html.escape(item['key'])}</td>"
        f"<td>{html.escape(item['status'])}</td>"
        f"<td>{html.escape(item['reason'])}</td>"
        "</tr>"
        for item in profile["deferred"]
    )
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>VisionFlow 장비 준비도</title><style>
body {{ font-family: Arial, sans-serif; background:#f1f5f9; color:#0f172a; margin:32px; }}
main {{ max-width:1100px; margin:auto; }}
section {{ background:white; padding:22px; border-radius:14px; margin:16px 0; }}
table {{ width:100%; border-collapse:collapse; }}
th,td {{ padding:10px; border-bottom:1px solid #e2e8f0; text-align:left; }}
</style></head><body><main><section><h1>VisionFlow 장비 준비도</h1>
<p><strong>{html.escape(profile['status'])}</strong> · {html.escape(profile['role'])}</p>
<p>{html.escape(profile['generatedAt'])}</p></section>
<section><h2>도구</h2><table><tr><th>도구</th><th>상태</th><th>버전</th></tr>{tool_rows}</table></section>
<section><h2>서비스 포트</h2><table>
<tr><th>서비스</th><th>포트</th><th>상태</th></tr>{port_rows}</table></section>
<section><h2>후속 검증 항목</h2><table>
<tr><th>항목</th><th>상태</th><th>설명</th></tr>{deferred_rows}</table></section>
<section><h2>소스 동일성</h2><pre>
{html.escape(json.dumps(profile['sourceIdentity'], ensure_ascii=False, indent=2))}
</pre></section>
</main></body></html>"""


def create_output_paths(root: Path, output_root: Path, stem: str, now: datetime) -> tuple[Path, Path]:
    allowed = (root / "artifacts/machine-readiness").resolve()
    resolved = output_root.resolve()
    if not is_within(resolved, allowed):
        raise MachineReadinessError("출력 폴더는 artifacts/machine-readiness 내부여야 합니다.")
    resolved.mkdir(parents=True, exist_ok=True)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    json_path = resolved / f"{stem}-{timestamp}.json"
    html_path = resolved / f"{stem}-{timestamp}.html"
    if json_path.exists() or html_path.exists():
        suffix = uuid.uuid4().hex[:8]
        json_path = resolved / f"{stem}-{timestamp}-{suffix}.json"
        html_path = resolved / f"{stem}-{timestamp}-{suffix}.html"
    return json_path, html_path


def capture_profile(
    root: Path,
    *,
    role: str,
    output_root: Path,
    expect_gpu: bool,
    model: str | None,
    expect_model: bool,
    timeout_seconds: int,
    now: datetime,
    runner: CommandRunner = run_command,
    port_checker: PortProbe = probe_port,
) -> tuple[Path, Path, dict[str, Any], int]:
    tools = []
    for key, title, arguments, required_by_default in command_specs():
        required = required_by_default or (key == "nvidia-smi" and expect_gpu)
        result = runner(arguments, timeout_seconds)
        status = result.get("status")
        if key == "nvidia-smi" and not required and status != "PASS":
            status = "DEFERRED"
        tools.append(
            {
                "key": key,
                "title": title,
                "required": required,
                "status": status,
                "version": result.get("version", ""),
                "exitCode": result.get("exitCode"),
                "durationMs": result.get("durationMs"),
            }
        )
    services = [
        {
            "key": key,
            "title": title,
            "host": host,
            "port": port,
            "status": "REACHABLE" if port_checker(host, port, 0.5) else "NOT_REACHABLE",
            "blocking": False,
        }
        for key, title, host, port in SERVICE_PORTS
    ]
    markers = inspect_project_markers(root)
    try:
        source_identity = verify_source_archive(root)
    except MachineReadinessError as error:
        source_identity = {"status": "FAILED", "error": str(error)}
    model_result = inspect_model(root, model, expect_model)
    blocking = [
        item for item in tools if item["required"] and item["status"] != "PASS"
    ]
    blocking.extend(item for item in markers if item["status"] != "PASS")
    if source_identity.get("status") != "PASS":
        blocking.append(source_identity)
    if expect_model and model_result["status"] != "PASS":
        blocking.append(model_result)
    deferred = [
        inspect_mobile_evidence(root, now),
        {
            "key": "gpu-best-model",
            "status": "DEFERRED" if not expect_gpu or not expect_model else "IN_SCOPE",
            "reason": "HP OMEN RTX 5060과 best.pt 이식 후 검증",
        },
        {
            "key": "dji-mini4-pro",
            "status": "OUT_OF_SCOPE",
            "reason": "DJI 전용 연동은 3차 프로젝트 범위",
        },
    ]
    status = "BLOCKED" if blocking else "BASELINE_READY_WITH_DEFERRED"
    if not blocking and expect_gpu and expect_model:
        status = "TARGET_READY"
    profile = {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "operation": PROFILE_OPERATION,
        "profileId": str(uuid.uuid4()),
        "generatedAt": now.isoformat(),
        "role": role,
        "status": status,
        "expectations": {"gpuRequired": expect_gpu, "modelRequired": expect_model},
        "platform": platform_snapshot(root),
        "tools": tools,
        "projectMarkers": markers,
        "services": services,
        "sourceIdentity": source_identity,
        "model": model_result,
        "deferred": deferred,
        "summary": {
            "blocking": len(blocking),
            "unreachableServices": sum(
                item["status"] == "NOT_REACHABLE" for item in services
            ),
            "validatedDeferred": sum(
                item["status"] == "PASS" for item in deferred
            ),
        },
    }
    json_path, html_path = create_output_paths(
        root,
        output_root,
        f"visionflow-machine-{role}",
        now,
    )
    write_json(json_path, profile)
    write_text_atomic(html_path, render_profile_html(profile))
    checksum = sha256_file(json_path)
    write_text_atomic(
        json_path.with_suffix(".sha256"),
        f"{checksum}  {json_path.name}\n",
    )
    return json_path, html_path, profile, 1 if blocking else 0


def read_profile(root: Path, value: str, expected_role: str) -> dict[str, Any]:
    path = Path(value)
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    allowed = (root / "artifacts/machine-readiness").resolve()
    if not is_within(resolved, allowed) or not resolved.is_file() or resolved.is_symlink():
        raise MachineReadinessError(f"장비 프로필 경로가 올바르지 않습니다: {resolved}")
    expected = parse_sidecar(resolved.with_suffix(".sha256"), resolved.name)
    if sha256_file(resolved) != expected:
        raise MachineReadinessError("장비 프로필 SHA-256이 sidecar와 다릅니다.")
    profile = json.loads(resolved.read_text(encoding="utf-8-sig"))
    if not isinstance(profile, dict):
        raise MachineReadinessError("장비 프로필 최상위 값이 객체가 아닙니다.")
    if profile.get("schemaVersion") != SCHEMA_VERSION or profile.get("project") != PROJECT_NAME:
        raise MachineReadinessError("VisionFlow 장비 프로필이 아닙니다.")
    if profile.get("operation") != PROFILE_OPERATION or profile.get("role") != expected_role:
        raise MachineReadinessError(f"{expected_role} 장비 프로필이 아닙니다.")
    return profile


def compare_profiles(
    root: Path,
    baseline: dict[str, Any],
    target: dict[str, Any],
    *,
    output_root: Path,
    now: datetime,
) -> tuple[Path, dict[str, Any], int]:
    baseline_tools = {item["key"]: item for item in baseline.get("tools", [])}
    target_tools = {item["key"]: item for item in target.get("tools", [])}
    comparisons = []
    blocking = []
    warnings = []
    for key, baseline_tool in baseline_tools.items():
        target_tool = target_tools.get(key)
        if target_tool is None:
            item = {"key": key, "status": "MISSING", "detail": "대상 프로필에 도구가 없음"}
            if baseline_tool.get("required"):
                blocking.append(item)
        elif target_tool.get("required") and target_tool.get("status") != "PASS":
            item = {"key": key, "status": "FAILED", "detail": "대상 필수 도구가 준비되지 않음"}
            blocking.append(item)
        elif baseline_tool.get("version") != target_tool.get("version"):
            item = {
                "key": key,
                "status": "VERSION_DIFFERENT",
                "baseline": baseline_tool.get("version"),
                "target": target_tool.get("version"),
            }
            warnings.append(item)
        else:
            item = {"key": key, "status": "MATCH"}
        comparisons.append(item)
    baseline_source = baseline.get("sourceIdentity", {})
    target_source = target.get("sourceIdentity", {})
    source_matches = (
        baseline_source.get("status") == "PASS"
        and target_source.get("status") == "PASS"
        and baseline_source.get("manifestSha256") == target_source.get("manifestSha256")
    )
    source_comparison = {
        "status": "MATCH" if source_matches else "MISMATCH",
        "baselineManifestSha256": baseline_source.get("manifestSha256"),
        "targetManifestSha256": target_source.get("manifestSha256"),
    }
    if not source_matches:
        blocking.append(source_comparison)
    if target.get("status") == "BLOCKED":
        blocking.append({"status": "TARGET_PROFILE_BLOCKED"})
    status = "BLOCKED" if blocking else (
        "COMPATIBLE_WITH_VERSION_DIFFERENCES" if warnings else "COMPATIBLE"
    )
    result = {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "operation": "MACHINE_READINESS_COMPARISON",
        "generatedAt": now.isoformat(),
        "status": status,
        "baselineProfileId": baseline.get("profileId"),
        "targetProfileId": target.get("profileId"),
        "sourceIdentity": source_comparison,
        "tools": comparisons,
        "summary": {"blocking": len(blocking), "warnings": len(warnings)},
    }
    allowed = (root / "artifacts/machine-readiness").resolve()
    resolved = output_root.resolve()
    if not is_within(resolved, allowed):
        raise MachineReadinessError("비교 결과 폴더가 허용 경로를 벗어났습니다.")
    resolved.mkdir(parents=True, exist_ok=True)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    path = resolved / f"visionflow-machine-comparison-{timestamp}.json"
    if path.exists():
        path = resolved / f"visionflow-machine-comparison-{timestamp}-{uuid.uuid4().hex[:8]}.json"
    write_json(path, result)
    return path, result, 1 if blocking else 0


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VisionFlow machine readiness")
    parser.add_argument("--root", default=str(default_root))
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture = subparsers.add_parser("capture")
    capture.add_argument("--role", choices=("baseline", "target"), default="baseline")
    capture.add_argument("--output", default="artifacts/machine-readiness")
    capture.add_argument("--expect-gpu", action="store_true")
    capture.add_argument("--model")
    capture.add_argument("--expect-model", action="store_true")
    capture.add_argument("--timeout-seconds", type=int, default=10)
    compare = subparsers.add_parser("compare")
    compare.add_argument("--baseline", required=True)
    compare.add_argument("--target", required=True)
    compare.add_argument("--output", default="artifacts/machine-readiness")
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    args = build_parser(default_root).parse_args(arguments)
    root = Path(args.root).resolve()
    try:
        if not root.is_dir():
            raise MachineReadinessError(f"프로젝트 루트를 찾을 수 없습니다: {root}")
        if args.command == "capture":
            if args.timeout_seconds <= 0:
                raise MachineReadinessError("명령 제한 시간은 양수여야 합니다.")
            output = Path(args.output)
            output_root = output.resolve() if output.is_absolute() else (root / output).resolve()
            json_path, html_path, profile, exit_code = capture_profile(
                root,
                role=args.role,
                output_root=output_root,
                expect_gpu=args.expect_gpu,
                model=args.model,
                expect_model=args.expect_model,
                timeout_seconds=args.timeout_seconds,
                now=datetime.now(timezone.utc),
            )
            print(f"VisionFlow machine readiness: {profile['status']}")
            print(f"JSON profile: {json_path}")
            print(f"HTML profile: {html_path}")
            return exit_code
        baseline = read_profile(root, args.baseline, "baseline")
        target = read_profile(root, args.target, "target")
        output = Path(args.output)
        output_root = output.resolve() if output.is_absolute() else (root / output).resolve()
        path, result, exit_code = compare_profiles(
            root,
            baseline,
            target,
            output_root=output_root,
            now=datetime.now(timezone.utc),
        )
        print(f"VisionFlow machine comparison: {result['status']}")
        print(f"JSON comparison: {path}")
        return exit_code
    except (MachineReadinessError, FileNotFoundError, OSError, json.JSONDecodeError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
