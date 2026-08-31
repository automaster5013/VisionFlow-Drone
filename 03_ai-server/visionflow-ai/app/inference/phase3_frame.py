from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any

import numpy as np
from ultralytics import YOLO

from app.config import Settings
from app.domain import Detection, FramePacket, InferencePacket
from app.inference.phase3_association import TrackedPersonBox
from app.inference.phase3_pose import (
    Phase3PoseFrameResult,
    build_pose_frame_result,
)
from app.inference.phase3_ppe_depth import PpeDepthFrameResult
from app.inference.phase3_runtime import Phase3Runtime
from app.inference.phase3_segmentation import (
    Phase3SegmentationFrameResult,
    build_segmentation_frame_result,
    render_segmentation_overlay,
)
from app.model_contract import TrackKind
from app.model_runtime import ClassResolver, resolve_identity_class

ModelFactory = Callable[[str], Any]


@dataclass(frozen=True, slots=True)
class Phase3FrameAnalysis:
    inference: InferencePacket
    ppe: PpeDepthFrameResult | None
    tracked_person_count: int
    ppe_sampled: bool
    pose: Phase3PoseFrameResult | None = None
    pose_sampled: bool = False
    segmentation: Phase3SegmentationFrameResult | None = None
    segmentation_sampled: bool = False


