from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
CONTRACT_ID = "visionflow.phase2b1.visdrone-weight-contract"
SMALL_OBJECT_DEFINITION = "COCO_AREA_LT_32_SQUARED_PX_AT_ORIGINAL_RESOLUTION"
SMALL_OBJECT_MAX_AREA_PX = 32 * 32
SHOWDOWN_MATCH_IOU_THRESHOLD = 0.5
SHOWDOWN_METRIC_PROVENANCE = "MODEL_DIFFERENCE_PROXY"
SHOWDOWN_RECOVERED_LABEL = "RECOVERED SMALL OBJECT"
LABELED_EVALUATION_POLICY_ID = "LABELED_SMALL_OBJECT_COMPARE"
LABELED_EVALUATION_CONTRACT_ID = (
    "visionflow.phase2b4.labeled-small-object-evaluation"
)
LABELED_METRIC_PROVENANCE = "LABELED_HELD_OUT_GROUND_TRUTH"
FINAL_HELDOUT_SPLIT = "FINAL_HELDOUT"
COCO_VISDRONE_CANONICAL_CLASSES = (
    "person",
    "bicycle",
    "car",
    "truck",
    "bus",
    "motorcycle",
)


class ModelProfile(StrEnum):
    GENERAL_LIVE = "GENERAL_LIVE"
    AERIAL_SMALL_OBJECT_LIVE = "AERIAL_SMALL_OBJECT_LIVE"
    DETERMINISTIC_COMPARE = "DETERMINISTIC_COMPARE"


class ModelRole(StrEnum):
    GENERAL_DETECTION = "GENERAL_DETECTION"
    AERIAL_SMALL_OBJECT_DETECTION = "AERIAL_SMALL_OBJECT_DETECTION"
    PPE_DETECTION = "PPE_DETECTION"


class TrainingStage(StrEnum):
    COCO_BASE = "COCO_BASE"
    VISDRONE_S1 = "VISDRONE_S1"
    VISIONFLOW_S2 = "VISIONFLOW_S2"


class HeadMode(StrEnum):
    END_TO_END = "END_TO_END"
    ONE_TO_MANY_NMS = "ONE_TO_MANY_NMS"


class TrackKind(StrEnum):
    HUMAN = "HUMAN"
    VEHICLE = "VEHICLE"
    CYCLE = "CYCLE"
    OTHER = "OTHER"


class ModelContractError(ValueError):
    pass


