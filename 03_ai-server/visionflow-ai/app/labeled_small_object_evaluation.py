"""Ground-truth small-object comparison for VisionFlow Phase 2B-4."""

from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import json
import math
import statistics
import time
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.model_contract import (
    COCO_VISDRONE_CANONICAL_CLASSES,
    FINAL_HELDOUT_SPLIT,
    LABELED_EVALUATION_CONTRACT_ID,
    LABELED_EVALUATION_POLICY_ID,
    LABELED_METRIC_PROVENANCE,
    SHOWDOWN_MATCH_IOU_THRESHOLD,
    SMALL_OBJECT_MAX_AREA_PX,
    VISDRONE_CLASS_MAPPING,
    ModelContractError,
    ModelProfile,
    load_json_object,
    sha256_file,
    validate_profile_registry,
)
from app.model_evaluation import label_path, load_dataset_inventory, normalize_names
from app.model_runtime import create_runtime_model_comparison_selection

SPLIT_CONTRACT_ID = "visionflow.phase2b4.video-split-manifest"
MEASUREMENT_SCOPE = "SEQUENTIAL_ISOLATED_MODEL_RUN"
VISDRONE_SOURCE_NAMES = tuple(str(item["sourceName"]) for item in VISDRONE_CLASS_MAPPING)
VISDRONE_CANONICAL_BY_ID = {
    int(item["id"]): str(item["canonicalName"]) for item in VISDRONE_CLASS_MAPPING
}
LABELED_EVALUATION_SPLIT_UNITS = (
    "VIDEO_SEQUENCE",
    "OFFICIAL_DATASET_SPLIT",
)
S1_TRAINING_RECEIPT_CONTRACT_ID = (
    "visionflow.phase2b6e20.s1-training-checkpoint-resume"
)
S1_TRAINING_RECEIPT_STATUS = "TRAINED_AWAITING_EVALUATION"
S1_TRAINING_RECEIPT_STAGE = "VISDRONE_S1"
S1_TRAINING_RECEIPT_NEXT_ACTION = "LABELED_SMALL_OBJECT_EVALUATION_REQUIRED"
S1_EVALUATION_READINESS_CONTRACT_ID = (
    "visionflow.phase2b6e25.s1-labeled-evaluation-readiness"
)

BBox = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class GroundTruth:
    image: str
    index: int
    source_class_id: int
    source_name: str
    canonical_name: str
    bbox: BBox
    area_px: float
    small: bool


@dataclass(frozen=True, slots=True)
class Prediction:
    source_class_id: int
    source_name: str
    canonical_name: str
    bbox: BBox
    confidence: float


@dataclass(frozen=True, slots=True)
class MatchResult:
    pairs: tuple[tuple[int, int, float], ...]
    unmatched_ground_truth: tuple[int, ...]
    unmatched_predictions: tuple[int, ...]


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _optional_ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def bbox_iou(first: BBox, second: BBox) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union > 0.0 else 0.0


def deterministic_match(
    ground_truth: Sequence[GroundTruth],
    predictions: Sequence[Prediction],
    iou_threshold: float = SHOWDOWN_MATCH_IOU_THRESHOLD,
) -> MatchResult:
    if iou_threshold != SHOWDOWN_MATCH_IOU_THRESHOLD:
        raise ValueError("Phase 2B-4 match IoU는 0.5로 고정됩니다.")
    candidates: list[tuple[float, int, int]] = []
    for gt_index, truth in enumerate(ground_truth):
        for prediction_index, prediction in enumerate(predictions):
            if truth.canonical_name != prediction.canonical_name:
                continue
            overlap = bbox_iou(truth.bbox, prediction.bbox)
            if overlap >= iou_threshold:
                candidates.append((-overlap, gt_index, prediction_index))
    candidates.sort()

    used_truth: set[int] = set()
    used_predictions: set[int] = set()
    pairs: list[tuple[int, int, float]] = []
    for negative_iou, gt_index, prediction_index in candidates:
        if gt_index in used_truth or prediction_index in used_predictions:
            continue
        used_truth.add(gt_index)
        used_predictions.add(prediction_index)
        pairs.append((gt_index, prediction_index, -negative_iou))
    pairs.sort(key=lambda item: (item[0], item[1]))
    return MatchResult(
        pairs=tuple(pairs),
        unmatched_ground_truth=tuple(
            index for index in range(len(ground_truth)) if index not in used_truth
        ),
        unmatched_predictions=tuple(
            index for index in range(len(predictions)) if index not in used_predictions
        ),
    )


def parse_yolo_label_file(
    path: Path,
    *,
    image: str,
    width: int,
    height: int,
    names: Mapping[int, str],
) -> tuple[GroundTruth, ...]:
    if not path.is_file():
        raise ValueError(f"라벨 파일이 없습니다: {path}")
    if width <= 0 or height <= 0:
        raise ValueError("원본 이미지 크기는 양수여야 합니다.")
    truths: list[GroundTruth] = []
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line:
            continue
        fields = line.split()
        if len(fields) != 5:
            raise ValueError(f"YOLO detect 라벨은 5개 필드여야 합니다: {path}:{line_number}")
        try:
            raw_class, center_x, center_y, box_width, box_height = map(float, fields)
        except ValueError as error:
            raise ValueError(f"라벨 숫자 형식이 올바르지 않습니다: {path}:{line_number}") from error
        class_id = int(raw_class)
        if raw_class != class_id or class_id not in names:
            raise ValueError(f"라벨 클래스 ID가 데이터 계약과 다릅니다: {path}:{line_number}")
        values = (center_x, center_y, box_width, box_height)
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"라벨 좌표는 유한한 수여야 합니다: {path}:{line_number}")
        if not 0.0 <= center_x <= 1.0 or not 0.0 <= center_y <= 1.0:
            raise ValueError(f"라벨 중심 좌표가 0~1 범위를 벗어났습니다: {path}:{line_number}")
        if not 0.0 < box_width <= 1.0 or not 0.0 < box_height <= 1.0:
            raise ValueError(f"라벨 너비/높이가 0~1 범위를 벗어났습니다: {path}:{line_number}")
        left = (center_x - box_width / 2.0) * width
        top = (center_y - box_height / 2.0) * height
        right = (center_x + box_width / 2.0) * width
        bottom = (center_y + box_height / 2.0) * height
        if left < 0.0 or top < 0.0 or right > width or bottom > height:
            raise ValueError(f"라벨 박스가 원본 이미지 경계를 벗어났습니다: {path}:{line_number}")
        source_name = names[class_id]
        expected_source = VISDRONE_SOURCE_NAMES[class_id]
        if source_name != expected_source:
            raise ValueError(
                "FINAL_HELDOUT 클래스가 VisDrone2019-DET 계약과 다릅니다: "
                f"id={class_id}, expected={expected_source}, actual={source_name}"
            )
        area = box_width * width * box_height * height
        truths.append(
            GroundTruth(
                image=image,
                index=len(truths),
                source_class_id=class_id,
                source_name=source_name,
                canonical_name=VISDRONE_CANONICAL_BY_ID[class_id],
                bbox=(left, top, right, bottom),
                area_px=area,
                small=area < SMALL_OBJECT_MAX_AREA_PX,
            )
        )
    return tuple(truths)


