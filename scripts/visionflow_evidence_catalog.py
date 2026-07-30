"""Build a bounded VisionFlow evidence and checksum integrity catalog."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

if __package__:
    from scripts.visionflow_checksum_retention import (
        build_plan as retention_plan,
    )
    from scripts.visionflow_checksum_retention import managed_runs
else:
    from visionflow_checksum_retention import (
        build_plan as retention_plan,
    )
    from visionflow_checksum_retention import managed_runs


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
OPERATION = "EVIDENCE_INTEGRITY_CATALOG"
HEALTHY = "HEALTHY"
CLEANUP_RECOMMENDED = "CLEANUP_RECOMMENDED"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
DEFAULT_OUTPUT = Path("artifacts/evidence-catalog")
MAX_SIDECAR_BYTES = 1024 * 1024
CHECKSUM_LINE = re.compile(r"^([0-9a-fA-F]{64})[ \t]+\*?(.+?)$")


class EvidenceCatalogError(RuntimeError):
    """Raised when the evidence catalog cannot be built safely."""


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


def relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as error:
        raise EvidenceCatalogError(
            f"프로젝트 밖의 경로입니다: {path}"
        ) from error


def safe_target_name(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or "\\" in value
        or ".." in path.parts
        or path.name in {"", ".", ".."}
    ):
        raise EvidenceCatalogError(
            f"안전하지 않은 체크섬 대상 경로입니다: {value}"
        )
    return path


def sidecar_scope(root: Path, sidecar: Path) -> str:
    relative = sidecar.resolve().relative_to(root.resolve())
    if len(relative.parts) == 1:
        return "root-patch"
    return relative.parts[0]


def sidecar_paths(root: Path) -> list[Path]:
    paths = [
        path.resolve()
        for path in root.glob("*.sha256")
        if path.is_file() and not path.is_symlink()
    ]
    for relative in (Path("artifacts"), Path("backups")):
        parent = (root / relative).resolve()
        if not parent.is_dir() or parent.is_symlink():
            continue
        paths.extend(
            path.resolve()
            for path in parent.rglob("*.sha256")
            if path.is_file() and not path.is_symlink()
        )
    return sorted(set(paths), key=lambda path: path.as_posix())


def parse_sidecar(sidecar: Path) -> list[tuple[str, PurePosixPath]]:
    if sidecar.stat().st_size > MAX_SIDECAR_BYTES:
        raise EvidenceCatalogError(
            f"체크섬 파일이 허용 크기를 초과합니다: {sidecar.name}"
        )
    entries: list[tuple[str, PurePosixPath]] = []
    names: set[str] = set()
    for line_number, raw_line in enumerate(
        sidecar.read_text(encoding="utf-8-sig").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line:
            continue
        match = CHECKSUM_LINE.fullmatch(line)
        if match is None:
            raise EvidenceCatalogError(
                f"{sidecar.name} {line_number}행 형식이 올바르지 않습니다."
            )
        name = safe_target_name(match.group(2).strip())
        normalized = name.as_posix()
        if normalized in names:
            raise EvidenceCatalogError(
                f"체크섬 대상이 중복되었습니다: {normalized}"
            )
        names.add(normalized)
        entries.append((match.group(1).lower(), name))
    if not entries:
        raise EvidenceCatalogError(
            f"체크섬 대상이 없습니다: {sidecar.name}"
        )
    return entries


def inspect_sidecar(root: Path, sidecar: Path, now: datetime) -> dict[str, Any]:
    scope = sidecar_scope(root, sidecar)
    result: dict[str, Any] = {
        "path": relative_path(root, sidecar),
        "scope": scope,
        "status": "VERIFIED",
        "severity": "INFO",
        "detail": "모든 체크섬 대상의 크기와 SHA-256이 일치합니다.",
        "ageDays": round(
            max(
                0.0,
                (
                    now.astimezone(timezone.utc)
                    - datetime.fromtimestamp(
                        sidecar.stat().st_mtime,
                        tz=timezone.utc,
                    )
                ).total_seconds()
                / 86400.0,
            ),
            3,
        ),
        "sidecarBytes": sidecar.stat().st_size,
        "targetCount": 0,
        "targetBytes": 0,
        "targets": [],
    }
    try:
        entries = parse_sidecar(sidecar)
    except (EvidenceCatalogError, OSError, UnicodeDecodeError) as error:
        result.update(
            {
                "status": "INVALID_FORMAT",
                "severity": (
                    "WARNING" if scope == "root-patch" else "ERROR"
                ),
                "detail": str(error),
            }
        )
        return result

    targets = []
    statuses: set[str] = set()
    for expected, relative in entries:
        target = sidecar.parent.joinpath(*relative.parts).resolve()
        if not is_within(target, sidecar.parent.resolve()):
            status = "UNSAFE_PATH"
            detail = "대상 경로가 sidecar 폴더 밖에 있습니다."
            size = None
            actual = None
        elif not target.is_file() or target.is_symlink():
            status = "MISSING_TARGET"
            detail = "대상 파일을 찾을 수 없습니다."
            size = None
            actual = None
        else:
            size = target.stat().st_size
            actual = sha256_file(target)
            status = (
                "VERIFIED"
                if actual == expected
                else "HASH_MISMATCH"
            )
            detail = (
                "SHA-256 일치"
                if status == "VERIFIED"
                else "기록된 SHA-256과 현재 파일이 다릅니다."
            )
        statuses.add(status)
        targets.append(
            {
                "path": relative.as_posix(),
                "status": status,
                "detail": detail,
                "sizeBytes": size,
                "expectedSha256": expected,
                "actualSha256": actual,
            }
        )
    failures = statuses - {"VERIFIED"}
    result.update(
        {
            "status": (
                sorted(failures)[0] if failures else "VERIFIED"
            ),
            "severity": (
                "WARNING"
                if failures and scope == "root-patch"
                else "ERROR" if failures else "INFO"
            ),
            "detail": (
                "체크섬 대상 재검토가 필요합니다."
                if failures
                else result["detail"]
            ),
            "targetCount": len(targets),
            "targetBytes": sum(
                item["sizeBytes"] or 0 for item in targets
            ),
            "targets": targets,
        }
    )
    return result


def artifact_run_issues(root: Path) -> list[dict[str, str]]:
    issues = []
    for run in managed_runs(root):
        if run["validationError"] is None:
            continue
        issues.append(
            {
                "family": run["family"],
                "path": relative_path(root, run["path"]),
                "status": "INVALID_EVIDENCE_GROUP",
                "severity": "ERROR",
                "detail": run["validationError"],
            }
        )
    return issues


def build_catalog(
    *,
    root: Path,
    now: datetime,
    cleanup_min_age_days: float = 14.0,
    cleanup_keep_per_family: int = 3,
) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise EvidenceCatalogError(
            f"프로젝트 루트를 찾을 수 없습니다: {root}"
        )
    sidecars = [
        inspect_sidecar(root, path, now)
        for path in sidecar_paths(root)
    ]
    run_issues = artifact_run_issues(root)
    cleanup = retention_plan(
        root=root,
        min_age_days=cleanup_min_age_days,
        keep_per_family=cleanup_keep_per_family,
        include_patch_sidecars=True,
        now=now,
    )
    error_count = sum(
        item["severity"] == "ERROR" for item in sidecars
    ) + len(run_issues)
    warning_count = sum(
        item["severity"] == "WARNING" for item in sidecars
    )
    cleanup_count = cleanup["summary"]["eligibleItems"]
    if error_count:
        status = REVIEW_REQUIRED
    elif warning_count or cleanup_count:
        status = CLEANUP_RECOMMENDED
    else:
        status = HEALTHY
    verified = sum(
        item["status"] == "VERIFIED" for item in sidecars
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "operation": OPERATION,
        "generatedAt": now.astimezone(timezone.utc).isoformat(),
        "status": status,
        "summary": {
            "sidecarCount": len(sidecars),
            "verifiedSidecars": verified,
            "warningSidecars": warning_count,
            "errorSidecars": sum(
                item["severity"] == "ERROR" for item in sidecars
            ),
            "invalidArtifactRuns": len(run_issues),
            "cleanupCandidates": cleanup_count,
            "sidecarBytes": sum(
                item["sidecarBytes"] for item in sidecars
            ),
            "protectedTargetBytes": sum(
                item["targetBytes"] for item in sidecars
            ),
        },
        "sidecars": sidecars,
        "artifactRunIssues": run_issues,
        "cleanup": {
            "status": cleanup["status"],
            "policy": cleanup["policy"],
            "summary": cleanup["summary"],
            "candidates": cleanup["candidates"],
        },
        "safety": {
            "readOnlyScan": True,
            "sourceFilesModified": False,
            "permanentDelete": False,
            "catalogSidecarGenerated": False,
            "fixedOutputNames": True,
        },
    }


def format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{value} B"


def render_html(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    rows = []
    for item in report["sidecars"]:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(item['path']))}</td>"
            f"<td>{html.escape(str(item['scope']))}</td>"
            f"<td><span class=\"{html.escape(str(item['severity']).lower())}\">"
            f"{html.escape(str(item['status']))}</span></td>"
            f"<td>{item['targetCount']}</td>"
            f"<td>{item['ageDays']}</td>"
            f"<td>{html.escape(str(item['detail']))}</td>"
            "</tr>"
        )
    issue_rows = []
    for item in report["artifactRunIssues"]:
        issue_rows.append(
            "<tr>"
            f"<td>{html.escape(str(item['family']))}</td>"
            f"<td>{html.escape(str(item['path']))}</td>"
            f"<td>{html.escape(str(item['detail']))}</td>"
            "</tr>"
        )
    cleanup_rows = []
    for item in report["cleanup"]["candidates"]:
        cleanup_rows.append(
            "<tr>"
            f"<td>{html.escape(str(item['kind']))}</td>"
            f"<td>{html.escape(str(item['family']))}</td>"
            f"<td>{html.escape(str(item['path']))}</td>"
            f"<td>{item['ageDays']}</td>"
            f"<td>{format_bytes(int(item['totalBytes']))}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VisionFlow 증적 카탈로그</title>
<style>
body{{font-family:Arial,sans-serif;background:#f3f6fb;color:#14213d;margin:0}}
main{{max-width:1280px;margin:32px auto;padding:0 20px}}
section{{background:#fff;border:1px solid #dce4ef;border-radius:14px;
margin:18px 0;padding:22px;box-shadow:0 4px 18px #1d35571a}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}}
.card{{background:#f8fafc;border-radius:10px;padding:16px}}
.value{{font-size:28px;font-weight:700}} table{{width:100%;border-collapse:collapse}}
th,td{{border-bottom:1px solid #e5eaf1;padding:10px;text-align:left;vertical-align:top}}
.info{{color:#087f5b;font-weight:700}}.warning{{color:#b26a00;font-weight:700}}
.error{{color:#c92a2a;font-weight:700}} code{{background:#edf2f7;padding:2px 5px}}
</style></head><body><main>
<h1>VisionFlow 통합 증적 카탈로그</h1>
<p>상태: <strong>{html.escape(str(report['status']))}</strong> ·
{html.escape(str(report['generatedAt']))}</p>
<section><div class="cards">
<div class="card">체크섬 파일<div class="value">{summary['sidecarCount']}</div></div>
<div class="card">검증 완료<div class="value">{summary['verifiedSidecars']}</div></div>
<div class="card">경고<div class="value">{summary['warningSidecars']}</div></div>
<div class="card">오류<div class="value">{summary['errorSidecars'] + summary['invalidArtifactRuns']}</div></div>
<div class="card">정리 후보<div class="value">{summary['cleanupCandidates']}</div></div>
</div></section>
<section><h2>체크섬 무결성</h2><table>
<thead><tr><th>경로</th><th>범위</th><th>상태</th><th>대상</th><th>경과일</th><th>설명</th></tr></thead>
<tbody>{''.join(rows) or '<tr><td colspan="6">체크섬 파일 없음</td></tr>'}</tbody>
</table></section>
<section><h2>모델 증적 그룹 오류</h2><table>
<thead><tr><th>종류</th><th>경로</th><th>설명</th></tr></thead>
<tbody>{''.join(issue_rows) or '<tr><td colspan="3">오류 없음</td></tr>'}</tbody>
</table></section>
<section><h2>복원 가능한 정리 후보</h2><table>
<thead><tr><th>종류</th><th>계열</th><th>경로</th><th>경과일</th><th>크기</th></tr></thead>
<tbody>{''.join(cleanup_rows) or '<tr><td colspan="5">후보 없음</td></tr>'}</tbody>
</table></section>
<section><p>이 카탈로그는 파생 보고서이며 고정 파일명으로 덮어씁니다.
새 <code>*.sha256</code> 파일을 만들지 않으며 원본 증적을 변경하지 않습니다.</p></section>
</main></body></html>"""


