from __future__ import annotations

import hashlib
import os
import math
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import cv2
import torch
from ultralytics import YOLO

from app.domain import Detection, FramePacket, InferencePacket
from app.model_runtime import ClassResolver, resolve_identity_class


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
    elif isinstance(names, list | tuple):
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


def _box_iou(a: Detection, b: Detection) -> float:
    intersection = max(0.0, min(a.x2, b.x2) - max(a.x1, b.x1)) * max(0.0, min(a.y2, b.y2) - max(a.y1, b.y1))
    union = max(0.0, a.x2 - a.x1) * max(0.0, a.y2 - a.y1) + max(0.0, b.x2 - b.x1) * max(0.0, b.y2 - b.y1) - intersection
    return intersection / union if union > 0 else 0.0


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
        class_resolver: ClassResolver | None = None,
    ) -> None:
        self._model_profile = model_profile
        self._model_path = model_path
        self._device = device
        self._require_cuda = require_cuda
        self._class_resolver = class_resolver or resolve_identity_class
        self._validate_runtime(require_local_model=require_local_model)

        self._model = YOLO(model_path)
        self._effective_device = self._prepare_runtime_device()
        self._confidence = confidence
        self._iou = iou
        self._image_size = image_size
        self._resolved_model_path = self._resolve_model_path()
        self._status = self._build_status()
        self._warning_enabled = os.environ.get("AI_NO_HARDHAT_WARNING", "false").lower() == "true"
        self._warning_until = 0.0
        self._warning_source = None
        self._warning_asset = None
        if self._warning_enabled:
            self._warning_asset = cv2.imread(str(Path(__file__).parent.parent / "assets/no-hardhat-warning.png"), cv2.IMREAD_UNCHANGED)
            if self._warning_asset is None:
                raise FileNotFoundError("No-hardhat warning asset is missing")
        self._person_model = None
        person_path = os.environ.get("AI_PERSON_MODEL_PATH", "").strip()
        self._status["inferenceMode"] = "SINGLE_MODEL"
        if person_path:
            path = Path(person_path).expanduser()
            if not path.is_file():
                raise FileNotFoundError(f"Person detector model not found: {path}")
            output_classes = [item for item in self._status["classes"]
                              if self._class_resolver(int(item["id"]), str(item["name"])).canonical_name == "person"]
            if len(output_classes) != 1:
                raise ValueError("Person fusion requires exactly one person output class")
            self._person_output_id = int(output_classes[0]["id"])
            self._person_confidence = float(os.environ.get("AI_PERSON_CONFIDENCE", "0.25"))
            if not 0 < self._person_confidence <= 1:
                raise ValueError("AI_PERSON_CONFIDENCE must be in (0, 1]")
            self._person_model = YOLO(str(path))
            person_classes = [item for item in _normalized_classes(self._person_model.names)
                              if str(item["name"]).strip().lower() == "person"]
            if len(person_classes) != 1:
                raise ValueError("Auxiliary model must contain exactly one person class")
            self._person_source_id = int(person_classes[0]["id"])
            self._person_model.to(self._effective_device)
            self._status["inferenceMode"] = "PPE_WITH_PERSON_DETECTOR"
            self._status["personDetector"] = {
                "path": str(path), "sha256": _sha256(path),
                "confidence": self._person_confidence, "imageSize": self._image_size,
                "sourceClassId": self._person_source_id, "outputClassId": self._person_output_id,
                "boxSource": "model_prediction",
            }

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

    def track(self, **kwargs: Any) -> Any:
        return self._model.track(**kwargs)

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
        detections: list[Detection] = []
        for result in results or []:
            if result.boxes is None:
                continue
            for xyxy, confidence, class_id_value in zip(
                result.boxes.xyxy.detach().cpu().tolist(),
                result.boxes.conf.detach().cpu().tolist(),
                result.boxes.cls.detach().cpu().tolist(), strict=True,
            ):
                if confidence < self._confidence:
                    continue
                class_id = int(class_id_value)
                resolved = self._class_resolver(class_id, str(result.names.get(class_id, class_id)))
                detections.append(Detection(
                    class_id=class_id, class_name=resolved.canonical_name,
                    confidence=float(confidence), x1=float(xyxy[0]), y1=float(xyxy[1]),
                    x2=float(xyxy[2]), y2=float(xyxy[3]),
                ))

        if getattr(self, "_person_model", None) is not None:
            person_results = self._person_model.predict(
                source=frame.image, classes=[self._person_source_id],
                conf=self._person_confidence, iou=self._iou,
                imgsz=self._image_size, device=self._device, verbose=False,
            )
            people = [d for d in detections if d.class_name == "person"]
            detections = [d for d in detections if d.class_name != "person"]
            for result in person_results or []:
                if result.boxes is None:
                    continue
                for xyxy, confidence, class_id in zip(
                    result.boxes.xyxy.detach().cpu().tolist(),
                    result.boxes.conf.detach().cpu().tolist(),
                    result.boxes.cls.detach().cpu().tolist(), strict=True,
                ):
                    if int(class_id) != self._person_source_id or confidence < self._person_confidence:
                        continue
                    people.append(Detection(
                        class_id=self._person_output_id, class_name="person",
                        confidence=float(confidence), x1=float(xyxy[0]), y1=float(xyxy[1]),
                        x2=float(xyxy[2]), y2=float(xyxy[3]),
                    ))
            # Suppress duplicates across models without modifying predicted coordinates.
            kept: list[Detection] = []
            for person in sorted(people, key=lambda d: d.confidence, reverse=True):
                if not any(_box_iou(person, existing) > 0.5 for existing in kept):
                    kept.append(person)
            detections.extend(kept)
        inference_ms = (time.perf_counter() - started_at) * 1_000.0

        # Only draw model detections; PPE locations do not establish a person's extent.
        display_aliases = {
            "helmet": "hardhat",
            "vest": "vest",
            "head": "no-hardhat",
            "person": "person",
        }
        # Draw each object's box and label together, back to front.
        # PPE must remain visible even when a person box/label overlaps it.
        draw_priority = {"person": 0, "vest": 2, "helmet": 3, "head": 3}
        box_colors = {
            "person": (0, 255, 255),
            "vest": (0, 140, 255),
            "helmet": (255, 96, 32),
            "head": (0, 0, 220),
        }
        annotated_image = frame.image.copy()
        drawing_order = sorted(
            detections,
            key=lambda item: (
                draw_priority.get(item.class_name.strip().lower(), 1),
                item.confidence,
            ),
        )
        for detection in drawing_order:
            canonical_name = detection.class_name.strip().lower()
            hardhat_color = (255, 96, 32)
            cv2.rectangle(
                annotated_image,
                (int(detection.x1), int(detection.y1)),
                (int(detection.x2), int(detection.y2)),
                box_colors.get(canonical_name, (160, 160, 160)),
                2,
            )
            label_name = display_aliases.get(canonical_name, detection.class_name)
            label = f"{label_name} {detection.confidence:.2f}"
            font_scale = 0.70
            font_thickness = 2
            (label_width, label_height), baseline = cv2.getTextSize(
                label,
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                font_thickness,
            )
            label_x = max(0, int(detection.x1))
            label_bottom = max(label_height + baseline + 4, int(detection.y1))
            label_top = max(0, label_bottom - label_height - baseline - 6)
            background_color = (
                hardhat_color
                if canonical_name == "helmet"
                else (0, 0, 220)
                if canonical_name == "head"
                else (0, 140, 255)
                if canonical_name == "vest"
                else (24, 24, 24)
            )
            cv2.rectangle(
                annotated_image,
                (label_x, label_top),
                (label_x + label_width + 8, label_bottom),
                background_color,
                -1,
            )
            cv2.putText(
                annotated_image,
                label,
                (label_x + 4, label_bottom - baseline - 3),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                (255, 255, 255),
                font_thickness,
                cv2.LINE_AA,
            )

        if getattr(self, "_warning_enabled", False):
            self._draw_safety_warning(annotated_image, frame, detections)

        return InferencePacket(
            frame=frame,
            detections=tuple(detections),
            inference_ms=inference_ms,
            annotated_image=annotated_image,
        )

    def _draw_safety_warning(self, image, frame, detections) -> None:
        # Use the source timestamp so playback pauses do not create rapid flashing.
        now = frame.captured_at.timestamp()
        source = (frame.source_id, frame.session_id)
        if source != self._warning_source or now < getattr(self, "_warning_last_time", now):
            self._warning_until = 0.0
            self._warning_source = source
        self._warning_last_time = now
        if any(d.class_name in {"head", "no-hardhat"} for d in detections):
            self._warning_until = now + 1.5
        if now >= self._warning_until:
            return
        height, width = image.shape[:2]
        asset = self._warning_asset
        target_width = min(int(width * 0.70), asset.shape[1])
        target_height = max(1, round(asset.shape[0] * target_width / asset.shape[1]))
        text = cv2.resize(asset, (target_width, target_height), interpolation=cv2.INTER_AREA)
        left, top = (width - target_width) // 2, (height - target_height) // 2
        pad = max(4, int(width * 0.012))
        x1, y1, x2, y2 = max(0, left-pad), max(0, top-pad), min(width, left+target_width+pad), min(height, top+target_height+pad)
        region = image[y1:y2, x1:x2]
        original_region = region.copy()
        background = region.copy()
        background[:] = (16, 16, 180)
        pulse = 0.78
        cv2.addWeighted(background, pulse, region, 1-pulse, 0, dst=region)
        cv2.rectangle(image, (x1+2,y1+2), (x2-3,y2-3), (70,70,255), 2)
        roi = image[top:top+target_height, left:left+target_width]
        alpha = text[:, :, 3:4].astype("float32") / 255.0
        roi[:] = (text[:, :, :3] * alpha + roi * (1-alpha)).astype("uint8")
        # Fade the entire warning, including text and border, once every 2 seconds.
        visibility = max(0.0, min(1.0, 0.5 + 0.75 * math.cos(now * math.pi)))
        cv2.addWeighted(region, visibility, original_region, 1-visibility, 0, dst=region)
