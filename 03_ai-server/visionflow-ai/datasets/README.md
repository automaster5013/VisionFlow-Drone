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
