from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np


class FakeTensor:
    def sum(self) -> FakeTensor:
        return self

    def item(self) -> float:
        return 1.0


class FakeCuda:
    def __init__(self, calls: list[tuple[str, object]]) -> None:
        self.calls = calls

    def is_available(self) -> bool:
        return True

    def device_count(self) -> int:
        return 1

    def synchronize(self, index: int) -> None:
        self.calls.append(("synchronize", index))

    def get_device_properties(self, _index: int) -> object:
        return types.SimpleNamespace(
            name="NVIDIA GeForce RTX 5060 Laptop GPU",
            total_memory=8_151 * 1024 * 1024,
        )

    def get_device_capability(self, _index: int) -> tuple[int, int]:
        return (12, 0)


class FakeYolo:
    names = {0: "helmet", 1: "no-helmet"}

    def __init__(
        self,
        path: str,
        calls: list[tuple[str, object]],
    ) -> None:
        self.ckpt_path = path
        self.calls = calls

    def to(self, device: str) -> FakeYolo:
        self.calls.append(("model.to", device))
        return self


def load_detector_module(
    calls: list[tuple[str, object]],
) -> types.ModuleType:
    torch = types.ModuleType("torch")
    torch.__version__ = "2.12.1"
    torch.version = types.SimpleNamespace(cuda="13.0")
    torch.cuda = FakeCuda(calls)
    torch.backends = types.SimpleNamespace(
        cudnn=types.SimpleNamespace(version=lambda: 9_100),
    )

    def ones(_shape: tuple[int, ...], *, device: str) -> FakeTensor:
        calls.append(("torch.ones", device))
        return FakeTensor()

    torch.ones = ones

    ultralytics = types.ModuleType("ultralytics")
    ultralytics.YOLO = lambda path: FakeYolo(path, calls)

    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "inference"
        / "yolo_detector.py"
    )
    spec = importlib.util.spec_from_file_location(
        "visionflow_test_yolo_detector",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("YoloDetector 테스트 모듈을 불러올 수 없습니다.")

    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "numpy": np,
            "torch": torch,
            "ultralytics": ultralytics,
        },
    ):
        spec.loader.exec_module(module)
    return module


class YoloDetectorGpuRuntimeTest(unittest.TestCase):
    def test_model_is_moved_to_cuda_before_status_is_built(self) -> None:
        calls: list[tuple[str, object]] = []
        module = load_detector_module(calls)

        with tempfile.TemporaryDirectory() as temporary:
            model = Path(temporary) / "best.pt"
            model.write_bytes(b"visionflow-best")
            detector = module.YoloDetector(
                model_profile="best-gpu",
                model_path=str(model),
                require_cuda=True,
                require_local_model=True,
                confidence=0.35,
                iou=0.70,
                image_size=640,
                device="0",
            )

        self.assertEqual(
            [
                ("torch.ones", "cuda:0"),
                ("model.to", "cuda:0"),
                ("synchronize", 0),
            ],
            calls,
        )
        status = detector.status()
        self.assertEqual("cuda:0", status["deviceEffective"])
        self.assertTrue(status["cudaAvailable"])
        self.assertEqual(2, status["classCount"])

    def test_invalid_cuda_device_format_is_rejected(self) -> None:
        calls: list[tuple[str, object]] = []
        module = load_detector_module(calls)

        with tempfile.TemporaryDirectory() as temporary:
            model = Path(temporary) / "best.pt"
            model.write_bytes(b"visionflow-best")

            with self.assertRaisesRegex(ValueError, "AI_DEVICE"):
                module.YoloDetector(
                    model_profile="best-gpu",
                    model_path=str(model),
                    require_cuda=True,
                    require_local_model=True,
                    confidence=0.35,
                    iou=0.70,
                    image_size=640,
                    device="cuda:invalid",
                )

        self.assertEqual([], calls)


if __name__ == "__main__":
    unittest.main()
