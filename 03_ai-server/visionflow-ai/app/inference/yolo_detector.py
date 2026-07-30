from __future__ import annotations

import hashlib
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import torch
from ultralytics import YOLO

from app.domain import Detection, FramePacket, InferencePacket


def _requests_cuda(device: str) -> bool:
    normalized = device.strip().lower()
    return normalized not in {"", "cpu", "mps"}


def _cuda_device_index(device: str) -> int:
    normalized = device.strip().lower()

    if normalized.isdigit():
        return int(normalized)

    if normalized == "cuda":
        return 0

    if normalized.startswith("cuda:"):
        suffix = normalized.removeprefix("cuda:")
        if suffix.isdigit():
            return int(suffix)

    raise ValueError(
        "AI_DEVICE에는 0 이상의 GPU 번호, cuda 또는 cuda:0 형식을 사용하세요."
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as model_file:
        for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def _normalized_classes(names: Any) -> list[dict[str, object]]:
    if isinstance(names, Mapping):
        items = sorted(names.items(), key=lambda item: int(item[0]))
    elif isinstance(names, (list, tuple)):
        items = enumerate(names)
    else:
        return []

    return [
        {
            "id": int(class_id),
            "name": str(class_name),
        }
        for class_id, class_name in items
    ]


class YoloDetector:
    def __init__(
        self,
        *,
        model_profile: str,
        model_path: str,
        require_cuda: bool,
        require_local_model: bool,
        confidence: float,
        iou: float,
        image_size: int,
        device: str,
    ) -> None:
        self._model_profile = model_profile
        self._model_path = model_path
        self._device = device
        self._require_cuda = require_cuda
        self._validate_runtime(require_local_model=require_local_model)

        self._model = YOLO(model_path)
        self._effective_device = self._prepare_runtime_device()
        self._confidence = confidence
        self._iou = iou
        self._image_size = image_size
        self._resolved_model_path = self._resolve_model_path()
        self._status = self._build_status()

    def _validate_runtime(self, *, require_local_model: bool) -> None:
        local_model = Path(self._model_path).expanduser()

        if require_local_model and not local_model.is_file():
            raise FileNotFoundError(
                "로컬 YOLO 모델 파일을 찾을 수 없습니다: "
                f"{local_model.resolve()}\n"
                "호스트의 03_ai-server/visionflow-ai/models 폴더에 모델을 넣고 "
                "AI_MODEL_FILE 값을 확인하세요."
            )

        cuda_requested = _requests_cuda(self._device)
        cuda_available = torch.cuda.is_available()

        if self._require_cuda and not cuda_requested:
            raise RuntimeError(
                "GPU 실행이 필수이지만 AI_DEVICE가 CPU로 설정되어 있습니다. "
                "AI_DEVICE=0을 사용하세요."
            )

        if (self._require_cuda or cuda_requested) and not cuda_available:
            raise RuntimeError(
                "GPU가 요청되었지만 PyTorch CUDA를 사용할 수 없습니다. "
                "NVIDIA 드라이버, Docker Desktop GPU 지원, compose.gpu.yaml 및 "
                "CUDA용 PyTorch 이미지를 확인하세요."
            )

        if cuda_requested:
            device_index = _cuda_device_index(self._device)
            device_count = torch.cuda.device_count()

            if device_index >= device_count:
                raise RuntimeError(
                    f"요청한 CUDA 장치 {device_index}를 사용할 수 없습니다. "
                    f"감지된 CUDA 장치 수: {device_count}"
                )

    def _prepare_runtime_device(self) -> str:
        if not _requests_cuda(self._device):
            return self._device

        device_index = _cuda_device_index(self._device)
        effective_device = f"cuda:{device_index}"

        try:
            probe = torch.ones((1,), device=effective_device)
            if float(probe.sum().item()) != 1.0:
                raise RuntimeError("CUDA 텐서 연산 결과가 올바르지 않습니다.")

            self._model.to(effective_device)
            torch.cuda.synchronize(device_index)
        except Exception as error:
            raise RuntimeError(
                f"YOLO 모델을 {effective_device}에 적재하지 못했습니다."
            ) from error

        return effective_device

    def _resolve_model_path(self) -> Path | None:
        candidates = [self._model_path, getattr(self._model, "ckpt_path", None)]

        for candidate in candidates:
            if not candidate:
                continue

            path = Path(str(candidate)).expanduser()

            if path.is_file():
                return path.resolve()

        return None

    def _build_status(self) -> dict[str, object]:
        cuda_available = torch.cuda.is_available()
        cuda_requested = _requests_cuda(self._device)
        cuda_device_index = _cuda_device_index(self._device) if cuda_requested else None
        cuda_device_name: str | None = None
        cuda_capability: list[int] | None = None
        cuda_total_memory_bytes: int | None = None

        if cuda_available and cuda_device_index is not None:
            properties = torch.cuda.get_device_properties(cuda_device_index)
            cuda_device_name = properties.name
            cuda_capability = list(torch.cuda.get_device_capability(cuda_device_index))
            cuda_total_memory_bytes = properties.total_memory

        resolved_path = self._resolved_model_path
        classes = _normalized_classes(getattr(self._model, "names", None))

        return {
            "profile": self._model_profile,
            "requestedPath": self._model_path,
            "resolvedPath": str(resolved_path) if resolved_path is not None else None,
            "localFile": resolved_path is not None,
            "sizeBytes": resolved_path.stat().st_size if resolved_path is not None else None,
            "sha256": _sha256(resolved_path) if resolved_path is not None else None,
            "classCount": len(classes),
            "classes": classes,
            "confidence": self._confidence,
            "iou": self._iou,
            "imageSize": self._image_size,
            "deviceRequested": self._device,
            "deviceEffective": self._effective_device,
            "requireCuda": self._require_cuda,
            "torchVersion": torch.__version__,
            "torchCudaVersion": torch.version.cuda,
            "cudnnVersion": torch.backends.cudnn.version(),
            "cudaAvailable": cuda_available,
            "cudaDeviceCount": torch.cuda.device_count() if cuda_available else 0,
            "cudaDeviceIndex": cuda_device_index,
            "cudaDeviceName": cuda_device_name,
            "cudaCapability": cuda_capability,
            "cudaTotalMemoryBytes": cuda_total_memory_bytes,
        }

    def status(self) -> dict[str, object]:
        return {
            **self._status,
            "classes": [dict(item) for item in self._status["classes"]],
        }

    def infer(self, frame: FramePacket) -> InferencePacket:
        started_at = time.perf_counter()
        results = self._model.predict(
            source=frame.image,
            conf=self._confidence,
            iou=self._iou,
            imgsz=self._image_size,
            device=self._device,
            verbose=False,
        )
        inference_ms = (time.perf_counter() - started_at) * 1_000.0

        if not results:
            return InferencePacket(
                frame=frame,
                detections=(),
                inference_ms=inference_ms,
                annotated_image=frame.image.copy(),
            )

        result = results[0]
        detections: list[Detection] = []

        if result.boxes is not None:
            boxes = result.boxes
            coordinates = boxes.xyxy.detach().cpu().tolist()
            confidences = boxes.conf.detach().cpu().tolist()
            class_ids = boxes.cls.detach().cpu().tolist()
            names: Mapping[int, str] = result.names

            for xyxy, confidence, class_id_value in zip(
                coordinates,
                confidences,
                class_ids,
                strict=True,
            ):
                class_id = int(class_id_value)
                detections.append(
                    Detection(
                        class_id=class_id,
                        class_name=str(names.get(class_id, class_id)),
                        confidence=float(confidence),
                        x1=float(xyxy[0]),
                        y1=float(xyxy[1]),
                        x2=float(xyxy[2]),
                        y2=float(xyxy[3]),
                    )
                )

        annotated_image = np.asarray(result.plot())

        return InferencePacket(
            frame=frame,
            detections=tuple(detections),
            inference_ms=inference_ms,
            annotated_image=annotated_image,
        )