class Phase3FrameAnalyzer:
    def __init__(
        self,
        *,
        runtime: Phase3Runtime,
        source_fps: float,
        track_model_path: str,
        ppe_model_path: str,
        confidence: float,
        iou: float,
        image_size: int,
        device: str,
        pose_model_path: str | None = None,
        segmentation_model_path: str | None = None,
        track_model: Any | None = None,
        class_resolver: ClassResolver | None = None,
        model_factory: ModelFactory = YOLO,
    ) -> None:
        if source_fps <= 0:
            raise ValueError("source_fps must be positive.")
        if track_model is None and not track_model_path.strip():
            raise ValueError("track_model_path must not be blank.")
        if not ppe_model_path.strip():
            raise ValueError("ppe_model_path must not be blank.")
        if not 0.0 < confidence <= 1.0:
            raise ValueError("confidence must be in the range (0, 1].")
        if not 0.0 < iou <= 1.0:
            raise ValueError("iou must be in the range (0, 1].")
        if image_size <= 0:
            raise ValueError("image_size must be positive.")
        if not device.strip():
            raise ValueError("device must not be blank.")
        if runtime.pose_enabled and (
            pose_model_path is None or not pose_model_path.strip()
        ):
            raise ValueError(
                "pose_model_path must not be blank when pose is enabled."
            )
        if getattr(runtime, "segmentation_enabled", False) and (
            segmentation_model_path is None
            or not segmentation_model_path.strip()
        ):
            raise ValueError(
                "segmentation_model_path must not be blank when "
                "segmentation is enabled."
            )

        self._runtime = runtime
        self._source_fps = float(source_fps)
        self._confidence = confidence
        self._iou = iou
        self._image_size = image_size
        self._device = device
        self._class_resolver = class_resolver or resolve_identity_class
        self._track_model = (
            track_model
            if track_model is not None
            else model_factory(track_model_path)
        )
        self._ppe_model = model_factory(ppe_model_path)
        self._pose_model = (
            model_factory(pose_model_path)
            if runtime.pose_enabled and pose_model_path is not None
            else None
        )
        self._segmentation_model = (
            model_factory(segmentation_model_path)
            if (
                getattr(runtime, "segmentation_enabled", False)
                and segmentation_model_path is not None
            )
            else None
        )

    @property
    def sample_stride_frames(self) -> int:
        return self._runtime.sample_stride_frames

    def analyze(self, frame: FramePacket) -> Phase3FrameAnalysis:
        started_at = time.perf_counter()
        track_results = self._track_model.track(
            source=frame.image,
            persist=True,
            tracker="botsort.yaml",
            conf=self._confidence,
            iou=self._iou,
            imgsz=self._image_size,
            device=self._device,
            verbose=False,
        )
        inference_ms = (time.perf_counter() - started_at) * 1_000.0

        track_result = track_results[0] if track_results else None

        if track_result is None:
            detections = ()
            tracked_people = ()
            annotated_image = frame.image.copy()
        else:
            detections = _to_detections(
                track_result,
                class_resolver=self._class_resolver,
            )
            tracked_people = _to_tracked_people(
                track_result,
                class_resolver=self._class_resolver,
            )
            annotated_image = np.asarray(track_result.plot())

        inference = InferencePacket(
            frame=frame,
            detections=detections,
            inference_ms=inference_ms,
            annotated_image=annotated_image,
        )

        ppe_sampled = (
            frame.frame_index % self._runtime.sample_stride_frames == 0
        )
        ppe_result: PpeDepthFrameResult | None = None

        if ppe_sampled:
            if tracked_people:
                ppe_results = self._ppe_model.predict(
                    source=frame.image,
                    conf=self._confidence,
                    iou=self._iou,
                    imgsz=self._image_size,
                    device=self._device,
                    verbose=False,
                )
                ppe_detections = (
                    _to_detections(ppe_results[0])
                    if ppe_results
                    else ()
                )
            else:
                ppe_detections = ()

            ppe_result = self._runtime.process_sample(
                frame_index=frame.frame_index + 1,
                event_time_sec=frame.frame_index / self._source_fps,
                frame=frame.image,
                tracks=tracked_people,
                detections=ppe_detections,
            )

        pose_result, pose_sampled = self._analyze_pose(
            frame=frame,
            tracked_people=tracked_people,
        )
        segmentation_result, segmentation_sampled = (
            self._analyze_segmentation(
                frame=frame,
                tracked_people=tracked_people,
            )
        )
        if segmentation_result is not None:
            inference = replace(
                inference,
                annotated_image=render_segmentation_overlay(
                    image=inference.annotated_image,
                    result=segmentation_result,
                ),
            )

        return Phase3FrameAnalysis(
            inference=inference,
            ppe=ppe_result,
            tracked_person_count=len(tracked_people),
            ppe_sampled=ppe_sampled,
            pose=pose_result,
            pose_sampled=pose_sampled,
            segmentation=segmentation_result,
            segmentation_sampled=segmentation_sampled,
        )

    def _analyze_pose(
        self,
        *,
        frame: FramePacket,
        tracked_people: tuple[TrackedPersonBox, ...],
    ) -> tuple[Phase3PoseFrameResult | None, bool]:
        if not self._runtime.pose_enabled:
            return None, False

        if not self._runtime.should_sample_pose(frame.frame_index):
            return None, False

        policy_frame_index = frame.frame_index + 1

        if not tracked_people:
            return (
                Phase3PoseFrameResult(
                    frame_index=policy_frame_index,
                    observations=(),
                ),
                True,
            )

        if self._pose_model is None:
            raise RuntimeError(
                "Pose runtime is enabled but pose model is unavailable."
            )

        pose_results = self._pose_model.predict(
            source=frame.image,
            conf=self._confidence,
            iou=self._iou,
            imgsz=self._image_size,
            device=self._device,
            verbose=False,
        )

        if not pose_results:
            return (
                Phase3PoseFrameResult(
                    frame_index=policy_frame_index,
                    observations=(),
                ),
                True,
            )

        return (
            build_pose_frame_result(
                result=pose_results[0],
                tracks=tracked_people,
                frame_index=policy_frame_index,
            ),
            True,
        )

    def _analyze_segmentation(
        self,
        *,
        frame: FramePacket,
        tracked_people: tuple[TrackedPersonBox, ...],
    ) -> tuple[Phase3SegmentationFrameResult | None, bool]:
        if not getattr(
            self._runtime,
            "segmentation_enabled",
            False,
        ):
            return None, False

        if not self._runtime.should_sample_segmentation(
            frame.frame_index
        ):
            return None, False

        policy_frame_index = frame.frame_index + 1

        if self._segmentation_model is None:
            raise RuntimeError(
                "Segmentation runtime is enabled but segmentation "
                "model is unavailable."
            )

        segmentation_results = self._segmentation_model.predict(
            source=frame.image,
            conf=self._confidence,
            iou=self._iou,
            imgsz=self._image_size,
            device=self._device,
            verbose=False,
        )

        if not segmentation_results:
            return (
                Phase3SegmentationFrameResult(
                    frame_index=policy_frame_index,
                    instances=(),
                ),
                True,
            )

        return (
            build_segmentation_frame_result(
                result=segmentation_results[0],
                frame_index=policy_frame_index,
                tracks=tracked_people,
            ),
            True,
        )


