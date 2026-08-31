#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np
from ultralytics import YOLO

from app.domain import Detection
from app.inference.phase3_association import (
    TrackedPersonBox,
    associate_ppe_detections,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-video", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--track-model", required=True)
    parser.add_argument("--ppe-model", required=True)
    parser.add_argument("--duration-seconds", type=float, default=10.0)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--confidence", type=float, default=0.35)
    return parser.parse_args()


def result_detections(result: Any) -> tuple[Detection, ...]:
    boxes = getattr(result, "boxes", None)
    if boxes is None:
        return ()

    coordinates = boxes.xyxy.detach().cpu().tolist()
    confidences = boxes.conf.detach().cpu().tolist()
    class_ids = boxes.cls.detach().cpu().tolist()
    names: Mapping[int, str] = result.names

    return tuple(
        Detection(
            class_id=int(class_id),
            class_name=str(names.get(int(class_id), int(class_id))),
            confidence=float(confidence),
            x1=float(xyxy[0]),
            y1=float(xyxy[1]),
            x2=float(xyxy[2]),
            y2=float(xyxy[3]),
        )
        for xyxy, confidence, class_id in zip(
            coordinates,
            confidences,
            class_ids,
            strict=True,
        )
    )


def person_tracks(result: Any) -> tuple[TrackedPersonBox, ...]:
    detections = result_detections(result)
    persons = [
        detection
        for detection in detections
        if detection.class_name.strip().lower() == "person"
    ]
    return tuple(
        TrackedPersonBox(
            track_id=index + 1,
            x1=detection.x1,
            y1=detection.y1,
            x2=detection.x2,
            y2=detection.y2,
        )
        for index, detection in enumerate(persons)
    )


def scan_image(
    *,
    path: Path,
    track_model: YOLO,
    ppe_model: YOLO,
    confidence: float,
) -> dict[str, Any]:
    image = cv2.imread(str(path))
    if image is None:
        return {
            "file": path.name,
            "readable": False,
            "score": -1,
        }

    track_results = track_model.predict(
        source=image,
        conf=confidence,
        iou=0.70,
        imgsz=640,
        device="0",
        verbose=False,
    )
    ppe_results = ppe_model.predict(
        source=image,
        conf=confidence,
        iou=0.70,
        imgsz=640,
        device="0",
        verbose=False,
    )

    track_result = track_results[0] if track_results else None
    ppe_result = ppe_results[0] if ppe_results else None
    if track_result is None:
        tracks = ()
    else:
        tracks = person_tracks(track_result)

    if ppe_result is None:
        ppe = ()
    else:
        ppe = result_detections(ppe_result)

    association = associate_ppe_detections(
        tracks=tracks,
        detections=ppe,
    )

    no_helmet_tracks = 0
    helmet_tracks = 0
    track_details: list[dict[str, Any]] = []
    for match in association.matches:
        head_no_helmet = match.has_head and not match.has_helmet
        if head_no_helmet:
            no_helmet_tracks += 1
        if match.has_helmet:
            helmet_tracks += 1
        track_details.append(
            {
                "trackId": match.track_id,
                "helmetCount": match.helmet_count,
                "headCount": match.head_count,
                "vestCount": match.vest_count,
                "headNoHelmet": head_no_helmet,
            }
        )

    ppe_class_counts: dict[str, int] = {}
    for detection in ppe:
        name = detection.class_name.strip().lower()
        ppe_class_counts[name] = ppe_class_counts.get(name, 0) + 1

    # Prefer an associated bare-head track. Extra people/heads are useful;
    # helmets reduce confidence that the repeated frame will trigger policy.
    score = (
        no_helmet_tracks * 10_000
        + len(tracks) * 100
        + ppe_class_counts.get("head", 0) * 20
        - helmet_tracks * 50
        - ppe_class_counts.get("helmet", 0) * 10
    )

    return {
        "file": path.name,
        "readable": True,
        "width": int(image.shape[1]),
        "height": int(image.shape[0]),
        "personTracks": len(tracks),
        "headNoHelmetTracks": no_helmet_tracks,
        "helmetTracks": helmet_tracks,
        "ppeClassCounts": ppe_class_counts,
        "unassignedPpe": association.unassigned_count,
        "ignoredPpe": association.ignored_count,
        "trackDetails": track_details,
        "score": score,
    }


