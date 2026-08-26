"""GPU-free two-stage VisDrone training-plan validation for Phase 2B-5."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from collections.abc import Mapping, Sequence
from importlib import metadata
from pathlib import Path
from typing import Any

import yaml

from app.model_contract import (
    VISDRONE_CLASS_MAPPING,
    HeadMode,
    ModelContractError,
    ModelProfile,
    ModelRole,
    TrainingStage,
    load_json_object,
    sha256_file,
)
from app.model_evaluation import label_path, load_dataset_inventory

SCHEMA_VERSION = 1
TRAINING_PLAN_CONTRACT_ID = "visionflow.phase2b5.transfer-training-plan"
SPLIT_MANIFEST_CONTRACT_ID = "visionflow.phase2b4.video-split-manifest"
READINESS_STATUS = "READY"
MINIMUM_ULTRALYTICS_VERSION = "8.4.0"
DATASET_FINGERPRINT_MODE = "labels"
FINAL_HELDOUT_SPLIT = "FINAL_HELDOUT"

PUBLIC_TRAIN_ARGUMENTS = (
    "imgsz",
    "epochs",
    "batch",
    "seed",
    "device",
    "workers",
    "optimizer",
    "patience",
    "deterministic",
    "amp",
    "close_mosaic",
    "cache",
)
INTERNAL_YOLO26_ARGUMENTS = frozenset(
    {"muon_w", "sgd_w", "cls_w", "o2m", "topk"}
)
VISDRONE_NAMES = {
    int(item["id"]): str(item["sourceName"]) for item in VISDRONE_CLASS_MAPPING
}

STAGE_POLICIES: dict[TrainingStage, dict[str, object]] = {
    TrainingStage.VISDRONE_S1: {
        "parentFileName": "yolo26m.pt",
        "outputFileName": "yolo26m-visdrone-s1-best.pt",
        "sourceDatasets": ("VISDRONE2019_DET",),
        "parentManifestRequired": False,
    },
    TrainingStage.VISIONFLOW_S2: {
        "parentFileName": "yolo26m-visdrone-s1-best.pt",
        "outputFileName": "yolo26m-visdrone-s2-best.pt",
        "sourceDatasets": ("VISDRONE2019_DET", "VISIONFLOW_PRESENTATION"),
        "parentManifestRequired": True,
    },
}


class TrainingPlanError(ValueError):
    """Raised when a Phase 2B-5 training plan is not safe to lock."""


def _fail(message: str) -> None:
    raise TrainingPlanError(message)


def _object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{field}은(는) JSON 객체여야 합니다.")
    return {str(key): item for key, item in value.items()}


def _array(value: object, field: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        _fail(f"{field}은(는) JSON 배열이어야 합니다.")
    return list(value)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{field}은(는) 비어 있지 않은 문자열이어야 합니다.")
    return value.strip()


def _integer(value: object, field: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(f"{field}은(는) {minimum} 이상의 정수여야 합니다.")
    return value


def _boolean(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        _fail(f"{field}은(는) boolean이어야 합니다.")
    return value


def _sha256(value: object, field: str) -> str:
    normalized = _text(value, field).lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        _fail(f"{field}은(는) 64자리 SHA-256이어야 합니다.")
    return normalized


def _exact_keys(
    value: Mapping[str, object], expected: set[str], field: str
) -> None:
    actual = set(value)
    if actual == expected:
        return
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    _fail(f"{field} 키가 계약과 다릅니다: missing={missing}, unexpected={unexpected}")


def _resolve_under_root(root: Path, raw_path: object, field: str) -> Path:
    root = root.resolve()
    configured = Path(_text(raw_path, field))
    lexical = configured if configured.is_absolute() else root / configured
    lexical = Path(os.path.abspath(lexical))
    try:
        relative = lexical.relative_to(root)
    except ValueError as error:
        raise TrainingPlanError(f"{field}가 프로젝트 root 밖을 가리킵니다.") from error

    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            _fail(f"{field}에는 심볼릭 링크를 사용할 수 없습니다: {current}")
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as error:
        raise TrainingPlanError(f"{field}을(를) 찾을 수 없습니다: {lexical}") from error
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise TrainingPlanError(f"{field}가 프로젝트 root 밖을 가리킵니다.") from error
    return resolved


def _safe_file(root: Path, raw_path: object, field: str) -> Path:
    path = _resolve_under_root(root, raw_path, field)
    if not path.is_file():
        _fail(f"{field}은(는) 일반 파일이어야 합니다: {path}")
    return path


def _safe_directory(root: Path, path: Path, field: str) -> Path:
    resolved = _resolve_under_root(root, str(path), field)
    if not resolved.is_dir():
        _fail(f"{field}은(는) 디렉터리여야 합니다: {resolved}")
    return resolved


def _reject_dataset_symlinks(dataset_base: Path) -> None:
    for path in dataset_base.rglob("*"):
        if path.is_symlink():
            _fail(f"학습 데이터셋에는 심볼릭 링크를 사용할 수 없습니다: {path}")


def _validate_ultralytics_version(installed: str) -> str:
    match = re.match(r"^\s*(\d+)\.(\d+)\.(\d+)", installed)
    if match is None:
        _fail(f"Ultralytics 버전 형식을 해석할 수 없습니다: {installed}")
    version_tuple = tuple(int(value) for value in match.groups())
    if version_tuple < (8, 4, 0):
        _fail(
            "YOLO26 학습 계획에는 Ultralytics 8.4.0 이상이 필요합니다: "
            f"installed={installed}"
        )
    return installed.strip()


def installed_ultralytics_version() -> str:
    try:
        installed = metadata.version("ultralytics")
    except metadata.PackageNotFoundError as error:
        raise TrainingPlanError("Ultralytics 패키지가 설치되어 있지 않습니다.") from error
    return _validate_ultralytics_version(installed)


def _validate_stage(value: object) -> TrainingStage:
    try:
        stage = TrainingStage(_text(value, "plan.stage"))
    except ValueError as error:
        raise TrainingPlanError(
            "plan.stage는 VISDRONE_S1 또는 VISIONFLOW_S2여야 합니다."
        ) from error
    if stage not in STAGE_POLICIES:
        _fail("COCO_BASE는 Phase 2B-5 전이학습 계획으로 실행할 수 없습니다.")
    return stage


def _validate_model(
    raw_model: object,
    *,
    stage: TrainingStage,
    root: Path,
) -> dict[str, object]:
    model = _object(raw_model, "plan.model")
    _exact_keys(
        model,
        {
            "profile",
            "role",
            "family",
            "scale",
            "task",
            "parent",
            "outputFileName",
        },
        "plan.model",
    )
    expected_identity = {
        "profile": ModelProfile.AERIAL_SMALL_OBJECT_LIVE.value,
        "role": ModelRole.AERIAL_SMALL_OBJECT_DETECTION.value,
        "family": "YOLO26",
        "scale": "m",
        "task": "detect",
    }
    for key, expected in expected_identity.items():
        if model.get(key) != expected:
            _fail(
                f"plan.model.{key}가 항공 소형객체 YOLO26m 계약과 다릅니다. "
                "PPE 가중치는 사용할 수 없습니다."
            )

    policy = STAGE_POLICIES[stage]
    output_name = _text(model.get("outputFileName"), "plan.model.outputFileName")
    if Path(output_name).name != output_name:
        _fail("plan.model.outputFileName에는 파일명만 허용됩니다.")
    if output_name != policy["outputFileName"]:
        _fail("학습 단계의 출력 가중치 파일명이 표준 계약과 다릅니다.")

    parent = _object(model.get("parent"), "plan.model.parent")
    required_parent_keys = {"filePath", "fileName", "sha256"}
    if policy["parentManifestRequired"]:
        required_parent_keys.update({"manifestPath", "manifestSha256"})
    _exact_keys(parent, required_parent_keys, "plan.model.parent")
    parent_name = _text(parent.get("fileName"), "plan.model.parent.fileName")
    if parent_name != policy["parentFileName"]:
        _fail("학습 단계의 부모 가중치 파일명이 표준 lineage와 다릅니다.")
    parent_path = _safe_file(root, parent.get("filePath"), "plan.model.parent.filePath")
    if parent_path.name != parent_name:
        _fail("부모 가중치 경로의 파일명이 plan.model.parent.fileName과 다릅니다.")
    expected_parent_sha = _sha256(parent.get("sha256"), "plan.model.parent.sha256")
    actual_parent_sha = sha256_file(parent_path)
    if actual_parent_sha != expected_parent_sha:
        _fail("부모 가중치 SHA-256이 학습 계획과 다릅니다.")

    normalized_parent: dict[str, object] = {
        "path": str(parent_path),
        "fileName": parent_name,
        "sizeBytes": parent_path.stat().st_size,
        "sha256": actual_parent_sha,
    }
    if policy["parentManifestRequired"]:
        manifest_path = _safe_file(
            root,
            parent.get("manifestPath"),
            "plan.model.parent.manifestPath",
        )
        expected_manifest_sha = _sha256(
            parent.get("manifestSha256"),
            "plan.model.parent.manifestSha256",
        )
        actual_manifest_sha = sha256_file(manifest_path)
        if actual_manifest_sha != expected_manifest_sha:
            _fail("S1 부모 매니페스트 SHA-256이 학습 계획과 다릅니다.")
        _validate_s1_parent_manifest(
            load_json_object(manifest_path),
            parent_name=parent_name,
            parent_sha256=actual_parent_sha,
        )
        normalized_parent.update(
            {
                "manifestPath": str(manifest_path),
                "manifestSha256": actual_manifest_sha,
            }
        )

    return {
        **expected_identity,
        "parent": normalized_parent,
        "outputFileName": output_name,
    }


def _validate_s1_parent_manifest(
    manifest: Mapping[str, object],
    *,
    parent_name: str,
    parent_sha256: str,
) -> None:
    if manifest.get("schemaVersion") != SCHEMA_VERSION:
        _fail("S2 부모 매니페스트 schemaVersion은 1이어야 합니다.")
    if manifest.get("contractId") != "visionflow.phase2b1.visdrone-weight-contract":
        _fail("S2 부모 매니페스트가 Phase 2B-1 가중치 계약이 아닙니다.")
    if manifest.get("template") is True:
        _fail("S2 부모로 템플릿 S1 매니페스트를 사용할 수 없습니다.")
    model = _object(manifest.get("model"), "S1 parent manifest.model")
    if model.get("profile") != ModelProfile.AERIAL_SMALL_OBJECT_LIVE.value:
        _fail("S2 부모 매니페스트의 프로필이 AERIAL_SMALL_OBJECT_LIVE가 아닙니다.")
    if model.get("role") != ModelRole.AERIAL_SMALL_OBJECT_DETECTION.value:
        _fail("S2 부모 매니페스트의 역할이 항공 소형객체 Detection이 아닙니다.")
    if model.get("trainingStage") != TrainingStage.VISDRONE_S1.value:
        _fail("S2 부모 매니페스트 lineage는 VISDRONE_S1이어야 합니다.")
    if (
        model.get("family") != "YOLO26"
        or model.get("scale") != "m"
        or model.get("task") != "detect"
    ):
        _fail("S2 부모 매니페스트 모델은 YOLO26m detect여야 합니다.")
    weight = _object(model.get("weight"), "S1 parent manifest.model.weight")
    if weight.get("fileName") != parent_name:
        _fail("S2 부모 매니페스트의 가중치 파일명이 부모 파일과 다릅니다.")
    if _sha256(weight.get("sha256"), "S1 parent manifest.model.weight.sha256") != (
        parent_sha256
    ):
        _fail("S2 부모 매니페스트의 가중치 SHA-256이 부모 파일과 다릅니다.")
    classes = _array(manifest.get("classes"), "S1 parent manifest.classes")
    if classes != [dict(item) for item in VISDRONE_CLASS_MAPPING]:
        _fail("S2 부모 매니페스트 클래스가 VisDrone 10-class 계약과 다릅니다.")


def _validate_data(
    raw_data: object,
    *,
    stage: TrainingStage,
    root: Path,
) -> dict[str, object]:
    data = _object(raw_data, "plan.data")
    _exact_keys(
        data,
        {
            "dataYaml",
            "datasetName",
            "datasetVersion",
            "splitManifest",
            "sourceDatasets",
            "trainSplit",
            "valSplit",
            "fingerprintMode",
        },
        "plan.data",
    )
    dataset_name = _text(data.get("datasetName"), "plan.data.datasetName")
    dataset_version = _text(data.get("datasetVersion"), "plan.data.datasetVersion")
    train_split = _text(data.get("trainSplit"), "plan.data.trainSplit")
    val_split = _text(data.get("valSplit"), "plan.data.valSplit")
    if (train_split, val_split) != ("train", "val"):
        _fail("학습 계획의 split 이름은 train/val로 고정됩니다.")
    fingerprint_mode = _text(data.get("fingerprintMode"), "plan.data.fingerprintMode")
    if fingerprint_mode != DATASET_FINGERPRINT_MODE:
        _fail("Phase 2B-5 fingerprintMode는 labels로 고정됩니다.")

    source_datasets = tuple(
        _text(item, "plan.data.sourceDatasets[]")
        for item in _array(data.get("sourceDatasets"), "plan.data.sourceDatasets")
    )
    expected_sources = STAGE_POLICIES[stage]["sourceDatasets"]
    if source_datasets != expected_sources:
        _fail("학습 단계의 sourceDatasets 구성이 표준 계약과 다릅니다.")

    data_yaml = _safe_file(root, data.get("dataYaml"), "plan.data.dataYaml")
    split_manifest_path = _safe_file(
        root,
        data.get("splitManifest"),
        "plan.data.splitManifest",
    )
    try:
        train_spec, train_images = load_dataset_inventory(
            data_yaml, train_split, fingerprint_mode
        )
        val_spec, val_images = load_dataset_inventory(
            data_yaml, val_split, fingerprint_mode
        )
    except (FileNotFoundError, OSError, ValueError, yaml.YAMLError) as error:
        raise TrainingPlanError(f"학습 데이터 inventory를 만들 수 없습니다: {error}") from error

    dataset_base = _safe_directory(
        root,
        Path(str(train_spec["basePath"])),
        "data.yaml path",
    )
    if Path(str(val_spec["basePath"])).resolve() != dataset_base:
        _fail("train/val split의 dataset base가 다릅니다.")
    _reject_dataset_symlinks(dataset_base)
    if train_spec["names"] != VISDRONE_NAMES or val_spec["names"] != VISDRONE_NAMES:
        _fail(
            "data.yaml 클래스는 VisDrone2019-DET 10-class와 정확히 일치해야 하며 "
            "PPE 클래스를 혼합할 수 없습니다."
        )
    if train_spec["missingLabelFileCount"] or val_spec["missingLabelFileCount"]:
        _fail("train/val의 모든 이미지에는 빈 라벨을 포함한 라벨 파일이 필요합니다.")

    train_set = {path.resolve() for path in train_images}
    val_set = {path.resolve() for path in val_images}
    overlap = sorted(str(path) for path in train_set & val_set)
    if overlap:
        _fail(f"train/val 이미지가 중복됩니다: {overlap[:3]}")
    for image in (*train_images, *val_images):
        _safe_file(root, str(image), "dataset image")
        _safe_file(root, str(label_path(image)), "dataset label")
    _validate_detection_labels((*train_images, *val_images))

    split_manifest = load_json_object(split_manifest_path)
    normalized_split = validate_training_split_manifest(
        split_manifest,
        manifest_path=split_manifest_path,
        dataset_base=dataset_base,
        dataset_version=dataset_version,
        train_images=train_images,
        val_images=val_images,
    )
    combined_fingerprint = _combined_dataset_fingerprint(
        data_yaml_sha256=str(train_spec["yamlSha256"]),
        split_manifest_sha256=str(normalized_split["manifestSha256"]),
        train_fingerprint=str(train_spec["fingerprintSha256"]),
        val_fingerprint=str(val_spec["fingerprintSha256"]),
    )
    return {
        "datasetName": dataset_name,
        "datasetVersion": dataset_version,
        "sourceDatasets": list(source_datasets),
        "dataYamlPath": str(data_yaml),
        "dataYamlSha256": str(train_spec["yamlSha256"]),
        "datasetBase": str(dataset_base),
        "splitManifestPath": str(split_manifest_path),
        "splitManifestSha256": str(normalized_split["manifestSha256"]),
        "splitUnit": "VIDEO_SEQUENCE",
        "finalEvaluationExcludedFromTraining": True,
        "fingerprintMode": fingerprint_mode,
        "train": _inventory_evidence(train_spec),
        "val": _inventory_evidence(val_spec),
        "combinedFingerprintSha256": combined_fingerprint,
    }


def _validate_detection_labels(images: Sequence[Path]) -> None:
    for image in images:
        label = label_path(image)
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
                raise TrainingPlanError(
                    f"라벨 숫자 형식이 올바르지 않습니다: {label}:{line_number}"
                ) from error
            class_id = int(raw_class)
            if raw_class != class_id or class_id not in VISDRONE_NAMES:
                _fail(
                    "라벨 클래스 ID가 VisDrone 10-class 계약을 벗어났습니다: "
                    f"{label}:{line_number}"
                )
            values = (center_x, center_y, width, height)
            if not all(math.isfinite(value) for value in values):
                _fail(f"라벨 좌표는 유한한 수여야 합니다: {label}:{line_number}")
            if not 0.0 <= center_x <= 1.0 or not 0.0 <= center_y <= 1.0:
                _fail(f"라벨 중심 좌표가 0~1 범위를 벗어났습니다: {label}:{line_number}")
            if not 0.0 < width <= 1.0 or not 0.0 < height <= 1.0:
                _fail(f"라벨 너비/높이가 0~1 범위를 벗어났습니다: {label}:{line_number}")
            if (
                center_x - width / 2.0 < 0.0
                or center_y - height / 2.0 < 0.0
                or center_x + width / 2.0 > 1.0
                or center_y + height / 2.0 > 1.0
            ):
                _fail(f"라벨 박스가 이미지 경계를 벗어났습니다: {label}:{line_number}")


def _inventory_evidence(spec: Mapping[str, object]) -> dict[str, object]:
    return {
        "split": str(spec["split"]),
        "imageCount": int(spec["imageCount"]),
        "labelFileCount": int(spec["labelFileCount"]),
        "missingLabelFileCount": int(spec["missingLabelFileCount"]),
        "fingerprintSha256": str(spec["fingerprintSha256"]),
    }


def _combined_dataset_fingerprint(
    *,
    data_yaml_sha256: str,
    split_manifest_sha256: str,
    train_fingerprint: str,
    val_fingerprint: str,
) -> str:
    evidence = {
        "dataYamlSha256": data_yaml_sha256,
        "splitManifestSha256": split_manifest_sha256,
        "trainFingerprintSha256": train_fingerprint,
        "valFingerprintSha256": val_fingerprint,
    }
    encoded = json.dumps(
        evidence,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_training_split_manifest(
    raw_manifest: Mapping[str, object],
    *,
    manifest_path: Path,
    dataset_base: Path,
    dataset_version: str,
    train_images: Sequence[Path],
    val_images: Sequence[Path],
) -> dict[str, object]:
    manifest = _object(raw_manifest, "splitManifest")
    if manifest.get("schemaVersion") != SCHEMA_VERSION:
        _fail("split manifest schemaVersion은 1이어야 합니다.")
    if manifest.get("contractId") != SPLIT_MANIFEST_CONTRACT_ID:
        _fail("split manifest contractId가 영상 단위 분리 계약과 다릅니다.")
    if manifest.get("template") is True:
        _fail("split manifest 템플릿은 실제 학습 계획에 사용할 수 없습니다.")
    if manifest.get("datasetVersion") != dataset_version:
        _fail("split manifest datasetVersion이 학습 계획과 다릅니다.")
    if manifest.get("splitUnit") != "VIDEO_SEQUENCE":
        _fail("split 단위는 VIDEO_SEQUENCE여야 합니다.")
    if manifest.get("adjacentFramesAcrossSplits") is not False:
        _fail("인접 프레임을 서로 다른 split에 섞을 수 없습니다.")
    if manifest.get("finalEvaluationExcludedFromTraining") is not True:
        _fail("FINAL_HELDOUT은 학습에서 제외되어야 합니다.")

    sequences = _array(manifest.get("sequences"), "splitManifest.sequences")
    if not sequences:
        _fail("split manifest sequences가 비어 있습니다.")
    roots_by_split: dict[str, list[Path]] = {
        "TRAIN": [],
        "VAL": [],
        "TEST": [],
        FINAL_HELDOUT_SPLIT: [],
    }
    seen_ids: set[str] = set()
    seen_source_hashes: set[str] = set()
    for index, raw_sequence in enumerate(sequences):
        sequence = _object(raw_sequence, f"splitManifest.sequences[{index}]")
        sequence_id = _text(
            sequence.get("sequenceId"), f"splitManifest.sequences[{index}].sequenceId"
        )
        if sequence_id in seen_ids:
            _fail("split manifest sequenceId는 고유해야 합니다.")
        seen_ids.add(sequence_id)
        _text(
            sequence.get("sourceVideoFile"),
            f"splitManifest.sequences[{index}].sourceVideoFile",
        )
        source_sha = _sha256(
            sequence.get("sourceVideoSha256"),
            f"splitManifest.sequences[{index}].sourceVideoSha256",
        )
        if source_sha in seen_source_hashes:
            _fail("split manifest sourceVideoSha256는 고유해야 합니다.")
        seen_source_hashes.add(source_sha)
        split = _text(
            sequence.get("split"), f"splitManifest.sequences[{index}].split"
        )
        if split not in roots_by_split:
            _fail(f"splitManifest.sequences[{index}].split 값이 올바르지 않습니다.")
        roots = _array(
            sequence.get("imageRoots"),
            f"splitManifest.sequences[{index}].imageRoots",
        )
        if not roots or len({_text(root, "imageRoot") for root in roots}) != len(roots):
            _fail("각 sequence의 imageRoots는 비어 있지 않은 고유 경로 목록이어야 합니다.")
        for raw_root in roots:
            configured = Path(_text(raw_root, "splitManifest imageRoot"))
            if configured.is_absolute():
                _fail("split manifest imageRoots에는 상대 경로만 허용됩니다.")
            resolved = _safe_directory(
                dataset_base,
                dataset_base / configured,
                "splitManifest imageRoot",
            )
            roots_by_split[split].append(resolved)

    for required_split in ("TRAIN", "VAL", FINAL_HELDOUT_SPLIT):
        if not roots_by_split[required_split]:
            _fail(f"split manifest에 {required_split} VIDEO_SEQUENCE가 필요합니다.")

    _validate_image_membership(
        train_images,
        expected_split="TRAIN",
        roots_by_split=roots_by_split,
    )
    _validate_image_membership(
        val_images,
        expected_split="VAL",
        roots_by_split=roots_by_split,
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "contractId": SPLIT_MANIFEST_CONTRACT_ID,
        "datasetVersion": dataset_version,
        "splitUnit": "VIDEO_SEQUENCE",
        "manifestPath": str(manifest_path.resolve()),
        "manifestSha256": sha256_file(manifest_path),
        "sequenceCount": len(sequences),
    }


def _validate_image_membership(
    images: Sequence[Path],
    *,
    expected_split: str,
    roots_by_split: Mapping[str, Sequence[Path]],
) -> None:
    def belongs(image: Path, root: Path) -> bool:
        try:
            image.resolve().relative_to(root)
            return True
        except ValueError:
            return False

    for image in images:
        expected_matches = [
            root for root in roots_by_split[expected_split] if belongs(image, root)
        ]
        wrong_matches = [
            root
            for split, roots in roots_by_split.items()
            if split != expected_split
            for root in roots
            if belongs(image, root)
        ]
        if len(expected_matches) != 1 or wrong_matches:
            _fail(
                f"{expected_split} 이미지는 정확히 하나의 동일 split "
                f"VIDEO_SEQUENCE root에만 속해야 합니다: {image}"
            )


def _validate_training(raw_training: object) -> dict[str, object]:
    training = _object(raw_training, "plan.training")
    internal = sorted(set(training) & INTERNAL_YOLO26_ARGUMENTS)
    if internal:
        _fail(
            "YOLO26 내부 학습 인자는 사용자 계획에 지정할 수 없습니다: "
            f"{internal}"
        )
    _exact_keys(training, set(PUBLIC_TRAIN_ARGUMENTS), "plan.training")
    normalized: dict[str, object] = {
        "imgsz": _integer(training.get("imgsz"), "plan.training.imgsz", minimum=32),
        "epochs": _integer(training.get("epochs"), "plan.training.epochs", minimum=1),
        "batch": _integer(training.get("batch"), "plan.training.batch", minimum=1),
        "seed": _integer(training.get("seed"), "plan.training.seed", minimum=0),
        "device": _text(training.get("device"), "plan.training.device"),
        "workers": _integer(training.get("workers"), "plan.training.workers", minimum=0),
        "optimizer": _text(training.get("optimizer"), "plan.training.optimizer"),
        "patience": _integer(
            training.get("patience"), "plan.training.patience", minimum=0
        ),
        "deterministic": _boolean(
            training.get("deterministic"), "plan.training.deterministic"
        ),
        "amp": _boolean(training.get("amp"), "plan.training.amp"),
        "close_mosaic": _integer(
            training.get("close_mosaic"),
            "plan.training.close_mosaic",
            minimum=0,
        ),
        "cache": _boolean(training.get("cache"), "plan.training.cache"),
    }
    if normalized["optimizer"] != "MuSGD":
        _fail("YOLO26 전이학습 optimizer는 MuSGD로 고정됩니다.")
    if normalized["deterministic"] is not True:
        _fail("재현 가능한 비교를 위해 deterministic=true가 필요합니다.")
    return normalized


def _validate_inference_evidence(raw_evidence: object) -> dict[str, object]:
    evidence = _object(raw_evidence, "plan.inferenceEvidence")
    expected = {
        "defaultHeadMode": HeadMode.END_TO_END.value,
        "compareHeadModes": [
            HeadMode.END_TO_END.value,
            HeadMode.ONE_TO_MANY_NMS.value,
        ],
        "trainingHeadSwitchAllowed": False,
    }
    _exact_keys(evidence, set(expected), "plan.inferenceEvidence")
    if evidence != expected:
        _fail(
            "inferenceEvidence는 END_TO_END 기본값과 학습 후 두 head 비교를 "
            "정확히 선언해야 합니다."
        )
    return expected


def compile_training_plan(
    *,
    root: Path,
    plan_path: Path,
    ultralytics_version: str | None = None,
) -> dict[str, object]:
    """Validate inputs and return a locked plan without importing or running YOLO."""
    root = root.resolve()
    safe_plan_path = _safe_file(root, str(plan_path), "planPath")
    plan = load_json_object(safe_plan_path)
    if plan.get("schemaVersion") != SCHEMA_VERSION:
        _fail("plan.schemaVersion은 1이어야 합니다.")
    if plan.get("contractId") != TRAINING_PLAN_CONTRACT_ID:
        _fail("plan.contractId가 Phase 2B-5 계약과 다릅니다.")
    if plan.get("template") is True:
        _fail("템플릿 학습 계획은 readiness lock에 사용할 수 없습니다.")
    _integer(plan.get("planVersion"), "plan.planVersion", minimum=1)
    _exact_keys(
        plan,
        {
            "schemaVersion",
            "contractId",
            "template",
            "planVersion",
            "stage",
            "model",
            "data",
            "training",
            "inferenceEvidence",
        },
        "plan",
    )
    if plan.get("template") is not False:
        _fail("plan.template은 실제 계획에서 false여야 합니다.")

    stage = _validate_stage(plan.get("stage"))
    model = _validate_model(plan.get("model"), stage=stage, root=root)
    data = _validate_data(plan.get("data"), stage=stage, root=root)
    training = _validate_training(plan.get("training"))
    inference_evidence = _validate_inference_evidence(plan.get("inferenceEvidence"))
    installed_version = _validate_ultralytics_version(
        ultralytics_version
        if ultralytics_version is not None
        else installed_ultralytics_version()
    )

    compiled_arguments: dict[str, object] = {"data": data["dataYamlPath"]}
    for key in PUBLIC_TRAIN_ARGUMENTS:
        compiled_arguments[key] = training[key]
    report: dict[str, object] = {
        "schemaVersion": SCHEMA_VERSION,
        "contractId": TRAINING_PLAN_CONTRACT_ID,
        "status": READINESS_STATUS,
        "stage": stage.value,
        "plan": {
            "path": str(safe_plan_path),
            "sha256": sha256_file(safe_plan_path),
        },
        "model": model,
        "data": data,
        "runtime": {
            "ultralytics": installed_version,
            "minimumUltralytics": MINIMUM_ULTRALYTICS_VERSION,
        },
        "compiledTraining": {
            "constructorWeight": model["parent"]["path"],
            "argumentOrder": ["data", *PUBLIC_TRAIN_ARGUMENTS],
            "arguments": compiled_arguments,
        },
        "inferenceEvidence": inference_evidence,
        "safeguards": {
            "trainingExecuted": False,
            "gpuAccessed": False,
            "dockerAccessed": False,
            "torchImported": False,
            "ultralyticsImported": False,
        },
    }
    report["evidenceLockSha256"] = hashlib.sha256(
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
    candidate = Path(raw_path)
    lexical = candidate if candidate.is_absolute() else root / candidate
    lexical = Path(os.path.abspath(lexical))
    try:
        lexical.relative_to(root)
    except ValueError as error:
        raise TrainingPlanError("output이 프로젝트 root 밖을 가리킵니다.") from error
    current = root
    for part in lexical.relative_to(root).parts[:-1]:
        current = current / part
        if current.is_symlink():
            _fail(f"output 경로에는 심볼릭 링크를 사용할 수 없습니다: {current}")
    if lexical.exists() or lexical.is_symlink():
        _fail(f"기존 readiness report를 덮어쓰지 않습니다: {lexical}")
    return lexical


def write_readiness_report(root: Path, output: str, report: Mapping[str, object]) -> Path:
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
            "Validate and lock a VisionFlow S1/S2 transfer-training plan without "
            "loading YOLO, torch, CUDA, or Docker."
        )
    )
    parser.add_argument("--root", default=".", help="VisionFlow AI project root")
    parser.add_argument("--plan", required=True, help="Concrete training plan JSON")
    output = parser.add_mutually_exclusive_group()
    output.add_argument(
        "--output",
        help="New readiness report path under --root (existing files are refused)",
    )
    output.add_argument(
        "--check-only",
        action="store_true",
        help="Validate and print the report without writing a file (default)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    root = Path(arguments.root).resolve()
    try:
        report = compile_training_plan(
            root=root,
            plan_path=Path(arguments.plan),
        )
        if arguments.output:
            target = write_readiness_report(root, arguments.output, report)
            print(f"VISIONFLOW_PHASE2B5_TRAINING_PLAN=READY output={target}")
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))
    except (ModelContractError, TrainingPlanError, OSError, ValueError) as error:
        print(f"VISIONFLOW_PHASE2B5_TRAINING_PLAN=FAIL error={error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
