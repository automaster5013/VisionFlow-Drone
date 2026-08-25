from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import numpy as np

from app.domain import FramePacket, VideoSourceType
from app.model_contract import TrackKind
from app.model_runtime import ResolvedModelClass


class FakeTensor:
    def __init__(self, value=None) -> None:
        self.value = value

    def sum(self) -> FakeTensor:
        return self

    def item(self) -> float:
        return 1.0

    def detach(self) -> FakeTensor:
        return self

    def cpu(self) -> FakeTensor:
        return self

    def tolist(self):
        return np.asarray(self.value).tolist()


class FakeBoxes:
    xyxy = FakeTensor([[1.0, 2.0, 10.0, 12.0]])
    conf = FakeTensor([0.91])
    cls = FakeTensor([1])


class FakeResult:
    boxes = FakeBoxes()
    names = {0: "helmet", 1: "no-helmet"}

    def plot(self):
        return np.zeros((16, 16, 3), dtype=np.uint8)


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

    def predict(self, **kwargs):
        self.calls.append(("model.predict", kwargs["device"]))
        return [FakeResult()]

    def track(self, **kwargs):
        self.calls.append(("model.track", kwargs["device"]))
        return ("shared-track-result",)


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

    def test_inference_uses_canonical_class_and_track_reuses_loaded_model(self) -> None:
        calls: list[tuple[str, object]] = []
        module = load_detector_module(calls)

        def resolver(class_id: int, source_name: str) -> ResolvedModelClass:
            self.assertEqual(1, class_id)
            self.assertEqual("no-helmet", source_name)
            return ResolvedModelClass(
                class_id=class_id,
                source_name=source_name,
                canonical_name="person",
                track_kind=TrackKind.HUMAN,
            )

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
                class_resolver=resolver,
            )
            frame = FramePacket(
                source_id="camera-1",
                session_id="session-1",
                source_type=VideoSourceType.DUMMY_VIDEO,
                drone_id=1,
                frame_index=0,
                captured_at=datetime(2026, 8, 26, tzinfo=UTC),
                image=np.zeros((16, 16, 3), dtype=np.uint8),
            )
            inference = detector.infer(frame)
            track_results = detector.track(device="0")

        self.assertEqual("person", inference.detections[0].class_name)
        self.assertEqual(("shared-track-result",), track_results)
        self.assertIn(("model.predict", "0"), calls)
        self.assertIn(("model.track", "0"), calls)


if __name__ == "__main__":
    unittest.main()
