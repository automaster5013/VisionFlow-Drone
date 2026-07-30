"""Create and verify a minimal safe VisionFlow model-release sign-off bundle."""

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
from typing import Any, Mapping, Sequence

try:
    from visionflow_model_promotion import (
        READY_STATUS as PROMOTION_READY_STATUS,
        ModelPromotionError,
        artifact_entry,
        is_within,
        newest_artifact,
        parse_timestamp,
        read_json,
        resolve_inside,
        sha256_file,
        verify_report as verify_promotion_report,
    )
    from visionflow_model_release import (
        ACTIVATED_STATUS,
        ModelReleaseError,
        verify_activation_report,
        verify_release_report,
        verify_sidecar,
        write_sidecar,
    )
    from visionflow_model_soak import (
        BLOCKED_STATUS as SOAK_BLOCKED_STATUS,
        PASSED_STATUS as SOAK_PASSED_STATUS,
        ModelSoakError,
        input_by_key as soak_input_by_key,
        verify_report as verify_soak_report,
    )
    from visionflow_model_soak_decision import (
        FAILED_STATUS as DECISION_FAILED_STATUS,
        ROLLED_BACK_STATUS as DECISION_ROLLED_BACK_STATUS,
        STABILIZED_STATUS as DECISION_STABILIZED_STATUS,
        ModelSoakDecisionError,
        linked_artifact_path,
        report_input as decision_input,
        verify_decision_report,
    )
except ModuleNotFoundError:  # pragma: no cover - package import during tests
    from scripts.visionflow_model_promotion import (
        READY_STATUS as PROMOTION_READY_STATUS,
        ModelPromotionError,
        artifact_entry,
        is_within,
        newest_artifact,
        parse_timestamp,
        read_json,
        resolve_inside,
        sha256_file,
        verify_report as verify_promotion_report,
    )
    from scripts.visionflow_model_release import (
        ACTIVATED_STATUS,
        ModelReleaseError,
        verify_activation_report,
        verify_release_report,
        verify_sidecar,
        write_sidecar,
    )
    from scripts.visionflow_model_soak import (
        BLOCKED_STATUS as SOAK_BLOCKED_STATUS,
        PASSED_STATUS as SOAK_PASSED_STATUS,
        ModelSoakError,
        input_by_key as soak_input_by_key,
        verify_report as verify_soak_report,
    )
    from scripts.visionflow_model_soak_decision import (
        FAILED_STATUS as DECISION_FAILED_STATUS,
        ROLLED_BACK_STATUS as DECISION_ROLLED_BACK_STATUS,
        STABILIZED_STATUS as DECISION_STABILIZED_STATUS,
        ModelSoakDecisionError,
        linked_artifact_path,
        report_input as decision_input,
        verify_decision_report,
    )


SCHEMA_VERSION = 1
PROJECT_NAME = "visionflow"
OPERATION = "MODEL_RELEASE_SIGNOFF"
SIGNED_OFF_STATUS = "MODEL_RELEASE_SIGNED_OFF"
REJECTED_STATUS = "MODEL_RELEASE_REJECTED_ROLLED_BACK"
BLOCKED_STATUS = "MODEL_RELEASE_SIGNOFF_BLOCKED"
DEFAULT_OUTPUT = Path("artifacts/model-release-signoff")
DECISION_PATTERN = (
    "artifacts/model-soak-decision/decision-*/"
    "visionflow-model-soak-decision.json"
)
REPORT_NAME = "visionflow-model-release-signoff.json"
HTML_NAME = "visionflow-model-release-signoff.html"
BUNDLE_NAME = "visionflow-model-release-signoff.zip"
SIDECAR_NAME = "visionflow-model-release-signoff.sha256"
MANIFEST_NAME = "bundle-manifest.json"


