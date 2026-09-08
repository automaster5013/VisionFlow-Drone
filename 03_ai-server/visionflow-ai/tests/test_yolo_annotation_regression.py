from datetime import UTC, datetime
from unittest.mock import Mock

import numpy as np
import pytest
import torch
from ultralytics.engine.results import Results

from app.domain import FramePacket, VideoSourceType
from app.inference.yolo_detector import YoloDetector
from app.model_runtime import resolve_identity_class


@pytest.mark.parametrize('class_id', [0, 1, 2, 3, None])
def test_annotation_survives_each_class_and_empty_frame(class_id):
    image = np.zeros((240, 320, 3), dtype=np.uint8)
    names = {0: 'helmet', 1: 'vest', 2: 'head', 3: 'person'}
    boxes = np.array([[80, 60, 160, 140, 0.91, class_id]], dtype=np.float32) if class_id is not None else np.empty((0, 6), dtype=np.float32)
    detector = YoloDetector.__new__(YoloDetector)
    detector._model = Mock()
    detector._model.predict.side_effect = lambda **kwargs: [Results(image.copy(), 'test', names.copy(), boxes=torch.from_numpy(boxes.copy()))]
    detector._confidence = 0.35
    detector._iou = 0.7
    detector._image_size = 640
    detector._device = 'cpu'
    detector._class_resolver = resolve_identity_class
    for frame_index in range(3):
        frame = FramePacket('test', 'test', VideoSourceType.DUMMY_VIDEO, 1, frame_index, datetime.now(UTC), image)
        result = detector.infer(frame)
        assert result.annotated_image.shape == image.shape
        assert not np.shares_memory(result.annotated_image, image)
        if class_id is not None:
            assert any(d.class_name == names[class_id] for d in result.detections)
            assert result.annotated_image.any()
        else:
            assert not result.detections
    assert not image.any(), 'Inference must not modify the incoming frame'


@pytest.mark.parametrize('front_class,back_class,color', [
    (0, 3, (255, 96, 32)), (2, 3, (0, 0, 220)),
    (1, 3, (0, 140, 255)), (0, 1, (255, 96, 32)),
    (2, 1, (0, 0, 220)),
])
@pytest.mark.parametrize('reverse', [False, True])
def test_ppe_box_and_label_stay_in_front(front_class, back_class, color, reverse):
    image = np.zeros((240, 320, 3), dtype=np.uint8)
    names = {0: 'helmet', 1: 'vest', 2: 'head', 3: 'person'}
    ids = [front_class, back_class]
    if reverse:
        ids.reverse()
    boxes = torch.tensor([[80, 60, 160, 140, 0.91, i] for i in ids])
    detector = YoloDetector.__new__(YoloDetector)
    detector._model = Mock()
    detector._model.predict.return_value = [Results(image.copy(), 'test', names.copy(), boxes=boxes)]
    detector._confidence = 0.35
    detector._iou = 0.7
    detector._image_size = 640
    detector._device = 'cpu'
    detector._class_resolver = resolve_identity_class
    frame = FramePacket('test', 'test', VideoSourceType.DUMMY_VIDEO, 1, 0, datetime.now(UTC), image)
    result = detector.infer(frame)
    assert tuple(result.annotated_image[140, 120]) == color, 'Foreground bounding box was covered'
    assert tuple(result.annotated_image[58, 81]) == color, 'Foreground label was covered'
    assert [d.class_id for d in result.detections[:2]] == ids, 'Rendering must not reorder detection data'


def test_aligned_distant_helmets_do_not_create_a_tall_person():
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    names = {0: 'helmet', 1: 'vest', 2: 'head', 3: 'person'}
    coordinates = [[580, 120, 600, 140, 0.61, 0],
                   [582, 410, 602, 430, 0.72, 0],
                   [810, 220, 842, 300, 0.80, 3]]
    detector = YoloDetector.__new__(YoloDetector)
    detector._model = Mock()
    detector._model.predict.return_value = [Results(image.copy(), 'test', names.copy(), boxes=torch.tensor(coordinates))]
    detector._confidence = 0.35
    detector._iou = 0.7
    detector._image_size = 640
    detector._device = 'cpu'
    detector._class_resolver = resolve_identity_class
    frame = FramePacket('test', 'test', VideoSourceType.DUMMY_VIDEO, 1, 0, datetime.now(UTC), image)
    result = detector.infer(frame)
    assert len(result.detections) == 3
    people = [d for d in result.detections if d.class_name == 'person']
    assert len(people) == 1
    assert (people[0].x1, people[0].y1, people[0].x2, people[0].y2) == (810, 220, 842, 300)
    assert not result.annotated_image[500:, 550:630].any()
