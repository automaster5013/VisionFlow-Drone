# VisionFlow YOLO 학습·검증 데이터셋

실제 데이터는 Git과 Docker 이미지에 포함하지 않습니다. 데이터 버전과 파일 fingerprint, split manifest SHA-256만 모델 매니페스트에 기록합니다.

## 필수 분리 정책

- split 단위는 이미지가 아니라 원본 `VIDEO_SEQUENCE`입니다.
- 동일 영상의 인접 프레임을 train/val/test에 나누어 넣지 않습니다.
- 발표용 최종 검증영상은 train·val과 분리된 held-out 세트로 유지합니다.
- 작은 객체는 원본 해상도에서 COCO 기준 `area < 32² px`로 평가합니다.
- 전체 Precision/Recall/mAP 외에 작은 객체 Recall·미탐률과 클래스별 성능을 별도로 저장합니다.

권장 구조:

```text
datasets/
├─ visdrone2019-det/
│  ├─ data.yaml
│  └─ split-manifest.json
├─ visionflow-presentation/
│  ├─ data.yaml
│  └─ split-manifest.json
├─ visionflow-s2/
│  ├─ data.yaml
│  └─ split-manifest.json
└─ final-heldout/
   ├─ data.yaml
   └─ split-manifest.json
```

## 전이학습 단계

1. S1: `yolo26m.pt`에서 VisDrone2019-DET로 전이학습하고 `yolo26m-visdrone-s1-best.pt`를 생성합니다.
2. S2: S1 best에서 VisDrone 재학습 데이터와 VisionFlow 발표환경 유사 데이터를 학습하고 `yolo26m-visdrone-s2-best.pt`를 생성합니다.
3. 최종 held-out 영상은 두 단계 학습에서 모두 제외합니다.

VisDrone2019-DET의 10개 클래스는 `pedestrian`, `people`, `bicycle`, `car`, `van`, `truck`, `tricycle`, `awning-tricycle`, `bus`, `motor`입니다. PPE 클래스는 없으므로 `ppe-yolo26m-best.pt`의 학습 데이터나 역할과 혼합하지 않습니다.

평가 명령의 `-ModelFile`과 `-DataYaml`에는 고정 모델명과 해당 split의 YAML을 명시합니다.

```bat
scripts\run-visionflow-model-evaluation.bat ^
  -ModelFile yolo26m-visdrone-s2-best.pt ^
  -DataYaml final-heldout/data.yaml
```

## FINAL_HELDOUT 영상 계약

실제 작은 객체 Recall·미탐률 비교에는 라벨이 있는 `FINAL_HELDOUT`만 사용합니다. `data.yaml`의 `test`가 가리키는 모든 이미지에는 빈 라벨을 포함한 YOLO detect 라벨 파일이 있어야 하고, 클래스 ID/이름은 VisDrone2019-DET 10개 클래스와 정확히 일치해야 합니다.

`final-heldout.split-manifest.template.json`을 `split-manifest.json`으로 복사한 뒤 실제 데이터 버전, 원본 영상 파일, SHA-256, 영상별 이미지 root를 기록하고 `template`을 `false`로 바꿉니다. 각 평가 이미지는 정확히 하나의 `FINAL_HELDOUT` 영상 root에만 속해야 합니다. `sourceVideoSha256` 중복, 서로 겹치는 split, 데이터셋 밖의 경로는 평가 전에 차단됩니다.

작은 객체 면적은 resize된 추론 입력이 아니라 원본 이미지에서 YOLO 라벨의 폭·높이를 복원해 계산하며 `area < 1024 px`만 포함합니다. 런타임 Showdown의 `MODEL_DIFFERENCE_PROXY`는 이 정답 기반 결과에 합산하지 않습니다.

```bat
scripts\run-visionflow-labeled-small-object-evaluation.bat ^
  --baseline-model models\yolo26m.pt ^
  --candidate-model models\yolo26m-visdrone-s2-best.pt ^
  --candidate-manifest models\manifests\yolo26m-visdrone-s2-best.manifest.json ^
  --data datasets\final-heldout\data.yaml ^
  --split-manifest datasets\final-heldout\split-manifest.json ^
  --device 0 --imgsz 1280
```

실행기는 두 모델을 순차·격리 적재하고 동일한 정렬 이미지 목록을 사용합니다. 실제 가중치와 held-out 데이터가 준비되기 전에는 GPU 평가를 실행하거나 결과를 추정하지 않습니다.

## S1/S2 학습 계획 잠금

실제 GPU 학습 전에 `config/visdrone-s1-training.plan.template.json` 또는 `config/visdrone-s2-training.plan.template.json`을 복사해 실계획을 만듭니다. 실제 부모 가중치·S1 매니페스트·데이터 경로와 SHA-256을 넣고 `template`을 `false`로 바꿉니다. 템플릿의 `batch=2`는 8GB VRAM 출발점일 뿐 최종 성능값이 아니며, Phase 2B-6 GPU 승인 후 사전점검으로 확정합니다.

```bat
scripts\run-visionflow-model-training-plan.bat ^
  --root . ^
  --plan config\visdrone-s1-training.plan.json ^
  --check-only
```

계획 잠금은 GPU·PyTorch·YOLO 모델을 불러오거나 학습을 시작하지 않습니다. 다음 항목이 모두 맞아야 `READY` 증거를 생성합니다.