def create_phase3_frame_analyzer(
    *,
    settings: Settings,
    runtime: Phase3Runtime | None,
    source_fps: float,
    track_model: Any | None = None,
    class_resolver: ClassResolver | None = None,
    model_factory: ModelFactory = YOLO,
) -> Phase3FrameAnalyzer | None:
    if runtime is None:
        return None

    return Phase3FrameAnalyzer(
        runtime=runtime,
        source_fps=source_fps,
        track_model_path=settings.model_path,
        ppe_model_path=settings.phase3_ppe_model_path,
        confidence=settings.confidence,
        iou=settings.iou,
        image_size=settings.image_size,
        device=settings.device,
        pose_model_path=(
            settings.phase3_pose_model_path
            if runtime.pose_enabled
            else None
        ),
        segmentation_model_path=(
            settings.phase3_segmentation_model_path
            if getattr(runtime, "segmentation_enabled", False)
            else None
        ),
        track_model=track_model,
        class_resolver=class_resolver,
        model_factory=model_factory,
    )


def _to_detections(
    result: Any,
    *,
    class_resolver: ClassResolver = resolve_identity_class,
) -> tuple[Detection, ...]:
    boxes = getattr(result, "boxes", None)
    if boxes is None:
        return ()

    coordinates = boxes.xyxy.detach().cpu().tolist()
    confidences = boxes.conf.detach().cpu().tolist()
    class_ids = boxes.cls.detach().cpu().tolist()
    names: Mapping[int, str] = result.names

    detections: list[Detection] = []
    for xyxy, confidence, class_id_value in zip(
        coordinates,
        confidences,
        class_ids,
        strict=True,
    ):
        class_id = int(class_id_value)
        source_name = str(names.get(class_id, class_id))
        resolved_class = class_resolver(class_id, source_name)
        detections.append(
            Detection(
                class_id=class_id,
                class_name=resolved_class.canonical_name,
                confidence=float(confidence),
                x1=float(xyxy[0]),
                y1=float(xyxy[1]),
                x2=float(xyxy[2]),
                y2=float(xyxy[3]),
            )
        )
    return tuple(detections)


def _to_tracked_people(
    result: Any,
    *,
    class_resolver: ClassResolver = resolve_identity_class,
) -> tuple[TrackedPersonBox, ...]:
    boxes = getattr(result, "boxes", None)
    if boxes is None or boxes.id is None:
        return ()

    track_ids = boxes.id.detach().cpu().tolist()
    coordinates = boxes.xyxy.detach().cpu().tolist()
    class_ids = boxes.cls.detach().cpu().tolist()
    names: Mapping[int, str] = result.names

    tracked_people: list[TrackedPersonBox] = []

    for track_id_value, xyxy, class_id_value in zip(
        track_ids,
        coordinates,
        class_ids,
        strict=True,
    ):
        class_id = int(class_id_value)
        source_name = str(names.get(class_id, class_id))
        resolved_class = class_resolver(class_id, source_name)

        if resolved_class.track_kind is not TrackKind.HUMAN:
            continue

        tracked_people.append(
            TrackedPersonBox(
                track_id=int(track_id_value),
                x1=float(xyxy[0]),
                y1=float(xyxy[1]),
                x2=float(xyxy[2]),
                y2=float(xyxy[3]),
            )
        )

    return tuple(tracked_people)