def _require_object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ModelContractError(f"{field}은(는) JSON 객체여야 합니다.")
    return {str(key): item for key, item in value.items()}


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelContractError(f"{field}은(는) 비어 있지 않은 문자열이어야 합니다.")
    return value.strip()


def _require_sha256(value: object, field: str) -> str:
    normalized = _require_text(value, field).lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ModelContractError(f"{field}은(는) 64자리 SHA-256이어야 합니다.")
    return normalized


def _require_integer(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ModelContractError(f"{field}은(는) {minimum} 이상의 정수여야 합니다.")
    return value


def _canonical_content_sha256(value: Mapping[str, object], hash_field: str) -> str:
    payload = dict(value)
    stored = _require_sha256(payload.pop(hash_field, None), hash_field)
    calculated = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if calculated != stored:
        raise ModelContractError(f"{hash_field} 자체 해시가 올바르지 않습니다.")
    return stored


def _same_local_file(left: Path, right: Path) -> bool:
    try:
        return left.samefile(right)
    except OSError:
        return left.resolve() == right.resolve()


def resolve_visdrone_candidate_class(class_id: int, source_name: str) -> str:
    expected_source = (
        VISDRONE_SOURCE_NAMES[class_id]
        if 0 <= class_id < len(VISDRONE_SOURCE_NAMES)
        else None
    )
    if expected_source is None or source_name != expected_source:
        raise ModelContractError(
            "로드된 S1 모델 클래스가 VisDrone2019-DET 계약과 다릅니다: "
            f"id={class_id}, expected={expected_source}, actual={source_name}"
        )
    return VISDRONE_CANONICAL_BY_ID[class_id]


def validate_s1_training_receipt(
    raw_receipt: Mapping[str, object],
    *,
    receipt_path: Path,
    candidate_path: Path,
    data_yaml_sha256: str,
    split_manifest_sha256: str,
) -> dict[str, object]:
    receipt = _require_object(raw_receipt, "candidateTrainingReceipt")
    if receipt.get("schemaVersion") != 1:
        raise ModelContractError("S1 학습 영수증 schemaVersion은 1이어야 합니다.")
    if receipt.get("contractId") != S1_TRAINING_RECEIPT_CONTRACT_ID:
        raise ModelContractError("S1 학습 영수증 contractId가 다릅니다.")
    if receipt.get("status") != S1_TRAINING_RECEIPT_STATUS:
        raise ModelContractError("S1 학습 영수증은 평가 대기 상태여야 합니다.")
    if receipt.get("stage") != S1_TRAINING_RECEIPT_STAGE:
        raise ModelContractError("S1 학습 영수증 stage는 VISDRONE_S1이어야 합니다.")
    if receipt.get("nextAction") != S1_TRAINING_RECEIPT_NEXT_ACTION:
        raise ModelContractError("S1 학습 영수증 nextAction이 평가 계약과 다릅니다.")
    receipt_content_sha256 = _canonical_content_sha256(
        receipt, "executionReceiptSha256"
    )
    run_name = _require_text(receipt.get("runName"), "receipt.runName")

    artifacts = _require_object(receipt.get("artifacts"), "receipt.artifacts")
    canonical = _require_object(
        artifacts.get("canonicalWeight"), "receipt.artifacts.canonicalWeight"
    )
    canonical_path = Path(
        _require_text(canonical.get("path"), "receipt.artifacts.canonicalWeight.path")
    )
    canonical_sha256 = _require_sha256(
        canonical.get("sha256"), "receipt.artifacts.canonicalWeight.sha256"
    )
    canonical_size = _require_integer(
        canonical.get("sizeBytes"),
        "receipt.artifacts.canonicalWeight.sizeBytes",
        minimum=1,
    )
    if not _same_local_file(canonical_path, candidate_path):
        raise ModelContractError("S1 영수증 canonicalWeight 경로가 후보 가중치와 다릅니다.")
    if candidate_path.is_symlink() or not candidate_path.is_file():
        raise ModelContractError("S1 후보 가중치는 로컬 일반 파일이어야 합니다.")
    if candidate_path.name != "yolo26m-visdrone-s1-best.pt":
        raise ModelContractError("S1 후보 가중치 파일명이 표준 계약과 다릅니다.")
    if candidate_path.stat().st_size != canonical_size:
        raise ModelContractError("S1 후보 가중치 크기가 영수증과 다릅니다.")
    if sha256_file(candidate_path) != canonical_sha256:
        raise ModelContractError("S1 후보 가중치 SHA-256이 영수증과 다릅니다.")
    best = _require_object(
        artifacts.get("bestCheckpoint"), "receipt.artifacts.bestCheckpoint"
    )
    if (
        _require_sha256(
            best.get("sha256"), "receipt.artifacts.bestCheckpoint.sha256"
        )
        != canonical_sha256
    ):
        raise ModelContractError("S1 best checkpoint와 canonical weight SHA-256이 다릅니다.")

    evidence = _require_object(receipt.get("evidence"), "receipt.evidence")
    if (
        _require_sha256(
            evidence.get("dataYamlSha256"), "receipt.evidence.dataYamlSha256"
        )
        != data_yaml_sha256
    ):
        raise ModelContractError("S1 영수증과 평가 data.yaml SHA-256이 다릅니다.")
    if _require_sha256(
        evidence.get("splitManifestSha256"),
        "receipt.evidence.splitManifestSha256",
    ) != split_manifest_sha256:
        raise ModelContractError("S1 영수증과 FINAL_HELDOUT split manifest SHA-256이 다릅니다.")
    dataset_fingerprint = _require_sha256(
        evidence.get("datasetCombinedFingerprintSha256"),
        "receipt.evidence.datasetCombinedFingerprintSha256",
    )

    resume = _require_object(receipt.get("resume"), "receipt.resume")
    if resume.get("explicitResumeConfirmed") is not True or resume.get("resumeFlag") is not True:
        raise ModelContractError("S1 체크포인트 재개가 명시적으로 승인되지 않았습니다.")
    if resume.get("yoloTrainCalls") != 1:
        raise ModelContractError("S1 재개 학습의 YOLO train 호출 횟수는 1이어야 합니다.")
    completed_epochs = _require_integer(
        resume.get("completedEpochsAfterResume"),
        "receipt.resume.completedEpochsAfterResume",
        minimum=1,
    )
    metrics = _require_object(receipt.get("metrics"), "receipt.metrics")
    if metrics.get("finalCompletedEpochs") != completed_epochs:
        raise ModelContractError("S1 영수증의 완료 epoch 증거가 서로 다릅니다.")
    final_map50 = metrics.get("finalMap50")
    final_map50_95 = metrics.get("finalMap50_95")
    for field, value in (
        ("finalMap50", final_map50),
        ("finalMap50_95", final_map50_95),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not 0.0 <= float(value) <= 1.0
        ):
            raise ModelContractError(f"receipt.metrics.{field} 값이 올바르지 않습니다.")

    safeguards = _require_object(receipt.get("safeguards"), "receipt.safeguards")
    expected_safeguards = {
        "automaticRetryPerformed": False,
        "canonicalWeightPromoted": True,
        "dockerAccessed": False,
        "failedR1Preserved": True,
        "gitMutated": False,
        "inputsUnchanged": True,
        "overwritePerformed": False,
        "staleReceiptArchivePreserved": True,
        "trainingResumed": True,
        "yoloTrainCalls": 1,
    }
    for field, expected in expected_safeguards.items():
        if safeguards.get(field) != expected:
            raise ModelContractError(f"receipt.safeguards.{field} 값이 계약과 다릅니다.")
    return {
        "proofType": "S1_TRAINING_EXECUTION_RECEIPT",
        "receiptFileSha256": sha256_file(receipt_path),
        "receiptContentSha256": receipt_content_sha256,
        "runName": run_name,
        "trainingStage": S1_TRAINING_RECEIPT_STAGE,
        "status": S1_TRAINING_RECEIPT_STATUS,
        "candidateSha256": canonical_sha256,
        "candidateSizeBytes": canonical_size,
        "trainingDatasetFingerprintSha256": dataset_fingerprint,
        "finalCompletedEpochs": completed_epochs,
        "earlyStopped": resume.get("earlyStopped") is True,
        "finalMap50": float(final_map50),
        "finalMap50_95": float(final_map50_95),
    }


def validate_s1_candidate_loaded_status(
    status: Mapping[str, object], proof: Mapping[str, object]
) -> None:
    if status.get("profile") != ModelProfile.AERIAL_SMALL_OBJECT_LIVE.value:
        raise ModelContractError("로드된 S1 후보 모델 profile이 다릅니다.")
    if status.get("task") != "detect":
        raise ModelContractError("로드된 S1 후보 모델 task는 detect여야 합니다.")
    if status.get("sha256") != proof.get("candidateSha256"):
        raise ModelContractError("로드된 S1 후보 모델 SHA-256이 영수증과 다릅니다.")
    if status.get("sizeBytes") != proof.get("candidateSizeBytes"):
        raise ModelContractError("로드된 S1 후보 모델 크기가 영수증과 다릅니다.")
    expected_classes = [
        {"id": index, "name": source_name}
        for index, source_name in enumerate(VISDRONE_SOURCE_NAMES)
    ]
    if (
        status.get("classCount") != len(expected_classes)
        or status.get("classes") != expected_classes
    ):
        raise ModelContractError("로드된 S1 후보 모델 클래스가 VisDrone 계약과 다릅니다.")


def validate_video_split_manifest(
    raw_manifest: Mapping[str, object],
    *,
    manifest_path: Path,
    dataset_base: Path,
    images: Sequence[Path],
) -> dict[str, object]:
    if raw_manifest.get("schemaVersion") != 1:
        raise ValueError("split manifest schemaVersion은 1이어야 합니다.")
    if raw_manifest.get("contractId") != SPLIT_CONTRACT_ID:
        raise ValueError("split manifest contractId가 Phase 2B-4 계약과 다릅니다.")
    if raw_manifest.get("template") is True:
        raise ValueError("split manifest 템플릿은 실제 평가에 사용할 수 없습니다.")
    split_unit = raw_manifest.get("splitUnit")
    if split_unit not in LABELED_EVALUATION_SPLIT_UNITS:
        raise ValueError("split 단위가 라벨 평가 계약과 다릅니다.")
    if raw_manifest.get("adjacentFramesAcrossSplits") is not False:
        raise ValueError("인접 프레임을 서로 다른 split에 섞을 수 없습니다.")
    if raw_manifest.get("finalEvaluationExcludedFromTraining") is not True:
        raise ValueError("FINAL_HELDOUT은 학습에서 제외되어야 합니다.")
    dataset_version = raw_manifest.get("datasetVersion")
    if not isinstance(dataset_version, str) or not dataset_version.strip():
        raise ValueError("split manifest datasetVersion이 필요합니다.")

    if split_unit == "VIDEO_SEQUENCE":
        collection_name = "sequences"
        identifier_name = "sequenceId"
        artifact_file_name = "sourceVideoFile"
        artifact_sha_name = "sourceVideoSha256"
    else:
        collection_name = "sources"
        identifier_name = "sourceId"
        artifact_file_name = "sourceArtifactFile"
        artifact_sha_name = "sourceArtifactSha256"
    raw_items = raw_manifest.get(collection_name)
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError(f"split manifest {collection_name}가 비어 있습니다.")

    seen_ids: set[str] = set()
    seen_hashes: set[str] = set()
    held_out_roots: list[Path] = []
    other_roots: list[Path] = []
    normalized_items: list[dict[str, object]] = []
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, Mapping):
            raise ValueError(f"{collection_name}[{index}]는 객체여야 합니다.")
        identifier = str(raw_item.get(identifier_name, "")).strip()
        artifact_file = str(raw_item.get(artifact_file_name, "")).strip()
        artifact_sha = str(raw_item.get(artifact_sha_name, "")).strip().lower()
        split = str(raw_item.get("split", "")).strip()
        roots = raw_item.get("imageRoots")
        if not identifier or identifier in seen_ids:
            raise ValueError(f"{identifier_name}는 비어 있지 않고 고유해야 합니다.")
        seen_ids.add(identifier)
        if not artifact_file:
            raise ValueError(f"{collection_name}[{index}].{artifact_file_name}이 필요합니다.")
        if len(artifact_sha) != 64 or any(char not in "0123456789abcdef" for char in artifact_sha):
            raise ValueError(f"{collection_name}[{index}].{artifact_sha_name}가 올바르지 않습니다.")
        if artifact_sha in seen_hashes:
            raise ValueError(f"{artifact_sha_name}는 전체 source에서 고유해야 합니다.")
        seen_hashes.add(artifact_sha)
        if split not in {"TRAIN", "VAL", "TEST", FINAL_HELDOUT_SPLIT}:
            raise ValueError(f"{collection_name}[{index}].split 값이 올바르지 않습니다.")
        if (
            not isinstance(roots, list)
            or not roots
            or len(set(map(str, roots))) != len(roots)
        ):
            raise ValueError(
                f"{collection_name}[{index}].imageRoots는 "
                "고유한 경로 목록이어야 합니다."
            )
        resolved_roots: list[Path] = []
        for raw_root in roots:
            if not isinstance(raw_root, str) or not raw_root.strip():
                raise ValueError(f"{collection_name}[{index}].imageRoots 경로가 올바르지 않습니다.")
            root = Path(raw_root)
            if root.is_absolute():
                raise ValueError("split manifest imageRoots에는 상대 경로만 허용됩니다.")
            resolved = (dataset_base / root).resolve()
            try:
                resolved.relative_to(dataset_base.resolve())
            except ValueError as error:
                raise ValueError("split manifest imageRoot가 데이터셋 밖을 가리킵니다.") from error
            resolved_roots.append(resolved)
            (held_out_roots if split == FINAL_HELDOUT_SPLIT else other_roots).append(resolved)
        normalized_items.append(
            {
                identifier_name: identifier,
                artifact_file_name: artifact_file,
                artifact_sha_name: artifact_sha,
                "split": split,
                "imageRoots": [
                    root.relative_to(dataset_base).as_posix() for root in resolved_roots
                ],
            }
        )
    if not held_out_roots:
        raise ValueError("split manifest에 FINAL_HELDOUT source가 없습니다.")

    def belongs(image: Path, root: Path) -> bool:
        try:
            image.resolve().relative_to(root)
            return True
        except ValueError:
            return False

    for image in images:
        held_matches = [root for root in held_out_roots if belongs(image, root)]
        other_matches = [root for root in other_roots if belongs(image, root)]
        if len(held_matches) != 1 or other_matches:
            raise ValueError(
                "평가 이미지는 정확히 하나의 FINAL_HELDOUT root에만 속해야 합니다: "
                f"{image}"
            )
    return {
        "schemaVersion": 1,
        "contractId": SPLIT_CONTRACT_ID,
        "datasetVersion": dataset_version.strip(),
        "splitUnit": split_unit,
        "manifestPath": str(manifest_path.resolve()),
        "manifestSha256": sha256_file(manifest_path),
        collection_name: normalized_items,
    }


