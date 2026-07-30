from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path

READY_STATUS = "GPU_MODEL_READY"


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


def main() -> int:
    model_path = os.getenv("AI_MODEL_PATH", "/app/models/yolo26n.pt")
    model_profile = os.getenv("AI_MODEL_PROFILE", "yolo26n-gpu")
    device = os.getenv("AI_DEVICE", "0")
    expected_sha256 = os.getenv("AI_EXPECTED_MODEL_SHA256", "")

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

    print(
        json.dumps(
            {
                "success": True,
                "status": READY_STATUS,
                "message": "CUDA와 YOLO 모델을 정상적으로 사용할 수 있습니다.",
                "model": model_status,
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
