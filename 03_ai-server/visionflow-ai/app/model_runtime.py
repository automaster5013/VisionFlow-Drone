from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.model_contract import (
    CONTRACT_ID,
    ModelContractError,
    ModelProfile,
    ModelRole,
    TrackKind,
    TrainingStage,
    load_json_object,
    validate_profile_registry,
    validate_weight_manifest,
)

DEFAULT_PROFILES_PATH = "config/model-profiles-v1.json"
VISDRONE_MAPPING_ID = "VISDRONE2019_DET"
LEGACY_MAPPING_ID = "LEGACY_IDENTITY"
GENERAL_MAPPING_ID = "COCO_IDENTITY"


@dataclass(frozen=True, slots=True)
class ResolvedModelClass:
    class_id: int
    source_name: str
    canonical_name: str
    track_kind: TrackKind


ClassResolver = Callable[[int, str], ResolvedModelClass]


def resolve_identity_class(class_id: int, source_name: str) -> ResolvedModelClass:
    normalized_name = source_name.strip()
    track_kind = (
        TrackKind.HUMAN
        if normalized_name.lower() == "person"
        else TrackKind.OTHER
    )
    return ResolvedModelClass(
        class_id=class_id,
        source_name=normalized_name,
        canonical_name=normalized_name,
        track_kind=track_kind,
    )


@dataclass(frozen=True, slots=True)
class RuntimeClassResolver:
    mapping_id: str
    classes: tuple[ResolvedModelClass, ...] = ()
    strict: bool = False

    def resolve(self, class_id: int, source_name: str) -> ResolvedModelClass:
        normalized_name = source_name.strip()
        if not self.strict:
            return resolve_identity_class(class_id, normalized_name)

        for item in self.classes:
            if item.class_id != class_id:
                continue
            if item.source_name != normalized_name:
                raise ModelContractError(
                    "로드된 모델 클래스 이름이 런타임 매핑과 다릅니다: "
                    f"id={class_id}, expected={item.source_name}, actual={normalized_name}"
                )
            return item

        raise ModelContractError(
            f"로드된 모델 클래스 ID가 런타임 매핑에 없습니다: {class_id}"
        )


@dataclass(frozen=True, slots=True)
class RuntimeModelSelection:
    requested_profile: str
    model_path: str
    mode: str
    profile: ModelProfile | None
    role: ModelRole | None
    training_stage: TrainingStage | None
    weight_file: str
    manifest_required: bool
    class_resolver: RuntimeClassResolver
    registry: Mapping[str, object] | None = None
    manifest: Mapping[str, object] | None = None

    def resolve_class(self, class_id: int, source_name: str) -> ResolvedModelClass:
        return self.class_resolver.resolve(class_id, source_name)

    def validate_loaded_status(
        self,
        status: Mapping[str, object],
    ) -> dict[str, object]:
        if status.get("profile") != self.requested_profile:
            raise ModelContractError(
                "로드된 모델 상태의 profile이 선택한 런타임 프로필과 다릅니다."
            )

        if self.mode == "LEGACY_COMPAT":
            return {
                "validation": "LEGACY_COMPAT",
                "profile": self.requested_profile,
                "weightFile": self.weight_file,
                "classCount": status.get("classCount"),
            }

        if self.profile is None or self.role is None or self.training_stage is None:
            raise ModelContractError("표준 런타임 프로필 정보가 완전하지 않습니다.")

        if self.manifest is not None:
            if self.registry is None:
                raise ModelContractError("매니페스트 검증에 프로필 레지스트리가 필요합니다.")
            contract = validate_weight_manifest(
                self.manifest,
                self.registry,
                model_status=status,
                activation=True,
            )
            if contract["profile"] != self.profile.value:
                raise ModelContractError(
                    "매니페스트 프로필과 선택한 런타임 프로필이 다릅니다."
                )
            return {**contract, "validation": "WEIGHT_MANIFEST"}

        return {
            "contractId": CONTRACT_ID,
            "validation": "PROFILE_REGISTRY",
            "profile": self.profile.value,
            "role": self.role.value,
            "trainingStage": self.training_stage.value,
            "activationEligible": True,
            "weightFile": self.weight_file,
            "classCount": status.get("classCount"),
        }

    def enrich_status(
        self,
        status: Mapping[str, object],
        contract: Mapping[str, object],
    ) -> dict[str, object]:
        enriched = dict(status)
        enriched["runtimeContract"] = {
            "mode": self.mode,
            "profile": contract.get("profile", self.requested_profile),
            "role": contract.get("role"),
            "trainingStage": contract.get("trainingStage"),
            "activationEligible": contract.get("activationEligible"),
            "validation": contract.get("validation"),
            "manifestRequired": self.manifest_required,
            "manifestValidated": contract.get("validation") == "WEIGHT_MANIFEST",
            "classMappingId": self.class_resolver.mapping_id,
            "mappedClassCount": len(self.class_resolver.classes),
        }
        return enriched


def _file_name(path: str) -> str:
    return Path(path.replace("\\", "/")).name


def _profile_config(
    registry: Mapping[str, object],
    profile: ModelProfile,
) -> dict[str, Any]:
    profiles = registry.get("profiles")
    if not isinstance(profiles, Mapping):
        raise ModelContractError("프로필 레지스트리에 profiles 객체가 없습니다.")
    selected = profiles.get(profile.value)
    if not isinstance(selected, Mapping):
        raise ModelContractError(f"프로필 레지스트리에 {profile.value}가 없습니다.")
    return {str(key): value for key, value in selected.items()}


