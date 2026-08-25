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
