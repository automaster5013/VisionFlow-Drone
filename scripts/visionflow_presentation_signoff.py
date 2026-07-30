"""Create and independently verify a safe VisionFlow presentation sign-off."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

try:
    from visionflow_presentation_gate import (
        READY_STATUS as GATE_READY_STATUS,
        REPORT_ROOT as GATE_ROOT,
        PresentationGateError,
        verify_gate_report,
    )
    from visionflow_presentation_performance import (
        READY_STATUS as PERFORMANCE_READY_STATUS,
        REPORT_ROOT as PERFORMANCE_ROOT,
        PresentationPerformanceError,
        verify_performance_report,
    )
    from visionflow_presentation_quick_check import (
        READY_STATUS as QUICK_CHECK_READY_STATUS,
        REPORT_ROOT as QUICK_CHECK_ROOT,
        PresentationQuickCheckError,
        verify_quick_check_report,
    )
    from visionflow_presentation_rehearsal import (
        READY_STATUS as REHEARSAL_READY_STATUS,
        REPORT_ROOT as REHEARSAL_ROOT,
        PresentationRehearsalError,
        relative_path,
        verify_rehearsal_report,
    )
except ModuleNotFoundError:  # pragma: no cover - package import during tests
    from scripts.visionflow_presentation_gate import (
        READY_STATUS as GATE_READY_STATUS,
        REPORT_ROOT as GATE_ROOT,
        PresentationGateError,
        verify_gate_report,
    )
    from scripts.visionflow_presentation_performance import (
        READY_STATUS as PERFORMANCE_READY_STATUS,
        REPORT_ROOT as PERFORMANCE_ROOT,
        PresentationPerformanceError,
        verify_performance_report,
    )
    from scripts.visionflow_presentation_quick_check import (
        READY_STATUS as QUICK_CHECK_READY_STATUS,
        REPORT_ROOT as QUICK_CHECK_ROOT,
        PresentationQuickCheckError,
        verify_quick_check_report,
    )
    from scripts.visionflow_presentation_rehearsal import (
        READY_STATUS as REHEARSAL_READY_STATUS,
        REPORT_ROOT as REHEARSAL_ROOT,
        PresentationRehearsalError,
        relative_path,
        verify_rehearsal_report,
    )


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
SCOPE = "SECOND_PROJECT_DIGITAL_TWIN"
OPERATION = "PRESENTATION_FINAL_SIGNOFF"
BUNDLE_OPERATION = "PRESENTATION_FINAL_SIGNOFF_BUNDLE"
READY_STATUS = "PRESENTATION_SIGNOFF_READY_WITH_DEFERRED"
REPORT_ROOT = Path("artifacts/presentation-signoff")
REPORT_NAME = "visionflow-presentation-signoff.json"
HTML_NAME = "visionflow-presentation-signoff.html"
BUNDLE_NAME = "visionflow-presentation-signoff.zip"
SIDECAR_NAME = "visionflow-presentation-signoff.sha256"
MANIFEST_NAME = "bundle-manifest.json"
MAX_JSON_BYTES = 5 * 1024 * 1024
MAX_BUNDLE_ENTRY_BYTES = 8 * 1024 * 1024
MAX_BUNDLE_TOTAL_BYTES = 64 * 1024 * 1024
STAGE_POLICIES = {
    "presentation-gate": (
        "PRESENTATION_DAY_SIGNOFF",
        GATE_READY_STATUS,
    ),
    "presentation-rehearsal": (
        "PRESENTATION_STABILITY_REHEARSAL",
        REHEARSAL_READY_STATUS,
    ),
    "presentation-performance": (
        "PRESENTATION_PERFORMANCE_ANALYSIS",
        PERFORMANCE_READY_STATUS,
    ),
    "presentation-quick-check": (
        "PRESENTATION_QUICK_CHECK",
        QUICK_CHECK_READY_STATUS,
    ),
}
FORBIDDEN_BUNDLE_SUFFIXES = {
    ".pt",
    ".env",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".mp4",
    ".sql",
    ".dump",
}


class PresentationSignoffError(RuntimeError):
    """Raised when final presentation sign-off evidence cannot be trusted."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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


def sanitize_error(error: Exception, root: Path) -> str:
    value = str(error)
    for candidate in {
        str(root.resolve()),
        str(root.resolve()).replace("\\", "/"),
        str(root.resolve()).replace("/", "\\"),
    }:
        value = value.replace(candidate, "<PROJECT_ROOT>")
    return value


