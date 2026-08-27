"""Controlled GPU batch calibration for VisionFlow Phase 2B-6C."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.model_contract import load_json_object, sha256_file
from app.model_dataset_intake import (
    DATASET_INTAKE_CONTRACT_ID,
    DatasetIntakeError,
    build_dataset_intake_report,
)
from app.model_training_gpu_preflight import (
    COCO_NAMES,
    GPU_NEXT_ACTION,
    GPU_STATUS,
    TRAINING_GPU_PREFLIGHT_CONTRACT_ID,
    VISDRONE_NAMES,
)
from app.model_training_plan import (
    TrainingPlanError,
    compile_training_plan,
)

SCHEMA_VERSION = 1
TRAINING_BATCH_CALIBRATION_CONTRACT_ID = (
    "visionflow.phase2b6.training-batch-calibration"
)
CPU_STATUS = "READY_FOR_EXPLICIT_GPU_BATCH_CALIBRATION"
CALIBRATED_STATUS = "READY_FOR_TRAINING_APPROVAL"
PLAN_UPDATE_STATUS = "PLAN_BATCH_UPDATE_REQUIRED"
CPU_NEXT_ACTION = "EXPLICIT_GPU_BATCH_CALIBRATION_REQUIRED"
CALIBRATED_NEXT_ACTION = "EXPLICIT_TRAINING_APPROVAL_REQUIRED"
PLAN_UPDATE_NEXT_ACTION = "UPDATE_PLAN_BATCH_AND_RERUN_PHASE2B6A_6B_6C"
AUTOBATCH_METHOD = "VISIONFLOW_BOUNDED_ULTRALYTICS_PROFILE_OPS"
AUTOBATCH_SYMBOL = "ultralytics.utils.torch_utils.profile_ops"
AUTOBATCH_MEMORY_FRACTION = 0.60
AUTOBATCH_CANDIDATE_POLICY = "POWERS_OF_TWO_UP_TO_PLANNED_BATCH"

TorchProvider = Callable[[], object]
YoloFactory = Callable[[str], object]
BatchProbe = Callable[..., Sequence[object | None]]


class TrainingBatchCalibrationError(ValueError):
    """Raised when training batch calibration evidence is unsafe or stale."""


def _fail(message: str) -> None:
    raise TrainingBatchCalibrationError(message)


def _object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{field}은(는) JSON 객체여야 합니다.")
    return {str(key): item for key, item in value.items()}


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(f"{field}은(는) {minimum} 이상의 정수여야 합니다.")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{field}은(는) 비어 있지 않은 문자열이어야 합니다.")
    return value.strip()


def _exact_keys(
    value: Mapping[str, object], expected: set[str], field: str
) -> None:
    actual = set(value)
    if actual == expected:
        return
    _fail(
        f"{field} 키가 계약과 다릅니다: "
        f"missing={sorted(expected - actual)}, unexpected={sorted(actual - expected)}"
    )


def _canonical_sha256(value: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _safe_file(root: Path, raw_path: Path | str, field: str) -> Path:
    root = root.resolve()
    configured = Path(raw_path)
    lexical = configured if configured.is_absolute() else root / configured
    lexical = Path(os.path.abspath(lexical))
    try:
        relative = lexical.relative_to(root)
    except ValueError as error:
        raise TrainingBatchCalibrationError(
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
        raise TrainingBatchCalibrationError(
            f"{field}을(를) 찾을 수 없습니다: {lexical}"
        ) from error
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise TrainingBatchCalibrationError(
            f"{field}가 프로젝트 root 밖을 가리킵니다."
        ) from error
    if not resolved.is_file():
        _fail(f"{field}은(는) 일반 파일이어야 합니다: {resolved}")
    return resolved


def _verify_receipt_sha(
    receipt: Mapping[str, object],
    field: str,
    receipt_field: str,
) -> str:
    claimed = receipt.get(receipt_field)
    if not isinstance(claimed, str) or re.fullmatch(r"[0-9a-f]{64}", claimed) is None:
        _fail(f"{field}.{receipt_field} 형식이 올바르지 않습니다.")
    content = dict(receipt)
    content.pop(receipt_field, None)
    if _canonical_sha256(content) != claimed:
        _fail(f"{field}.{receipt_field}가 receipt 내용과 다릅니다.")
    return claimed


def _load_current_intake(
    *,
    root: Path,
    plan_path: Path,
    intake_receipt_path: Path,
    ultralytics_version: str | None,
    image_probe: Callable[[Path], tuple[int, int]] | None,
) -> tuple[dict[str, Any], Path]:
    expected = build_dataset_intake_report(
        root=root,
        plan_path=plan_path,
        ultralytics_version=ultralytics_version,
        image_probe=image_probe,
    )
    path = _safe_file(root, intake_receipt_path, "datasetIntakeReceipt")
    receipt = load_json_object(path)
    if receipt.get("schemaVersion") != SCHEMA_VERSION:
        _fail("dataset intake receipt schemaVersion은 1이어야 합니다.")
    if receipt.get("contractId") != DATASET_INTAKE_CONTRACT_ID:
        _fail("dataset intake receipt 계약 ID가 Phase 2B-6A와 다릅니다.")
    if receipt.get("status") != "READY":
        _fail("dataset intake receipt 상태가 READY가 아닙니다.")
    _verify_receipt_sha(receipt, "datasetIntakeReceipt", "receiptSha256")
    if receipt != expected:
        _fail(
            "dataset intake receipt가 현재 계획·데이터 full fingerprint "
            "재계산 결과와 다릅니다."
        )
    return receipt, path


def _expected_preflight_keys() -> set[str]:
    return {
        "schemaVersion",
        "contractId",
        "status",
        "stage",
        "nextAction",
        "plan",
        "datasetIntake",
        "model",
        "dataset",
        "training",
        "runtime",
        "modelProbe",
        "safeguards",
        "preflightReceiptSha256",
    }


def _verify_preflight_receipt(
    *,
    root: Path,
    receipt_path: Path,
    readiness: Mapping[str, object],
    intake: Mapping[str, object],
    intake_path: Path,
) -> tuple[dict[str, Any], Path]:
    path = _safe_file(root, receipt_path, "trainingGpuPreflightReceipt")
    receipt = load_json_object(path)
    _exact_keys(receipt, _expected_preflight_keys(), "trainingGpuPreflightReceipt")
    if receipt.get("schemaVersion") != SCHEMA_VERSION:
        _fail("training GPU preflight receipt schemaVersion은 1이어야 합니다.")
    if receipt.get("contractId") != TRAINING_GPU_PREFLIGHT_CONTRACT_ID:
        _fail("training GPU preflight receipt 계약 ID가 Phase 2B-6B와 다릅니다.")
    if (
        receipt.get("status") != GPU_STATUS
        or receipt.get("nextAction") != GPU_NEXT_ACTION
    ):
        _fail("training GPU preflight receipt가 batch calibration 준비 상태가 아닙니다.")
    _verify_receipt_sha(
        receipt,
        "trainingGpuPreflightReceipt",
        "preflightReceiptSha256",
    )

    plan = _object(receipt.get("plan"), "trainingGpuPreflightReceipt.plan")
    model = _object(receipt.get("model"), "trainingGpuPreflightReceipt.model")
    dataset = _object(receipt.get("dataset"), "trainingGpuPreflightReceipt.dataset")
    training = _object(receipt.get("training"), "trainingGpuPreflightReceipt.training")
    linked_intake = _object(
        receipt.get("datasetIntake"),
        "trainingGpuPreflightReceipt.datasetIntake",
    )
    runtime = _object(receipt.get("runtime"), "trainingGpuPreflightReceipt.runtime")
    model_probe = _object(
        receipt.get("modelProbe"),
        "trainingGpuPreflightReceipt.modelProbe",
    )
    safeguards = _object(
        receipt.get("safeguards"),
        "trainingGpuPreflightReceipt.safeguards",
    )
    ready_plan = _object(readiness.get("plan"), "readiness.plan")
    ready_model = _object(readiness.get("model"), "readiness.model")
    parent = _object(ready_model.get("parent"), "readiness.model.parent")
    ready_data = _object(readiness.get("data"), "readiness.data")
    compiled = _object(readiness.get("compiledTraining"), "readiness.compiledTraining")
    arguments = _object(compiled.get("arguments"), "compiledTraining.arguments")
    ready_runtime = _object(readiness.get("runtime"), "readiness.runtime")
    intake_dataset = _object(intake.get("dataset"), "datasetIntake.dataset")

    expected_plan = {
        "path": str(ready_plan["path"]),
        "sha256": str(ready_plan["sha256"]),
        "evidenceLockSha256": str(readiness["evidenceLockSha256"]),
    }
    expected_linked_intake = {
        "path": str(intake_path),
        "fileSha256": sha256_file(intake_path),
        "receiptSha256": str(intake["receiptSha256"]),
        "combinedFingerprintSha256": str(
            intake_dataset["combinedFingerprintSha256"]
        ),
    }
    expected_model = {
        "parentPath": str(parent["path"]),
        "parentFileName": str(parent["fileName"]),
        "parentSha256": str(parent["sha256"]),
        "outputFileName": str(ready_model["outputFileName"]),
    }
    expected_dataset = {
        "dataYamlSha256": str(ready_data["dataYamlSha256"]),
        "splitManifestSha256": str(ready_data["splitManifestSha256"]),
        "classCount": len(VISDRONE_NAMES),
        "splitUnit": str(ready_data["splitUnit"]),
    }
    expected_training = {
        "requestedDevice": str(arguments["device"]),
        "imgsz": int(arguments["imgsz"]),
        "plannedBatch": int(arguments["batch"]),
        "batchStatus": "PROVISIONAL",
    }
    if plan != expected_plan:
        _fail("training GPU preflight의 계획 증거가 현재 readiness와 다릅니다.")
    if linked_intake != expected_linked_intake:
        _fail("training GPU preflight의 intake 증거가 현재 receipt와 다릅니다.")
    if model != expected_model or dataset != expected_dataset:
        _fail("training GPU preflight의 모델·데이터 증거가 현재 입력과 다릅니다.")
    if training != expected_training:
        _fail("training GPU preflight의 batch 계획 증거가 현재 계획과 다릅니다.")
    if receipt.get("stage") != readiness.get("stage"):
        _fail("training GPU preflight stage가 현재 계획과 다릅니다.")
    if runtime.get("mode") != "CONFIRMED_GPU_PROBE":
        _fail("training GPU preflight가 실제 GPU probe receipt가 아닙니다.")
    if runtime.get("ultralytics") != ready_runtime.get("ultralytics"):
        _fail("training GPU preflight Ultralytics 버전이 readiness와 다릅니다.")
    device_index = _device_index(arguments.get("device"))
    if runtime.get("deviceIndex") != device_index:
        _fail("training GPU preflight CUDA device가 현재 계획과 다릅니다.")
    expected_class_count = (
        len(COCO_NAMES)
        if readiness.get("stage") == "VISDRONE_S1"
        else len(VISDRONE_NAMES)
    )
    expected_probe = {
        "loaded": True,
        "device": f"cuda:{device_index}",
        "task": "detect",
        "classCount": expected_class_count,
    }
    if model_probe != expected_probe:
        _fail("training GPU preflight 부모 모델 identity가 완전하지 않습니다.")
    expected_safeguards = {
        "trainingExecuted": False,
        "batchCalibrated": False,
        "dockerAccessed": False,
        "dataMutated": False,
        "gpuAccessed": True,
        "torchImported": True,
        "ultralyticsImported": True,
        "modelLoaded": True,
    }
    if safeguards != expected_safeguards:
        _fail("training GPU preflight safeguard가 GPU probe 계약과 다릅니다.")
    for field in (
        "torch",
        "cudaRuntime",
        "deviceName",
        "computeCapability",
        "totalVramBytes",
        "freeVramBytesAfterModelLoad",
    ):
        if runtime.get(field) is None:
            _fail(f"training GPU preflight runtime 증거가 없습니다: {field}")
    return receipt, path


def _device_index(raw_device: object) -> int:
    if not isinstance(raw_device, str) or re.fullmatch(r"\d+", raw_device) is None:
        _fail("plan.training.device는 단일 CUDA 인덱스여야 합니다.")
    return int(raw_device)


def _normalized_names(raw_names: object) -> dict[int, str]:
    if isinstance(raw_names, Mapping):
        try:
            return {int(key): str(value) for key, value in raw_names.items()}
        except (TypeError, ValueError) as error:
            raise TrainingBatchCalibrationError(
                "로드한 부모 모델의 클래스 매핑을 해석할 수 없습니다."
            ) from error
    if isinstance(raw_names, Sequence) and not isinstance(
        raw_names, (str, bytes, bytearray)
    ):
        return {index: str(value) for index, value in enumerate(raw_names)}
    _fail("로드한 부모 모델에 클래스 매핑이 없습니다.")


def _validate_model_identity(stage: str, model: object) -> object:
    task = getattr(model, "task", None)
    if not task:
        task = getattr(getattr(model, "model", None), "task", None)
    if str(task or "") != "detect":
        _fail("부모 YOLO 모델 task는 detect여야 합니다.")
    names = _normalized_names(getattr(model, "names", None))
    expected = COCO_NAMES if stage == "VISDRONE_S1" else VISDRONE_NAMES
    if names != expected:
        _fail("부모 YOLO 모델 클래스 identity가 현재 학습 stage와 다릅니다.")
    inner = getattr(model, "model", None)
    if inner is None:
        _fail("AutoBatch에 전달할 내부 PyTorch 모델이 없습니다.")
    return inner


def _load_gpu_components(
    *,
    torch_provider: TorchProvider | None,
    yolo_factory: YoloFactory | None,
    batch_probe: BatchProbe | None,
) -> tuple[object, YoloFactory, BatchProbe, str]:
    try:
        torch_module = (
            torch_provider()
            if torch_provider is not None
            else importlib.import_module("torch")
        )
        imported_ultralytics = ""
        factory = yolo_factory
        probe = batch_probe
        if factory is None:
            ultralytics_module = importlib.import_module("ultralytics")
            imported_ultralytics = str(
                getattr(ultralytics_module, "__version__", "")
            ).strip()
            candidate = getattr(ultralytics_module, "YOLO", None)
            if candidate is None or not callable(candidate):
                _fail("Ultralytics YOLO factory를 찾을 수 없습니다.")
            factory = candidate
        if probe is None:
            torch_utils_module = importlib.import_module(
                "ultralytics.utils.torch_utils"
            )
            candidate = getattr(torch_utils_module, "profile_ops", None)
            if candidate is None or not callable(candidate):
                _fail("Ultralytics profile_ops 함수를 찾을 수 없습니다.")
            probe = candidate
        return torch_module, factory, probe, imported_ultralytics
    except TrainingBatchCalibrationError:
        raise
    except (ImportError, AttributeError, OSError, RuntimeError) as error:
        raise TrainingBatchCalibrationError(
            f"GPU batch calibration 런타임을 불러올 수 없습니다: {error}"
        ) from error


def _cuda_metric(cuda: object, name: str, device_index: int) -> int:
    method = getattr(cuda, name, None)
    if method is None or not callable(method):
        _fail(f"CUDA 메모리 계측 함수를 찾을 수 없습니다: {name}")
    return int(method(device_index))


def _bounded_candidate_batches(
    planned_batch: int,
    train_image_count: int,
) -> list[int]:
    ceiling = min(planned_batch, train_image_count, 1024)
    candidates: list[int] = []
    value = 1
    while value <= ceiling:
        candidates.append(value)
        value *= 2
    if candidates[-1] != ceiling:
        candidates.append(ceiling)
    return candidates


def _profile_memory_gb(profile: object | None) -> float | None:
    if profile is None:
        return None
    if not isinstance(profile, Sequence) or isinstance(
        profile,
        (str, bytes, bytearray),
    ):
        _fail("Ultralytics profile_ops 결과 형식이 올바르지 않습니다.")
    if len(profile) < 3:
        _fail("Ultralytics profile_ops 결과에 메모리 증거가 없습니다.")
    raw_memory = profile[2]
    if isinstance(raw_memory, bool) or not isinstance(raw_memory, (int, float)):
        _fail("Ultralytics profile_ops 메모리 증거가 숫자가 아닙니다.")
    memory_gb = float(raw_memory)
    if memory_gb <= 0.0:
        _fail("Ultralytics profile_ops 메모리 증거는 양수여야 합니다.")
    return memory_gb


def _run_gpu_calibration(
    *,
    stage: str,
    parent_path: Path,
    device_index: int,
    imgsz: int,
    amp: bool,
    planned_batch: int,
    train_image_count: int,
    maximum_objects_per_image: int,
    preflight_runtime: Mapping[str, object],
    torch_provider: TorchProvider | None,
    yolo_factory: YoloFactory | None,
    batch_probe: BatchProbe | None,
) -> tuple[int, list[dict[str, object]], float, dict[str, object]]:
    torch_module, factory, probe, imported_ultralytics = _load_gpu_components(
        torch_provider=torch_provider,
        yolo_factory=yolo_factory,
        batch_probe=batch_probe,
    )
    expected_ultralytics = _text(
        preflight_runtime.get("ultralytics"),
        "preflight.runtime.ultralytics",
    )
    if imported_ultralytics and imported_ultralytics != expected_ultralytics:
        _fail("현재 Ultralytics 버전이 GPU preflight receipt와 다릅니다.")
    cuda = getattr(torch_module, "cuda", None)
    if cuda is None or not bool(cuda.is_available()):
        _fail("CUDA를 사용할 수 없어 GPU batch calibration을 진행할 수 없습니다.")
    if device_index < 0 or device_index >= int(cuda.device_count()):
        _fail("학습 계획의 CUDA device가 사용 가능한 GPU 범위를 벗어났습니다.")
    cudnn = getattr(getattr(torch_module, "backends", None), "cudnn", None)
    if cudnn is not None and bool(getattr(cudnn, "benchmark", False)):
        _fail("재현 가능한 AutoBatch에는 torch.backends.cudnn.benchmark=false가 필요합니다.")
    properties = cuda.get_device_properties(device_index)
    device_name = str(properties.name)
    total_vram = int(properties.total_memory)
    compute_capability = f"{int(properties.major)}.{int(properties.minor)}"
    torch_version = str(getattr(torch_module, "__version__", "")).strip()
    cuda_runtime = str(getattr(getattr(torch_module, "version", None), "cuda", ""))
    expected_runtime = {
        "torch": torch_version,
        "cudaRuntime": cuda_runtime,
        "deviceIndex": device_index,
        "deviceName": device_name,
        "computeCapability": compute_capability,
        "totalVramBytes": total_vram,
    }
    for field, value in expected_runtime.items():
        if preflight_runtime.get(field) != value:
            _fail(f"현재 GPU runtime이 preflight receipt와 다릅니다: {field}")

    model = factory(str(parent_path))
    move = getattr(model, "to", None)
    if move is None or not callable(move):
        _fail("부모 YOLO 모델을 CUDA 장치로 이동할 수 없습니다.")
    move(f"cuda:{device_index}")
    inner = _validate_model_identity(stage, model)
    train_method = getattr(inner, "train", None)
    if train_method is None or not callable(train_method):
        _fail("AutoBatch에 전달할 내부 PyTorch 모델을 train 모드로 전환할 수 없습니다.")
    try:
        inner_copy = deepcopy(inner)
    except (MemoryError, OSError, RuntimeError, TypeError, ValueError) as error:
        raise TrainingBatchCalibrationError(
            f"bounded AutoBatch 모델 복제가 실패했습니다: {error}"
        ) from error
    copied_train_method = getattr(inner_copy, "train", None)
    if copied_train_method is None or not callable(copied_train_method):
        _fail("복제한 AutoBatch 모델을 train 모드로 전환할 수 없습니다.")
    inner_copy = copied_train_method()
    free_before, reported_total = cuda.mem_get_info(device_index)
    if int(reported_total) != total_vram:
        _fail("CUDA VRAM 총량 보고가 일관되지 않습니다.")
    allocated_before = _cuda_metric(cuda, "memory_allocated", device_index)
    reserved_before = _cuda_metric(cuda, "memory_reserved", device_index)
    if allocated_before < 0 or reserved_before < 0:
        _fail("CUDA 초기 메모리 계측값은 음수일 수 없습니다.")
    if allocated_before >= total_vram or reserved_before > total_vram:
        _fail("CUDA 초기 메모리 계측값이 GPU 총량을 벗어났습니다.")
    total_vram_gib = total_vram / float(1 << 30)
    available_vram_gib = total_vram_gib - (
        allocated_before + reserved_before
    ) / float(1 << 30)
    profile_memory_target_gb = float(
        round(available_vram_gib * AUTOBATCH_MEMORY_FRACTION)
    )
    if profile_memory_target_gb <= 0.0:
        _fail("60% AutoBatch 메모리 목표가 0 GB 이하입니다.")
    candidate_batches = _bounded_candidate_batches(
        planned_batch,
        train_image_count,
    )
    reset = getattr(cuda, "reset_peak_memory_stats", None)
    if reset is None or not callable(reset):
        _fail("CUDA peak memory 초기화 함수를 찾을 수 없습니다.")
    reset(device_index)
    try:
        empty = getattr(torch_module, "empty", None)
        device_factory = getattr(torch_module, "device", None)
        autocast_factory = getattr(torch_module, "autocast", None)
        if empty is None or not callable(empty):
            _fail("PyTorch empty tensor factory를 찾을 수 없습니다.")
        if device_factory is None or not callable(device_factory):
            _fail("PyTorch CUDA device factory를 찾을 수 없습니다.")
        if autocast_factory is None or not callable(autocast_factory):
            _fail("PyTorch autocast context를 찾을 수 없습니다.")
        inputs = [
            empty(batch, 3, imgsz, imgsz)
            for batch in candidate_batches
        ]
        with autocast_factory(device_type="cuda", enabled=amp):
            profiles = probe(
                inputs,
                inner_copy,
                n=1,
                device=device_factory(f"cuda:{device_index}"),
                max_num_obj=maximum_objects_per_image,
            )
        synchronize = getattr(cuda, "synchronize", None)
        if synchronize is not None and callable(synchronize):
            synchronize(device_index)
    except (MemoryError, OSError, RuntimeError, TypeError, ValueError) as error:
        raise TrainingBatchCalibrationError(
            f"bounded Ultralytics AutoBatch 프로파일이 실패했습니다: {error}"
        ) from error
    if not isinstance(profiles, Sequence) or isinstance(
        profiles,
        (str, bytes, bytearray),
    ):
        _fail("Ultralytics profile_ops가 후보별 결과 목록을 반환하지 않았습니다.")
    if len(profiles) != len(candidate_batches):
        _fail("Ultralytics profile_ops 후보 수와 결과 수가 다릅니다.")
    candidate_profiles: list[dict[str, object]] = []
    safe_candidates: list[int] = []
    for batch, profile in zip(candidate_batches, profiles, strict=True):
        memory_gb = _profile_memory_gb(profile)
        within_target = (
            memory_gb is not None
            and memory_gb <= profile_memory_target_gb
            and memory_gb < total_vram_gib
        )
        candidate_profiles.append(
            {
                "batch": batch,
                "usable": memory_gb is not None,
                "profileMemoryGb": memory_gb,
                "withinMemoryTarget": within_target,
            }
        )
        if within_target:
            safe_candidates.append(batch)
    if not safe_candidates:
        _fail("60% VRAM 목표를 만족하는 bounded AutoBatch 후보가 없습니다.")
    recommended = max(safe_candidates)
    peak_allocated = _cuda_metric(cuda, "max_memory_allocated", device_index)
    peak_reserved = _cuda_metric(cuda, "max_memory_reserved", device_index)
    free_after, reported_total_after = cuda.mem_get_info(device_index)
    if int(reported_total_after) != total_vram:
        _fail("AutoBatch 후 CUDA VRAM 총량 보고가 일관되지 않습니다.")
    if peak_allocated <= allocated_before:
        _fail("AutoBatch 학습 그래프의 peak VRAM 증가가 없어 fallback으로 판단됩니다.")
    if peak_allocated >= total_vram:
        _fail("AutoBatch peak allocated VRAM이 GPU 총량 이상입니다.")
    if peak_reserved < peak_allocated or peak_reserved > total_vram:
        _fail("AutoBatch peak reserved VRAM 계측값이 일관되지 않습니다.")
    if int(free_before) < 0 or int(free_after) < 0:
        _fail("CUDA free VRAM 계측값은 음수일 수 없습니다.")
    if int(free_before) > total_vram or int(free_after) > total_vram:
        _fail("CUDA free VRAM 계측값이 GPU 총량을 벗어났습니다.")
    runtime = {
        "mode": "CONFIRMED_GPU_BATCH_CALIBRATION",
        "ultralytics": expected_ultralytics,
        "torch": torch_version,
        "cudaRuntime": cuda_runtime,
        "deviceIndex": device_index,
        "deviceName": device_name,
        "computeCapability": compute_capability,
        "totalVramBytes": total_vram,
        "freeVramBytesBeforeProfile": int(free_before),
        "freeVramBytesAfterProfile": int(free_after),
        "allocatedVramBytesBeforeProfile": allocated_before,
        "reservedVramBytesBeforeProfile": reserved_before,
        "peakAllocatedVramBytes": peak_allocated,
        "peakReservedVramBytes": peak_reserved,
    }
    return recommended, candidate_profiles, profile_memory_target_gb, runtime


def build_training_batch_calibration_report(
    *,
    root: Path,
    plan_path: Path,
    intake_receipt_path: Path,
    preflight_receipt_path: Path,
    confirm_gpu_batch_calibration: bool = False,
    ultralytics_version: str | None = None,
    image_probe: Callable[[Path], tuple[int, int]] | None = None,
    torch_provider: TorchProvider | None = None,
    yolo_factory: YoloFactory | None = None,
    batch_probe: BatchProbe | None = None,
) -> dict[str, object]:
    """Re-lock 6A/6B evidence and optionally profile a safe GPU batch."""
    root = root.resolve()
    readiness = compile_training_plan(
        root=root,
        plan_path=plan_path,
        ultralytics_version=ultralytics_version,
    )
    intake, intake_path = _load_current_intake(
        root=root,
        plan_path=plan_path,
        intake_receipt_path=intake_receipt_path,
        ultralytics_version=ultralytics_version,
        image_probe=image_probe,
    )
    preflight, preflight_path = _verify_preflight_receipt(
        root=root,
        receipt_path=preflight_receipt_path,
        readiness=readiness,
        intake=intake,
        intake_path=intake_path,
    )
    ready_plan = _object(readiness.get("plan"), "readiness.plan")
    ready_model = _object(readiness.get("model"), "readiness.model")
    parent = _object(ready_model.get("parent"), "readiness.model.parent")
    ready_data = _object(readiness.get("data"), "readiness.data")
    compiled = _object(readiness.get("compiledTraining"), "readiness.compiledTraining")
    arguments = _object(compiled.get("arguments"), "compiledTraining.arguments")
    intake_dataset = _object(intake.get("dataset"), "datasetIntake.dataset")
    train = _object(intake_dataset.get("train"), "datasetIntake.dataset.train")
    preflight_runtime = _object(preflight.get("runtime"), "preflight.runtime")
    parent_path = _safe_file(root, str(parent["path"]), "parentWeight")
    planned_batch = _integer(arguments.get("batch"), "plan.training.batch", minimum=1)
    train_image_count = _integer(
        train.get("imageCount"),
        "intake.train.imageCount",
        minimum=1,
    )
    maximum_objects = _integer(
        train.get("maximumObjectsPerImage"),
        "intake.train.maximumObjectsPerImage",
        minimum=1,
    )
    input_hashes = {
        "plan": sha256_file(_safe_file(root, plan_path, "planPath")),
        "intake": sha256_file(intake_path),
        "preflight": sha256_file(preflight_path),
        "parent": sha256_file(parent_path),
    }
    status = CPU_STATUS
    next_action = CPU_NEXT_ACTION
    recommended_batch: int | None = None
    candidate_profiles: list[dict[str, object]] = []
    profile_memory_target_gb: float | None = None
    batch_status = "PROVISIONAL"
    runtime: dict[str, object] = {
        "mode": "CPU_CHECK_ONLY",
        "ultralytics": str(preflight_runtime["ultralytics"]),
        "torch": None,
        "cudaRuntime": None,
        "deviceIndex": None,
        "deviceName": None,
        "computeCapability": None,
        "totalVramBytes": None,
        "freeVramBytesBeforeProfile": None,
        "freeVramBytesAfterProfile": None,
        "allocatedVramBytesBeforeProfile": None,
        "reservedVramBytesBeforeProfile": None,
        "peakAllocatedVramBytes": None,
        "peakReservedVramBytes": None,
        "candidatePolicy": AUTOBATCH_CANDIDATE_POLICY,
        "candidateBatchSizes": _bounded_candidate_batches(
            planned_batch,
            train_image_count,
        ),
        "candidateProfiles": candidate_profiles,
        "profileMemoryTargetGb": profile_memory_target_gb,
    }
    if confirm_gpu_batch_calibration:
        amp = arguments.get("amp")
        if not isinstance(amp, bool):
            _fail("plan.training.amp는 boolean이어야 합니다.")
        (
            recommended_batch,
            candidate_profiles,
            profile_memory_target_gb,
            runtime,
        ) = _run_gpu_calibration(
            stage=str(readiness["stage"]),
            parent_path=parent_path,
            device_index=_device_index(arguments.get("device")),
            imgsz=_integer(arguments.get("imgsz"), "plan.training.imgsz", minimum=32),
            amp=amp,
            planned_batch=planned_batch,
            train_image_count=train_image_count,
            maximum_objects_per_image=maximum_objects,
            preflight_runtime=preflight_runtime,
            torch_provider=torch_provider,
            yolo_factory=yolo_factory,
            batch_probe=batch_probe,
        )
        runtime["candidatePolicy"] = AUTOBATCH_CANDIDATE_POLICY
        runtime["candidateBatchSizes"] = _bounded_candidate_batches(
            planned_batch,
            train_image_count,
        )
        runtime["candidateProfiles"] = candidate_profiles
        runtime["profileMemoryTargetGb"] = profile_memory_target_gb
        batch_status = "CALIBRATED"
        if recommended_batch == planned_batch:
            status = CALIBRATED_STATUS
            next_action = CALIBRATED_NEXT_ACTION
        else:
            status = PLAN_UPDATE_STATUS
            next_action = PLAN_UPDATE_NEXT_ACTION

    current_hashes = {
        "plan": sha256_file(_safe_file(root, plan_path, "planPath")),
        "intake": sha256_file(intake_path),
        "preflight": sha256_file(preflight_path),
        "parent": sha256_file(parent_path),
    }
    if current_hashes != input_hashes:
        _fail("batch calibration 중 입력 계획·receipt·가중치가 변경되었습니다.")

    report: dict[str, object] = {
        "schemaVersion": SCHEMA_VERSION,
        "contractId": TRAINING_BATCH_CALIBRATION_CONTRACT_ID,
        "status": status,
        "stage": str(readiness["stage"]),
        "nextAction": next_action,
        "plan": {
            "path": str(ready_plan["path"]),
            "sha256": str(ready_plan["sha256"]),
            "evidenceLockSha256": str(readiness["evidenceLockSha256"]),
        },
        "datasetIntake": {
            "path": str(intake_path),
            "fileSha256": input_hashes["intake"],
            "receiptSha256": str(intake["receiptSha256"]),
            "combinedFingerprintSha256": str(
                intake_dataset["combinedFingerprintSha256"]
            ),
        },
        "gpuPreflight": {
            "path": str(preflight_path),
            "fileSha256": input_hashes["preflight"],
            "receiptSha256": str(preflight["preflightReceiptSha256"]),
            "status": str(preflight["status"]),
        },
        "model": {
            "parentPath": str(parent_path),
            "parentFileName": str(parent["fileName"]),
            "parentSha256": input_hashes["parent"],
            "outputFileName": str(ready_model["outputFileName"]),
        },
        "dataset": {
            "dataYamlSha256": str(ready_data["dataYamlSha256"]),
            "splitManifestSha256": str(ready_data["splitManifestSha256"]),
            "combinedFingerprintSha256": str(
                intake_dataset["combinedFingerprintSha256"]
            ),
            "trainImageCount": train_image_count,
            "maximumObjectsPerImage": maximum_objects,
        },
        "calibration": {
            "method": AUTOBATCH_METHOD,
            "symbol": AUTOBATCH_SYMBOL,
            "memoryFraction": AUTOBATCH_MEMORY_FRACTION,
            "imgsz": int(arguments["imgsz"]),
            "amp": bool(arguments["amp"]),
            "plannedBatch": planned_batch,
            "recommendedBatch": recommended_batch,
            "batchStatus": batch_status,
            "planBatchMatchesRecommendation": (
                None
                if recommended_batch is None
                else recommended_batch == planned_batch
            ),
        },
        "runtime": runtime,
        "safeguards": {
            "trainingExecuted": False,
            "yoloTrainCalled": False,
            "optimizerStepExecuted": False,
            "weightsPersisted": False,
            "planMutated": False,
            "dataMutated": False,
            "dockerAccessed": False,
            "gpuAccessed": confirm_gpu_batch_calibration,
            "torchImported": confirm_gpu_batch_calibration,
            "ultralyticsImported": confirm_gpu_batch_calibration,
            "modelLoaded": confirm_gpu_batch_calibration,
            "trainingGraphProfiled": confirm_gpu_batch_calibration,
            "batchCalibrated": confirm_gpu_batch_calibration,
            "inputsUnchanged": True,
        },
    }
    report["calibrationReceiptSha256"] = _canonical_sha256(report)
    return report


def _output_path(root: Path, raw_path: str) -> Path:
    root = root.resolve()
    configured = Path(raw_path)
    lexical = configured if configured.is_absolute() else root / configured
    lexical = Path(os.path.abspath(lexical))
    try:
        relative = lexical.relative_to(root)
    except ValueError as error:
        raise TrainingBatchCalibrationError(
            "output이 프로젝트 root 밖을 가리킵니다."
        ) from error
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink():
            _fail(f"output 경로에는 심볼릭 링크를 사용할 수 없습니다: {current}")
    if lexical.exists() or lexical.is_symlink():
        _fail(f"기존 training batch calibration receipt를 덮어쓰지 않습니다: {lexical}")
    return lexical


def write_training_batch_calibration_report(
    root: Path,
    output: str,
    report: Mapping[str, object],
) -> Path:
    target = _output_path(root, output)
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
            "Re-lock Phase 2B-6A/6B evidence and optionally run an explicitly "
            "confirmed Ultralytics GPU AutoBatch profile without training."
        )
    )
    parser.add_argument("--root", default=".", help="VisionFlow AI project root")
    parser.add_argument("--plan", required=True, help="Concrete S1/S2 training plan")
    parser.add_argument(
        "--intake-receipt",
        required=True,
        help="Phase 2B-6A READY dataset intake receipt",
    )
    parser.add_argument(
        "--preflight-receipt",
        required=True,
        help="Phase 2B-6B READY_FOR_BATCH_CALIBRATION GPU receipt",
    )
    parser.add_argument(
        "--confirm-gpu-batch-calibration",
        action="store_true",
        help="Explicitly allow CUDA model loading and AutoBatch graph profiling",
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument(
        "--output",
        help="New calibration receipt under --root (existing files are refused)",
    )
    output.add_argument(
        "--check-only",
        action="store_true",
        help="Validate and print the receipt without writing a file (default)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    root = Path(arguments.root).resolve()
    try:
        report = build_training_batch_calibration_report(
            root=root,
            plan_path=Path(arguments.plan),
            intake_receipt_path=Path(arguments.intake_receipt),
            preflight_receipt_path=Path(arguments.preflight_receipt),
            confirm_gpu_batch_calibration=arguments.confirm_gpu_batch_calibration,
        )
        if arguments.output:
            target = write_training_batch_calibration_report(
                root,
                arguments.output,
                report,
            )
            print(
                "VISIONFLOW_PHASE2B6_TRAINING_BATCH_CALIBRATION="
                f"{report['status']} output={target}"
            )
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))
    except (
        DatasetIntakeError,
        TrainingBatchCalibrationError,
        TrainingPlanError,
        OSError,
        ValueError,
    ) as error:
        print(
            f"VISIONFLOW_PHASE2B6_TRAINING_BATCH_CALIBRATION=FAIL error={error}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