class ModelReleaseSignoffError(RuntimeError):
    """Raised when model release sign-off evidence cannot be trusted."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def chain_paths(
    *,
    root: Path,
    decision_path: Path,
) -> dict[str, Any]:
    root = root.resolve()
    try:
        decision_path, decision = verify_decision_report(
            root=root,
            report_path=decision_path,
        )
    except (
        ModelSoakDecisionError,
        ModelSoakError,
        ModelReleaseError,
        OSError,
    ) as error:
        raise ModelReleaseSignoffError(str(error)) from error

    soak_path = linked_artifact_path(
        root,
        decision_input(decision, "model-soak"),
        "모델 소크",
    )
    activation_path = linked_artifact_path(
        root,
        decision_input(decision, "model-release-activation"),
        "모델 릴리스 실행",
    )
    release_path = linked_artifact_path(
        root,
        decision_input(decision, "model-release"),
        "모델 릴리스 준비",
    )
    try:
        soak_path, soak = verify_soak_report(
            root=root,
            report_path=soak_path,
        )
        activation_path, activation = verify_activation_report(
            root=root,
            report_path=activation_path,
        )
        release_path, release = verify_release_report(
            root=root,
            report_path=release_path,
        )
    except (
        ModelSoakError,
        ModelReleaseError,
        ModelPromotionError,
        OSError,
    ) as error:
        raise ModelReleaseSignoffError(str(error)) from error

    promotion_path = linked_artifact_path(
        root,
        soak_input_by_key(soak, "model-promotion"),
        "모델 승격",
    )
    try:
        promotion_path, promotion = verify_promotion_report(
            root=root,
            report_path=promotion_path,
        )
    except (ModelPromotionError, OSError) as error:
        raise ModelReleaseSignoffError(str(error)) from error

    soak_activation_path = linked_artifact_path(
        root,
        soak_input_by_key(soak, "model-release-activation"),
        "소크 모델 릴리스 실행",
    )
    activation_release_path = linked_artifact_path(
        root,
        activation.get("release"),
        "활성화 모델 릴리스 준비",
    )
    release_promotion_path = linked_artifact_path(
        root,
        release.get("promotion"),
        "릴리스 모델 승격",
    )
    active_model = activation.get("activeModel")
    release_model = release.get("activeModel")
    decision_model = decision.get("activeModel")
    soak_model = soak.get("model")
    active_sha = (
        active_model.get("sha256")
        if isinstance(active_model, Mapping)
        else None
    )
    if (
        soak_activation_path != activation_path
        or activation_release_path != release_path
        or release_promotion_path != promotion_path
        or not isinstance(active_model, Mapping)
        or active_model != release_model
        or active_model != decision_model
        or not isinstance(soak_model, Mapping)
        or soak_model.get("sha256") != active_sha
        or soak_model.get("fileName") != active_model.get("fileName")
    ):
        raise ModelReleaseSignoffError(
            "모델 승격·릴리스·활성화·소크·결정 연결이 다릅니다."
        )
    return {
        "decisionPath": decision_path,
        "decision": decision,
        "soakPath": soak_path,
        "soak": soak,
        "activationPath": activation_path,
        "activation": activation,
        "releasePath": release_path,
        "release": release,
        "promotionPath": promotion_path,
        "promotion": promotion,
    }


def status_for_chain(chain: Mapping[str, Any]) -> str:
    decision_status = chain["decision"].get("status")
    soak_status = chain["soak"].get("status")
    if (
        decision_status == DECISION_STABILIZED_STATUS
        and soak_status == SOAK_PASSED_STATUS
    ):
        return SIGNED_OFF_STATUS
    if (
        decision_status == DECISION_ROLLED_BACK_STATUS
        and soak_status == SOAK_BLOCKED_STATUS
    ):
        return REJECTED_STATUS
    return BLOCKED_STATUS


def check(
    items: list[dict[str, str]],
    *,
    key: str,
    title: str,
    status: str,
    detail: str,
) -> None:
    items.append(
        {
            "key": key,
            "title": title,
            "status": status,
            "detail": detail,
        }
    )


def build_report(
    *,
    root: Path,
    decision_path: Path,
    now: datetime,
    signoff_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = root.resolve()
    chain = chain_paths(root=root, decision_path=decision_path)
    status = status_for_chain(chain)
    promotion = chain["promotion"]
    release = chain["release"]
    activation = chain["activation"]
    soak = chain["soak"]
    decision = chain["decision"]
    checks: list[dict[str, str]] = []
    check(
        checks,
        key="chain-integrity",
        title="전체 증적 SHA-256 연결",
        status="PASS",
        detail="승격→릴리스→활성화→소크→결정 연결 일치",
    )
    check(
        checks,
        key="promotion",
        title="모델 승격 승인",
        status=(
            "PASS"
            if promotion.get("status") == PROMOTION_READY_STATUS
            else "FAILED"
        ),
        detail=str(promotion.get("status")),
    )
    check(
        checks,
        key="activation",
        title="승격 모델 활성화",
        status=(
            "PASS"
            if activation.get("status") == ACTIVATED_STATUS
            else "FAILED"
        ),
        detail=str(activation.get("status")),
    )
    soak_check_status = (
        "PASS"
        if soak.get("status") == SOAK_PASSED_STATUS
        else "REJECTED"
    )
    check(
        checks,
        key="post-release-soak",
        title="5분 모델 소크",
        status=soak_check_status,
        detail=str(soak.get("status")),
    )
    decision_status = decision.get("status")
    decision_check_status = (
        "PASS"
        if decision_status == DECISION_STABILIZED_STATUS
        else (
            "REJECTED"
            if decision_status == DECISION_ROLLED_BACK_STATUS
            else "FAILED"
        )
    )
    check(
        checks,
        key="release-decision",
        title="모델 릴리스 최종 결정",
        status=decision_check_status,
        detail=str(decision_status),
    )
    report = {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "operation": OPERATION,
        "signoffId": signoff_id or str(uuid.uuid4()),
        "generatedAt": now.astimezone(timezone.utc).isoformat(),
        "status": status,
        "inputs": [
            artifact_entry(
                root,
                "model-promotion",
                chain["promotionPath"],
            ),
            artifact_entry(
                root,
                "model-release",
                chain["releasePath"],
            ),
            artifact_entry(
                root,
                "model-release-activation",
                chain["activationPath"],
            ),
            artifact_entry(root, "model-soak", chain["soakPath"]),
            artifact_entry(
                root,
                "model-soak-decision",
                chain["decisionPath"],
            ),
        ],
        "model": release.get("activeModel"),
        "rollbackModel": release.get("rollbackModel"),
        "accuracy": promotion.get("accuracy"),
        "promotionPerformance": promotion.get("performance"),
        "soakMeasurement": soak.get("measurement"),
        "decisionStatus": decision_status,
        "checks": checks,
        "summary": {
            "approved": status == SIGNED_OFF_STATUS,
            "safeRollback": status == REJECTED_STATUS,
            "blocking": status == BLOCKED_STATUS,
        },
        "safety": {
            "readOnlyVerification": True,
            "databaseMutation": False,
            "dockerMutation": False,
            "modelWeightsIncluded": False,
            "sourceVideoIncluded": False,
            "environmentFilesIncluded": False,
            "commandOutputRecorded": False,
            "operatorKeysRecorded": False,
            "absolutePathsRecorded": False,
        },
    }
    return report, chain


def render_html(report: Mapping[str, Any]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['title']))}</td>"
        f"<td>{html.escape(str(item['status']))}</td>"
        f"<td>{html.escape(str(item['detail']))}</td>"
        "</tr>"
        for item in report["checks"]
    )
    model = report["model"]
    measurement = report["soakMeasurement"]
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VisionFlow 모델 릴리스 최종 승인</title><style>
body{{margin:0;background:#eef3f8;color:#0f172a;font-family:Arial,'Noto Sans KR',sans-serif}}
main{{max-width:1050px;margin:32px auto;padding:0 20px}}
section{{background:#fff;border:1px solid #dbe4ee;border-radius:16px;padding:24px;margin:16px 0}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid #e2e8f0;text-align:left}}
code{{word-break:break-all}}
</style></head><body><main><section>
<h1>VisionFlow 모델 릴리스 최종 승인</h1>
<p>{html.escape(str(report['status']))}</p>
<p>{html.escape(str(report['generatedAt']))}</p></section>
<section><h2>모델</h2>
<p>{html.escape(str(model.get('fileName')))}</p>
<p><code>{html.escape(str(model.get('sha256')))}</code></p></section>
<section><h2>5분 소크 요약</h2>
<p>처리 FPS {html.escape(str(measurement.get('averageProcessingFps')))} /
평균 지연 {html.escape(str(measurement.get('averageInferenceMs')))} ms /
P95 {html.escape(str(measurement.get('maximumObservedP95InferenceMs')))} ms</p>
</section><section><table><tr><th>항목</th><th>상태</th><th>내용</th></tr>
{rows}</table></section></main></body></html>"""