def _activation_stage(profile: Mapping[str, object]) -> TrainingStage:
    raw_stages = profile.get("activationTrainingStages")
    if not isinstance(raw_stages, list) or len(raw_stages) != 1:
        raise ModelContractError("LIVE 프로필에는 활성화 학습 단계가 정확히 하나여야 합니다.")
    try:
        return TrainingStage(str(raw_stages[0]))
    except ValueError as error:
        raise ModelContractError("LIVE 활성화 학습 단계가 올바르지 않습니다.") from error


def _weight_file(profile: Mapping[str, object], stage: TrainingStage) -> str:
    raw_files = profile.get("weightFiles")
    if not isinstance(raw_files, Mapping):
        raise ModelContractError("프로필에 weightFiles 객체가 없습니다.")
    selected = raw_files.get(stage.value)
    if not isinstance(selected, str) or not selected.strip():
        raise ModelContractError("활성화 학습 단계의 가중치 파일명이 없습니다.")
    return selected.strip()


def _visdrone_resolver(registry: Mapping[str, object]) -> RuntimeClassResolver:
    raw_mappings = registry.get("classMappings")
    if not isinstance(raw_mappings, Mapping):
        raise ModelContractError("프로필 레지스트리에 classMappings 객체가 없습니다.")
    raw_classes = raw_mappings.get(VISDRONE_MAPPING_ID)
    if not isinstance(raw_classes, list):
        raise ModelContractError("VisDrone 런타임 클래스 매핑이 없습니다.")

    classes: list[ResolvedModelClass] = []
    for raw_item in raw_classes:
        if not isinstance(raw_item, Mapping):
            raise ModelContractError("VisDrone 런타임 클래스 매핑 항목이 올바르지 않습니다.")
        classes.append(
            ResolvedModelClass(
                class_id=int(raw_item["id"]),
                source_name=str(raw_item["sourceName"]),
                canonical_name=str(raw_item["canonicalName"]),
                track_kind=TrackKind(str(raw_item["trackKind"])),
            )
        )
    return RuntimeClassResolver(
        mapping_id=VISDRONE_MAPPING_ID,
        classes=tuple(classes),
        strict=True,
    )


def create_runtime_model_selection(
    *,
    model_profile: str,
    model_path: str,
    manifest_path: str = "",
    profiles_path: str = DEFAULT_PROFILES_PATH,
) -> RuntimeModelSelection:
    normalized_profile = model_profile.strip()
    normalized_path = model_path.strip()
    weight_file = _file_name(normalized_path)

    try:
        profile = ModelProfile(normalized_profile)
    except ValueError:
        return RuntimeModelSelection(
            requested_profile=normalized_profile,
            model_path=normalized_path,
            mode="LEGACY_COMPAT",
            profile=None,
            role=None,
            training_stage=None,
            weight_file=weight_file,
            manifest_required=False,
            class_resolver=RuntimeClassResolver(mapping_id=LEGACY_MAPPING_ID),
        )

    if profile is ModelProfile.DETERMINISTIC_COMPARE:
        raise ModelContractError(
            "DETERMINISTIC_COMPARE는 단일 LIVE 런타임에서 사용할 수 없습니다. "
            "Small Object Showdown 오케스트레이터 단계에서 활성화하세요."
        )

    registry = validate_profile_registry(load_json_object(Path(profiles_path)))
    selected_profile = _profile_config(registry, profile)
    stage = _activation_stage(selected_profile)
    expected_file = _weight_file(selected_profile, stage)
    if weight_file != expected_file:
        raise ModelContractError(
            f"{profile.value} LIVE 가중치는 {expected_file}이어야 합니다: {weight_file}"
        )

    role = ModelRole(str(selected_profile["modelRole"]))
    requires_manifest = profile is ModelProfile.AERIAL_SMALL_OBJECT_LIVE
    normalized_manifest_path = manifest_path.strip()
    if requires_manifest and not normalized_manifest_path:
        raise ModelContractError(
            "AERIAL_SMALL_OBJECT_LIVE에는 S2 실가중치 매니페스트가 필요합니다."
        )

    manifest = (
        load_json_object(Path(normalized_manifest_path))
        if normalized_manifest_path
        else None
    )
    if manifest is not None:
        contract = validate_weight_manifest(
            manifest,
            registry,
            activation=True,
        )
        if contract["profile"] != profile.value:
            raise ModelContractError(
                "매니페스트 프로필과 AI_MODEL_PROFILE이 다릅니다."
            )

    class_resolver = (
        _visdrone_resolver(registry)
        if profile is ModelProfile.AERIAL_SMALL_OBJECT_LIVE
        else RuntimeClassResolver(mapping_id=GENERAL_MAPPING_ID)
    )
    return RuntimeModelSelection(
        requested_profile=normalized_profile,
        model_path=normalized_path,
        mode="STANDARD",
        profile=profile,
        role=role,
        training_stage=stage,
        weight_file=expected_file,
        manifest_required=requires_manifest,
        class_resolver=class_resolver,
        registry=registry,
        manifest=manifest,
    )
