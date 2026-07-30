# VisionFlow YOLO 모델 A/B 성능 벤치마크

이 단계는 스마트폰 없이 동일한 더미 영상으로 `yolo26n.pt`와 파인튜닝한 `best.pt`의 실행 성능을 비교합니다. 탐지 정확도 비교는 다음 단계에서 별도의 검증 데이터셋으로 수행합니다.

## 1. 고정 입력 영상 준비

동일한 MP4 파일을 다음 경로에 배치합니다.

```text
C:\VisionFlow-Drone\03_ai-server\visionflow-ai\data\dummy\benchmark.mp4
```

`compose.yaml`에 다음 읽기 전용 볼륨이 추가되어 컨테이너의 `/app/data/dummy`에서 같은 파일을 사용합니다.

## 2. `.env.docker` 벤치마크 설정

```dotenv
AI_SOURCE_TYPE=DUMMY_VIDEO
AI_SOURCE_ID=fixed-benchmark-video-001
AI_DUMMY_VIDEO_PATH=/app/data/dummy/benchmark.mp4
AI_LOOP_VIDEO=true
AI_REALTIME_PLAYBACK=false
AI_SAVE_ANNOTATED_VIDEO=false
AI_REPORT_EVENTS=false
AI_SNAPSHOT_ENABLED=false
AI_MAX_FRAMES=0

AI_IMAGE_SIZE=640
AI_CONFIDENCE=0.35
AI_IOU=0.70
```

`AI_REALTIME_PLAYBACK=false`는 영상 원래 FPS에 맞춰 기다리지 않고 장치가 처리할 수 있는 속도로 계속 추론하게 합니다. 두 모델에 동일한 값을 사용해야 합니다.

## 3. yolo26n.pt 기준 모델 측정

HP OMEN에서 GPU 스택을 시작합니다.

```bat
scripts\run-visionflow-gpu.bat -ModelFile yolo26n.pt
```

10초 워밍업 후 성능 누적값을 초기화하고 60초 동안 측정합니다.

```bat
scripts\run-visionflow-ai-benchmark.bat ^
  -DurationSeconds 60 ^
  -WarmupSeconds 10 ^
  -HardwareLabel HP-OMEN-RTX5060 ^
  -RunLabel yolo26n-gpu ^
  -InputFilePath "03_ai-server\visionflow-ai\data\dummy\benchmark.mp4"
```

## 4. best.pt 후보 모델 측정

```bat
scripts\run-visionflow-gpu.bat -ModelFile best.pt
```

```bat
scripts\run-visionflow-ai-benchmark.bat ^
  -DurationSeconds 60 ^
  -WarmupSeconds 10 ^
  -HardwareLabel HP-OMEN-RTX5060 ^
  -RunLabel best-gpu ^
  -InputFilePath "03_ai-server\visionflow-ai\data\dummy\benchmark.mp4"
```

각 JSON에는 다음 재현 정보가 포함됩니다.

- 모델 프로필, 경로, 크기, SHA-256 및 클래스 목록
- 입력 영상 이름, 크기 및 SHA-256
- PyTorch/CUDA/cuDNN 버전과 실제 GPU 이름
- image size, confidence, IoU
- 워밍업 시간과 성능 계측 초기화 시각
- 입력·처리 FPS, 평균/P95/최대 추론 지연, 드롭 및 큐 깊이

## 5. 두 결과 비교

생성된 JSON 파일의 실제 경로를 사용합니다.

```bat
scripts\compare-visionflow-ai-benchmarks.bat ^
  "artifacts\ai-benchmark\visionflow-ai-benchmark-...-yolo26n-gpu.json" ^
  "artifacts\ai-benchmark\visionflow-ai-benchmark-...-best-gpu.json" ^
  --label hp-omen-yolo26n-vs-best
```

출력 위치:

```text
artifacts\ai-benchmark-comparison\*.json
artifacts\ai-benchmark-comparison\*.csv
artifacts\ai-benchmark-comparison\*.md
```

비교기는 다음 조건이 다르면 `INVALID_COMPARISON`으로 판정합니다.

- 하드웨어 또는 실행 장치
- 입력 영상 SHA-256
- 영상 소스 종류
- image size, confidence 또는 IoU
- 측정 시간
- 평균 입력 FPS가 10%보다 크게 차이 나는 경우

입력 속도가 2 FPS 미만이면 저부하 측정 경고가 표시됩니다.

## 6. 확인 API

```text
GET  http://localhost:8000/api/models/status
GET  http://localhost:8000/api/metrics/status
POST http://localhost:8000/api/metrics/reset
```

`POST /api/metrics/reset`은 AI 파이프라인을 중지하지 않고 성능 측정 구간의 프레임 수, 지연 표본 및 누적 최대값만 초기화합니다.

## 결과 해석 범위

이 결과는 실행 성능 비교입니다. `best.pt`가 실제 관제 대상 탐지에서 더 정확한지는 검증 데이터셋의 precision, recall, mAP 및 클래스별 오탐·미탐을 별도로 평가해야 합니다.