- Ultralytics 8.4.0 이상과 공개 학습 인자만 사용
- VisDrone2019-DET 원본 10개 클래스의 ID·이름 일치 및 PPE 혼합 차단
- train/val 이미지 중복 없음, 모든 이미지의 라벨 파일 존재
- 모든 train/val 이미지가 정확히 하나의 동일 split `VIDEO_SEQUENCE` root에 소속
- `FINAL_HELDOUT` 영상이 학습 split에 포함되지 않음
- S1은 `yolo26m.pt`, S2는 검증된 S1 best와 S1 매니페스트를 부모로 사용

실제 데이터셋에는 `split-manifest.json`의 TRAIN·VAL·FINAL_HELDOUT 영상 root를 모두 기록합니다. S2 `data.yaml`은 VisDrone 재학습 데이터와 VisionFlow 발표환경 유사 데이터를 하나의 10-class 계약으로 합쳐 가리켜야 합니다. 인접 프레임을 다른 split에 섞거나 동일 이미지를 train/val 양쪽에서 참조하면 계획 잠금 단계에서 실패합니다.

## Phase 2B-6A Dataset Intake Receipt

학습 계획이 `READY`여도 실제 이미지 바이트가 바뀌거나, 동일 이미지가 다른 경로로 train/val에 복사되거나, 손상 이미지와 orphan 라벨이 남아 있으면 학습을 시작하지 않습니다. Phase 2B-6A는 CPU에서 이미지를 디코딩하고 원본 바이트를 포함한 `full` fingerprint와 클래스 분포를 잠급니다.

```bat
scripts\run-visionflow-model-dataset-intake.bat ^
  --root . ^
  --plan config\visdrone-s1-training.plan.json ^
  --output output\dataset-intake\visdrone-s1-ready.json
```

receipt에는 train/val별 이미지·라벨·객체 수, 이미지당 최대 객체 수, 빈 라벨 이미지 수, 원본 해상도 범위, 클래스별 객체 수, 작은 객체 수·비율, 이미지 전체 SHA-256 fingerprint가 포함됩니다. `maximumObjectsPerImage`는 밀집된 VisDrone 장면의 AutoBatch 메모리 프로파일에 그대로 전달됩니다. 서로 다른 경로의 동일 이미지가 양쪽 split에서 발견되거나, 10개 클래스 중 객체가 없는 클래스가 있거나, 관리되는 train/val 라벨 root에 orphan 라벨이 있으면 실패합니다.

`--output`을 생략하거나 `--check-only`를 사용하면 파일을 만들지 않습니다. `output/*`, 실제 `datasets/*`, 모델 가중치는 계속 Git에서 제외합니다. 이 점검은 OpenCV의 CPU 이미지 디코딩만 사용하며 PyTorch·CUDA·YOLO 학습·Docker를 실행하지 않습니다.

## Phase 2B-6B Training GPU Preflight

GPU 학습 사전점검은 concrete 학습 계획과 Phase 2B-6A dataset intake receipt를 함께 입력받습니다. 기본 CPU 모드는 계획을 다시 컴파일하고 현재 이미지 바이트를 다시 검사하여 receipt의 `receiptSha256`, 계획 `evidenceLockSha256`, data YAML·영상 split manifest SHA-256과 train/val full fingerprint가 모두 그대로인지 확인합니다.

```bat
scripts\run-visionflow-model-training-gpu-preflight.bat ^
  --root . ^
  --plan config\visdrone-s1-training.plan.json ^
  --intake-receipt output\dataset-intake\visdrone-s1-ready.json ^
  --check-only
```

CPU 결과가 `READY_FOR_GPU_PROBE`여도 GPU 접근 승인은 아닙니다. 물리 GPU 점검을 별도로 승인한 경우에만 `--confirm-gpu-probe`를 추가합니다. 이 명시적 모드는 학습 계획의 단일 CUDA 장치, GPU 이름·compute capability·VRAM, PyTorch/CUDA/Ultralytics 버전과 정확한 부모 가중치의 Detection 클래스 identity를 확인합니다.

사전점검은 `YOLO.train()`을 호출하지 않고 데이터셋을 수정하지 않습니다. 계획의 `batch`는 계속 `PROVISIONAL`이며 GPU probe 통과 후 상태는 `READY_FOR_BATCH_CALIBRATION`, 다음 작업은 `GPU_BATCH_CALIBRATION_REQUIRED`로 고정됩니다. 실제 batch calibration과 S1/S2 학습은 별도 승인 단계입니다.

## Phase 2B-6C GPU Batch Calibration

GPU batch calibration은 Phase 2B-6A intake와 `READY_FOR_BATCH_CALIBRATION` 상태의 Phase 2B-6B receipt를 다시 잠급니다. 기본 `--check-only` 경로는 Torch·Ultralytics·CUDA를 불러오지 않으며 실제 GPU 보정에는 별도의 `--confirm-gpu-batch-calibration` 승인이 필요합니다.

```bat
scripts\run-visionflow-model-training-batch-calibration.bat ^
  --root . ^
  --plan config\visdrone-s1-training.plan.json ^
  --intake-receipt output\dataset-intake\visdrone-s1-ready.json ^
  --preflight-receipt output\training-gpu-preflight\visdrone-s1-gpu.json ^
  --check-only
```

명시 승인 경로는 GPU 메모리 60%를 목표로 Ultralytics AutoBatch 학습 그래프를 프로파일링합니다. train split의 `maximumObjectsPerImage`와 이미지 수를 사용하며 `YOLO.train()`, optimizer step, 가중치 저장, 계획·데이터 수정은 수행하지 않습니다. 추천 batch가 계획과 다르면 계획을 자동 수정하지 않고 Phase 2B-6A·6B 증거를 다시 생성하도록 요구합니다.