def source_evidence_files(chain: Mapping[str, Any]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for key, path_key in (
        ("model-promotion", "promotionPath"),
        ("model-release", "releasePath"),
        ("model-release-activation", "activationPath"),
        ("model-soak", "soakPath"),
        ("model-soak-decision", "decisionPath"),
    ):
        json_path = chain[path_key]
        result[f"evidence/{key}.json"] = json_path
        result[f"evidence/{key}.html"] = json_path.with_suffix(".html")
        if key != "model-release":
            result[f"evidence/{key}.sha256"] = json_path.with_suffix(
                ".sha256"
            )
    for path in result.values():
        if not path.is_file() or path.is_symlink():
            raise ModelReleaseSignoffError(
                f"번들 원본 증적 파일이 없습니다: {path.name}"
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
    for name, path in source_evidence_files(chain).items():
        entries[name] = path.read_bytes()
    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "operation": "MODEL_RELEASE_SIGNOFF_BUNDLE",
        "generatedAt": report.get("generatedAt"),
        "status": report.get("status"),
        "model": report.get("model"),
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
            "sourceVideoIncluded": False,
            "environmentFilesIncluded": False,
            "operatorKeysIncluded": False,
        },
    }
    entries[MANIFEST_NAME] = json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
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


def write_signoff(
    *,
    output_directory: Path,
    report: dict[str, Any],
    chain: Mapping[str, Any],
) -> tuple[Path, Path, Path, Path]:
    timestamp = parse_timestamp(
        report["generatedAt"],
        "모델 릴리스 최종 승인",
    ).strftime("%Y%m%dT%H%M%SZ")
    run_directory = output_directory / f"signoff-{timestamp}"
    if run_directory.exists():
        run_directory = output_directory / (
            f"signoff-{timestamp}-{uuid.uuid4().hex[:8]}"
        )
    run_directory.mkdir(parents=True, exist_ok=False)
    report_path = run_directory / REPORT_NAME
    html_path = run_directory / HTML_NAME
    bundle_path = run_directory / BUNDLE_NAME
    sidecar_path = run_directory / SIDECAR_NAME
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    html_path.write_text(render_html(report), encoding="utf-8")
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
        [report_path, html_path, bundle_path],
    )
    return report_path, html_path, bundle_path, sidecar_path


