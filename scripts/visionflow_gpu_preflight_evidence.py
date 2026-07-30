"""Create and independently verify VisionFlow GPU preflight evidence."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
OPERATION = "GPU_MODEL_PREFLIGHT"
READY_STATUS = "GPU_MODEL_READY"


class GpuPreflightEvidenceError(RuntimeError):
    """Raised when GPU preflight evidence is incomplete or inconsistent."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_checksum(value: object) -> bool:
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


def resolve_inside(root: Path, value: str | Path, title: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if not is_within(resolved, root.resolve()):
        raise GpuPreflightEvidenceError(
            f"{title} 경로가 프로젝트 밖에 있습니다: {candidate}"
        )
    return resolved


def extract_json_object(raw_output: str) -> dict[str, Any]:
    """Extract the last JSON object from mixed Docker Compose output."""

    decoder = json.JSONDecoder()
    candidates: list[dict[str, Any]] = []
    for index, character in enumerate(raw_output):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(raw_output[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            candidates.append(value)

    if not candidates:
        raise GpuPreflightEvidenceError(
            "컨테이너 GPU 사전점검 출력에서 JSON 객체를 찾을 수 없습니다."
        )
    preflight_results = [
        value
        for value in candidates
        if "success" in value and (
            "status" in value
            or "message" in value
        )
    ]
    if not preflight_results:
        raise GpuPreflightEvidenceError(
            "컨테이너 출력에서 GPU 사전점검 결과 JSON을 찾을 수 없습니다."
        )
    return preflight_results[-1]


def normalized_nonempty_lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


def validate_container_result(
    result: Mapping[str, Any],
    *,
    expected_sha256: str,
    expected_size: int,
) -> dict[str, Any]:
    if result.get("success") is not True or result.get("status") != READY_STATUS:
        message = str(result.get("message", "GPU 사전점검이 실패했습니다."))
        raise GpuPreflightEvidenceError(message)

    model = result.get("model")
    if not isinstance(model, Mapping):
        raise GpuPreflightEvidenceError(
            "컨테이너 GPU 사전점검 결과에 모델 상태가 없습니다."
        )

    if (
        model.get("localFile") is not True
        or model.get("cudaAvailable") is not True
        or model.get("requireCuda") is not True
        or not str(model.get("deviceEffective", "")).startswith("cuda:")
    ):
        raise GpuPreflightEvidenceError(
            "컨테이너가 로컬 모델을 CUDA 필수 모드로 적재하지 못했습니다."
        )

    model_sha256 = str(model.get("sha256", "")).strip().lower()
    if not is_checksum(model_sha256) or model_sha256 != expected_sha256:
        raise GpuPreflightEvidenceError(
            "호스트와 컨테이너의 모델 SHA-256이 다릅니다."
        )

    if model.get("sizeBytes") != expected_size:
        raise GpuPreflightEvidenceError(
            "호스트와 컨테이너의 모델 파일 크기가 다릅니다."
        )

    return dict(model)


def filtered_model_status(model: Mapping[str, Any]) -> dict[str, Any]:
    """Keep useful runtime metadata without recording container paths."""

    keys = (
        "profile",
        "sizeBytes",
        "sha256",
        "classCount",
        "confidence",
        "iou",
        "imageSize",
        "deviceRequested",
        "deviceEffective",
        "requireCuda",
        "torchVersion",
        "torchCudaVersion",
        "cudnnVersion",
        "cudaAvailable",
        "cudaDeviceCount",
        "cudaDeviceIndex",
        "cudaDeviceName",
        "cudaCapability",
        "cudaTotalMemoryBytes",
    )
    return {key: model.get(key) for key in keys}


def render_html(report: Mapping[str, Any]) -> str:
    model = report["model"]
    runtime = report["runtime"]
    checks = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['title']))}</td>"
        f"<td>{html.escape(str(item['status']))}</td>"
        f"<td>{html.escape(str(item['detail']))}</td>"
        "</tr>"
        for item in report["checks"]
    )
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VisionFlow GPU 사전점검</title><style>
body{{margin:0;background:#eef3f8;color:#0f172a;font-family:Arial,'Noto Sans KR',sans-serif}}
main{{max-width:980px;margin:32px auto;padding:0 20px}}
section{{background:#fff;border:1px solid #dbe4ee;border-radius:16px;padding:24px;margin:16px 0}}
h1{{margin-top:0}}.ready{{color:#047857;font-weight:800}}
table{{width:100%;border-collapse:collapse}}
th,td{{padding:10px;border-bottom:1px solid #e2e8f0;text-align:left}}
code{{word-break:break-all}}
</style></head><body><main>
<section><h1>VisionFlow GPU·모델 사전점검</h1>
<p class="ready">{html.escape(str(report['status']))}</p>
<p>{html.escape(str(report['generatedAt']))}</p></section>
<section><h2>모델 동일성</h2>
<p>파일: <strong>{html.escape(str(model['fileName']))}</strong></p>
<p>크기: {html.escape(str(model['sizeBytes']))} bytes</p>
<p>SHA-256: <code>{html.escape(str(model['sha256']))}</code></p></section>
<section><h2>CUDA 런타임</h2>
<p>GPU: {html.escape(str(runtime.get('cudaDeviceName') or '-'))}</p>
<p>장치: {html.escape(str(runtime.get('deviceEffective') or '-'))}</p>
<p>PyTorch: {html.escape(str(runtime.get('torchVersion') or '-'))} /
CUDA {html.escape(str(runtime.get('torchCudaVersion') or '-'))}</p></section>
<section><h2>검증 항목</h2><table>
<tr><th>항목</th><th>상태</th><th>내용</th></tr>{checks}</table></section>
<section><h2>개인정보·비밀정보 보호</h2>
<p>모델 내용, 운영자 키, 환경변수 값, GPU 일련번호는 기록하지
않습니다.</p></section>
</main></body></html>"""


def write_evidence(
    *,
    root: Path,
    model_path: Path,
    expected_sha256: str,
    gpu_info: str,
    docker_info: str,
    container_output: str,
    output_directory: Path,
    now: datetime | None = None,
) -> tuple[Path, Path, Path, dict[str, Any]]:
    root = root.resolve()
    model_path = resolve_inside(root, model_path, "모델")
    output_directory = resolve_inside(root, output_directory, "증적 출력")

    if not model_path.is_file() or model_path.is_symlink():
        raise GpuPreflightEvidenceError(
            f"일반 모델 파일을 찾을 수 없습니다: {model_path.name}"
        )

    host_sha256 = sha256_file(model_path)
    normalized_expected = expected_sha256.strip().lower()
    if not is_checksum(normalized_expected) or normalized_expected != host_sha256:
        raise GpuPreflightEvidenceError(
            "PowerShell에서 전달한 모델 SHA-256과 실제 파일이 다릅니다."
        )

    gpu_lines = normalized_nonempty_lines(gpu_info)
    docker_lines = normalized_nonempty_lines(docker_info)
    if not gpu_lines:
        raise GpuPreflightEvidenceError("NVIDIA GPU 조회 결과가 비어 있습니다.")
    if not docker_lines:
        raise GpuPreflightEvidenceError(
            "Docker 서버 버전 조회 결과가 비어 있습니다."
        )

    container_result = extract_json_object(container_output)
    model_status = validate_container_result(
        container_result,
        expected_sha256=host_sha256,
        expected_size=model_path.stat().st_size,
    )
    runtime = filtered_model_status(model_status)

    generated_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    timestamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
    run_directory = output_directory / f"gpu-preflight-{timestamp}"
    if run_directory.exists():
        run_directory = output_directory / (
            f"gpu-preflight-{timestamp}-{uuid.uuid4().hex[:8]}"
        )
    run_directory.mkdir(parents=True, exist_ok=False)

    checks = [
        {
            "key": "nvidia-driver",
            "title": "NVIDIA 드라이버",
            "status": "PASS",
            "detail": gpu_lines[0],
        },
        {
            "key": "docker-engine",
            "title": "Docker Engine",
            "status": "PASS",
            "detail": docker_lines[-1],
        },
        {
            "key": "cuda-tensor",
            "title": "CUDA 텐서 연산",
            "status": "PASS",
            "detail": f"{runtime.get('deviceEffective')} 실제 할당·동기화 완료",
        },
        {
            "key": "model-load",
            "title": "YOLO 모델 CUDA 적재",
            "status": "PASS",
            "detail": f"{model_path.name} CUDA 적재 완료",
        },
        {
            "key": "model-identity",
            "title": "호스트·컨테이너 모델 동일성",
            "status": "PASS",
            "detail": "파일 크기와 SHA-256 일치",
        },
    ]
    report: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "operation": OPERATION,
        "generatedAt": generated_at.isoformat(),
        "status": READY_STATUS,
        "model": {
            "fileName": model_path.name,
            "sizeBytes": model_path.stat().st_size,
            "sha256": host_sha256,
            "profile": runtime.get("profile"),
        },
        "runtime": runtime,
        "host": {
            "nvidiaSmi": gpu_lines,
            "dockerServerVersion": docker_lines[-1],
        },
        "checks": checks,
        "summary": {
            "total": len(checks),
            "passed": len(checks),
            "failed": 0,
        },
        "safety": {
            "modelContentRecorded": False,
            "modelAbsolutePathRecorded": False,
            "operatorKeysRecorded": False,
            "environmentValuesRecorded": False,
            "gpuSerialRecorded": False,
            "databaseMutation": False,
        },
    }

    json_path = run_directory / "visionflow-gpu-preflight.json"
    html_path = run_directory / "visionflow-gpu-preflight.html"
    sidecar_path = run_directory / "visionflow-gpu-preflight.sha256"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    html_path.write_text(render_html(report), encoding="utf-8")
    sidecar_path.write_text(
        (
            f"{sha256_file(json_path)}  {json_path.name}\n"
            f"{sha256_file(html_path)}  {html_path.name}\n"
        ),
        encoding="utf-8",
    )
    return json_path, html_path, sidecar_path, report


def read_report(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GpuPreflightEvidenceError(
            "GPU 사전점검 JSON을 읽을 수 없습니다."
        ) from error
    if not isinstance(value, dict):
        raise GpuPreflightEvidenceError(
            "GPU 사전점검 JSON 최상위 값이 객체가 아닙니다."
        )
    return value


def verify_evidence(
    *,
    root: Path,
    report_path: Path,
) -> tuple[Path, dict[str, Any]]:
    root = root.resolve()
    report_path = resolve_inside(root, report_path, "GPU 사전점검 보고서")
    html_path = report_path.with_suffix(".html")
    sidecar_path = report_path.with_suffix(".sha256")
    for path in (report_path, html_path, sidecar_path):
        if not path.is_file() or path.is_symlink():
            raise GpuPreflightEvidenceError(
                f"GPU 사전점검 증적 파일을 찾을 수 없습니다: {path.name}"
            )

    recorded: dict[str, str] = {}
    for line in sidecar_path.read_text(encoding="utf-8-sig").splitlines():
        parts = line.strip().split()
        if len(parts) != 2 or not is_checksum(parts[0]):
            raise GpuPreflightEvidenceError(
                "GPU 사전점검 SHA-256 형식이 잘못되었습니다."
            )
        recorded[parts[1]] = parts[0].lower()
    if set(recorded) != {report_path.name, html_path.name}:
        raise GpuPreflightEvidenceError("GPU 사전점검 SHA-256 파일 목록이 다릅니다.")
    for path in (report_path, html_path):
        if recorded[path.name] != sha256_file(path):
            raise GpuPreflightEvidenceError(
                f"GPU 사전점검 증적 SHA-256이 다릅니다: {path.name}"
            )

    report = read_report(report_path)
    checks = report.get("checks")
    summary = report.get("summary")
    safety = report.get("safety")
    model = report.get("model")
    runtime = report.get("runtime")
    if (
        report.get("schemaVersion") != SCHEMA_VERSION
        or report.get("project") != PROJECT_NAME
        or report.get("operation") != OPERATION
        or report.get("status") != READY_STATUS
    ):
        raise GpuPreflightEvidenceError("GPU_MODEL_READY 증적이 아닙니다.")
    if (
        not isinstance(checks, list)
        or not checks
        or any(
            not isinstance(item, dict) or item.get("status") != "PASS"
            for item in checks
        )
        or summary
        != {"total": len(checks), "passed": len(checks), "failed": 0}
    ):
        raise GpuPreflightEvidenceError(
            "GPU 사전점검 항목 집계가 올바르지 않습니다."
        )
    if (
        not isinstance(model, dict)
        or not is_checksum(model.get("sha256"))
        or not isinstance(runtime, dict)
        or runtime.get("cudaAvailable") is not True
        or runtime.get("requireCuda") is not True
        or not str(runtime.get("deviceEffective", "")).startswith("cuda:")
    ):
        raise GpuPreflightEvidenceError("GPU 모델 런타임 증적이 올바르지 않습니다.")
    model_name = model.get("fileName")
    if (
        not isinstance(model_name, str)
        or not model_name
        or Path(model_name).name != model_name
    ):
        raise GpuPreflightEvidenceError(
            "GPU 증적의 모델 파일명이 올바르지 않습니다."
        )
    current_model = (
        root
        / "03_ai-server"
        / "visionflow-ai"
        / "models"
        / model_name
    )
    if (
        not current_model.is_file()
        or current_model.is_symlink()
        or current_model.stat().st_size != model.get("sizeBytes")
        or sha256_file(current_model) != model.get("sha256")
    ):
        raise GpuPreflightEvidenceError(
            "현재 모델 파일이 GPU 사전점검 증적과 다릅니다."
        )
    if (
        not isinstance(safety, dict)
        or any(
            safety.get(key) is not False
            for key in (
                "modelContentRecorded",
                "modelAbsolutePathRecorded",
                "operatorKeysRecorded",
                "environmentValuesRecorded",
                "gpuSerialRecorded",
                "databaseMutation",
            )
        )
    ):
        raise GpuPreflightEvidenceError(
            "GPU 사전점검 안전 메타데이터가 올바르지 않습니다."
        )
    return report_path, report


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Create or verify VisionFlow GPU preflight evidence."
    )
    subparsers = value.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build")
    build.add_argument("--root", required=True)
    build.add_argument("--model", required=True)
    build.add_argument("--expected-sha256", required=True)
    build.add_argument("--gpu-info", required=True)
    build.add_argument("--docker-info", required=True)
    build.add_argument("--container-output", required=True)
    build.add_argument(
        "--output-directory",
        default="artifacts/gpu-readiness",
    )

    verify = subparsers.add_parser("verify")
    verify.add_argument("--root", required=True)
    verify.add_argument("--report", required=True)
    return value


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    root = Path(arguments.root)
    try:
        if arguments.command == "build":
            json_path, html_path, sidecar_path, report = write_evidence(
                root=root,
                model_path=Path(arguments.model),
                expected_sha256=arguments.expected_sha256,
                gpu_info=Path(arguments.gpu_info).read_text(
                    encoding="utf-8-sig"
                ),
                docker_info=Path(arguments.docker_info).read_text(
                    encoding="utf-8-sig"
                ),
                container_output=Path(arguments.container_output).read_text(
                    encoding="utf-8-sig"
                ),
                output_directory=Path(arguments.output_directory),
            )
            print(f"VisionFlow GPU evidence: {report['status']}")
            print(f"JSON report: {json_path}")
            print(f"HTML report: {html_path}")
            print(f"SHA-256   : {sidecar_path}")
            return 0

        report_path, report = verify_evidence(
            root=root,
            report_path=Path(arguments.report),
        )
        print("VisionFlow GPU evidence: VERIFIED")
        print(f"Status: {report['status']}")
        print(f"Report: {report_path}")
        return 0
    except (GpuPreflightEvidenceError, OSError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
