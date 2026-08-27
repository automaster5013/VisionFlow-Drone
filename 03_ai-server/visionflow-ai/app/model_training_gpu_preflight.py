"""Controlled GPU training preflight for VisionFlow Phase 2B-6B."""

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
from pathlib import Path
from typing import Any

from app.model_contract import VISDRONE_CLASS_MAPPING, load_json_object, sha256_file
from app.model_dataset_intake import (
    DATASET_INTAKE_CONTRACT_ID,
    DatasetIntakeError,
    build_dataset_intake_report,
)
from app.model_training_plan import (
    TrainingPlanError,
    compile_training_plan,
)

SCHEMA_VERSION = 1
TRAINING_GPU_PREFLIGHT_CONTRACT_ID = (
    "visionflow.phase2b6.training-gpu-preflight"
)
CPU_STATUS = "READY_FOR_GPU_PROBE"
GPU_STATUS = "READY_FOR_BATCH_CALIBRATION"
CPU_NEXT_ACTION = "EXPLICIT_GPU_PROBE_REQUIRED"
GPU_NEXT_ACTION = "GPU_BATCH_CALIBRATION_REQUIRED"
VISDRONE_NAMES = {
    int(item["id"]): str(item["sourceName"])
    for item in VISDRONE_CLASS_MAPPING
}
COCO_NAMES = {
    index: name
    for index, name in enumerate(
        (
            "person",
            "bicycle",
            "car",
            "motorcycle",
            "airplane",
            "bus",
            "train",
            "truck",
            "boat",
            "traffic light",
            "fire hydrant",
            "stop sign",
            "parking meter",
            "bench",
            "bird",
            "cat",
            "dog",
            "horse",
            "sheep",
            "cow",
            "elephant",
            "bear",
            "zebra",
            "giraffe",
            "backpack",
            "umbrella",
            "handbag",
            "tie",
            "suitcase",
            "frisbee",
            "skis",
            "snowboard",
            "sports ball",
            "kite",
            "baseball bat",
            "baseball glove",
            "skateboard",
            "surfboard",
            "tennis racket",
            "bottle",
            "wine glass",
            "cup",
            "fork",
            "knife",
            "spoon",
            "bowl",
            "banana",
            "apple",
            "sandwich",
            "orange",
            "broccoli",
            "carrot",
            "hot dog",
            "pizza",
            "donut",
            "cake",
            "chair",
            "couch",
            "potted plant",
            "bed",
            "dining table",
            "toilet",
            "tv",
            "laptop",
            "mouse",
            "remote",
            "keyboard",
            "cell phone",
            "microwave",
            "oven",
            "toaster",
            "sink",
            "refrigerator",
            "book",
            "clock",
            "vase",
            "scissors",
            "teddy bear",
            "hair drier",
            "toothbrush",
        )
    )
}
TorchProvider = Callable[[], object]
YoloFactory = Callable[[str], object]


class TrainingGpuPreflightError(ValueError):
    """Raised when GPU training prerequisites are not safely locked."""


def _fail(message: str) -> None:
    raise TrainingGpuPreflightError(message)


