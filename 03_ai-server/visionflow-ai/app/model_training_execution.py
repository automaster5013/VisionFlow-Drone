"""Explicit, fail-closed S1 training execution for VisionFlow Phase 2B-6D."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import platform
import re
import shutil
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.model_contract import load_json_object, sha256_file
from app.model_dataset_intake import DatasetIntakeError
from app.model_training_batch_calibration import (
    AUTOBATCH_MEMORY_FRACTION,
    AUTOBATCH_METHOD,
    AUTOBATCH_SYMBOL,
    CALIBRATED_NEXT_ACTION,
    CALIBRATED_STATUS,
    TRAINING_BATCH_CALIBRATION_CONTRACT_ID,
    TrainingBatchCalibrationError,
    build_training_batch_calibration_report,
)
from app.model_training_gpu_preflight import COCO_NAMES, VISDRONE_NAMES
from app.model_training_plan import TrainingPlanError, compile_training_plan

SCHEMA_VERSION = 1
S1_TRAINING_EXECUTION_CONTRACT_ID = "visionflow.phase2b6.s1-training-execution"
READY_STATUS = "READY_FOR_EXPLICIT_S1_TRAINING"
READY_NEXT_ACTION = "EXPLICIT_S1_TRAINING_APPROVAL_REQUIRED"
TRAINED_STATUS = "TRAINED_AWAITING_EVALUATION"
TRAINED_NEXT_ACTION = "LABELED_SMALL_OBJECT_EVALUATION_REQUIRED"
EXPECTED_STAGE = "VISDRONE_S1"
EXPECTED_PARENT_FILE = "yolo26m.pt"
EXPECTED_OUTPUT_FILE = "yolo26m-visdrone-s1-best.pt"
RUN_ROOT = Path("output/training-runs")
CANONICAL_WEIGHT_ROOT = Path("models")
RUN_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")

TorchProvider = Callable[[], object]
YoloFactory = Callable[[str], object]
Clock = Callable[[], datetime]


class S1TrainingExecutionError(ValueError):
    """Raised when S1 training evidence or output violates the execution contract."""


def _fail(message: str) -> None:
    raise S1TrainingExecutionError(message)


def _object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{field}은(는) JSON 객체여야 합니다.")
    return {str(key): item for key, item in value.items()}


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{field}은(는) 비어 있지 않은 문자열이어야 합니다.")
    return value.strip()


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(f"{field}은(는) {minimum} 이상의 정수여야 합니다.")
    return value


def _exact_keys(value: Mapping[str, object], expected: set[str], field: str) -> None:
    actual = set(value)
    if actual != expected:
        _fail(
            f"{field} 키가 계약과 다릅니다: "
            f"missing={sorted(expected - actual)}, unexpected={sorted(actual - expected)}"
        )


def _canonical_sha256(value: Mapping[str, object], receipt_field: str) -> str:
    payload = dict(value)
    payload.pop(receipt_field, None)
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _safe_existing_file(root: Path, raw_path: Path | str, field: str) -> Path:
    root = root.resolve()
    configured = Path(raw_path)
    lexical = configured if configured.is_absolute() else root / configured
    lexical = Path(os.path.abspath(lexical))
    try:
        relative = lexical.relative_to(root)
    except ValueError as error:
        raise S1TrainingExecutionError(
            f"{field}가 프로젝트 root 밖을 가리킵니다."
        ) from error
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            _fail(f"{field}에는 심볼릭 링크를 사용할 수 없습니다: {current}")
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as error:
        raise S1TrainingExecutionError(
            f"{field}을(를) 찾을 수 없습니다: {lexical}"
        ) from error
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise S1TrainingExecutionError(
            f"{field}가 프로젝트 root 밖을 가리킵니다."
        ) from error
    if not resolved.is_file():
        _fail(f"{field}은(는) 일반 파일이어야 합니다: {resolved}")
    return resolved


def _safe_new_path(root: Path, relative_path: Path, field: str) -> Path:
    root = root.resolve()
    if relative_path.is_absolute():
        _fail(f"{field}에는 프로젝트 root 기준 상대 경로만 허용됩니다.")
    lexical = Path(os.path.abspath(root / relative_path))
    try:
        parts = lexical.relative_to(root).parts
    except ValueError as error:
        raise S1TrainingExecutionError(
            f"{field}가 프로젝트 root 밖을 가리킵니다."
        ) from error
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            _fail(f"{field}에는 심볼릭 링크를 사용할 수 없습니다: {current}")
    if lexical.exists() or lexical.is_symlink():
        _fail(f"기존 {field}을(를) 덮어쓰지 않습니다: {lexical}")
    return lexical


def _validate_run_name(run_name: str) -> str:
    normalized = run_name.strip()
    if RUN_NAME_PATTERN.fullmatch(normalized) is None:
        _fail(
            "runName은 영숫자로 시작하는 1~80자의 영숫자·점·밑줄·하이픈만 "
            "허용합니다."
        )
    return normalized


def _verify_receipt_sha(
    receipt: Mapping[str, object], field: str, receipt_field: str
) -> str:
    claimed = receipt.get(receipt_field)
    if not isinstance(claimed, str) or re.fullmatch(r"[0-9a-f]{64}", claimed) is None:
        _fail(f"{field}.{receipt_field} 형식이 올바르지 않습니다.")
    if _canonical_sha256(receipt, receipt_field) != claimed:
        _fail(f"{field}.{receipt_field}가 receipt 내용과 다릅니다.")
    return claimed


def _expected_calibration_keys() -> set[str]:
    return {
        "schemaVersion",
        "contractId",
        "status",
        "stage",
        "nextAction",
        "plan",
        "datasetIntake",
        "gpuPreflight",
        "model",
        "dataset",
        "calibration",
        "runtime",
        "safeguards",
        "calibrationReceiptSha256",
    }


def _verify_calibration_receipt(
    *,
    root: Path,
    calibration_receipt_path: Path,
    current: Mapping[str, object],
    preflight_receipt_path: Path,
) -> tuple[dict[str, Any], Path]:
    path = _safe_existing_file(
        root,
        calibration_receipt_path,
        "trainingBatchCalibrationReceipt",
    )
    receipt = load_json_object(path)
    _exact_keys(receipt, _expected_calibration_keys(), "calibrationReceipt")
    if receipt.get("schemaVersion") != SCHEMA_VERSION:
        _fail("calibration receipt schemaVersion은 1이어야 합니다.")
    if receipt.get("contractId") != TRAINING_BATCH_CALIBRATION_CONTRACT_ID:
        _fail("calibration receipt 계약 ID가 Phase 2B-6C와 다릅니다.")
    if receipt.get("stage") != EXPECTED_STAGE:
        _fail("Phase 2B-6D는 VISDRONE_S1 학습만 허용합니다.")
    if (
        receipt.get("status") != CALIBRATED_STATUS
        or receipt.get("nextAction") != CALIBRATED_NEXT_ACTION
    ):
        _fail("calibration receipt가 실제 S1 학습 승인 대기 상태가 아닙니다.")
    _verify_receipt_sha(
        receipt,
        "calibrationReceipt",
        "calibrationReceiptSha256",
    )

    for field in (
        "plan",
        "datasetIntake",
        "gpuPreflight",
        "model",
        "dataset",
    ):
        if receipt.get(field) != current.get(field):
            _fail(f"calibration receipt의 {field} 증거가 현재 입력과 다릅니다.")

    model = _object(receipt.get("model"), "calibrationReceipt.model")
    if (
        model.get("parentFileName") != EXPECTED_PARENT_FILE
        or model.get("outputFileName") != EXPECTED_OUTPUT_FILE
    ):
        _fail("S1 부모·출력 가중치 파일명 계약이 다릅니다.")

    calibration = _object(
        receipt.get("calibration"),
        "calibrationReceipt.calibration",
    )
    expected_calibration = {
        "method": AUTOBATCH_METHOD,
        "symbol": AUTOBATCH_SYMBOL,
        "memoryFraction": AUTOBATCH_MEMORY_FRACTION,
        "imgsz": calibration.get("imgsz"),
        "amp": calibration.get("amp"),
        "plannedBatch": calibration.get("plannedBatch"),
        "recommendedBatch": calibration.get("recommendedBatch"),
        "batchStatus": "CALIBRATED",
        "planBatchMatchesRecommendation": True,
    }
    if calibration != expected_calibration:
        _fail("S1 batch calibration이 확정·일치 상태가 아닙니다.")
    planned_batch = _integer(
        calibration.get("plannedBatch"),
        "calibration.plannedBatch",
        minimum=1,
    )
    if calibration.get("recommendedBatch") != planned_batch:
        _fail("계획 batch와 GPU 추천 batch가 일치하지 않습니다.")

    preflight_path = _safe_existing_file(
        root,
        preflight_receipt_path,
        "trainingGpuPreflightReceipt",
    )
    preflight = load_json_object(preflight_path)
    preflight_runtime = _object(preflight.get("runtime"), "preflight.runtime")
    runtime = _object(receipt.get("runtime"), "calibrationReceipt.runtime")
    if runtime.get("mode") != "CONFIRMED_GPU_BATCH_CALIBRATION":
        _fail("calibration receipt가 실제 GPU calibration 증거가 아닙니다.")
    for field in (
        "ultralytics",
        "torch",
        "cudaRuntime",
        "deviceIndex",
        "deviceName",
        "computeCapability",
        "totalVramBytes",
    ):
        if runtime.get(field) != preflight_runtime.get(field):
            _fail(f"calibration runtime이 GPU preflight와 다릅니다: {field}")

    safeguards = _object(
        receipt.get("safeguards"),
        "calibrationReceipt.safeguards",
    )
    required_true = {
        "gpuAccessed",
        "torchImported",
        "ultralyticsImported",
        "modelLoaded",
        "trainingGraphProfiled",
        "batchCalibrated",
        "inputsUnchanged",
    }
    required_false = {
        "trainingExecuted",
        "yoloTrainCalled",
        "optimizerStepExecuted",
        "weightsPersisted",
        "planMutated",
        "dataMutated",
        "dockerAccessed",
    }
    if any(safeguards.get(field) is not True for field in required_true):
        _fail("calibration receipt의 GPU 보정 safeguard가 완전하지 않습니다.")
    if any(safeguards.get(field) is not False for field in required_false):
        _fail("calibration receipt가 학습 미실행 경계를 보장하지 않습니다.")
    return receipt, path


def _normalized_names(raw_names: object) -> dict[int, str]:
    if isinstance(raw_names, Mapping):
        try:
            return {int(key): str(value) for key, value in raw_names.items()}
        except (TypeError, ValueError) as error:
            raise S1TrainingExecutionError(
                "YOLO 클래스 매핑을 해석할 수 없습니다."
            ) from error
    if isinstance(raw_names, Sequence) and not isinstance(
        raw_names,
        (str, bytes, bytearray),
    ):
        return {index: str(value) for index, value in enumerate(raw_names)}
    _fail("YOLO 모델에 클래스 매핑이 없습니다.")


def _validate_model_identity(
    model: object,
    *,
    expected_names: Mapping[int, str],
    field: str,
) -> None:
    task = getattr(model, "task", None)
    if not task:
        task = getattr(getattr(model, "model", None), "task", None)
    if str(task or "") != "detect":
        _fail(f"{field} task는 detect여야 합니다.")
    if _normalized_names(getattr(model, "names", None)) != dict(expected_names):
        _fail(f"{field} 클래스 identity가 계약과 다릅니다.")


def _load_training_runtime(
    *,
    torch_provider: TorchProvider | None,
    yolo_factory: YoloFactory | None,
    expected_ultralytics: str,
) -> tuple[object, YoloFactory, str]:
    try:
        torch_module = (
            torch_provider()
            if torch_provider is not None
            else importlib.import_module("torch")
        )
        factory = yolo_factory
        observed_ultralytics = expected_ultralytics if factory is not None else ""
        if factory is None:
            ultralytics_module = importlib.import_module("ultralytics")
            observed_ultralytics = str(
                getattr(ultralytics_module, "__version__", "")
            ).strip()
            candidate = getattr(ultralytics_module, "YOLO", None)
            if candidate is None or not callable(candidate):
                _fail("Ultralytics YOLO factory를 찾을 수 없습니다.")
            factory = candidate
        if observed_ultralytics != expected_ultralytics:
            _fail("현재 Ultralytics 버전이 calibration receipt와 다릅니다.")
        return torch_module, factory, observed_ultralytics
    except S1TrainingExecutionError:
        raise
    except (ImportError, AttributeError, OSError, RuntimeError) as error:
        raise S1TrainingExecutionError(
            f"S1 학습 런타임을 불러올 수 없습니다: {error}"
        ) from error


def _verify_runtime(
    torch_module: object,
    expected: Mapping[str, object],
) -> dict[str, object]:
    cuda = getattr(torch_module, "cuda", None)
    if cuda is None or not bool(cuda.is_available()):
        _fail("CUDA를 사용할 수 없어 S1 학습을 실행할 수 없습니다.")
    device_index = _integer(
        expected.get("deviceIndex"),
        "calibration.runtime.deviceIndex",
    )
    if device_index >= int(cuda.device_count()):
        _fail("승인된 CUDA 장치가 현재 GPU 범위를 벗어났습니다.")
    cudnn = getattr(getattr(torch_module, "backends", None), "cudnn", None)
    if cudnn is not None and bool(getattr(cudnn, "benchmark", False)):
        _fail("재현 가능한 S1 학습에는 cudnn.benchmark=false가 필요합니다.")
    properties = cuda.get_device_properties(device_index)
    observed = {
        "python": platform.python_version(),
        "ultralytics": _text(expected.get("ultralytics"), "runtime.ultralytics"),
        "torch": str(getattr(torch_module, "__version__", "")).strip(),
        "cudaRuntime": str(
            getattr(getattr(torch_module, "version", None), "cuda", "")
        ).strip(),
        "deviceIndex": device_index,
        "deviceName": str(properties.name),
        "computeCapability": f"{int(properties.major)}.{int(properties.minor)}",
        "totalVramBytes": int(properties.total_memory),
    }
    for field in (
        "torch",
        "cudaRuntime",
        "deviceIndex",
        "deviceName",
        "computeCapability",
        "totalVramBytes",
    ):
        if observed[field] != expected.get(field):
            _fail(f"현재 학습 runtime이 calibration receipt와 다릅니다: {field}")
    return observed


def _timestamp(clock: Clock) -> str:
    value = clock()
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _artifact_evidence(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        _fail(f"학습 산출물은 심볼릭 링크가 아닌 일반 파일이어야 합니다: {path}")
    size = path.stat().st_size
    if size < 1:
        _fail(f"학습 산출물이 비어 있습니다: {path}")
    return {
        "path": str(path.resolve()),
        "sizeBytes": size,
        "sha256": sha256_file(path),
    }


def _atomic_promote(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(source, temporary)
        if sha256_file(temporary) != sha256_file(source):
            _fail("표준 S1 가중치 복사 후 SHA-256이 원본 best.pt와 다릅니다.")
        if target.exists() or target.is_symlink():
            _fail(f"기존 표준 S1 가중치를 덮어쓰지 않습니다: {target}")
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _compiled_arguments_from_plan_lock(
    *,
    root: Path,
    plan_path: Path,
    intake_receipt_path: Path,
    preflight_receipt_path: Path,
    ultralytics_version: str | None,
    image_probe: Callable[[Path], tuple[int, int]] | None,
) -> tuple[dict[str, object], dict[str, object]]:
    current = build_training_batch_calibration_report(
        root=root,
        plan_path=plan_path,
        intake_receipt_path=intake_receipt_path,
        preflight_receipt_path=preflight_receipt_path,
        confirm_gpu_batch_calibration=False,
        ultralytics_version=ultralytics_version,
        image_probe=image_probe,
    )
    readiness = compile_training_plan(
        root=root,
        plan_path=plan_path,
        ultralytics_version=ultralytics_version,
    )
    compiled = _object(readiness.get("compiledTraining"), "readiness.compiledTraining")
    arguments = _object(compiled.get("arguments"), "compiledTraining.arguments")
    return current, arguments


def build_s1_training_execution_report(
    *,
    root: Path,
    plan_path: Path,
    intake_receipt_path: Path,
    preflight_receipt_path: Path,
    calibration_receipt_path: Path,
    run_name: str,
    confirm_s1_training: bool = False,
    ultralytics_version: str | None = None,
    image_probe: Callable[[Path], tuple[int, int]] | None = None,
    torch_provider: TorchProvider | None = None,
    yolo_factory: YoloFactory | None = None,
    clock: Clock | None = None,
) -> dict[str, object]:
    """Re-lock all prior evidence and optionally execute exactly one S1 train call."""
    root = root.resolve()
    normalized_run_name = _validate_run_name(run_name)
    current, arguments = _compiled_arguments_from_plan_lock(
        root=root,
        plan_path=plan_path,
        intake_receipt_path=intake_receipt_path,
        preflight_receipt_path=preflight_receipt_path,
        ultralytics_version=ultralytics_version,
        image_probe=image_probe,
    )
    calibration, calibration_path = _verify_calibration_receipt(
        root=root,
        calibration_receipt_path=calibration_receipt_path,
        current=current,
        preflight_receipt_path=preflight_receipt_path,
    )
    calibration_block = _object(calibration["calibration"], "calibration.calibration")
    if arguments.get("batch") != calibration_block.get("plannedBatch"):
        _fail("현재 계획의 batch가 calibration receipt와 다릅니다.")
    if current.get("stage") != EXPECTED_STAGE:
        _fail("Phase 2B-6D는 VISDRONE_S1 학습만 허용합니다.")

    run_directory = _safe_new_path(
        root,
        RUN_ROOT / normalized_run_name,
        "S1 training run directory",
    )
    canonical_weight = _safe_new_path(
        root,
        CANONICAL_WEIGHT_ROOT / EXPECTED_OUTPUT_FILE,
        "표준 S1 가중치",
    )
    input_hashes = {
        "plan": sha256_file(_safe_existing_file(root, plan_path, "planPath")),
        "intake": sha256_file(
            _safe_existing_file(root, intake_receipt_path, "datasetIntakeReceipt")
        ),
        "preflight": sha256_file(
            _safe_existing_file(root, preflight_receipt_path, "gpuPreflightReceipt")
        ),
        "calibration": sha256_file(calibration_path),
        "parent": str(_object(current["model"], "current.model")["parentSha256"]),
    }
    controlled_arguments = {
        **arguments,
        "project": str((root / RUN_ROOT).resolve()),
        "name": normalized_run_name,
        "exist_ok": False,
        "resume": False,
    }
    status = READY_STATUS
    next_action = READY_NEXT_ACTION
    now = clock or (lambda: datetime.now(UTC))
    started_at: str | None = None
    completed_at: str | None = None
    runtime: dict[str, object] = {
        "mode": "CPU_CHECK_ONLY",
        "python": None,
        "ultralytics": str(_object(calibration["runtime"], "runtime")["ultralytics"]),
        "torch": None,
        "cudaRuntime": None,
        "deviceIndex": None,
        "deviceName": None,
        "computeCapability": None,
        "totalVramBytes": None,
    }
    artifacts: dict[str, object] = {
        "runDirectory": None,
        "bestCheckpoint": None,
        "lastCheckpoint": None,
        "canonicalWeight": None,
    }

    if confirm_s1_training:
        expected_runtime = _object(calibration["runtime"], "calibration.runtime")
        torch_module, factory, observed_ultralytics = _load_training_runtime(
            torch_provider=torch_provider,
            yolo_factory=yolo_factory,
            expected_ultralytics=str(expected_runtime["ultralytics"]),
        )
        runtime = {
            "mode": "CONFIRMED_S1_TRAINING",
            **_verify_runtime(torch_module, expected_runtime),
            "ultralytics": observed_ultralytics,
        }
        if arguments.get("device") != str(runtime["deviceIndex"]):
            _fail("학습 계획의 device가 승인된 calibration CUDA 장치와 다릅니다.")
        parent_path = _safe_existing_file(
            root,
            str(_object(current["model"], "current.model")["parentPath"]),
            "S1 parent weight",
        )
        parent_model = factory(str(parent_path))
        _validate_model_identity(
            parent_model,
            expected_names=COCO_NAMES,
            field="S1 parent model",
        )
        train = getattr(parent_model, "train", None)
        if train is None or not callable(train):
            _fail("S1 부모 YOLO 모델에 train()이 없습니다.")
        started_at = _timestamp(now)
        try:
            result = train(**controlled_arguments)
        except (MemoryError, OSError, RuntimeError, TypeError, ValueError) as error:
            raise S1TrainingExecutionError(f"S1 YOLO.train()이 실패했습니다: {error}") from error
        completed_at = _timestamp(now)
        trainer = getattr(parent_model, "trainer", None)
        raw_save_dir = getattr(result, "save_dir", None) or getattr(
            trainer,
            "save_dir",
            None,
        )
        if raw_save_dir is None:
            _fail("Ultralytics 학습 결과에서 save_dir를 확인할 수 없습니다.")
        observed_save_dir = Path(str(raw_save_dir)).resolve()
        if observed_save_dir != run_directory.resolve():
            _fail("Ultralytics save_dir가 승인된 S1 run directory와 다릅니다.")
        best_checkpoint = run_directory / "weights/best.pt"
        last_checkpoint = run_directory / "weights/last.pt"
        best_evidence = _artifact_evidence(best_checkpoint)
        last_evidence = _artifact_evidence(last_checkpoint)
        trained_model = factory(str(best_checkpoint))
        _validate_model_identity(
            trained_model,
            expected_names=VISDRONE_NAMES,
            field="trained S1 best model",
        )

        post_current, post_arguments = _compiled_arguments_from_plan_lock(
            root=root,
            plan_path=plan_path,
            intake_receipt_path=intake_receipt_path,
            preflight_receipt_path=preflight_receipt_path,
            ultralytics_version=ultralytics_version,
            image_probe=image_probe,
        )
        post_calibration, post_calibration_path = _verify_calibration_receipt(
            root=root,
            calibration_receipt_path=calibration_receipt_path,
            current=post_current,
            preflight_receipt_path=preflight_receipt_path,
        )
        post_hashes = {
            "plan": sha256_file(_safe_existing_file(root, plan_path, "planPath")),
            "intake": sha256_file(
                _safe_existing_file(root, intake_receipt_path, "datasetIntakeReceipt")
            ),
            "preflight": sha256_file(
                _safe_existing_file(root, preflight_receipt_path, "gpuPreflightReceipt")
            ),
            "calibration": sha256_file(post_calibration_path),
            "parent": str(
                _object(post_current["model"], "postCurrent.model")["parentSha256"]
            ),
        }
        if (
            post_hashes != input_hashes
            or post_arguments != arguments
            or post_calibration != calibration
        ):
            _fail("S1 학습 중 계획·데이터·receipt·부모 가중치가 변경되었습니다.")
        _atomic_promote(best_checkpoint, canonical_weight)
        canonical_evidence = _artifact_evidence(canonical_weight)
        if canonical_evidence["sha256"] != best_evidence["sha256"]:
            _fail("표준 S1 가중치와 best checkpoint SHA-256이 다릅니다.")
        artifacts = {
            "runDirectory": str(run_directory.resolve()),
            "bestCheckpoint": best_evidence,
            "lastCheckpoint": last_evidence,
            "canonicalWeight": canonical_evidence,
        }
        status = TRAINED_STATUS
        next_action = TRAINED_NEXT_ACTION

    report: dict[str, object] = {
        "schemaVersion": SCHEMA_VERSION,
        "contractId": S1_TRAINING_EXECUTION_CONTRACT_ID,
        "status": status,
        "stage": EXPECTED_STAGE,
        "nextAction": next_action,
        "approval": {
            "explicitS1TrainingConfirmed": confirm_s1_training,
            "gpuBatchCalibrated": True,
            "resumeAllowed": False,
            "overwriteAllowed": False,
        },
        "plan": current["plan"],
        "datasetIntake": current["datasetIntake"],
        "gpuPreflight": current["gpuPreflight"],
        "batchCalibration": {
            "path": str(calibration_path),
            "fileSha256": input_hashes["calibration"],
            "receiptSha256": str(calibration["calibrationReceiptSha256"]),
            "status": str(calibration["status"]),
        },
        "model": current["model"],
        "dataset": current["dataset"],
        "training": {
            "runName": normalized_run_name,
            "arguments": controlled_arguments,
            "startedAt": started_at,
            "completedAt": completed_at,
        },
        "runtime": runtime,
        "artifacts": artifacts,
        "safeguards": {
            "trainingExecuted": confirm_s1_training,
            "yoloTrainCalled": confirm_s1_training,
            "weightsPersisted": confirm_s1_training,
            "canonicalWeightPromoted": confirm_s1_training,
            "manifestMaterialized": False,
            "activationEligible": False,
            "evaluationMeasured": False,
            "planMutated": False,
            "dataMutated": False,
            "dockerAccessed": False,
            "gpuAccessed": confirm_s1_training,
            "torchImported": confirm_s1_training,
            "ultralyticsImported": confirm_s1_training,
            "inputsUnchanged": True,
        },
    }
    report["executionReceiptSha256"] = _canonical_sha256(
        report,
        "executionReceiptSha256",
    )
    return report


def write_s1_training_execution_report(
    root: Path,
    output: str,
    report: Mapping[str, object],
) -> Path:
    target = _safe_new_path(root.resolve(), Path(output), "S1 training receipt")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Re-lock Phase 2B-5/6A/6B/6C evidence and execute VISDRONE_S1 "
            "training only after an explicit confirmation flag."
        )
    )
    parser.add_argument("--root", default=".", help="VisionFlow AI project root")
    parser.add_argument("--plan", required=True, help="Concrete VISDRONE_S1 plan")
    parser.add_argument("--intake-receipt", required=True)
    parser.add_argument("--preflight-receipt", required=True)
    parser.add_argument("--calibration-receipt", required=True)
    parser.add_argument("--run-name", required=True)
    parser.add_argument(
        "--confirm-s1-training",
        action="store_true",
        help="Explicitly allow one guarded YOLO.train() call on the approved GPU",
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument(
        "--output",
        help="New execution receipt under --root (existing files are refused)",
    )
    output.add_argument(
        "--check-only",
        action="store_true",
        help="Validate and print readiness without training or writing (default)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.confirm_s1_training and not arguments.output:
        print(
            "VISIONFLOW_PHASE2B6_S1_TRAINING_EXECUTION=FAIL "
            "error=명시 학습에는 새 --output receipt 경로가 필요합니다.",
            file=sys.stderr,
        )
        return 1
    root = Path(arguments.root).resolve()
    try:
        if arguments.output:
            _safe_new_path(
                root,
                Path(arguments.output),
                "S1 training receipt",
            )
        report = build_s1_training_execution_report(
            root=root,
            plan_path=Path(arguments.plan),
            intake_receipt_path=Path(arguments.intake_receipt),
            preflight_receipt_path=Path(arguments.preflight_receipt),
            calibration_receipt_path=Path(arguments.calibration_receipt),
            run_name=arguments.run_name,
            confirm_s1_training=arguments.confirm_s1_training,
        )
        if arguments.output:
            target = write_s1_training_execution_report(
                root,
                arguments.output,
                report,
            )
            print(
                "VISIONFLOW_PHASE2B6_S1_TRAINING_EXECUTION="
                f"{report['status']} output={target}"
            )
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))
    except (
        DatasetIntakeError,
        S1TrainingExecutionError,
        TrainingBatchCalibrationError,
        TrainingPlanError,
        OSError,
        ValueError,
    ) as error:
        print(
            f"VISIONFLOW_PHASE2B6_S1_TRAINING_EXECUTION=FAIL error={error}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