VISDRONE_CLASS_MAPPING: tuple[dict[str, object], ...] = (
    {"id": 0, "sourceName": "pedestrian", "canonicalName": "person", "trackKind": "HUMAN"},
    {"id": 1, "sourceName": "people", "canonicalName": "person", "trackKind": "HUMAN"},
    {"id": 2, "sourceName": "bicycle", "canonicalName": "bicycle", "trackKind": "CYCLE"},
    {"id": 3, "sourceName": "car", "canonicalName": "car", "trackKind": "VEHICLE"},
    {"id": 4, "sourceName": "van", "canonicalName": "van", "trackKind": "VEHICLE"},
    {"id": 5, "sourceName": "truck", "canonicalName": "truck", "trackKind": "VEHICLE"},
    {"id": 6, "sourceName": "tricycle", "canonicalName": "tricycle", "trackKind": "VEHICLE"},
    {
        "id": 7,
        "sourceName": "awning-tricycle",
        "canonicalName": "awning-tricycle",
        "trackKind": "VEHICLE",
    },
    {"id": 8, "sourceName": "bus", "canonicalName": "bus", "trackKind": "VEHICLE"},
    {"id": 9, "sourceName": "motor", "canonicalName": "motorcycle", "trackKind": "CYCLE"},
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ModelContractError(
            f"JSON 파일을 읽을 수 없습니다: {path}: {error}"
        ) from error
    return _object(value, str(path))


def _fail(message: str) -> None:
    raise ModelContractError(message)


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


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(f"{field}은(는) {minimum} 이상의 정수여야 합니다.")
    return value


def _boolean(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        _fail(f"{field}은(는) boolean이어야 합니다.")
    return value


def _ratio(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"{field}은(는) 0과 1 사이의 수여야 합니다.")
    normalized = float(value)
    if not 0.0 <= normalized <= 1.0:
        _fail(f"{field}은(는) 0과 1 사이의 수여야 합니다.")
    return normalized


def _sha256(value: object, field: str) -> str:
    normalized = _text(value, field).lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        _fail(f"{field}은(는) 64자리 SHA-256이어야 합니다.")
    return normalized


def _enum(value: object, enum_type: type[StrEnum], field: str) -> StrEnum:
    try:
        return enum_type(_text(value, field))
    except ValueError as error:
        allowed = ", ".join(item.value for item in enum_type)
        raise ModelContractError(
            f"{field} 값이 올바르지 않습니다. 허용값: {allowed}"
        ) from error


def _validate_contract_header(value: Mapping[str, object], field: str) -> None:
    if value.get("schemaVersion") != SCHEMA_VERSION:
        _fail(f"{field}.schemaVersion은 {SCHEMA_VERSION}이어야 합니다.")
    if value.get("contractId") != CONTRACT_ID:
        _fail(f"{field}.contractId가 VisionFlow Phase 2B-1 계약과 다릅니다.")


def validate_profile_registry(registry: Mapping[str, object]) -> dict[str, Any]:
    normalized = _object(registry, "profileRegistry")
    _validate_contract_header(normalized, "profileRegistry")
    profiles = _object(normalized.get("profiles"), "profileRegistry.profiles")
    expected_profiles = {profile.value for profile in ModelProfile}
    if set(profiles) != expected_profiles:
        _fail(
            "profileRegistry.profiles에는 세 표준 프로필만 정확히 있어야 합니다."
        )

    general = _object(profiles[ModelProfile.GENERAL_LIVE], "profiles.GENERAL_LIVE")
    aerial = _object(
        profiles[ModelProfile.AERIAL_SMALL_OBJECT_LIVE],
        "profiles.AERIAL_SMALL_OBJECT_LIVE",
    )
    compare = _object(
        profiles[ModelProfile.DETERMINISTIC_COMPARE],
        "profiles.DETERMINISTIC_COMPARE",
    )
    _validate_single_profile(
        general,
        "profiles.GENERAL_LIVE",
        expected_role=ModelRole.GENERAL_DETECTION,
        allowed_stages={TrainingStage.COCO_BASE},
        activation_stages={TrainingStage.COCO_BASE},
        expected_files={TrainingStage.COCO_BASE: "yolo26m.pt"},
    )
    _validate_single_profile(
        aerial,
        "profiles.AERIAL_SMALL_OBJECT_LIVE",
        expected_role=ModelRole.AERIAL_SMALL_OBJECT_DETECTION,
        allowed_stages={TrainingStage.VISDRONE_S1, TrainingStage.VISIONFLOW_S2},
        activation_stages={TrainingStage.VISIONFLOW_S2},
        expected_files={
            TrainingStage.VISDRONE_S1: "yolo26m-visdrone-s1-best.pt",
            TrainingStage.VISIONFLOW_S2: "yolo26m-visdrone-s2-best.pt",
        },
    )
    _validate_compare_profile(compare)

    class_mappings = _object(normalized.get("classMappings"), "profileRegistry.classMappings")
    mapping = _array(
        class_mappings.get("VISDRONE2019_DET"),
        "profileRegistry.classMappings.VISDRONE2019_DET",
    )
    _validate_visdrone_mapping(mapping, "profileRegistry.classMappings.VISDRONE2019_DET")
    _validate_labeled_evaluation_contract(normalized.get("evaluationContracts"))
    return normalized


def _validate_single_profile(
    profile: Mapping[str, object],
    field: str,
    *,
    expected_role: ModelRole,
    allowed_stages: set[TrainingStage],
    activation_stages: set[TrainingStage],
    expected_files: Mapping[TrainingStage, str],
) -> None:
    if profile.get("mode") != "SINGLE":
        _fail(f"{field}.mode는 SINGLE이어야 합니다.")
    if _enum(profile.get("modelRole"), ModelRole, f"{field}.modelRole") != expected_role:
        _fail(f"{field}.modelRole이 표준 역할과 다릅니다.")
    default_head_mode = _enum(
        profile.get("defaultHeadMode"), HeadMode, f"{field}.defaultHeadMode"
    )
    if default_head_mode != HeadMode.END_TO_END:
        _fail(f"{field}.defaultHeadMode는 END_TO_END여야 합니다.")
    actual_allowed = {
        _enum(item, TrainingStage, f"{field}.allowedTrainingStages[]")
        for item in _array(profile.get("allowedTrainingStages"), f"{field}.allowedTrainingStages")
    }
    actual_activation = {
        _enum(item, TrainingStage, f"{field}.activationTrainingStages[]")
        for item in _array(
            profile.get("activationTrainingStages"),
            f"{field}.activationTrainingStages",
        )
    }
    if actual_allowed != allowed_stages or actual_activation != activation_stages:
        _fail(f"{field}의 학습 단계 정책이 표준 계약과 다릅니다.")
    weight_files = _object(profile.get("weightFiles"), f"{field}.weightFiles")
    if weight_files != {stage.value: name for stage, name in expected_files.items()}:
        _fail(f"{field}.weightFiles가 표준 파일명 계약과 다릅니다.")


def _validate_compare_profile(profile: Mapping[str, object]) -> None:
    field = "profiles.DETERMINISTIC_COMPARE"
    expected = {
        "mode": "COMPARE",
        "baselineProfile": ModelProfile.GENERAL_LIVE.value,
        "candidateProfile": ModelProfile.AERIAL_SMALL_OBJECT_LIVE.value,
        "sameInputFrames": True,
        "headMode": HeadMode.END_TO_END.value,
        "auxiliaryInference": False,
        "backendReporting": False,
        "snapshotEnabled": False,
        "matchIouThreshold": SHOWDOWN_MATCH_IOU_THRESHOLD,
        "smallObjectDefinition": SMALL_OBJECT_DEFINITION,
        "smallObjectMaxAreaPx": SMALL_OBJECT_MAX_AREA_PX,
        "metricProvenance": SHOWDOWN_METRIC_PROVENANCE,
        "recoveredLabel": SHOWDOWN_RECOVERED_LABEL,
    }
    for key, expected_value in expected.items():
        if profile.get(key) != expected_value:
            _fail(f"{field}.{key}가 결정론적 비교 계약과 다릅니다.")


def _validate_visdrone_mapping(mapping: Sequence[object], field: str) -> None:
    normalized: list[dict[str, object]] = []
    for index, raw_item in enumerate(mapping):
        item = _object(raw_item, f"{field}[{index}]")
        normalized.append(
            {
                "id": _integer(item.get("id"), f"{field}[{index}].id"),
                "sourceName": _text(item.get("sourceName"), f"{field}[{index}].sourceName"),
                "canonicalName": _text(
                    item.get("canonicalName"), f"{field}[{index}].canonicalName"
                ),
                "trackKind": _enum(
                    item.get("trackKind"), TrackKind, f"{field}[{index}].trackKind"
                ).value,
            }
        )
    if normalized != [dict(item) for item in VISDRONE_CLASS_MAPPING]:
        _fail(f"{field}가 VisDrone2019-DET 10-class 표준 매핑과 다릅니다.")


def _validate_labeled_evaluation_contract(raw_contracts: object) -> None:
    field = "profileRegistry.evaluationContracts"
    contracts = _object(raw_contracts, field)
    if set(contracts) != {LABELED_EVALUATION_POLICY_ID}:
        _fail(f"{field}에는 Phase 2B-4 표준 평가 계약만 정확히 있어야 합니다.")
    contract = _object(
        contracts[LABELED_EVALUATION_POLICY_ID],
        f"{field}.{LABELED_EVALUATION_POLICY_ID}",
    )
    expected = {
        "baselineProfile": ModelProfile.GENERAL_LIVE.value,
        "candidateProfile": ModelProfile.AERIAL_SMALL_OBJECT_LIVE.value,
        "datasetSplit": FINAL_HELDOUT_SPLIT,
        "splitUnit": "VIDEO_SEQUENCE",
        "sameDatasetFingerprint": True,
        "matchIouThreshold": SHOWDOWN_MATCH_IOU_THRESHOLD,
        "smallObjectDefinition": SMALL_OBJECT_DEFINITION,
        "smallObjectMaxAreaPx": SMALL_OBJECT_MAX_AREA_PX,
        "metricProvenance": LABELED_METRIC_PROVENANCE,
        "runtimeProxyExcluded": True,
        "baselineCanonicalClasses": list(COCO_VISDRONE_CANONICAL_CLASSES),
    }
    for key, expected_value in expected.items():
        if contract.get(key) != expected_value:
            _fail(
                f"{field}.{LABELED_EVALUATION_POLICY_ID}.{key}가 "
                "라벨 기반 평가 계약과 다릅니다."
            )


def validate_weight_manifest(
    manifest: Mapping[str, object],
    registry: Mapping[str, object],
    *,
    weight_path: Path | None = None,
    model_status: Mapping[str, object] | None = None,
    activation: bool = False,
) -> dict[str, object]:
    normalized_registry = validate_profile_registry(registry)
    normalized = _object(manifest, "manifest")
    _validate_contract_header(normalized, "manifest")
    if normalized.get("template") is True:
        _fail("템플릿 매니페스트는 실가중치 검증에 사용할 수 없습니다.")
    _integer(normalized.get("manifestVersion"), "manifest.manifestVersion", minimum=1)

    model = _object(normalized.get("model"), "manifest.model")
    profile = _enum(model.get("profile"), ModelProfile, "manifest.model.profile")
    if profile == ModelProfile.DETERMINISTIC_COMPARE:
        _fail(
            "DETERMINISTIC_COMPARE는 두 모델 오케스트레이션 프로필이며 "
            "단일 가중치 역할이 아닙니다."
        )
    profile_config = _object(
        _object(normalized_registry["profiles"], "profileRegistry.profiles")[profile.value],
        f"profiles.{profile.value}",
    )
    role = _enum(model.get("role"), ModelRole, "manifest.model.role")
    expected_role = _enum(
        profile_config.get("modelRole"), ModelRole, f"profiles.{profile.value}.modelRole"
    )
    if role != expected_role:
        _fail(
            "매니페스트 모델 역할이 프로필 역할과 다릅니다. "
            "PPE 가중치는 대체할 수 없습니다."
        )
    if (
        model.get("family") != "YOLO26"
        or model.get("scale") != "m"
        or model.get("task") != "detect"
    ):
        _fail("Phase 2B-1 가중치는 YOLO26m detect 모델이어야 합니다.")
    stage = _enum(model.get("trainingStage"), TrainingStage, "manifest.model.trainingStage")
    allowed_stages = {
        _enum(item, TrainingStage, "profile.allowedTrainingStages[]")
        for item in _array(
            profile_config.get("allowedTrainingStages"),
            "profile.allowedTrainingStages",
        )
    }
    if stage not in allowed_stages:
        _fail("학습 단계가 선택한 모델 프로필에서 허용되지 않습니다.")
    activation_eligible = _boolean(
        model.get("activationEligible"), "manifest.model.activationEligible"
    )
    activation_stages = {
        _enum(item, TrainingStage, "profile.activationTrainingStages[]")
        for item in _array(
            profile_config.get("activationTrainingStages"), "profile.activationTrainingStages"
        )
    }
    if activation and (not activation_eligible or stage not in activation_stages):
        _fail("이 학습 단계의 가중치는 LIVE 활성화가 허용되지 않습니다.")

    weight = _object(model.get("weight"), "manifest.model.weight")
    file_name = _text(weight.get("fileName"), "manifest.model.weight.fileName")
    if Path(file_name).name != file_name:
        _fail("manifest.model.weight.fileName에는 파일명만 허용됩니다.")
    expected_file = _object(
        profile_config.get("weightFiles"), "profile.weightFiles"
    ).get(stage.value)
    if file_name != expected_file:
        _fail("가중치 파일명이 프로필/학습 단계 파일명 계약과 다릅니다.")
    size_bytes = _integer(weight.get("sizeBytes"), "manifest.model.weight.sizeBytes", minimum=1)
    weight_sha256 = _sha256(weight.get("sha256"), "manifest.model.weight.sha256")
    _validate_lineage(model.get("lineage"), stage)

    classes = _array(normalized.get("classes"), "manifest.classes")
    if profile == ModelProfile.AERIAL_SMALL_OBJECT_LIVE:
        _validate_visdrone_mapping(classes, "manifest.classes")
    else:
        _validate_contiguous_classes(classes)
    _validate_data(normalized.get("data"))
    _validate_training(normalized.get("training"))
    _validate_runtime(normalized.get("runtime"))
    _validate_inference(normalized.get("inference"), activation=activation)
    _validate_evaluation(normalized.get("evaluation"), classes)

    if weight_path is not None:
        _validate_local_weight(weight_path, file_name, size_bytes, weight_sha256)
    if model_status is not None:
        _validate_model_status(model_status, file_name, size_bytes, weight_sha256, classes)

    return {
        "contractId": CONTRACT_ID,
        "profile": profile.value,
        "role": role.value,
        "trainingStage": stage.value,
        "activationEligible": activation_eligible,
        "weightFile": file_name,
        "weightSha256": weight_sha256,
        "classCount": len(classes),
    }


def _validate_lineage(raw_lineage: object, stage: TrainingStage) -> None:
    lineage = _object(raw_lineage, "manifest.model.lineage")
    parent_file = _text(lineage.get("parentFileName"), "manifest.model.lineage.parentFileName")
    _sha256(lineage.get("parentSha256"), "manifest.model.lineage.parentSha256")
    expected_parent = {
        TrainingStage.COCO_BASE: "ultralytics-yolo26m-pretrained",
        TrainingStage.VISDRONE_S1: "yolo26m.pt",
        TrainingStage.VISIONFLOW_S2: "yolo26m-visdrone-s1-best.pt",
    }[stage]
    if parent_file != expected_parent:
        _fail("학습 단계의 부모 가중치 lineage가 표준 계약과 다릅니다.")


def _validate_contiguous_classes(classes: Sequence[object]) -> None:
    identifiers: list[int] = []
    names: list[str] = []
    for index, raw_item in enumerate(classes):
        item = _object(raw_item, f"manifest.classes[{index}]")
        identifiers.append(_integer(item.get("id"), f"manifest.classes[{index}].id"))
        names.append(_text(item.get("sourceName"), f"manifest.classes[{index}].sourceName"))
    if identifiers != list(range(len(classes))) or len(names) != len(set(names)):
        _fail(
            "manifest.classes의 ID는 0부터 연속이고 sourceName은 고유해야 합니다."
        )


def _validate_data(raw_data: object) -> None:
    data = _object(raw_data, "manifest.data")
    _text(data.get("datasetName"), "manifest.data.datasetName")
    _text(data.get("datasetVersion"), "manifest.data.datasetVersion")
    _sha256(data.get("datasetFingerprintSha256"), "manifest.data.datasetFingerprintSha256")
    split = _object(data.get("splitPolicy"), "manifest.data.splitPolicy")
    if split.get("unit") != "VIDEO_SEQUENCE":
        _fail("데이터 분리는 VIDEO_SEQUENCE 단위여야 합니다.")
    if split.get("adjacentFramesAcrossSplits") is not False:
        _fail(
            "동일 영상의 인접 프레임을 서로 다른 split에 섞을 수 없습니다."
        )
    if split.get("finalEvaluationExcludedFromTraining") is not True:
        _fail("발표용 최종 검증영상은 학습에서 제외해야 합니다.")
    _sha256(split.get("splitManifestSha256"), "manifest.data.splitPolicy.splitManifestSha256")


def _validate_training(raw_training: object) -> None:
    training = _object(raw_training, "manifest.training")
    _integer(training.get("imageSize"), "manifest.training.imageSize", minimum=1)
    _integer(training.get("epochs"), "manifest.training.epochs", minimum=1)
    _integer(training.get("batch"), "manifest.training.batch", minimum=1)
    _integer(training.get("seed"), "manifest.training.seed")


def _validate_runtime(raw_runtime: object) -> None:
    runtime = _object(raw_runtime, "manifest.runtime")
    for key in ("python", "ultralytics", "torch", "cuda"):
        _text(runtime.get(key), f"manifest.runtime.{key}")


def _validate_inference(raw_inference: object, *, activation: bool) -> None:
    inference = _object(raw_inference, "manifest.inference")
    default_mode = _enum(
        inference.get("defaultHeadMode"),
        HeadMode,
        "manifest.inference.defaultHeadMode",
    )
    supported = {
        _enum(item, HeadMode, "manifest.inference.supportedHeadModes[]")
        for item in _array(
            inference.get("supportedHeadModes"),
            "manifest.inference.supportedHeadModes",
        )
    }
    if not {HeadMode.END_TO_END, HeadMode.ONE_TO_MANY_NMS}.issubset(supported):
        _fail("두 YOLO26 head mode 비교 지원을 매니페스트에 선언해야 합니다.")
    if activation and default_mode != HeadMode.END_TO_END:
        _fail("LIVE 활성화 기본값은 YOLO26 END_TO_END여야 합니다.")


def _validate_evaluation(raw_evaluation: object, classes: Sequence[object]) -> None:
    evaluation = _object(raw_evaluation, "manifest.evaluation")
    if evaluation.get("status") != "MEASURED":
        _fail("실가중치 매니페스트 평가는 MEASURED 상태여야 합니다.")
    for key in ("precision", "recall", "map50", "map50_95"):
        _ratio(evaluation.get(key), f"manifest.evaluation.{key}")
    small = _object(evaluation.get("smallObject"), "manifest.evaluation.smallObject")
    if small.get("definition") != SMALL_OBJECT_DEFINITION:
        _fail("작은 객체 기준이 VisionFlow 표준 정의와 다릅니다.")
    small_recall = _ratio(small.get("recall"), "manifest.evaluation.smallObject.recall")
    miss_rate = _ratio(small.get("missRate"), "manifest.evaluation.smallObject.missRate")
    if abs((1.0 - small_recall) - miss_rate) > 1e-6:
        _fail("작은 객체 missRate는 1 - recall과 일치해야 합니다.")
    per_class = _array(evaluation.get("perClass"), "manifest.evaluation.perClass")
    measured_names: list[str] = []
    for index, raw_item in enumerate(per_class):
        item = _object(raw_item, f"manifest.evaluation.perClass[{index}]")
        measured_names.append(_text(item.get("sourceName"), f"perClass[{index}].sourceName"))
        for key in ("precision", "recall", "map50", "map50_95"):
            _ratio(item.get(key), f"perClass[{index}].{key}")
    class_names = [
        _text(_object(item, "manifest.classes[]").get("sourceName"), "classes[].sourceName")
        for item in classes
    ]
    if measured_names != class_names:
        _fail(
            "evaluation.perClass는 클래스 순서와 전체 범위를 정확히 일치시켜야 합니다."
        )


def _validate_local_weight(
    path: Path,
    file_name: str,
    size_bytes: int,
    expected_sha256: str,
) -> None:
    if path.is_symlink() or not path.is_file():
        _fail(
            f"가중치는 심볼릭 링크가 아닌 로컬 일반 파일이어야 합니다: {path}"
        )
    if path.name != file_name:
        _fail("로컬 가중치 파일명이 매니페스트와 다릅니다.")
    if path.stat().st_size != size_bytes:
        _fail("로컬 가중치 크기가 매니페스트와 다릅니다.")
    if sha256_file(path) != expected_sha256:
        _fail("로컬 가중치 SHA-256이 매니페스트와 다릅니다.")


def _validate_model_status(
    status: Mapping[str, object],
    file_name: str,
    size_bytes: int,
    expected_sha256: str,
    classes: Sequence[object],
) -> None:
    status_sha256 = _sha256(status.get("sha256"), "modelStatus.sha256")
    if status_sha256 != expected_sha256 or status.get("sizeBytes") != size_bytes:
        _fail("로드된 모델의 크기 또는 SHA-256이 매니페스트와 다릅니다.")
    resolved_path = status.get("resolvedPath")
    if isinstance(resolved_path, str) and Path(resolved_path).name != file_name:
        _fail("로드된 모델 파일명이 매니페스트와 다릅니다.")
    if status.get("task") is not None and status.get("task") != "detect":
        _fail("로드된 Ultralytics 모델 task는 detect여야 합니다.")
    expected_classes = []
    for item in classes:
        class_item = _object(item, "manifest.classes[]")
        expected_classes.append(
            {
                "id": int(class_item["id"]),
                "name": str(class_item["sourceName"]),
            }
        )
    actual_classes = status.get("classes")
    if actual_classes != expected_classes or status.get("classCount") != len(expected_classes):
        _fail("로드된 모델 클래스 ID/이름이 매니페스트와 다릅니다.")