def read_json(path: Path, title: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise PresentationSignoffError(
            f"{title} 파일을 찾을 수 없습니다."
        )
    if path.stat().st_size > MAX_JSON_BYTES:
        raise PresentationSignoffError(
            f"{title} JSON 크기가 너무 큽니다."
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PresentationSignoffError(
            f"{title} JSON 형식이 올바르지 않습니다."
        ) from error
    if not isinstance(value, dict):
        raise PresentationSignoffError(
            f"{title} JSON 최상위 값은 객체여야 합니다."
        )
    return value


def read_json_bytes(value: bytes, title: str) -> dict[str, Any]:
    if len(value) > MAX_JSON_BYTES:
        raise PresentationSignoffError(
            f"{title} JSON 크기가 너무 큽니다."
        )
    try:
        result = json.loads(value.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PresentationSignoffError(
            f"{title} JSON 형식이 올바르지 않습니다."
        ) from error
    if not isinstance(result, dict):
        raise PresentationSignoffError(
            f"{title} JSON 최상위 값은 객체여야 합니다."
        )
    return result


def artifact_entry(root: Path, path: Path) -> dict[str, Any]:
    return {
        "path": relative_path(root, path),
        "fileName": path.name,
        "sizeBytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def newest_quick_check(root: Path, value: str | None) -> Path:
    allowed = (root / QUICK_CHECK_ROOT).resolve()
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
            for item in allowed.glob(
                "visionflow-presentation-quick-check-*.json"
            )
            if item.is_file() and not item.is_symlink()
        ] if allowed.is_dir() else []
        if not candidates:
            raise PresentationSignoffError(
                "발표 퀵체크 JSON이 없습니다."
            )
        path = max(
            candidates,
            key=lambda item: (item.stat().st_mtime_ns, item.name),
        )
    if (
        not is_within(path, allowed)
        or not path.is_file()
        or path.is_symlink()
        or path.suffix.lower() != ".json"
    ):
        raise PresentationSignoffError(
            "발표 퀵체크 보고서 경로가 올바르지 않습니다."
        )
    return path


def linked_artifact(
    root: Path,
    value: Any,
    *,
    directory: Path,
    title: str,
) -> Path:
    if not isinstance(value, Mapping):
        raise PresentationSignoffError(f"{title} 연결 정보가 없습니다.")
    relative = value.get("path")
    if not isinstance(relative, str):
        raise PresentationSignoffError(f"{title} 상대경로가 없습니다.")
    allowed = (root / directory).resolve()
    path = (root / relative).resolve()
    if (
        not is_within(path, allowed)
        or not path.is_file()
        or path.is_symlink()
        or value.get("fileName") != path.name
        or value.get("sizeBytes") != path.stat().st_size
        or value.get("sha256") != sha256_file(path)
    ):
        raise PresentationSignoffError(f"{title} 파일 동일성이 다릅니다.")
    return path


def verify_chain(
    *,
    root: Path,
    quick_check_path: Path,
) -> dict[str, Any]:
    try:
        quick_check_path, quick_check = verify_quick_check_report(
            root,
            relative_path(root, quick_check_path),
        )
    except PresentationQuickCheckError as error:
        raise PresentationSignoffError(str(error)) from error
    if quick_check.get("status") != QUICK_CHECK_READY_STATUS:
        raise PresentationSignoffError(
            f"발표 퀵체크가 READY가 아닙니다: {quick_check.get('status')}"
        )
    performance_path = linked_artifact(
        root,
        quick_check.get("sourcePerformance"),
        directory=PERFORMANCE_ROOT,
        title="발표 성능",
    )
    try:
        performance_path, performance = verify_performance_report(
            root,
            relative_path(root, performance_path),
        )
    except PresentationPerformanceError as error:
        raise PresentationSignoffError(str(error)) from error
    if performance.get("status") != PERFORMANCE_READY_STATUS:
        raise PresentationSignoffError(
            f"발표 성능 판정이 READY가 아닙니다: {performance.get('status')}"
        )
    rehearsal_path = linked_artifact(
        root,
        performance.get("sourceRehearsal"),
        directory=REHEARSAL_ROOT,
        title="발표 리허설",
    )
    try:
        rehearsal_path, rehearsal = verify_rehearsal_report(
            root,
            relative_path(root, rehearsal_path),
        )
    except PresentationRehearsalError as error:
        raise PresentationSignoffError(str(error)) from error
    if rehearsal.get("status") != REHEARSAL_READY_STATUS:
        raise PresentationSignoffError(
            f"발표 리허설이 READY가 아닙니다: {rehearsal.get('status')}"
        )
    gate_path = linked_artifact(
        root,
        rehearsal.get("sourcePresentationGate"),
        directory=GATE_ROOT,
        title="발표 운영 게이트",
    )
    try:
        gate_path, gate = verify_gate_report(
            root,
            relative_path(root, gate_path),
        )
    except PresentationGateError as error:
        raise PresentationSignoffError(str(error)) from error
    if gate.get("status") != GATE_READY_STATUS:
        raise PresentationSignoffError(
            f"발표 운영 게이트가 READY가 아닙니다: {gate.get('status')}"
        )
    if (
        quick_check.get("sourcePerformanceAnalysisId")
        != str(performance.get("analysisId"))
        or performance.get("sourceRehearsalId")
        != str(rehearsal.get("rehearsalId"))
    ):
        raise PresentationSignoffError(
            "퀵체크·성능·리허설 식별자 연결이 다릅니다."
        )
    return {
        "gatePath": gate_path,
        "gate": gate,
        "rehearsalPath": rehearsal_path,
        "rehearsal": rehearsal,
        "performancePath": performance_path,
        "performance": performance,
        "quickCheckPath": quick_check_path,
        "quickCheck": quick_check,
    }


def build_report(
    *,
    root: Path,
    chain: Mapping[str, Any],
    now: datetime,
    signoff_id: str | None = None,
) -> dict[str, Any]:
    gate = chain["gate"]
    rehearsal = chain["rehearsal"]
    performance = chain["performance"]
    quick_check = chain["quickCheck"]
    deferred = [
        {
            "key": str(item.get("key")),
            "status": str(item.get("status")),
            "scope": str(item.get("scope")),
            "reason": str(item.get("reason")),
        }
        for item in quick_check.get("deferred", [])
        if isinstance(item, Mapping)
    ]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "scope": SCOPE,
        "operation": OPERATION,
        "signoffId": signoff_id or str(uuid.uuid4()),
        "generatedAt": now.astimezone(timezone.utc).isoformat(),
        "status": READY_STATUS,
        "inputs": [
            {
                "key": "presentation-gate",
                **artifact_entry(root, chain["gatePath"]),
            },
            {
                "key": "presentation-rehearsal",
                **artifact_entry(root, chain["rehearsalPath"]),
            },
            {
                "key": "presentation-performance",
                **artifact_entry(root, chain["performancePath"]),
            },
            {
                "key": "presentation-quick-check",
                **artifact_entry(root, chain["quickCheckPath"]),
            },
        ],
        "presentation": {
            "gateStatus": str(gate.get("status")),
            "rehearsalPassedRuns": rehearsal["summary"]["passedRuns"],
            "rehearsalRequestedRuns": rehearsal["summary"]["requestedRuns"],
            "performanceStatus": str(performance.get("status")),
            "bottleneck": str(
                performance["analysis"]["bottleneck"]["name"]
            ),
            "runBudgetUsagePercent": performance["analysis"][
                "runTiming"
            ]["budgetUsagePercent"],
            "watchStageCount": performance["analysis"]["summary"][
                "watchStageCount"
            ],
            "quickCheckPassed": quick_check["summary"]["passed"],
            "quickCheckTotal": quick_check["summary"]["total"],
            "diagnosisCode": str(quick_check["diagnosis"]["code"]),
        },
        "deferred": deferred,
        "summary": {
            "approved": True,
            "blocking": 0,
            "verifiedStages": 4,
            "deferred": sum(
                item["status"] == "DEFERRED" for item in deferred
            ),
            "outOfScope": sum(
                item["status"] == "OUT_OF_SCOPE" for item in deferred
            ),
        },
        "safety": {
            "readOnly": True,
            "databaseMutation": False,
            "serviceMutation": False,
            "modelWeightsIncluded": False,
            "databaseBackupIncluded": False,
            "sourceVideoIncluded": False,
            "environmentFilesIncluded": False,
            "operatorKeysIncluded": False,
            "privateKeysIncluded": False,
            "absolutePathsRecorded": False,
            "gpuValidationExecuted": False,
            "smartphoneSensorValidationExecuted": False,
            "djiIntegrationExecuted": False,
        },
    }


def render_html(report: Mapping[str, Any]) -> str:
    presentation = report["presentation"]
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['key']))}</td>"
        f"<td><code>{html.escape(str(item['path']))}</code></td>"
        f"<td><code>{html.escape(str(item['sha256']))}</code></td>"
        "</tr>"
        for item in report["inputs"]
    )
    deferred_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['key']))}</td>"
        f"<td>{html.escape(str(item['status']))}</td>"
        f"<td>{html.escape(str(item['reason']))}</td>"
        "</tr>"
        for item in report["deferred"]
    )
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VisionFlow 발표 최종 사인오프</title><style>
body{{margin:0;background:#eef3f8;color:#0f172a;font-family:Arial,'Noto Sans KR',sans-serif}}
main{{max-width:1100px;margin:32px auto;padding:0 20px}}
section{{background:#fff;border:1px solid #dbe4ee;border-radius:16px;padding:24px;margin:16px 0}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid #e2e8f0;text-align:left;vertical-align:top}}
.ready{{color:#047857;font-weight:800}}code{{word-break:break-all}}
</style></head><body><main>
<section><h1>VisionFlow 발표 최종 사인오프</h1>
<p class="ready">{html.escape(str(report['status']))}</p>
<p>리허설 {presentation['rehearsalPassedRuns']}/{presentation['rehearsalRequestedRuns']} ·
퀵체크 {presentation['quickCheckPassed']}/{presentation['quickCheckTotal']} ·
진단 {html.escape(str(presentation['diagnosisCode']))}</p>
<p>병목 {html.escape(str(presentation['bottleneck']))} ·
전체 예산 사용률 {presentation['runBudgetUsagePercent']}% ·
주의 단계 {presentation['watchStageCount']}개</p></section>
<section><h2>검증 입력</h2><table><thead><tr><th>단계</th><th>경로</th><th>SHA-256</th></tr></thead>
<tbody>{rows}</tbody></table></section>
<section><h2>보류·범위 외</h2><table><thead><tr><th>항목</th><th>상태</th><th>사유</th></tr></thead>
<tbody>{deferred_rows}</tbody></table></section>
</main></body></html>
"""


def normalize_newlines(value: str) -> str:
    """Return text with platform-specific line endings normalized to LF."""
    return value.replace("\r\n", "\n").replace("\r", "\n")


def evidence_files(chain: Mapping[str, Any]) -> dict[str, Path]:
    result = {}
    for key, path_key in (
        ("presentation-gate", "gatePath"),
        ("presentation-rehearsal", "rehearsalPath"),
        ("presentation-performance", "performancePath"),
        ("presentation-quick-check", "quickCheckPath"),
    ):
        json_path = Path(chain[path_key])
        result[f"evidence/{key}.json"] = json_path
        result[f"evidence/{key}.html"] = json_path.with_suffix(".html")
        result[f"evidence/{key}.sha256"] = json_path.with_suffix(".sha256")
    for path in result.values():
        if not path.is_file() or path.is_symlink():
            raise PresentationSignoffError(
                f"발표 사인오프 원본 증적 파일이 없습니다: {path.name}"
            )
    return result


def build_bundle_entries(
    *,
    report_path: Path,
    html_path: Path,
    chain: Mapping[str, Any],
    report: Mapping[str, Any],
) -> dict[str, bytes]:
    entries = {
        f"signoff/{REPORT_NAME}": report_path.read_bytes(),
        f"signoff/{HTML_NAME}": html_path.read_bytes(),
    }
    for name, path in evidence_files(chain).items():
        entries[name] = path.read_bytes()
    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "operation": BUNDLE_OPERATION,
        "generatedAt": report.get("generatedAt"),
        "status": report.get("status"),
        "files": [
            {
                "path": name,
                "sizeBytes": len(content),
                "sha256": sha256_bytes(content),
            }
            for name, content in sorted(entries.items())
        ],
        "safety": {
            "modelWeightsIncluded": False,
            "databaseBackupIncluded": False,
            "sourceVideoIncluded": False,
            "environmentFilesIncluded": False,
            "operatorKeysIncluded": False,
            "privateKeysIncluded": False,
        },
    }
    entries[MANIFEST_NAME] = (
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    return entries


def write_zip(path: Path, entries: Mapping[str, bytes]) -> None:
    with zipfile.ZipFile(
        path,
        mode="x",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for name, content in sorted(entries.items()):
            archive.writestr(name, content)


def write_sidecar(path: Path, files: Iterable[Path]) -> None:
    path.write_text(
        "".join(
            f"{sha256_file(item)}  {item.name}\n"
            for item in files
        ),
        encoding="utf-8",
    )


def validate_output_root(root: Path, output: Path) -> None:
    if output.resolve() != (root / REPORT_ROOT).resolve() or output.is_symlink():
        raise PresentationSignoffError(
            "발표 사인오프 출력 폴더는 "
            "artifacts/presentation-signoff여야 합니다."
        )


def write_signoff(
    *,
    root: Path,
    output_root: Path,
    report: dict[str, Any],
    chain: Mapping[str, Any],
    now: datetime,
) -> tuple[Path, Path, Path, Path]:
    validate_output_root(root, output_root)
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_directory = output_root / f"signoff-{stamp}"
    if run_directory.exists():
        run_directory = output_root / (
            f"signoff-{stamp}-{uuid.uuid4().hex[:8]}"
        )
    run_directory.mkdir(parents=True, exist_ok=False)
    report_path = run_directory / REPORT_NAME
    html_path = run_directory / HTML_NAME
    bundle_path = run_directory / BUNDLE_NAME
    sidecar_path = run_directory / SIDECAR_NAME
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    html_path.write_text(
        render_html(report),
        encoding="utf-8",
        newline="\n",
    )
    write_zip(
        bundle_path,
        build_bundle_entries(
            report_path=report_path,
            html_path=html_path,
            chain=chain,
            report=report,
        ),
    )
    write_sidecar(
        sidecar_path,
        (report_path, html_path, bundle_path),
    )
    return report_path, html_path, bundle_path, sidecar_path


def verify_sidecar(path: Path, files: Iterable[Path]) -> None:
    expected_files = list(files)
    if not path.is_file() or path.is_symlink():
        raise PresentationSignoffError(
            "발표 사인오프 sidecar가 없습니다."
        )
    try:
        lines = [
            line.strip().split()
            for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
    except UnicodeDecodeError as error:
        raise PresentationSignoffError(
            "발표 사인오프 sidecar가 UTF-8이 아닙니다."
        ) from error
    if len(lines) != len(expected_files) or any(
        len(parts) != 2 for parts in lines
    ):
        raise PresentationSignoffError(
            "발표 사인오프 sidecar 형식이 올바르지 않습니다."
        )
    recorded = {parts[1]: parts[0].lower() for parts in lines}
    if set(recorded) != {item.name for item in expected_files}:
        raise PresentationSignoffError(
            "발표 사인오프 sidecar 파일 목록이 다릅니다."
        )
    for item in expected_files:
        checksum = recorded[item.name]
        if (
            not is_checksum(checksum)
            or not item.is_file()
            or item.is_symlink()
            or checksum != sha256_file(item)
        ):
            raise PresentationSignoffError(
                f"발표 사인오프 SHA-256이 다릅니다: {item.name}"
            )


def verify_bundle(
    *,
    bundle_path: Path,
    expected: Mapping[str, bytes],
) -> None:
    try:
        with zipfile.ZipFile(bundle_path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise PresentationSignoffError(
                    "발표 사인오프 번들에 중복 경로가 있습니다."
                )
            actual = {}
            for name in names:
                pure = PurePosixPath(name)
                if pure.is_absolute() or ".." in pure.parts or name.endswith("/"):
                    raise PresentationSignoffError(
                        "발표 사인오프 번들 경로가 안전하지 않습니다."
                    )
                actual[name] = archive.read(name)
    except (OSError, zipfile.BadZipFile) as error:
        raise PresentationSignoffError(
            "발표 사인오프 ZIP을 읽을 수 없습니다."
        ) from error
    if actual != dict(expected):
        raise PresentationSignoffError(
            "발표 사인오프 ZIP 내용이 현재 증적과 다릅니다."
        )
    for name in actual:
        pure = PurePosixPath(name.lower())
        if (
            pure.suffix in FORBIDDEN_BUNDLE_SUFFIXES
            or pure.name.startswith(".env")
        ):
            raise PresentationSignoffError(
                f"발표 사인오프 ZIP에 금지 파일이 있습니다: {name}"
            )


def expected_bundle_paths() -> set[str]:
    paths = {
        MANIFEST_NAME,
        f"signoff/{REPORT_NAME}",
        f"signoff/{HTML_NAME}",
    }
    for key in STAGE_POLICIES:
        paths.update(
            {
                f"evidence/{key}.json",
                f"evidence/{key}.html",
                f"evidence/{key}.sha256",
            }
        )
    return paths


def read_portable_bundle(bundle_path: Path) -> dict[str, bytes]:
    if not bundle_path.is_file() or bundle_path.is_symlink():
        raise PresentationSignoffError(
            "휴대형 발표 사인오프 ZIP을 찾을 수 없습니다."
        )
    try:
        with zipfile.ZipFile(bundle_path) as archive:
            information = archive.infolist()
            names = [item.filename for item in information]
            if len(names) != len(set(names)):
                raise PresentationSignoffError(
                    "휴대형 발표 사인오프 ZIP에 중복 경로가 있습니다."
                )
            if set(names) != expected_bundle_paths():
                raise PresentationSignoffError(
                    "휴대형 발표 사인오프 ZIP 파일 목록이 다릅니다."
                )
            total_size = 0
            entries: dict[str, bytes] = {}
            for item in information:
                name = item.filename
                pure = PurePosixPath(name)
                file_type = (item.external_attr >> 16) & 0o170000
                if (
                    pure.is_absolute()
                    or "\\" in name
                    or ".." in pure.parts
                    or item.is_dir()
                    or file_type == 0o120000
                    or item.flag_bits & 0x1
                ):
                    raise PresentationSignoffError(
                        "휴대형 발표 사인오프 ZIP 경로 또는 "
                        "파일 형식이 안전하지 않습니다."
                    )
                if (
                    item.file_size > MAX_BUNDLE_ENTRY_BYTES
                    or total_size + item.file_size
                    > MAX_BUNDLE_TOTAL_BYTES
                ):
                    raise PresentationSignoffError(
                        "휴대형 발표 사인오프 ZIP 크기가 허용 범위를 "
                        "초과했습니다."
                    )
                lowered = PurePosixPath(name.lower())
                if (
                    lowered.suffix in FORBIDDEN_BUNDLE_SUFFIXES
                    or lowered.name.startswith(".env")
                ):
                    raise PresentationSignoffError(
                        "휴대형 발표 사인오프 ZIP에 금지 파일이 "
                        f"있습니다: {name}"
                    )
                content = archive.read(item)
                if len(content) != item.file_size:
                    raise PresentationSignoffError(
                        "휴대형 발표 사인오프 ZIP 파일 크기가 다릅니다."
                    )
                entries[name] = content
                total_size += item.file_size
    except (OSError, zipfile.BadZipFile) as error:
        raise PresentationSignoffError(
            "휴대형 발표 사인오프 ZIP을 읽을 수 없습니다."
        ) from error
    return entries


def verify_portable_sidecar(
    *,
    bundle_path: Path,
    sidecar_path: Path,
) -> None:
    if not sidecar_path.is_file() or sidecar_path.is_symlink():
        raise PresentationSignoffError(
            "휴대형 발표 사인오프 SHA-256 sidecar가 없습니다."
        )
    try:
        lines = [
            line.strip().split()
            for line in sidecar_path.read_text(
                encoding="utf-8-sig"
            ).splitlines()
            if line.strip()
        ]
    except UnicodeDecodeError as error:
        raise PresentationSignoffError(
            "휴대형 발표 사인오프 sidecar가 UTF-8이 아닙니다."
        ) from error
    if (
        len(lines) != 3
        or any(len(parts) != 2 for parts in lines)
        or len({parts[1] for parts in lines}) != 3
    ):
        raise PresentationSignoffError(
            "휴대형 발표 사인오프 sidecar 형식이 올바르지 않습니다."
        )
    recorded = {
        parts[1]: parts[0].lower()
        for parts in lines
    }
    if set(recorded) != {REPORT_NAME, HTML_NAME, BUNDLE_NAME}:
        raise PresentationSignoffError(
            "휴대형 발표 사인오프 sidecar 파일 목록이 다릅니다."
        )
    checksum = recorded[BUNDLE_NAME]
    if (
        not is_checksum(checksum)
        or checksum != sha256_file(bundle_path)
    ):
        raise PresentationSignoffError(
            "휴대형 발표 사인오프 ZIP SHA-256이 다릅니다."
        )


def validate_portable_manifest(
    entries: Mapping[str, bytes],
    report: Mapping[str, Any],
) -> None:
    manifest = read_json_bytes(
        entries[MANIFEST_NAME],
        "휴대형 발표 사인오프 manifest",
    )
    if (
        manifest.get("schemaVersion") != SCHEMA_VERSION
        or manifest.get("project") != PROJECT_NAME
        or manifest.get("operation") != BUNDLE_OPERATION
        or manifest.get("generatedAt") != report.get("generatedAt")
        or manifest.get("status") != READY_STATUS
    ):
        raise PresentationSignoffError(
            "휴대형 발표 사인오프 manifest 메타데이터가 다릅니다."
        )
    files = manifest.get("files")
    if not isinstance(files, list):
        raise PresentationSignoffError(
            "휴대형 발표 사인오프 manifest 파일 목록이 없습니다."
        )
    payload = {
        name: content
        for name, content in entries.items()
        if name != MANIFEST_NAME
    }
    indexed: dict[str, Mapping[str, Any]] = {}
    for item in files:
        if not isinstance(item, Mapping):
            raise PresentationSignoffError(
                "휴대형 발표 사인오프 manifest 항목이 올바르지 "
                "않습니다."
            )
        name = item.get("path")
        if not isinstance(name, str) or name in indexed:
            raise PresentationSignoffError(
                "휴대형 발표 사인오프 manifest 경로가 없거나 "
                "중복됐습니다."
            )
        indexed[name] = item
    if set(indexed) != set(payload):
        raise PresentationSignoffError(
            "휴대형 발표 사인오프 manifest 파일 목록이 다릅니다."
        )
    for name, content in payload.items():
        item = indexed[name]
        if (
            item.get("sizeBytes") != len(content)
            or item.get("sha256") != sha256_bytes(content)
        ):
            raise PresentationSignoffError(
                "휴대형 발표 사인오프 manifest 파일 동일성이 "
                f"다릅니다: {name}"
            )
    if manifest.get("safety") != {
        "modelWeightsIncluded": False,
        "databaseBackupIncluded": False,
        "sourceVideoIncluded": False,
        "environmentFilesIncluded": False,
        "operatorKeysIncluded": False,
        "privateKeysIncluded": False,
    }:
        raise PresentationSignoffError(
            "휴대형 발표 사인오프 manifest 안전 메타데이터가 "
            "올바르지 않습니다."
        )


def validate_portable_input(
    *,
    key: str,
    entry: Mapping[str, Any],
    content: bytes,
) -> None:
    path_value = entry.get("path")
    file_name = entry.get("fileName")
    if not isinstance(path_value, str) or not isinstance(file_name, str):
        raise PresentationSignoffError(
            f"휴대형 발표 사인오프 입력 경로가 없습니다: {key}"
        )
    pure = PurePosixPath(path_value)
    expected_root = {
        "presentation-gate": GATE_ROOT,
        "presentation-rehearsal": REHEARSAL_ROOT,
        "presentation-performance": PERFORMANCE_ROOT,
        "presentation-quick-check": QUICK_CHECK_ROOT,
    }[key]
    expected_parts = PurePosixPath(expected_root.as_posix()).parts
    if (
        pure.is_absolute()
        or "\\" in path_value
        or ".." in pure.parts
        or pure.suffix.lower() != ".json"
        or pure.parts[:len(expected_parts)] != expected_parts
        or file_name != pure.name
        or entry.get("sizeBytes") != len(content)
        or entry.get("sha256") != sha256_bytes(content)
    ):
        raise PresentationSignoffError(
            f"휴대형 발표 사인오프 입력 동일성이 다릅니다: {key}"
        )


def validate_embedded_sidecar(
    *,
    key: str,
    entry: Mapping[str, Any],
    json_value: bytes,
    html_value: bytes,
    sidecar_value: bytes,
) -> None:
    try:
        lines = [
            line.strip().split()
            for line in sidecar_value.decode("utf-8-sig").splitlines()
            if line.strip()
        ]
    except UnicodeDecodeError as error:
        raise PresentationSignoffError(
            f"내장 {key} sidecar가 UTF-8이 아닙니다."
        ) from error
    json_name = str(entry.get("fileName"))
    html_name = str(PurePosixPath(json_name).with_suffix(".html"))
    if (
        len(lines) != 2
        or any(len(parts) != 2 for parts in lines)
        or len({parts[1] for parts in lines}) != 2
    ):
        raise PresentationSignoffError(
            f"내장 {key} sidecar 형식이 올바르지 않습니다."
        )
    recorded = {parts[1]: parts[0].lower() for parts in lines}
    if set(recorded) != {json_name, html_name}:
        raise PresentationSignoffError(
            f"내장 {key} sidecar 파일 목록이 다릅니다."
        )
    if (
        not all(is_checksum(value) for value in recorded.values())
        or recorded[json_name] != sha256_bytes(json_value)
        or recorded[html_name] != sha256_bytes(html_value)
    ):
        raise PresentationSignoffError(
            f"내장 {key} SHA-256이 다릅니다."
        )


def without_key(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): item
        for key, item in value.items()
        if key != "key"
    }


def validate_portable_report(
    *,
    entries: Mapping[str, bytes],
) -> dict[str, Any]:
    report = read_json_bytes(
        entries[f"signoff/{REPORT_NAME}"],
        "휴대형 발표 사인오프",
    )
    if (
        report.get("schemaVersion") != SCHEMA_VERSION
        or report.get("project") != PROJECT_NAME
        or report.get("scope") != SCOPE
        or report.get("operation") != OPERATION
        or report.get("status") != READY_STATUS
        or not isinstance(report.get("generatedAt"), str)
    ):
        raise PresentationSignoffError(
            "VisionFlow 휴대형 발표 사인오프 보고서가 아닙니다."
        )
    try:
        uuid.UUID(str(report.get("signoffId")))
        datetime.fromisoformat(
            report["generatedAt"].replace("Z", "+00:00")
        )
    except (ValueError, AttributeError) as error:
        raise PresentationSignoffError(
            "휴대형 발표 사인오프 ID 또는 생성 시각이 "
            "올바르지 않습니다."
        ) from error
    inputs = report.get("inputs")
    if not isinstance(inputs, list) or len(inputs) != len(STAGE_POLICIES):
        raise PresentationSignoffError(
            "휴대형 발표 사인오프 입력 목록이 다릅니다."
        )
    stages: dict[str, dict[str, Any]] = {}
    input_entries: dict[str, Mapping[str, Any]] = {}
    for key, (operation, status) in STAGE_POLICIES.items():
        entry = input_by_key(report, key)
        json_value = entries[f"evidence/{key}.json"]
        html_value = entries[f"evidence/{key}.html"]
        sidecar_value = entries[f"evidence/{key}.sha256"]
        validate_portable_input(
            key=key,
            entry=entry,
            content=json_value,
        )
        validate_embedded_sidecar(
            key=key,
            entry=entry,
            json_value=json_value,
            html_value=html_value,
            sidecar_value=sidecar_value,
        )
        try:
            decoded_html = html_value.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise PresentationSignoffError(
                f"내장 {key} HTML이 UTF-8이 아닙니다."
            ) from error
        lowered = decoded_html.lower()
        if any(
            token in lowered
            for token in (
                "<script",
                "<iframe",
                "<object",
                "<embed",
                "javascript:",
            )
        ):
            raise PresentationSignoffError(
                f"내장 {key} HTML에 실행 가능한 콘텐츠가 있습니다."
            )
        stage = read_json_bytes(json_value, f"내장 {key}")
        if (
            stage.get("schemaVersion") != SCHEMA_VERSION
            or stage.get("project") != PROJECT_NAME
            or stage.get("operation") != operation
            or stage.get("status") != status
        ):
            raise PresentationSignoffError(
                f"내장 {key} 메타데이터가 올바르지 않습니다."
            )
        stages[key] = stage
        input_entries[key] = entry

    gate = stages["presentation-gate"]
    rehearsal = stages["presentation-rehearsal"]
    performance = stages["presentation-performance"]
    quick_check = stages["presentation-quick-check"]
    if (
        rehearsal.get("sourcePresentationGate")
        != without_key(input_entries["presentation-gate"])
        or performance.get("sourceRehearsal")
        != without_key(input_entries["presentation-rehearsal"])
        or quick_check.get("sourcePerformance")
        != without_key(input_entries["presentation-performance"])
        or performance.get("sourceRehearsalId")
        != str(rehearsal.get("rehearsalId"))
        or quick_check.get("sourcePerformanceAnalysisId")
        != str(performance.get("analysisId"))
    ):
        raise PresentationSignoffError(
            "휴대형 발표 사인오프 단계 연결이 다릅니다."
        )
    try:
        expected_presentation = {
            "gateStatus": str(gate.get("status")),
            "rehearsalPassedRuns": rehearsal["summary"]["passedRuns"],
            "rehearsalRequestedRuns": rehearsal["summary"][
                "requestedRuns"
            ],
            "performanceStatus": str(performance.get("status")),
            "bottleneck": str(
                performance["analysis"]["bottleneck"]["name"]
            ),
            "runBudgetUsagePercent": performance["analysis"][
                "runTiming"
            ]["budgetUsagePercent"],
            "watchStageCount": performance["analysis"]["summary"][
                "watchStageCount"
            ],
            "quickCheckPassed": quick_check["summary"]["passed"],
            "quickCheckTotal": quick_check["summary"]["total"],
            "diagnosisCode": str(quick_check["diagnosis"]["code"]),
        }
    except (KeyError, TypeError) as error:
        raise PresentationSignoffError(
            "휴대형 발표 사인오프 요약 원본이 올바르지 않습니다."
        ) from error
    deferred = [
        {
            "key": str(item.get("key")),
            "status": str(item.get("status")),
            "scope": str(item.get("scope")),
            "reason": str(item.get("reason")),
        }
        for item in quick_check.get("deferred", [])
        if isinstance(item, Mapping)
    ]
    expected_summary = {
        "approved": True,
        "blocking": 0,
        "verifiedStages": 4,
        "deferred": sum(
            item["status"] == "DEFERRED" for item in deferred
        ),
        "outOfScope": sum(
            item["status"] == "OUT_OF_SCOPE" for item in deferred
        ),
    }
    expected_safety = {
        "readOnly": True,
        "databaseMutation": False,
        "serviceMutation": False,
        "modelWeightsIncluded": False,
        "databaseBackupIncluded": False,
        "sourceVideoIncluded": False,
        "environmentFilesIncluded": False,
        "operatorKeysIncluded": False,
        "privateKeysIncluded": False,
        "absolutePathsRecorded": False,
        "gpuValidationExecuted": False,
        "smartphoneSensorValidationExecuted": False,
        "djiIntegrationExecuted": False,
    }
    if (
        report.get("presentation") != expected_presentation
        or report.get("deferred") != deferred
        or report.get("summary") != expected_summary
        or report.get("safety") != expected_safety
    ):
        raise PresentationSignoffError(
            "휴대형 발표 사인오프 요약 또는 안전 메타데이터가 "
            "다릅니다."
        )
    try:
        html_value = entries[f"signoff/{HTML_NAME}"].decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise PresentationSignoffError(
            "휴대형 발표 사인오프 HTML이 UTF-8이 아닙니다."
        ) from error
    lowered = html_value.lower()
    if any(
        token in lowered
        for token in ("<script", "<iframe", "<object", "<embed", "javascript:")
    ):
        raise PresentationSignoffError(
            "휴대형 발표 사인오프 HTML에 실행 가능한 콘텐츠가 "
            "있습니다."
        )
    if normalize_newlines(html_value) != render_html(report):
        raise PresentationSignoffError(
            "휴대형 발표 사인오프 JSON과 HTML이 다릅니다."
        )
    return report


def verify_portable_bundle(
    *,
    bundle_path: Path,
    sidecar_path: Path | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    bundle = bundle_path.resolve()
    sidecar = (
        sidecar_path.resolve()
        if sidecar_path is not None
        else bundle.with_name(SIDECAR_NAME)
    )
    verify_portable_sidecar(
        bundle_path=bundle,
        sidecar_path=sidecar,
    )
    entries = read_portable_bundle(bundle)
    report = validate_portable_report(entries=entries)
    validate_portable_manifest(entries, report)
    return bundle, sidecar, report


def input_by_key(report: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    inputs = report.get("inputs")
    if not isinstance(inputs, list):
        raise PresentationSignoffError(
            "발표 사인오프 입력 목록이 없습니다."
        )
    matches = [
        item
        for item in inputs
        if isinstance(item, Mapping) and item.get("key") == key
    ]
    if len(matches) != 1:
        raise PresentationSignoffError(
            f"발표 사인오프 입력이 없거나 중복됐습니다: {key}"
        )
    return matches[0]


def verify_signoff_report(
    *,
    root: Path,
    report_path: Path,
) -> tuple[Path, dict[str, Any]]:
    root = root.resolve()
    candidate = (
        report_path.resolve()
        if report_path.is_absolute()
        else (root / report_path).resolve()
    )
    allowed = (root / REPORT_ROOT).resolve()
    if (
        not is_within(candidate, allowed)
        or not candidate.is_file()
        or candidate.is_symlink()
        or candidate.name != REPORT_NAME
    ):
        raise PresentationSignoffError(
            "발표 사인오프 보고서 경로가 올바르지 않습니다."
        )
    report_path = candidate
    html_path = report_path.with_name(HTML_NAME)
    bundle_path = report_path.with_name(BUNDLE_NAME)
    sidecar_path = report_path.with_name(SIDECAR_NAME)
    verify_sidecar(
        sidecar_path,
        (report_path, html_path, bundle_path),
    )
    report = read_json(report_path, "발표 사인오프")
    if (
        report.get("schemaVersion") != SCHEMA_VERSION
        or report.get("project") != PROJECT_NAME
        or report.get("scope") != SCOPE
        or report.get("operation") != OPERATION
        or report.get("status") != READY_STATUS
        or not isinstance(report.get("generatedAt"), str)
    ):
        raise PresentationSignoffError(
            "VisionFlow 발표 사인오프 보고서가 아닙니다."
        )
    try:
        uuid.UUID(str(report.get("signoffId")))
        generated_at = datetime.fromisoformat(
            report["generatedAt"].replace("Z", "+00:00")
        )
    except (ValueError, AttributeError) as error:
        raise PresentationSignoffError(
            "발표 사인오프 ID 또는 생성 시각이 올바르지 않습니다."
        ) from error
    quick_input = input_by_key(report, "presentation-quick-check")
    quick_path = linked_artifact(
        root,
        quick_input,
        directory=QUICK_CHECK_ROOT,
        title="발표 퀵체크",
    )
    chain = verify_chain(root=root, quick_check_path=quick_path)
    expected_input_paths = {
        "presentation-gate": chain["gatePath"],
        "presentation-rehearsal": chain["rehearsalPath"],
        "presentation-performance": chain["performancePath"],
        "presentation-quick-check": chain["quickCheckPath"],
    }
    for key, path in expected_input_paths.items():
        if input_by_key(report, key) != {
            "key": key,
            **artifact_entry(root, path),
        }:
            raise PresentationSignoffError(
                f"발표 사인오프 입력 동일성이 다릅니다: {key}"
            )
    rebuilt = build_report(
        root=root,
        chain=chain,
        now=generated_at,
        signoff_id=str(report.get("signoffId")),
    )
    if rebuilt != report:
        raise PresentationSignoffError(
            "현재 증적을 재계산한 발표 사인오프가 다릅니다."
        )
    try:
        html_value = html_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise PresentationSignoffError(
            "발표 사인오프 HTML이 UTF-8이 아닙니다."
        ) from error
    lowered = html_value.lower()
    if any(
        token in lowered
        for token in ("<script", "<iframe", "<object", "<embed", "javascript:")
    ):
        raise PresentationSignoffError(
            "발표 사인오프 HTML에 실행 가능한 콘텐츠가 있습니다."
        )
    if html_value != render_html(report):
        raise PresentationSignoffError(
            "발표 사인오프 JSON과 HTML이 다릅니다."
        )
    verify_bundle(
        bundle_path=bundle_path,
        expected=build_bundle_entries(
            report_path=report_path,
            html_path=html_path,
            chain=chain,
            report=report,
        ),
    )
    return report_path, report


def create_signoff(
    root: Path,
    *,
    quick_check_value: str | None,
    output_root: Path,
    now: datetime,
) -> tuple[Path, Path, Path, Path, dict[str, Any]]:
    quick_path = newest_quick_check(root, quick_check_value)
    chain = verify_chain(root=root, quick_check_path=quick_path)
    report = build_report(root=root, chain=chain, now=now)
    paths = write_signoff(
        root=root,
        output_root=output_root,
        report=report,
        chain=chain,
        now=now,
    )
    return (*paths, report)


def build_plan() -> list[dict[str, str]]:
    return [
        {
            "order": "01",
            "mode": "READ_ONLY",
            "detail": "게이트→리허설→성능→퀵체크 SHA-256 계보 재검증",
        },
        {
            "order": "02",
            "mode": "SUMMARIZE",
            "detail": "반복 성공·병목·예산 사용률·10개 경로 상태 요약",
        },
        {
            "order": "03",
            "mode": "SAFE_BUNDLE",
            "detail": "최종 4단계 JSON·HTML·sidecar만 ZIP으로 패키징",
        },
        {
            "order": "04",
            "mode": "VERIFY",
            "detail": "manifest·ZIP 경로·금지 파일·현재 원본 독립 재검증",
        },
        {
            "order": "05",
            "mode": "PORTABLE_VERIFY",
            "detail": "ZIP·sidecar만으로 외부 매체에서 무결성·계보 재검증",
        },
    ]


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="VisionFlow final presentation sign-off"
    )
    parser.add_argument("--root", default=str(default_root))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("plan", help="변경 없는 생성 계획 출력")
    create = subparsers.add_parser(
        "create",
        help="발표 최종 사인오프 번들 생성",
    )
    create.add_argument("--quick-check")
    create.add_argument("--output", default=REPORT_ROOT.as_posix())
    verify = subparsers.add_parser(
        "verify",
        help="발표 사인오프 독립 재검증",
    )
    verify.add_argument("--report", required=True)
    verify_bundle_parser = subparsers.add_parser(
        "verify-bundle",
        help="원본 artifacts 없이 휴대형 ZIP 독립 재검증",
    )
    verify_bundle_parser.add_argument("--bundle", required=True)
    verify_bundle_parser.add_argument("--sidecar")
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    args = build_parser(default_root).parse_args(arguments)
    root = Path(args.root).resolve()
    try:
        if not root.is_dir():
            raise PresentationSignoffError(
                "프로젝트 루트를 찾을 수 없습니다."
            )
        if args.command == "plan":
            print("VisionFlow presentation final sign-off: PLAN")
            for item in build_plan():
                print(f"{item['order']}. [{item['mode']}] {item['detail']}")
            print(
                "No database, service, model, smartphone, or DJI action "
                "was executed."
            )
            return 0
        if args.command == "verify":
            path, report = verify_signoff_report(
                root=root,
                report_path=Path(args.report),
            )
            print("VisionFlow presentation final sign-off: VERIFIED")
            print(f"Status: {report['status']}")
            print(f"Report: {path}")
            return 0
        if args.command == "verify-bundle":
            bundle_value = Path(args.bundle)
            bundle_path = (
                bundle_value.resolve()
                if bundle_value.is_absolute()
                else (root / bundle_value).resolve()
            )
            sidecar_path = None
            if args.sidecar:
                sidecar_value = Path(args.sidecar)
                sidecar_path = (
                    sidecar_value.resolve()
                    if sidecar_value.is_absolute()
                    else (root / sidecar_value).resolve()
                )
            bundle, sidecar, report = verify_portable_bundle(
                bundle_path=bundle_path,
                sidecar_path=sidecar_path,
            )
            print(
                "VisionFlow presentation sign-off bundle: "
                "PORTABLE_VERIFIED"
            )
            print(f"Status: {report['status']}")
            print("Verified stages: 4/4")
            print(f"Bundle: {bundle}")
            print(f"SHA-256: {sidecar}")
            return 0
        output_value = Path(args.output)
        output = (
            output_value.resolve()
            if output_value.is_absolute()
            else (root / output_value).resolve()
        )
        report_path, html_path, bundle, sidecar, report = create_signoff(
            root,
            quick_check_value=args.quick_check,
            output_root=output,
            now=datetime.now(timezone.utc),
        )
        print(f"VisionFlow presentation final sign-off: {report['status']}")
        print(
            "Verified stages: "
            f"{report['summary']['verifiedStages']}/4"
        )
        print(f"Report: {report_path}")
        print(f"HTML: {html_path}")
        print(f"Bundle: {bundle}")
        print(f"SHA-256: {sidecar}")
        return 0
    except (
        PresentationSignoffError,
        PresentationGateError,
        PresentationRehearsalError,
        PresentationPerformanceError,
        PresentationQuickCheckError,
        FileNotFoundError,
        OSError,
        ValueError,
        zipfile.BadZipFile,
    ) as error:
        print(f"[FAIL] {sanitize_error(error, root)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
