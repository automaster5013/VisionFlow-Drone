"""CPU-only dataset intake evidence for VisionFlow Phase 2B-6A."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from app.model_contract import (
    VISDRONE_CLASS_MAPPING,
    ModelContractError,
    sha256_file,
)
from app.model_evaluation import label_path, load_dataset_inventory
from app.model_training_plan import (
    TrainingPlanError,
    compile_training_plan,
)

SCHEMA_VERSION = 1
DATASET_INTAKE_CONTRACT_ID = "visionflow.phase2b6.dataset-intake-report"
INTAKE_STATUS = "READY"
SMALL_OBJECT_AREA_PX = 32 * 32
VISDRONE_NAMES = {
    int(item["id"]): str(item["sourceName"])
    for item in VISDRONE_CLASS_MAPPING
}
ImageProbe = Callable[[Path], tuple[int, int]]


class DatasetIntakeError(ValueError):
    """Raised when a dataset cannot be admitted for controlled training."""


def _fail(message: str) -> None:
    raise DatasetIntakeError(message)


def _opencv_image_dimensions(path: Path) -> tuple[int, int]:
    try:
        import cv2
        import numpy as np
    except ImportError as error:
        raise DatasetIntakeError(
            "이미지 무결성 점검에는 numpy와 opencv-python이 필요합니다."
        ) from error
    encoded = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)
    if image is None or len(image.shape) < 2:
        _fail(f"이미지를 디코딩할 수 없습니다: {path}")
    height, width = image.shape[:2]
    if width <= 0 or height <= 0:
        _fail(f"이미지 크기가 올바르지 않습니다: {path}")
    return int(width), int(height)


def _probe_dimensions(path: Path, probe: ImageProbe) -> tuple[int, int]:
    try:
        dimensions = probe(path)
    except DatasetIntakeError:
        raise
    except Exception as error:
        raise DatasetIntakeError(
            f"이미지 디코딩 중 오류가 발생했습니다: {path}: {error}"
        ) from error
    if (
        not isinstance(dimensions, tuple)
        or len(dimensions) != 2
        or any(isinstance(value, bool) or not isinstance(value, int) for value in dimensions)
    ):
        _fail(f"이미지 probe가 올바른 (width, height)를 반환하지 않았습니다: {path}")
    width, height = dimensions
    if width <= 0 or height <= 0:
        _fail(f"이미지 크기가 올바르지 않습니다: {path}")
    return width, height


def _label_objects(
    label: Path,
    *,
    image_width: int,
    image_height: int,
) -> tuple[list[int], int]:
    class_ids: list[int] = []
    small_count = 0
    for line_number, raw_line in enumerate(
        label.read_text(encoding="utf-8-sig").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line:
            continue
        fields = line.split()
        if len(fields) != 5:
            _fail(f"YOLO detect 라벨은 5개 필드여야 합니다: {label}:{line_number}")
        try:
            raw_class, center_x, center_y, width, height = map(float, fields)
        except ValueError as error:
            raise DatasetIntakeError(
                f"라벨 숫자 형식이 올바르지 않습니다: {label}:{line_number}"
            ) from error
        class_id = int(raw_class)
        if raw_class != class_id or class_id not in VISDRONE_NAMES:
            _fail(
                "라벨 클래스 ID가 VisDrone 10-class 계약을 벗어났습니다: "
                f"{label}:{line_number}"
            )
        coordinates = (center_x, center_y, width, height)
        if not all(math.isfinite(value) for value in coordinates):
            _fail(f"라벨 좌표는 유한한 수여야 합니다: {label}:{line_number}")
        if width <= 0.0 or height <= 0.0:
            _fail(f"라벨 너비와 높이는 0보다 커야 합니다: {label}:{line_number}")
        area = width * image_width * height * image_height
        class_ids.append(class_id)
        if area < SMALL_OBJECT_AREA_PX:
            small_count += 1
    return class_ids, small_count


def _class_distribution(class_counts: Mapping[int, int]) -> list[dict[str, object]]:
    return [
        {
            "id": class_id,
            "sourceName": VISDRONE_NAMES[class_id],
            "objectCount": int(class_counts[class_id]),
        }
        for class_id in sorted(VISDRONE_NAMES)
    ]


def _split_intake(
    *,
    split: str,
    images: Sequence[Path],
    fingerprint_sha256: str,
    probe: ImageProbe,
) -> tuple[dict[str, object], dict[str, tuple[Path, ...]], set[Path]]:
    class_counts = {class_id: 0 for class_id in VISDRONE_NAMES}
    hashes: dict[str, list[Path]] = {}
    expected_labels: set[Path] = set()
    total_image_bytes = 0
    empty_label_image_count = 0
    object_count = 0
    small_object_count = 0
    widths: list[int] = []
    heights: list[int] = []

    for image in images:
        if not image.is_file() or image.is_symlink():
            _fail(f"이미지는 심볼릭 링크가 아닌 일반 파일이어야 합니다: {image}")
        label = label_path(image).resolve()
        if not label.is_file() or label.is_symlink():
            _fail(f"라벨은 심볼릭 링크가 아닌 일반 파일이어야 합니다: {label}")
        expected_labels.add(label)
        width, height = _probe_dimensions(image, probe)
        widths.append(width)
        heights.append(height)
        total_image_bytes += image.stat().st_size
        image_sha = sha256_file(image)
        hashes.setdefault(image_sha, []).append(image.resolve())
        class_ids, small_count = _label_objects(
            label,
            image_width=width,
            image_height=height,
        )
        if not class_ids:
            empty_label_image_count += 1
        for class_id in class_ids:
            class_counts[class_id] += 1
        object_count += len(class_ids)
        small_object_count += small_count

    missing_classes = [
        VISDRONE_NAMES[class_id]
        for class_id, count in class_counts.items()
        if count == 0
    ]
    if missing_classes:
        _fail(f"{split} split에 객체가 없는 VisDrone 클래스가 있습니다: {missing_classes}")

    duplicate_count = sum(len(paths) - 1 for paths in hashes.values() if len(paths) > 1)
    image_count = len(images)
    report = {
        "split": split,
        "imageCount": image_count,
        "labelFileCount": len(expected_labels),
        "missingLabelFileCount": 0,
        "emptyLabelImageCount": empty_label_image_count,
        "emptyLabelImageRate": empty_label_image_count / image_count,
        "objectCount": object_count,
        "smallObjectCount": small_object_count,
        "smallObjectRate": small_object_count / object_count,
        "totalImageBytes": total_image_bytes,
        "minimumWidth": min(widths),
        "maximumWidth": max(widths),
        "minimumHeight": min(heights),
        "maximumHeight": max(heights),
        "uniqueImageContentCount": len(hashes),
        "duplicateImageContentCount": duplicate_count,
        "fingerprintMode": "full",
        "fingerprintSha256": fingerprint_sha256,
        "classes": _class_distribution(class_counts),
    }
    immutable_hashes = {key: tuple(value) for key, value in hashes.items()}
    return report, immutable_hashes, expected_labels


def _find_orphan_labels(dataset_base: Path, expected_labels: set[Path]) -> list[Path]:
    managed_roots: set[Path] = set()
    for label in expected_labels:
        relative = label.relative_to(dataset_base)
        parts = relative.parts
        label_indexes = [
            index for index, part in enumerate(parts) if part.casefold() == "labels"
        ]
        if not label_indexes:
            _fail(f"라벨 경로에 labels 디렉터리가 없습니다: {label}")
        index = label_indexes[-1]
        depth = min(index + 2, len(parts) - 1)
        managed_roots.add(dataset_base.joinpath(*parts[:depth]))
    candidates = {
        path.resolve()
        for root in managed_roots
        for path in root.rglob("*.txt")
        if path.is_file()
    }
    return sorted(candidates - expected_labels, key=lambda path: str(path).casefold())


def _combined_full_fingerprint(
    *,
    plan_sha256: str,
    data_yaml_sha256: str,
    split_manifest_sha256: str,
    train_fingerprint: str,
    val_fingerprint: str,
) -> str:
    evidence = {
        "planSha256": plan_sha256,
        "dataYamlSha256": data_yaml_sha256,
        "splitManifestSha256": split_manifest_sha256,
        "trainFingerprintSha256": train_fingerprint,
        "valFingerprintSha256": val_fingerprint,
    }
    return hashlib.sha256(
        json.dumps(
            evidence,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def build_dataset_intake_report(
    *,
    root: Path,
    plan_path: Path,
    ultralytics_version: str | None = None,
    image_probe: ImageProbe | None = None,
) -> dict[str, object]:
    """Build a full-content dataset receipt without GPU or training access."""
    root = root.resolve()
    readiness = compile_training_plan(
        root=root,
        plan_path=plan_path,
        ultralytics_version=ultralytics_version,
    )
    data = readiness["data"]
    if not isinstance(data, Mapping):
        _fail("학습 계획 readiness의 data 증거가 올바르지 않습니다.")
    data_yaml = Path(str(data["dataYamlPath"])).resolve()
    dataset_base = Path(str(data["datasetBase"])).resolve()
    split_manifest_path = Path(str(data["splitManifestPath"])).resolve()
    probe = image_probe or _opencv_image_dimensions

    train_spec, train_images = load_dataset_inventory(data_yaml, "train", "full")
    val_spec, val_images = load_dataset_inventory(data_yaml, "val", "full")
    train_report, train_hashes, train_labels = _split_intake(
        split="train",
        images=train_images,
        fingerprint_sha256=str(train_spec["fingerprintSha256"]),
        probe=probe,
    )
    val_report, val_hashes, val_labels = _split_intake(
        split="val",
        images=val_images,
        fingerprint_sha256=str(val_spec["fingerprintSha256"]),
        probe=probe,
    )

    shared_hashes = sorted(set(train_hashes) & set(val_hashes))
    if shared_hashes:
        examples = [
            {
                "sha256": value,
                "train": str(train_hashes[value][0]),
                "val": str(val_hashes[value][0]),
            }
            for value in shared_hashes[:3]
        ]
        _fail(f"train/val에 동일 이미지 콘텐츠가 있습니다: {examples}")

    orphan_labels = _find_orphan_labels(dataset_base, train_labels | val_labels)
    if orphan_labels:
        _fail(f"이미지와 연결되지 않은 orphan 라벨이 있습니다: {orphan_labels[:3]}")

    plan_evidence = readiness["plan"]
    if not isinstance(plan_evidence, Mapping):
        _fail("학습 계획 readiness의 plan 증거가 올바르지 않습니다.")
    plan_sha256 = str(plan_evidence["sha256"])
    data_yaml_sha256 = sha256_file(data_yaml)
    split_manifest_sha256 = sha256_file(split_manifest_path)
    combined_fingerprint = _combined_full_fingerprint(
        plan_sha256=plan_sha256,
        data_yaml_sha256=data_yaml_sha256,
        split_manifest_sha256=split_manifest_sha256,
        train_fingerprint=str(train_report["fingerprintSha256"]),
        val_fingerprint=str(val_report["fingerprintSha256"]),
    )
    report: dict[str, object] = {
        "schemaVersion": SCHEMA_VERSION,
        "contractId": DATASET_INTAKE_CONTRACT_ID,
        "status": INTAKE_STATUS,
        "stage": str(readiness["stage"]),
        "plan": {
            "path": str(plan_evidence["path"]),
            "sha256": plan_sha256,
            "evidenceLockSha256": str(readiness["evidenceLockSha256"]),
        },
        "dataset": {
            "name": str(data["datasetName"]),
            "version": str(data["datasetVersion"]),
            "sourceDatasets": list(data["sourceDatasets"]),
            "basePath": str(dataset_base),
            "dataYamlPath": str(data_yaml),
            "dataYamlSha256": data_yaml_sha256,
            "splitManifestPath": str(split_manifest_path),
            "splitManifestSha256": split_manifest_sha256,
            "splitUnit": "VIDEO_SEQUENCE",
            "classCount": len(VISDRONE_NAMES),
            "fingerprintMode": "full",
            "combinedFingerprintSha256": combined_fingerprint,
            "crossSplitDuplicateContentCount": 0,
            "orphanLabelFileCount": 0,
            "train": train_report,
            "val": val_report,
        },
        "runtime": dict(readiness["runtime"]),
        "safeguards": {
            "trainingExecuted": False,
            "gpuAccessed": False,
            "dockerAccessed": False,
            "torchImported": False,
            "ultralyticsImported": False,
            "imageDecodeCpuOnly": True,
        },
    }
    report["receiptSha256"] = hashlib.sha256(
        json.dumps(
            report,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return report


def _output_path(root: Path, raw_path: str) -> Path:
    root = root.resolve()
    configured = Path(raw_path)
    lexical = configured if configured.is_absolute() else root / configured
    lexical = Path(os.path.abspath(lexical))
    try:
        relative = lexical.relative_to(root)
    except ValueError as error:
        raise DatasetIntakeError("output이 프로젝트 root 밖을 가리킵니다.") from error
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink():
            _fail(f"output 경로에는 심볼릭 링크를 사용할 수 없습니다: {current}")
    if lexical.exists() or lexical.is_symlink():
        _fail(f"기존 dataset intake receipt를 덮어쓰지 않습니다: {lexical}")
    return lexical


def write_dataset_intake_report(
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
            "Build a CPU-only VisionFlow S1/S2 dataset intake receipt without "
            "loading YOLO, torch, CUDA, or Docker."
        )
    )
    parser.add_argument("--root", default=".", help="VisionFlow AI project root")
    parser.add_argument("--plan", required=True, help="Concrete S1/S2 training plan JSON")
    output = parser.add_mutually_exclusive_group()
    output.add_argument(
        "--output",
        help="New receipt path under --root (existing files are refused)",
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
        report = build_dataset_intake_report(
            root=root,
            plan_path=Path(arguments.plan),
        )
        if arguments.output:
            target = write_dataset_intake_report(root, arguments.output, report)
            print(f"VISIONFLOW_PHASE2B6_DATASET_INTAKE=READY output={target}")
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))
    except (
        DatasetIntakeError,
        ModelContractError,
        TrainingPlanError,
        OSError,
        ValueError,
    ) as error:
        print(
            f"VISIONFLOW_PHASE2B6_DATASET_INTAKE=FAIL error={error}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
