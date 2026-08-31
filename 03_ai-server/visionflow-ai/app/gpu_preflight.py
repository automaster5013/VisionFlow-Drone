from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path

from app.model_contract import (
    ModelProfile,
    load_json_object,
    validate_weight_manifest,
)

READY_STATUS = "GPU_MODEL_READY"
DEFAULT_PROFILES_PATH = "/app/config/model-profiles-v1.json"
MANIFEST_REQUIRED_PROFILES = {ModelProfile.AERIAL_SMALL_OBJECT_LIVE.value}


def validate_model_status(
    status: Mapping[str, object],
    *,
    expected_sha256: str,
) -> None:
    if status.get("localFile") is not True:
        raise RuntimeError("컨테이너가 로컬 YOLO 모델을 읽지 못했습니다.")

    if status.get("cudaAvailable") is not True:
        raise RuntimeError("PyTorch CUDA 장치를 사용할 수 없습니다.")

    if status.get("requireCuda") is not True:
        raise RuntimeError("CUDA 필수 실행 설정이 적용되지 않았습니다.")

    effective_device = str(status.get("deviceEffective", ""))
    if not effective_device.startswith("cuda:"):
        raise RuntimeError(
            f"YOLO 모델의 실제 장치가 CUDA가 아닙니다: {effective_device}"
        )

    model_sha256 = str(status.get("sha256", "")).strip().lower()
    if (
        len(model_sha256) != 64
        or any(character not in "0123456789abcdef" for character in model_sha256)
    ):
        raise RuntimeError("컨테이너 모델 SHA-256이 올바르지 않습니다.")

    normalized_expected = expected_sha256.strip().lower()
    if normalized_expected and normalized_expected != model_sha256:
        raise RuntimeError(
            "호스트와 컨테이너의 YOLO 모델 SHA-256이 다릅니다."
        )


def validate_contract_status(
    status: Mapping[str, object],
    *,
    model_profile: str,
    manifest_path: str,
    profiles_path: str = DEFAULT_PROFILES_PATH,
) -> dict[str, object] | None:
    normalized_profile = model_profile.strip()
    normalized_manifest = manifest_path.strip()
    if normalized_profile in MANIFEST_REQUIRED_PROFILES and not normalized_manifest:
        raise RuntimeError(
            f"{normalized_profile} 프로필에는 실가중치 매니페스트가 필요합니다."
        )
    if not normalized_manifest:
        return None

    manifest = load_json_object(Path(normalized_manifest))
    registry = load_json_object(Path(profiles_path))
    contract = validate_weight_manifest(
        manifest,
        registry,
        model_status=status,
        activation=True,
    )
    if contract["profile"] != normalized_profile:
        raise RuntimeError("AI_MODEL_PROFILE이 매니페스트 프로필과 다릅니다.")
    return contract


def main() -> int:
    model_path = os.getenv("AI_MODEL_PATH", "/app/models/yolo26n.pt")
    model_profile = os.getenv("AI_MODEL_PROFILE", "yolo26n-gpu")
    device = os.getenv("AI_DEVICE", "0")
    expected_sha256 = os.getenv("AI_EXPECTED_MODEL_SHA256", "")
    manifest_path = os.getenv("AI_MODEL_MANIFEST_PATH", "")
    profiles_path = os.getenv("AI_MODEL_PROFILES_PATH", DEFAULT_PROFILES_PATH)

    try:
        from app.inference import YoloDetector

        detector = YoloDetector(
            model_profile=model_profile,
            model_path=model_path,
            require_cuda=True,
            require_local_model=True,
            confidence=0.35,
            iou=0.70,
            image_size=640,
            device=device,
        )
        model_status = detector.status()
        validate_model_status(
            model_status,
            expected_sha256=expected_sha256,
        )
        model_contract = validate_contract_status(
            model_status,
            model_profile=model_profile,
            manifest_path=manifest_path,
            profiles_path=profiles_path,
        )
    except Exception as error:
        print(
            json.dumps(
                {
                    "success": False,
                    "message": str(error),
                    "modelProfile": model_profile,
                    "modelFile": Path(model_path).name,
                    "device": device,
                },
                ensure_ascii=False,
                indent=2,
            ),
            flush=True,
        )
        return 1

    output: dict[str, object] = {
        "success": True,
        "status": READY_STATUS,
        "message": "CUDA와 YOLO 모델을 정상적으로 사용할 수 있습니다.",
        "model": model_status,
    }
    if model_contract is not None:
        output["modelContract"] = model_contract
    print(
        json.dumps(output, ensure_ascii=False, indent=2),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