def summarize_latencies(
    latencies_ms: Sequence[float],
    *,
    peak_allocated: int = 0,
    peak_reserved: int = 0,
) -> dict[str, object]:
    if not latencies_ms or any(value < 0.0 for value in latencies_ms):
        raise ValueError("지연시간은 비어 있지 않은 0 이상 목록이어야 합니다.")
    ordered = sorted(float(value) for value in latencies_ms)

    def percentile(percent: float) -> float:
        if len(ordered) == 1:
            return ordered[0]
        rank = (len(ordered) - 1) * percent
        lower = math.floor(rank)
        upper = math.ceil(rank)
        if lower == upper:
            return ordered[lower]
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)

    average = statistics.fmean(ordered)
    return {
        "measurementScope": MEASUREMENT_SCOPE,
        "sampleCount": len(ordered),
        "averageLatencyMs": average,
        "p50LatencyMs": percentile(0.50),
        "p95LatencyMs": percentile(0.95),
        "maxLatencyMs": ordered[-1],
        "fps": 1000.0 / average if average > 0.0 else 0.0,
        "peakVramAllocatedBytes": int(peak_allocated),
        "peakVramReservedBytes": int(peak_reserved),
        "offlineDropRate": None,
        "offlineDropRateReason": "OFFLINE_SEQUENTIAL_EVALUATION_HAS_NO_INPUT_QUEUE",
    }