def output_paths(root: Path, output: Path) -> tuple[Path, Path]:
    allowed = (root / DEFAULT_OUTPUT).resolve()
    resolved = output.resolve()
    if resolved != allowed:
        raise EvidenceCatalogError(
            "출력 폴더는 artifacts/evidence-catalog이어야 합니다."
        )
    if resolved.exists() and (
        not resolved.is_dir() or resolved.is_symlink()
    ):
        raise EvidenceCatalogError(
            "증적 카탈로그 출력 경로가 일반 폴더가 아닙니다."
        )
    return (
        resolved / "visionflow-evidence-catalog.json",
        resolved / "visionflow-evidence-catalog.html",
    )


def write_catalog(
    *,
    root: Path,
    output: Path,
    report: Mapping[str, Any],
) -> tuple[Path, Path]:
    json_path, html_path = output_paths(root, output)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    token = f".tmp-{os.getpid()}"
    json_temporary = json_path.with_name(json_path.name + token)
    html_temporary = html_path.with_name(html_path.name + token)
    try:
        json_temporary.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8-sig",
        )
        html_temporary.write_text(
            render_html(report),
            encoding="utf-8",
        )
        os.replace(json_temporary, json_path)
        os.replace(html_temporary, html_path)
    finally:
        for path in (json_temporary, html_temporary):
            if path.exists():
                path.unlink()
    return json_path, html_path


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="VisionFlow evidence integrity catalog"
    )
    parser.add_argument("--root", default=str(default_root))
    parser.add_argument("--output", default=DEFAULT_OUTPUT.as_posix())
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--min-age-days", type=float, default=14.0)
    parser.add_argument("--keep-per-family", type=int, default=3)
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    args = build_parser(default_root).parse_args(arguments)
    root = Path(args.root).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    try:
        report = build_catalog(
            root=root,
            now=datetime.now(timezone.utc),
            cleanup_min_age_days=args.min_age_days,
            cleanup_keep_per_family=args.keep_per_family,
        )
        print(f"VisionFlow evidence catalog: {report['status']}")
        summary = report["summary"]
        print(
            "Checksums: "
            f"{summary['verifiedSidecars']}/{summary['sidecarCount']} verified"
        )
        print(
            "Review issues: "
            f"{summary['errorSidecars'] + summary['invalidArtifactRuns']}"
        )
        print(f"Cleanup candidates: {summary['cleanupCandidates']}")
        if not args.check_only:
            json_path, html_path = write_catalog(
                root=root,
                output=output,
                report=report,
            )
            print(f"JSON catalog: {json_path}")
            print(f"HTML catalog: {html_path}")
        return 1 if report["status"] == REVIEW_REQUIRED else 0
    except (
        EvidenceCatalogError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