def _object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{field}은(는) JSON 객체여야 합니다.")
    return {str(key): item for key, item in value.items()}


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
        raise TrainingGpuPreflightError(
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
        raise TrainingGpuPreflightError(
            f"{field}을(를) 찾을 수 없습니다: {lexical}"
        ) from error
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise TrainingGpuPreflightError(
            f"{field}가 프로젝트 root 밖을 가리킵니다."
        ) from error
    if not resolved.is_file():
        _fail(f"{field}은(는) 일반 파일이어야 합니다: {resolved}")
    return resolved


def _load_and_verify_intake_receipt(
    *,
    root: Path,
    receipt_path: Path,
    expected: Mapping[str, object],
) -> tuple[dict[str, Any], Path]:
    safe_path = _safe_file(root, receipt_path, "datasetIntakeReceipt")
    receipt = load_json_object(safe_path)
    if receipt.get("schemaVersion") != SCHEMA_VERSION:
        _fail("dataset intake receipt schemaVersion은 1이어야 합니다.")
    if receipt.get("contractId") != DATASET_INTAKE_CONTRACT_ID:
        _fail("dataset intake receipt 계약 ID가 Phase 2B-6A와 다릅니다.")
    if receipt.get("status") != "READY":
        _fail("dataset intake receipt 상태가 READY가 아닙니다.")
    claimed_sha = receipt.get("receiptSha256")
    if not isinstance(claimed_sha, str) or not re.fullmatch(
        r"[0-9a-f]{64}", claimed_sha
    ):
        _fail("dataset intake receiptSha256 형식이 올바르지 않습니다.")
    receipt_without_sha = dict(receipt)
    receipt_without_sha.pop("receiptSha256", None)
    if _canonical_sha256(receipt_without_sha) != claimed_sha:
        _fail("dataset intake receiptSha256이 receipt 내용과 다릅니다.")
    if receipt != dict(expected):
        _fail(
            "dataset intake receipt가 현재 계획·데이터 full fingerprint "
            "재계산 결과와 다릅니다. Phase 2B-6A intake를 다시 실행해야 합니다."
        )
    return receipt, safe_path


def _device_index(raw_device: object) -> int:
    if not isinstance(raw_device, str) or not re.fullmatch(r"\d+", raw_device):
        _fail(
            "학습 GPU preflight의 plan.training.device는 단일 CUDA 인덱스여야 "
            "합니다."
        )
    return int(raw_device)


def _normalized_names(raw_names: object) -> dict[int, str]:
    if isinstance(raw_names, Mapping):
        try:
            return {int(key): str(value) for key, value in raw_names.items()}
        except (TypeError, ValueError) as error:
            raise TrainingGpuPreflightError(
                "로드한 부모 모델의 클래스 매핑을 해석할 수 없습니다."
            ) from error
    if isinstance(raw_names, Sequence) and not isinstance(
        raw_names, (str, bytes, bytearray)
    ):
        return {index: str(value) for index, value in enumerate(raw_names)}
    _fail("로드한 부모 모델에 클래스 매핑이 없습니다.")


def _model_task(model: object) -> str:
    task = getattr(model, "task", None)
    if not task:
        inner = getattr(model, "model", None)
        task = getattr(inner, "task", None)
    if not task:
        args = getattr(getattr(model, "model", None), "args", None)
        if isinstance(args, Mapping):
            task = args.get("task")
    return str(task or "").strip()


def _validate_parent_model_identity(
    *, stage: str, model: object
) -> tuple[str, dict[int, str]]:
    task = _model_task(model)
    if task != "detect":
        _fail("부모 YOLO 모델 task는 detect여야 합니다.")
    names = _normalized_names(getattr(model, "names", None))
    if stage == "VISDRONE_S1":
        if names != COCO_NAMES:
            _fail("S1 부모 모델은 COCO 원본 80-class와 정확히 일치해야 합니다.")
    elif names != VISDRONE_NAMES:
        _fail("S2 부모 모델은 VisDrone 원본 10-class와 정확히 일치해야 합니다.")
    return task, names


def _load_gpu_modules(
    *,
    torch_provider: TorchProvider | None,
    yolo_factory: YoloFactory | None,
) -> tuple[object, YoloFactory, str]:
    try:
        torch_module = (
            torch_provider()
            if torch_provider is not None
            else importlib.import_module("torch")
        )
        if yolo_factory is not None:
            return torch_module, yolo_factory, ""
        ultralytics_module = importlib.import_module("ultralytics")
        factory = getattr(ultralytics_module, "YOLO", None)
        if factory is None or not callable(factory):
            _fail("Ultralytics YOLO factory를 찾을 수 없습니다.")
        return (
            torch_module,
            factory,
            str(getattr(ultralytics_module, "__version__", "")).strip(),
        )
    except TrainingGpuPreflightError:
        raise
    except (ImportError, AttributeError, OSError, RuntimeError) as error:
        raise TrainingGpuPreflightError(
            f"GPU probe 런타임을 불러올 수 없습니다: {error}"
        ) from error


def _probe_gpu(
    *,
    stage: str,
    parent_path: str,
    device_index: int,
    expected_ultralytics: str,
    torch_provider: TorchProvider | None,
    yolo_factory: YoloFactory | None,
) -> tuple[dict[str, object], dict[str, object]]:
    torch_module, factory, imported_ultralytics = _load_gpu_modules(
        torch_provider=torch_provider,
        yolo_factory=yolo_factory,
    )
    if imported_ultralytics and imported_ultralytics != expected_ultralytics:
        _fail(
            "import된 Ultralytics 버전이 계획 잠금에 사용된 설치 버전과 "
            "다릅니다."
        )
    cuda = getattr(torch_module, "cuda", None)
    if cuda is None or not bool(cuda.is_available()):
        _fail("CUDA를 사용할 수 없어 GPU probe를 진행할 수 없습니다.")
    device_count = int(cuda.device_count())
    if device_index < 0 or device_index >= device_count:
        _fail(
            "학습 계획의 CUDA device 인덱스가 사용 가능한 GPU 범위를 "
            "벗어났습니다."
        )
    try:
        properties = cuda.get_device_properties(device_index)
        device_name = str(properties.name)
        total_vram = int(properties.total_memory)
        major = int(properties.major)
        minor = int(properties.minor)
        model = factory(parent_path)
        to_method = getattr(model, "to", None)
        if to_method is None or not callable(to_method):
            _fail("부모 YOLO 모델을 CUDA 장치로 이동할 수 없습니다.")
        to_method(f"cuda:{device_index}")
        task, names = _validate_parent_model_identity(stage=stage, model=model)
        free_vram, reported_total = cuda.mem_get_info(device_index)
    except TrainingGpuPreflightError:
        raise
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as error:
        raise TrainingGpuPreflightError(
            f"CUDA 부모 모델 probe가 실패했습니다: {error}"
        ) from error
    if int(reported_total) != total_vram:
        _fail("CUDA VRAM 총량 보고가 일관되지 않습니다.")
    torch_version = str(getattr(torch_module, "__version__", "")).strip()
    cuda_runtime = str(getattr(getattr(torch_module, "version", None), "cuda", ""))
    if not torch_version or not cuda_runtime or not device_name or total_vram <= 0:
        _fail("GPU runtime 증거가 완전하지 않습니다.")
    runtime = {
        "mode": "CONFIRMED_GPU_PROBE",
        "ultralytics": expected_ultralytics,
        "torch": torch_version,
        "cudaRuntime": cuda_runtime,
        "deviceIndex": device_index,
        "deviceName": device_name,
        "computeCapability": f"{major}.{minor}",
        "totalVramBytes": total_vram,
        "freeVramBytesAfterModelLoad": int(free_vram),
    }
    model_probe = {
        "loaded": True,
        "device": f"cuda:{device_index}",
        "task": task,
        "classCount": len(names),
    }
    return runtime, model_probe


def build_training_gpu_preflight_report(
    *,
    root: Path,
    plan_path: Path,
    intake_receipt_path: Path,
    confirm_gpu_probe: bool = False,
    ultralytics_version: str | None = None,
    image_probe: Callable[[Path], tuple[int, int]] | None = None,
    torch_provider: TorchProvider | None = None,
    yolo_factory: YoloFactory | None = None,
) -> dict[str, object]:
    """Re-lock plan/intake evidence and optionally probe one CUDA parent model."""
    root = root.resolve()
    readiness = compile_training_plan(
        root=root,
        plan_path=plan_path,
        ultralytics_version=ultralytics_version,
    )
    recomputed_intake = build_dataset_intake_report(
        root=root,
        plan_path=plan_path,
        ultralytics_version=ultralytics_version,
        image_probe=image_probe,
    )
    intake, safe_intake_path = _load_and_verify_intake_receipt(
        root=root,
        receipt_path=intake_receipt_path,
        expected=recomputed_intake,
    )
    plan_evidence = _object(readiness.get("plan"), "readiness.plan")
    model_evidence = _object(readiness.get("model"), "readiness.model")
    parent = _object(model_evidence.get("parent"), "readiness.model.parent")
    data_evidence = _object(readiness.get("data"), "readiness.data")
    compiled = _object(
        readiness.get("compiledTraining"), "readiness.compiledTraining"
    )
    arguments = _object(compiled.get("arguments"), "compiledTraining.arguments")
    runtime_evidence = _object(readiness.get("runtime"), "readiness.runtime")
    intake_dataset = _object(intake.get("dataset"), "datasetIntake.dataset")
    device_index = _device_index(arguments.get("device"))

    status = CPU_STATUS
    next_action = CPU_NEXT_ACTION
    runtime: dict[str, object] = {
        "mode": "CPU_CHECK_ONLY",
        "ultralytics": str(runtime_evidence["ultralytics"]),
        "torch": None,
        "cudaRuntime": None,
        "deviceIndex": None,
        "deviceName": None,
        "computeCapability": None,
        "totalVramBytes": None,
        "freeVramBytesAfterModelLoad": None,
    }
    model_probe: dict[str, object] = {
        "loaded": False,
        "device": None,
        "task": None,
        "classCount": None,
    }
    if confirm_gpu_probe:
        runtime, model_probe = _probe_gpu(
            stage=str(readiness["stage"]),
            parent_path=str(parent["path"]),
            device_index=device_index,
            expected_ultralytics=str(runtime_evidence["ultralytics"]),
            torch_provider=torch_provider,
            yolo_factory=yolo_factory,
        )
        status = GPU_STATUS
        next_action = GPU_NEXT_ACTION

    report: dict[str, object] = {
        "schemaVersion": SCHEMA_VERSION,
        "contractId": TRAINING_GPU_PREFLIGHT_CONTRACT_ID,
        "status": status,
        "stage": str(readiness["stage"]),
        "nextAction": next_action,
        "plan": {
            "path": str(plan_evidence["path"]),
            "sha256": str(plan_evidence["sha256"]),
            "evidenceLockSha256": str(readiness["evidenceLockSha256"]),
        },
        "datasetIntake": {
            "path": str(safe_intake_path),
            "fileSha256": sha256_file(safe_intake_path),
            "receiptSha256": str(intake["receiptSha256"]),
            "combinedFingerprintSha256": str(
                intake_dataset["combinedFingerprintSha256"]
            ),
        },
        "model": {
            "parentPath": str(parent["path"]),
            "parentFileName": str(parent["fileName"]),
            "parentSha256": str(parent["sha256"]),
            "outputFileName": str(model_evidence["outputFileName"]),
        },
        "dataset": {
            "dataYamlSha256": str(data_evidence["dataYamlSha256"]),
            "splitManifestSha256": str(data_evidence["splitManifestSha256"]),
            "classCount": len(VISDRONE_NAMES),
            "splitUnit": str(data_evidence["splitUnit"]),
        },
        "training": {
            "requestedDevice": str(arguments["device"]),
            "imgsz": int(arguments["imgsz"]),
            "plannedBatch": int(arguments["batch"]),
            "batchStatus": "PROVISIONAL",
        },
        "runtime": runtime,
        "modelProbe": model_probe,
        "safeguards": {
            "trainingExecuted": False,
            "batchCalibrated": False,
            "dockerAccessed": False,
            "dataMutated": False,
            "gpuAccessed": confirm_gpu_probe,
            "torchImported": confirm_gpu_probe,
            "ultralyticsImported": confirm_gpu_probe,
            "modelLoaded": bool(model_probe["loaded"]),
        },
    }
    report["preflightReceiptSha256"] = _canonical_sha256(report)
    return report


def _output_path(root: Path, raw_path: str) -> Path:
    root = root.resolve()
    configured = Path(raw_path)
    lexical = configured if configured.is_absolute() else root / configured
    lexical = Path(os.path.abspath(lexical))
    try:
        relative = lexical.relative_to(root)
    except ValueError as error:
        raise TrainingGpuPreflightError(
            "output이 프로젝트 root 밖을 가리킵니다."
        ) from error
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink():
            _fail(f"output 경로에는 심볼릭 링크를 사용할 수 없습니다: {current}")
    if lexical.exists() or lexical.is_symlink():
        _fail(f"기존 training GPU preflight receipt를 덮어쓰지 않습니다: {lexical}")
    return lexical


def write_training_gpu_preflight_report(
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
            "Re-lock a VisionFlow S1/S2 plan and dataset intake receipt, then "
            "optionally perform an explicitly confirmed GPU parent-model probe."
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
        "--confirm-gpu-probe",
        action="store_true",
        help="Explicitly allow CUDA discovery and parent YOLO model loading",
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument(
        "--output",
        help="New preflight receipt path under --root (existing files are refused)",
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
        report = build_training_gpu_preflight_report(
            root=root,
            plan_path=Path(arguments.plan),
            intake_receipt_path=Path(arguments.intake_receipt),
            confirm_gpu_probe=arguments.confirm_gpu_probe,
        )
        if arguments.output:
            target = write_training_gpu_preflight_report(
                root,
                arguments.output,
                report,
            )
            print(
                "VISIONFLOW_PHASE2B6_TRAINING_GPU_PREFLIGHT="
                f"{report['status']} output={target}"
            )
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))
    except (
        DatasetIntakeError,
        TrainingGpuPreflightError,
        TrainingPlanError,
        OSError,
        ValueError,
    ) as error:
        print(
            f"VISIONFLOW_PHASE2B6_TRAINING_GPU_PREFLIGHT=FAIL error={error}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