def aggregate_metrics(
    records: Sequence[tuple[Sequence[GroundTruth], Sequence[Prediction], MatchResult]],
) -> dict[str, object]:
    class_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "groundTruth": 0,
            "tp": 0,
            "fp": 0,
            "fn": 0,
            "smallGroundTruth": 0,
            "smallTp": 0,
            "smallFn": 0,
        }
    )
    total_truth = total_tp = total_fp = 0
    small_truth = small_tp = 0
    for truths, predictions, matches in records:
        matched_truth = {gt_index for gt_index, _prediction_index, _iou in matches.pairs}
        matched_predictions = {
            prediction_index for _gt_index, prediction_index, _iou in matches.pairs
        }
        total_truth += len(truths)
        total_tp += len(matches.pairs)
        total_fp += len(matches.unmatched_predictions)
        for index, truth in enumerate(truths):
            row = class_counts[truth.canonical_name]
            row["groundTruth"] += 1
            matched = index in matched_truth
            row["tp" if matched else "fn"] += 1
            if truth.small:
                small_truth += 1
                row["smallGroundTruth"] += 1
                if matched:
                    small_tp += 1
                    row["smallTp"] += 1
                else:
                    row["smallFn"] += 1
        for index, prediction in enumerate(predictions):
            if index not in matched_predictions:
                class_counts[prediction.canonical_name]["fp"] += 1
    total_fn = total_truth - total_tp
    per_class = []
    for name in sorted(class_counts):
        row = class_counts[name]
        per_class.append(
            {
                "canonicalName": name,
                **row,
                "precision": _ratio(row["tp"], row["tp"] + row["fp"]),
                "recall": _ratio(row["tp"], row["groundTruth"]),
                "missRate": _ratio(row["fn"], row["groundTruth"]),
                "smallRecall": _optional_ratio(row["smallTp"], row["smallGroundTruth"]),
                "smallMissRate": _optional_ratio(row["smallFn"], row["smallGroundTruth"]),
            }
        )
    return {
        "groundTruthCount": total_truth,
        "tp": total_tp,
        "fp": total_fp,
        "fn": total_fn,
        "precision": _ratio(total_tp, total_tp + total_fp),
        "recall": _ratio(total_tp, total_truth),
        "missRate": _ratio(total_fn, total_truth),
        "smallGroundTruthCount": small_truth,
        "smallTp": small_tp,
        "smallFn": small_truth - small_tp,
        "smallRecall": _optional_ratio(small_tp, small_truth),
        "smallMissRate": _optional_ratio(small_truth - small_tp, small_truth),
        "perClass": per_class,
    }