def fit_frame(image: np.ndarray, max_width: int = 1280) -> np.ndarray:
    height, width = image.shape[:2]
    if width > max_width:
        scale = max_width / width
        width = int(round(width * scale))
        height = int(round(height * scale))
        image = cv2.resize(
            image,
            (width, height),
            interpolation=cv2.INTER_AREA,
        )

    # MP4 encoders are most reliable with even dimensions.
    height -= height % 2
    width -= width % 2
    return image[:height, :width]


def jitter_frame(image: np.ndarray, frame_index: int) -> np.ndarray:
    height, width = image.shape[:2]
    dx = (frame_index % 5) - 2
    dy = ((frame_index // 5) % 5) - 2
    matrix = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(
        image,
        matrix,
        (width, height),
        borderMode=cv2.BORDER_REFLECT,
    )


def build_video(
    *,
    image_path: Path,
    output_path: Path,
    duration_seconds: float,
    fps: float,
) -> dict[str, Any]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"selected image cannot be read: {image_path}")
    image = fit_frame(image)
    height, width = image.shape[:2]
    frame_count = max(1, int(round(duration_seconds * fps)))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        raise RuntimeError(f"cannot open VideoWriter: {output_path}")

    try:
        for index in range(frame_count):
            writer.write(jitter_frame(image, index))
    finally:
        writer.release()

    capture = cv2.VideoCapture(str(output_path))
    opened = capture.isOpened()
    detected_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    detected_fps = float(capture.get(cv2.CAP_PROP_FPS))
    ok, first = capture.read()
    capture.release()

    if not opened or not ok or first is None:
        raise RuntimeError(
            f"generated MP4 failed decode validation: {output_path}"
        )

    return {
        "frameCount": frame_count,
        "detectedFrameCount": detected_frames,
        "fps": fps,
        "detectedFps": detected_fps,
        "width": width,
        "height": height,
    }


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir)
    output_video = Path(args.output_video)
    report_path = Path(args.report)

    track_model = YOLO(args.track_model)
    ppe_model = YOLO(args.ppe_model)

    candidates = sorted(
        path
        for path in input_dir.iterdir()
        if path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )
    results = [
        scan_image(
            path=path,
            track_model=track_model,
            ppe_model=ppe_model,
            confidence=args.confidence,
        )
        for path in candidates
    ]

    eligible = [
        result
        for result in results
        if result.get("readable")
        and int(result.get("personTracks", 0)) > 0
        and int(result.get("headNoHelmetTracks", 0)) > 0
    ]

    report: dict[str, Any] = {
        "trackModel": args.track_model,
        "ppeModel": args.ppe_model,
        "confidence": args.confidence,
        "candidates": results,
        "selected": None,
        "video": None,
    }

    if not eligible:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            "[FAIL] head-without-helmet로 association되는 후보가 없습니다."
        )
        return 3

    selected = max(
        eligible,
        key=lambda result: (
            int(result["score"]),
            int(result["headNoHelmetTracks"]),
            int(result["personTracks"]),
        ),
    )
    selected_path = input_dir / str(selected["file"])

    video_info = build_video(
        image_path=selected_path,
        output_path=output_video,
        duration_seconds=args.duration_seconds,
        fps=args.fps,
    )

    report["selected"] = selected
    report["video"] = video_info
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "[PASS] selected="
        f"{selected['file']} "
        f"personTracks={selected['personTracks']} "
        f"headNoHelmetTracks={selected['headNoHelmetTracks']} "
        f"helmetTracks={selected['helmetTracks']}"
    )
    print(
        "[PASS] generated="
        f"{output_video} "
        f"frames={video_info['frameCount']} "
        f"fps={video_info['fps']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