def verify_bundle(
    *,
    bundle_path: Path,
    expected: Mapping[str, bytes],
) -> None:
    try:
        with zipfile.ZipFile(bundle_path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ModelReleaseSignoffError(
                    "모델 릴리스 승인 번들에 중복 경로가 있습니다."
                )
            actual: dict[str, bytes] = {}
            for name in names:
                pure = PurePosixPath(name)
                if pure.is_absolute() or ".." in pure.parts or name.endswith("/"):
                    raise ModelReleaseSignoffError(
                        "모델 릴리스 승인 번들 경로가 안전하지 않습니다."
                    )
                actual[name] = archive.read(name)
    except (OSError, zipfile.BadZipFile) as error:
        raise ModelReleaseSignoffError(
            "모델 릴리스 승인 ZIP을 읽을 수 없습니다."
        ) from error
    if actual != dict(expected):
        raise ModelReleaseSignoffError(
            "모델 릴리스 승인 ZIP 내용이 현재 증적과 다릅니다."
        )
    for name in actual:
        lowered = PurePosixPath(name.lower())
        if (
            lowered.suffix
            in {".pt", ".env", ".pem", ".key", ".p12", ".pfx", ".mp4"}
            or lowered.name.startswith(".env")
        ):
            raise ModelReleaseSignoffError(
                f"모델 릴리스 승인 ZIP에 금지 파일이 있습니다: {name}"
            )


def verify_signoff_report(
    *,
    root: Path,
    report_path: Path,
) -> tuple[Path, dict[str, Any]]:
    root = root.resolve()
    report_path = resolve_inside(root, report_path, "모델 릴리스 승인 보고서")
    html_path = report_path.with_suffix(".html")
    bundle_path = report_path.with_suffix(".zip")
    sidecar_path = report_path.with_suffix(".sha256")
    verify_sidecar(
        sidecar_path,
        [report_path, html_path, bundle_path],
    )
    report = read_json(report_path, "모델 릴리스 승인 보고서")
    if (
        report.get("schemaVersion") != SCHEMA_VERSION
        or report.get("project") != PROJECT_NAME
        or report.get("operation") != OPERATION
        or report.get("status")
        not in {SIGNED_OFF_STATUS, REJECTED_STATUS, BLOCKED_STATUS}
    ):
        raise ModelReleaseSignoffError(
            "VisionFlow 모델 릴리스 승인 보고서가 아닙니다."
        )
    try:
        uuid.UUID(str(report.get("signoffId")))
    except (ValueError, AttributeError) as error:
        raise ModelReleaseSignoffError(
            "모델 릴리스 승인 ID가 올바르지 않습니다."
        ) from error
    inputs = report.get("inputs")
    if not isinstance(inputs, list):
        raise ModelReleaseSignoffError("모델 릴리스 승인 입력이 없습니다.")
    by_key = {
        item.get("key"): item
        for item in inputs
        if isinstance(item, Mapping) and isinstance(item.get("key"), str)
    }
    if (
        len(by_key) != len(inputs)
        or set(by_key)
        != {
            "model-promotion",
            "model-release",
            "model-release-activation",
            "model-soak",
            "model-soak-decision",
        }
    ):
        raise ModelReleaseSignoffError(
            "모델 릴리스 승인 입력 종류가 다릅니다."
        )
    decision_path = linked_artifact_path(
        root,
        by_key["model-soak-decision"],
        "모델 소크 결정",
    )
    rebuilt, chain = build_report(
        root=root,
        decision_path=decision_path,
        now=parse_timestamp(report.get("generatedAt"), "모델 릴리스 승인"),
        signoff_id=str(report.get("signoffId")),
    )
    expected_paths = {
        "model-promotion": chain["promotionPath"],
        "model-release": chain["releasePath"],
        "model-release-activation": chain["activationPath"],
        "model-soak": chain["soakPath"],
        "model-soak-decision": chain["decisionPath"],
    }
    for key, path in expected_paths.items():
        if linked_artifact_path(root, by_key[key], key) != path:
            raise ModelReleaseSignoffError(
                "모델 릴리스 승인 증적 연결이 다릅니다."
            )
    if rebuilt != report:
        raise ModelReleaseSignoffError(
            "현재 증적을 재계산한 모델 릴리스 승인이 다릅니다."
        )
    if html_path.read_text(encoding="utf-8-sig") != render_html(report):
        raise ModelReleaseSignoffError(
            "모델 릴리스 승인 JSON과 HTML이 다릅니다."
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


def build_plan() -> list[str]:
    return [
        "승격→릴리스→활성화→5분 소크→결정 SHA-256 체인 재검증",
        "best.pt와 정확도·성능·CUDA·소크 결과 요약",
        "MODEL_RELEASE_STABILIZED만 최종 승인",
        "안전 롤백과 치명적 롤백 실패를 별도 상태로 기록",
        "모델·영상·환경파일을 제외한 최소 증빙 ZIP 생성",
        "JSON·HTML·ZIP·SHA-256 독립 재검증",
    ]


def output_path(root: Path, value: str) -> Path:
    output = resolve_inside(
        root,
        value,
        "모델 릴리스 승인 출력",
        require_file=False,
    )
    if not is_within(output, (root / DEFAULT_OUTPUT).resolve()):
        raise ModelReleaseSignoffError(
            "모델 릴리스 승인 출력은 artifacts/model-release-signoff "
            "안에 있어야 합니다."
        )
    return output


def parser(default_root: Path) -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="VisionFlow final model-release sign-off evidence"
    )
    value.add_argument("--root", default=str(default_root))
    subparsers = value.add_subparsers(dest="command", required=True)
    subparsers.add_parser("plan")
    create = subparsers.add_parser("create")
    create.add_argument("--decision")
    create.add_argument("--output", default=DEFAULT_OUTPUT.as_posix())
    verify = subparsers.add_parser("verify")
    verify.add_argument("--report", required=True)
    return value


def main(argv: Sequence[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    arguments = parser(default_root).parse_args(argv)
    root = Path(arguments.root).resolve()
    try:
        if arguments.command == "plan":
            print("VisionFlow model release sign-off: PLAN")
            for index, item in enumerate(build_plan(), start=1):
                print(f"{index:02d}. {item}")
            print("No model, database, Docker, or service was changed.")
            return 0
        if arguments.command == "verify":
            path, report = verify_signoff_report(
                root=root,
                report_path=Path(arguments.report),
            )
            print("VisionFlow model release sign-off: VERIFIED")
            print(f"Status: {report['status']}")
            print(f"Report: {path}")
            return 0

        decision_path = (
            resolve_inside(root, arguments.decision, "모델 소크 결정")
            if arguments.decision
            else newest_artifact(root, DECISION_PATTERN, "모델 소크 결정")
        )
        report, chain = build_report(
            root=root,
            decision_path=decision_path,
            now=datetime.now(timezone.utc),
        )
        report_path, html_path, bundle_path, sidecar_path = write_signoff(
            output_directory=output_path(root, arguments.output),
            report=report,
            chain=chain,
        )
        verify_signoff_report(root=root, report_path=report_path)
        print(f"VisionFlow model release sign-off: {report['status']}")
        print(f"JSON report: {report_path}")
        print(f"HTML report: {html_path}")
        print(f"Evidence ZIP: {bundle_path}")
        print(f"SHA-256   : {sidecar_path}")
        return 0 if report["status"] == SIGNED_OFF_STATUS else 1
    except (
        ModelReleaseSignoffError,
        ModelSoakDecisionError,
        ModelSoakError,
        ModelReleaseError,
        ModelPromotionError,
        OSError,
        zipfile.BadZipFile,
    ) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