def compare_records(
    truths_by_image: Mapping[str, Sequence[GroundTruth]],
    baseline_by_image: Mapping[str, Sequence[Prediction]],
    candidate_by_image: Mapping[str, Sequence[Prediction]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    baseline_records = []
    candidate_records = []
    evidence_rows: list[dict[str, object]] = []
    recovered = 0
    for image in sorted(truths_by_image):
        truths = truths_by_image[image]
        baseline = baseline_by_image.get(image, ())
        candidate = candidate_by_image.get(image, ())
        baseline_match = deterministic_match(truths, baseline)
        candidate_match = deterministic_match(truths, candidate)
        baseline_records.append((truths, baseline, baseline_match))
        candidate_records.append((truths, candidate, candidate_match))
        baseline_hit = {index for index, _prediction, _iou in baseline_match.pairs}
        candidate_hit = {index for index, _prediction, _iou in candidate_match.pairs}
        for index, truth in enumerate(truths):
            if not truth.small:
                continue
            was_recovered = index not in baseline_hit and index in candidate_hit
            recovered += int(was_recovered)
            if index not in baseline_hit or index not in candidate_hit:
                evidence_rows.append(
                    {
                        "image": image,
                        "groundTruthIndex": truth.index,
                        "sourceClass": truth.source_name,
                        "canonicalClass": truth.canonical_name,
                        "areaPx": truth.area_px,
                        "baselineHit": index in baseline_hit,
                        "candidateHit": index in candidate_hit,
                        "candidateRecovered": was_recovered,
                    }
                )
    baseline_metrics = aggregate_metrics(baseline_records)
    candidate_metrics = aggregate_metrics(candidate_records)
    if baseline_metrics["groundTruthCount"] == 0:
        raise ValueError("정답 객체가 없는 데이터셋으로 Recall을 주장할 수 없습니다.")
    if baseline_metrics["smallGroundTruthCount"] == 0:
        raise ValueError(
            "작은 정답 객체가 없는 데이터셋으로 "
            "small-object Recall을 주장할 수 없습니다."
        )
    baseline_small_recall = baseline_metrics["smallRecall"]
    candidate_small_recall = candidate_metrics["smallRecall"]
    baseline_small_miss = baseline_metrics["smallMissRate"]
    candidate_small_miss = candidate_metrics["smallMissRate"]
    comparison = {
        "recoveredSmallObjectCount": recovered,
        "smallRecallDelta": (
            candidate_small_recall - baseline_small_recall
            if isinstance(candidate_small_recall, float)
            and isinstance(baseline_small_recall, float)
            else None
        ),
        "smallMissRateDelta": (
            candidate_small_miss - baseline_small_miss
            if isinstance(candidate_small_miss, float)
            and isinstance(baseline_small_miss, float)
            else None
        ),
    }
    return {
        "baseline": baseline_metrics,
        "candidate": candidate_metrics,
        "comparison": comparison,
    }, evidence_rows


def _tensor_rows(value: Any) -> list[list[float]]:
    if value is None:
        return []
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [[float(item) for item in row] for row in value]


def _tensor_vector(value: Any) -> list[float]:
    if value is None:
        return []
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [float(item) for item in value]


def extract_predictions(
    result: Any,
    *,
    names: Mapping[int, str],
    canonical_resolver: Callable[[int, str], str | None],
) -> tuple[tuple[Prediction, ...], int]:
    boxes = getattr(result, "boxes", None)
    if boxes is None:
        return (), 0
    xyxy = _tensor_rows(getattr(boxes, "xyxy", None))
    class_values = _tensor_vector(getattr(boxes, "cls", None))
    confidence_values = _tensor_vector(getattr(boxes, "conf", None))
    if len(xyxy) != len(class_values) or len(xyxy) != len(confidence_values):
        raise ValueError("Ultralytics prediction tensor 길이가 서로 다릅니다.")
    predictions: list[Prediction] = []
    ignored = 0
    for index, coordinates in enumerate(xyxy):
        if len(coordinates) != 4:
            raise ValueError("Ultralytics prediction bbox 형식이 올바르지 않습니다.")
        class_id = int(class_values[index])
        source_name = names.get(class_id)
        if source_name is None:
            raise ValueError(f"모델 클래스 ID에 이름이 없습니다: {class_id}")
        canonical_name = canonical_resolver(class_id, source_name)
        if canonical_name is None:
            ignored += 1
            continue
        predictions.append(
            Prediction(
                source_class_id=class_id,
                source_name=source_name,
                canonical_name=canonical_name,
                bbox=tuple(coordinates),  # type: ignore[arg-type]
                confidence=confidence_values[index],
            )
        )
    return tuple(predictions), ignored


def _loaded_status(
    *,
    selection_profile: str,
    model_path: Path,
    model: Any,
) -> dict[str, object]:
    names = normalize_names(model.names)
    return {
        "profile": selection_profile,
        "resolvedPath": str(model_path),
        "sizeBytes": model_path.stat().st_size,
        "sha256": sha256_file(model_path),
        "task": str(getattr(model, "task", None) or "detect"),
        "classCount": len(names),
        "classes": [{"id": class_id, "name": name} for class_id, name in names.items()],
    }


def run_isolated_model(
    *,
    model_path: Path,
    profile: str,
    images: Sequence[Path],
    device: str,
    image_size: int,
    confidence: float,
    nms_iou: float,
    warmup: int,
    canonical_resolver: Callable[[int, str], str | None],
) -> tuple[dict[str, tuple[Prediction, ...]], dict[str, object], dict[str, object]]:
    import torch
    from ultralytics import YOLO

    if not torch.cuda.is_available() or device.strip().lower() == "cpu":
        raise RuntimeError("Phase 2B-4 성능 증거는 CUDA GPU에서만 생성할 수 있습니다.")
    normalized_device = device.strip().lower()
    if normalized_device.startswith("cuda:"):
        normalized_device = normalized_device.removeprefix("cuda:")
    if not normalized_device.isdigit():
        raise ValueError("Phase 2B-4 device는 단일 CUDA 장치 번호여야 합니다.")
    device_index = int(normalized_device)
    if device_index >= torch.cuda.device_count():
        raise ValueError(f"CUDA 장치 번호가 범위를 벗어났습니다: {device_index}")
    model = YOLO(str(model_path))
    names = normalize_names(model.names)
    status = _loaded_status(selection_profile=profile, model_path=model_path, model=model)
    predict_args = {
        "device": device,
        "imgsz": image_size,
        "conf": confidence,
        "iou": nms_iou,
        "verbose": False,
    }
    for _ in range(warmup):
        model.predict(source=str(images[0]), **predict_args)
    torch.cuda.synchronize(device_index)
    torch.cuda.reset_peak_memory_stats(device_index)

    latencies: list[float] = []
    predictions_by_image: dict[str, tuple[Prediction, ...]] = {}
    ignored_predictions = 0
    for image in images:
        torch.cuda.synchronize(device_index)
        started = time.perf_counter()
        results = model.predict(source=str(image), **predict_args)
        torch.cuda.synchronize(device_index)
        latencies.append((time.perf_counter() - started) * 1000.0)
        if len(results) != 1:
            raise RuntimeError("단일 이미지 추론 결과는 정확히 하나여야 합니다.")
        predictions, ignored = extract_predictions(
            results[0], names=names, canonical_resolver=canonical_resolver
        )
        predictions_by_image[str(image.resolve())] = predictions
        ignored_predictions += ignored
        del results
    performance = summarize_latencies(
        latencies,
        peak_allocated=torch.cuda.max_memory_allocated(device_index),
        peak_reserved=torch.cuda.max_memory_reserved(device_index),
    )
    performance["ignoredOutOfTaxonomyPredictionCount"] = ignored_predictions
    del model
    gc.collect()
    torch.cuda.empty_cache()
    return predictions_by_image, performance, status


def _read_ground_truth(
    dataset: Mapping[str, object],
    images: Sequence[Path],
) -> dict[str, tuple[GroundTruth, ...]]:
    import cv2

    raw_names = dataset.get("names")
    if not isinstance(raw_names, Mapping):
        raise ValueError("데이터셋 클래스 이름 계약이 없습니다.")
    names = {int(key): str(value) for key, value in raw_names.items()}
    if tuple(names.get(index) for index in range(len(names))) != VISDRONE_SOURCE_NAMES:
        raise ValueError("FINAL_HELDOUT data.yaml은 VisDrone2019-DET 10개 클래스여야 합니다.")
    records: dict[str, tuple[GroundTruth, ...]] = {}
    for image in images:
        frame = cv2.imread(str(image))
        if frame is None:
            raise ValueError(f"원본 이미지를 디코딩할 수 없습니다: {image}")
        height, width = frame.shape[:2]
        records[str(image.resolve())] = parse_yolo_label_file(
            label_path(image),
            image=str(image.resolve()),
            width=width,
            height=height,
            names=names,
        )
    if sum(len(items) for items in records.values()) == 0:
        raise ValueError("정답 객체가 없는 데이터셋으로 Recall을 주장할 수 없습니다.")
    return records


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    fieldnames = [
        "image",
        "groundTruthIndex",
        "sourceClass",
        "canonicalClass",
        "areaPx",
        "baselineHit",
        "candidateHit",
        "candidateRecovered",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _prepare_evaluation_inputs(args: argparse.Namespace) -> dict[str, object]:
    baseline_path = Path(args.baseline_model).resolve()
    candidate_path = Path(args.candidate_model).resolve()
    profiles_path = Path(args.profiles).resolve()
    data_yaml = Path(args.data).resolve()
    split_manifest_path = Path(args.split_manifest).resolve()
    manifest_value = str(getattr(args, "candidate_manifest", "") or "").strip()
    receipt_value = str(getattr(args, "candidate_training_receipt", "") or "").strip()
    if bool(manifest_value) == bool(receipt_value):
        raise ValueError(
            "--candidate-manifest와 --candidate-training-receipt 중 정확히 하나가 필요합니다."
        )
    proof_path = Path(manifest_value or receipt_value).resolve()
    for required in (
        baseline_path,
        candidate_path,
        proof_path,
        profiles_path,
        data_yaml,
        split_manifest_path,
    ):
        if not required.is_file():
            raise FileNotFoundError(f"평가 입력 파일을 찾을 수 없습니다: {required}")
    if args.split != "test":
        raise ValueError("Phase 2B-4 data.yaml split은 test로 고정됩니다.")

    registry = validate_profile_registry(load_json_object(profiles_path))
    raw_contracts = registry.get("evaluationContracts")
    if not isinstance(raw_contracts, Mapping):
        raise ModelContractError("프로필 레지스트리에 평가 계약이 없습니다.")
    contract = raw_contracts[LABELED_EVALUATION_POLICY_ID]
    if not isinstance(contract, Mapping):
        raise ModelContractError("라벨 기반 작은 객체 평가 계약이 올바르지 않습니다.")
    dataset, images = load_dataset_inventory(data_yaml, args.split, args.dataset_hash_mode)
    if dataset["missingLabelFileCount"] != 0:
        raise ValueError("FINAL_HELDOUT의 모든 이미지에는 라벨 파일이 필요합니다.")
    split_manifest = validate_video_split_manifest(
        load_json_object(split_manifest_path),
        manifest_path=split_manifest_path,
        dataset_base=Path(str(dataset["basePath"])),
        images=images,
    )
    allowed_split_units = contract.get("splitUnits")
    if (
        not isinstance(allowed_split_units, list)
        or split_manifest["splitUnit"] not in allowed_split_units
    ):
        raise ModelContractError("평가 splitUnit이 프로필 평가 계약에 허용되지 않습니다.")

    selection = None
    if manifest_value:
        selection = create_runtime_model_comparison_selection(
            baseline_model_path=str(baseline_path),
            candidate_model_path=str(candidate_path),
            candidate_manifest_path=str(proof_path),
            profiles_path=str(profiles_path),
        )
        candidate_manifest = load_json_object(proof_path)
        manifest_data = candidate_manifest.get("data")
        manifest_split = (
            manifest_data.get("splitPolicy")
            if isinstance(manifest_data, Mapping)
            else None
        )
        manifest_split_sha = (
            manifest_split.get("splitManifestSha256")
            if isinstance(manifest_split, Mapping)
            else None
        )
        if manifest_split_sha != split_manifest["manifestSha256"]:
            raise ModelContractError(
                "후보 가중치 매니페스트와 FINAL_HELDOUT split manifest SHA-256이 다릅니다."
            )
        proof = {
            "proofType": "S2_WEIGHT_MANIFEST",
            "manifestSha256": sha256_file(proof_path),
        }
        def resolver(class_id: int, name: str) -> str:
            return selection.candidate.resolve_class(class_id, name).canonical_name
    else:
        proof = validate_s1_training_receipt(
            load_json_object(proof_path),
            receipt_path=proof_path,
            candidate_path=candidate_path,
            data_yaml_sha256=sha256_file(data_yaml),
            split_manifest_sha256=str(split_manifest["manifestSha256"]),
        )
        resolver = resolve_visdrone_candidate_class
    return {
        "baselinePath": baseline_path,
        "candidatePath": candidate_path,
        "proofPath": proof_path,
        "profilesPath": profiles_path,
        "dataYaml": data_yaml,
        "splitManifestPath": split_manifest_path,
        "contract": dict(contract),
        "dataset": dataset,
        "images": images,
        "splitManifest": split_manifest,
        "selection": selection,
        "candidateProof": proof,
        "candidateResolver": resolver,
    }


def build_evaluation_readiness_report(args: argparse.Namespace) -> dict[str, object]:
    prepared = _prepare_evaluation_inputs(args)
    dataset = prepared["dataset"]
    split_manifest = prepared["splitManifest"]
    proof = prepared["candidateProof"]
    baseline_path = prepared["baselinePath"]
    candidate_path = prepared["candidatePath"]
    assert isinstance(dataset, Mapping)
    assert isinstance(split_manifest, Mapping)
    assert isinstance(proof, Mapping)
    assert isinstance(baseline_path, Path)
    assert isinstance(candidate_path, Path)
    return {
        "schemaVersion": 1,
        "contractId": S1_EVALUATION_READINESS_CONTRACT_ID,
        "status": "READY_FOR_EXPLICIT_GPU_LABELED_EVALUATION",
        "nextAction": "EXPLICIT_GPU_LABELED_EVALUATION_REQUIRED",
        "dataset": {
            "split": FINAL_HELDOUT_SPLIT,
            "splitUnit": split_manifest["splitUnit"],
            "splitManifestSha256": split_manifest["manifestSha256"],
            "imageCount": dataset["imageCount"],
            "labelFileCount": dataset["labelFileCount"],
            "missingLabelFileCount": dataset["missingLabelFileCount"],
            "fingerprintSha256": dataset["fingerprintSha256"],
        },
        "baseline": {
            "fileName": baseline_path.name,
            "sha256": sha256_file(baseline_path),
        },
        "candidate": {
            "fileName": candidate_path.name,
            "sha256": sha256_file(candidate_path),
            **dict(proof),
        },
        "safeguards": {
            "gpuAccessed": False,
            "inferenceExecuted": False,
            "trainingExecuted": False,
            "torchImported": False,
            "ultralyticsImported": False,
            "modelLoaded": False,
            "outputCreated": False,
        },
    }


def run_evaluation(args: argparse.Namespace) -> tuple[Path, dict[str, object]]:
    prepared = _prepare_evaluation_inputs(args)
    baseline_path = prepared["baselinePath"]
    candidate_path = prepared["candidatePath"]
    dataset = prepared["dataset"]
    images = prepared["images"]
    split_manifest = prepared["splitManifest"]
    contract = prepared["contract"]
    selection = prepared["selection"]
    candidate_proof = prepared["candidateProof"]
    candidate_resolver = prepared["candidateResolver"]
    assert isinstance(baseline_path, Path)
    assert isinstance(candidate_path, Path)
    assert isinstance(dataset, Mapping)
    assert isinstance(images, Sequence)
    assert isinstance(split_manifest, Mapping)
    assert isinstance(contract, Mapping)
    assert isinstance(candidate_proof, Mapping)
    if not callable(candidate_resolver):
        raise RuntimeError("후보 모델 클래스 resolver가 올바르지 않습니다.")
    truths_by_image = _read_ground_truth(dataset, images)

    baseline_classes = set(COCO_VISDRONE_CANONICAL_CLASSES)
    baseline_predictions, baseline_performance, baseline_status = run_isolated_model(
        model_path=baseline_path,
        profile=ModelProfile.GENERAL_LIVE.value,
        images=images,
        device=args.device,
        image_size=args.imgsz,
        confidence=args.conf,
        nms_iou=args.iou,
        warmup=args.warmup,
        canonical_resolver=lambda _class_id, name: name if name in baseline_classes else None,
    )
    candidate_predictions, candidate_performance, candidate_status = run_isolated_model(
        model_path=candidate_path,
        profile=ModelProfile.AERIAL_SMALL_OBJECT_LIVE.value,
        images=images,
        device=args.device,
        image_size=args.imgsz,
        confidence=args.conf,
        nms_iou=args.iou,
        warmup=args.warmup,
        canonical_resolver=candidate_resolver,
    )
    if selection is not None:
        selection.validate_loaded_status(
            baseline_status=baseline_status,
            candidate_status=candidate_status,
        )
    else:
        validate_s1_candidate_loaded_status(candidate_status, candidate_proof)
    metrics, evidence_rows = compare_records(
        truths_by_image,
        baseline_predictions,
        candidate_predictions,
    )
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_directory = Path(args.output).resolve() / f"labeled-small-object-{timestamp}"
    run_directory.mkdir(parents=True, exist_ok=False)
    evidence_path = run_directory / "missed-small-objects.csv"
    _write_csv(evidence_path, evidence_rows)
    baseline_metrics = metrics["baseline"]
    candidate_metrics = metrics["candidate"]
    comparison_metrics = metrics["comparison"]
    if not all(
        isinstance(value, Mapping)
        for value in (baseline_metrics, candidate_metrics, comparison_metrics)
    ):
        raise RuntimeError("평가 지표 집계 결과가 올바르지 않습니다.")
    report: dict[str, object] = {
        "schemaVersion": 1,
        "contractId": LABELED_EVALUATION_CONTRACT_ID,
        "generatedAt": datetime.now(UTC).isoformat(),
        "metricProvenance": LABELED_METRIC_PROVENANCE,
        "dataset": {
            **dataset,
            "split": FINAL_HELDOUT_SPLIT,
            "splitUnit": split_manifest["splitUnit"],
            "splitManifestSha256": split_manifest["manifestSha256"],
            "groundTruthCount": baseline_metrics["groundTruthCount"],
            "smallGroundTruthCount": baseline_metrics["smallGroundTruthCount"],
        },
        "policy": dict(contract),
        "baseline": {
            "model": {
                "fileName": baseline_path.name,
                "sha256": sha256_file(baseline_path),
                "profile": ModelProfile.GENERAL_LIVE.value,
            },
            "metrics": baseline_metrics,
            "performance": baseline_performance,
        },
        "candidate": {
            "model": {
                "fileName": candidate_path.name,
                "sha256": sha256_file(candidate_path),
                "profile": ModelProfile.AERIAL_SMALL_OBJECT_LIVE.value,
                **dict(candidate_proof),
            },
            "metrics": candidate_metrics,
            "performance": candidate_performance,
        },
        "comparison": comparison_metrics,
        "evidence": {
            "recallClaimEligible": True,
            "runtimeProxyExcluded": True,
            "runtimeProxyProvenance": "MODEL_DIFFERENCE_PROXY",
            "candidateProofType": candidate_proof["proofType"],
            "missedObjectsCsv": evidence_path.name,
            "missedOrRecoveredSmallObjectCount": len(evidence_rows),
        },
    }
    (run_directory / "evaluation-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return run_directory, report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="VisionFlow Phase 2B-4 라벨 기반 작은 객체 비교 평가"
    )
    parser.add_argument("--baseline-model", required=True)
    parser.add_argument("--candidate-model", required=True)
    candidate_proof = parser.add_mutually_exclusive_group(required=True)
    candidate_proof.add_argument("--candidate-manifest")
    candidate_proof.add_argument("--candidate-training-receipt")
    parser.add_argument("--profiles", default="config/model-profiles-v1.json")
    parser.add_argument("--data", required=True)
    parser.add_argument("--split-manifest", required=True)
    parser.add_argument("--split", default="test")
    parser.add_argument("--device", default="0")
    parser.add_argument("--imgsz", type=int, default=1280)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--iou", type=float, default=0.7)
    parser.add_argument("--match-iou", type=float, default=SHOWDOWN_MATCH_IOU_THRESHOLD)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--dataset-hash-mode", choices=("labels", "full"), default="full")
    parser.add_argument("--output", default="artifacts/labeled-small-object-evaluation")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--confirm-gpu-evaluation", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.match_iou != SHOWDOWN_MATCH_IOU_THRESHOLD:
        raise ValueError("--match-iou는 0.5로 고정됩니다.")
    if args.imgsz <= 0 or args.warmup < 0:
        raise ValueError("imgsz는 양수이고 warmup은 0 이상이어야 합니다.")
    if not 0.0 <= args.conf <= 1.0 or not 0.0 <= args.iou <= 1.0:
        raise ValueError("conf와 iou는 0~1 사이여야 합니다.")
    if args.check_only:
        if args.confirm_gpu_evaluation:
            raise ValueError("--check-only에서는 GPU 평가 승인을 함께 사용할 수 없습니다.")
        report = build_evaluation_readiness_report(args)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print("VISIONFLOW_LABELED_SMALL_OBJECT_EVALUATION_READINESS=PASS")
        return 0
    if not args.confirm_gpu_evaluation:
        raise ValueError("실제 GPU 평가는 --confirm-gpu-evaluation 명시적 승인이 필요합니다.")
    run_directory, report = run_evaluation(args)
    print("VISIONFLOW_LABELED_SMALL_OBJECT_EVALUATION=PASS")
    print(f"REPORT={run_directory / 'evaluation-report.json'}")
    print(f"PROVENANCE={report['metricProvenance']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
