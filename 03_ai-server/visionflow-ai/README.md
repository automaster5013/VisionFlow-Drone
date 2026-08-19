# VisionFlow AI 디지털 트윈 워커

2차 프로젝트용 공통 영상 입력 및 YOLO26 추론 워커입니다. 더미 영상, 스마트폰 RTSP/HTTP 영상, 브라우저가 업로드한 카메라 프레임을 동일한 `FramePacket` 계약으로 처리합니다.

## 지원 입력

- `DUMMY_VIDEO`: MP4 등 저장 영상
- `SMARTPHONE_LIVE + STREAM_URL`: 스마트폰 RTSP 또는 HTTP/MJPEG URL
- `SMARTPHONE_LIVE + BROWSER_UPLOAD`: Next.js `/mobile-camera`에서 업로드한 JPEG 프레임
- `DJI_LIVE + REPLAY_FILE`: 저장 영상을 DJI 의미론으로 재생하는 소프트웨어 검증 입력
- `DJI_LIVE + ANDROID_BRIDGE`: Android MSDK H.264/H.265 encoded stream을 Edge AI에서 디코딩하는 입력

브라우저 업로드도 백엔드 이벤트에는 `SMARTPHONE_LIVE`로 기록됩니다. 따라서 Spring Boot와 MySQL의 기존 `sourceType` 계약은 변경하지 않습니다.

## 설치 위치

```text
C:\VisionFlow-Drone\03_ai-server\visionflow-ai
```

```bat
cd /d C:\VisionFlow-Drone\03_ai-server\visionflow-ai
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 브라우저 카메라 입력 설정

`.env.example`을 `.env`로 복사한 다음 다음 항목을 설정합니다.

```dotenv
AI_SOURCE_TYPE=SMARTPHONE_LIVE
AI_SMARTPHONE_INPUT_MODE=BROWSER_UPLOAD
AI_DRONE_ID=1

AI_BROWSER_UPLOAD_FPS=5.0
AI_BROWSER_UPLOAD_QUEUE_CAPACITY=3
AI_BROWSER_UPLOAD_MAX_PAYLOAD_BYTES=2000000

AI_MODEL_PATH=yolo26n.pt
AI_DEVICE=cpu
AI_MAX_FRAMES=0
AI_SHOW_PREVIEW=false
AI_SAVE_ANNOTATED_VIDEO=false

AI_REPORT_EVENTS=true
AI_BACKEND_EVENT_URL=http://localhost:8080/api/ai/events
AI_SNAPSHOT_ENABLED=true

AI_STREAM_ENABLED=true
AI_STREAM_HOST=127.0.0.1
AI_STREAM_PORT=8000
AI_STREAM_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

`BROWSER_UPLOAD`에서는 실제 드론 ID, 영상 소스 ID와 세션 ID를 `/mobile-camera` 화면이 프레임마다 전달합니다. `AI_DRONE_ID`는 설정 유효성 확인을 위해 1 이상의 기존 값을 유지합니다.

## 실행과 독립 확인

Spring Boot를 먼저 실행한 다음 AI 워커를 실행합니다.

```bat
cd /d C:\VisionFlow-Drone\03_ai-server\visionflow-ai
.venv\Scripts\activate
python -m app.main
```

확인 주소:

```text
http://localhost:8000/health
http://localhost:8000/api/ingest/status
http://localhost:8000/api/streams/status
http://localhost:8000/api/models/status
http://localhost:8000/api/streams/annotated.mjpeg
```

프레임이 들어오기 전 `/api/ingest/status`는 `running: true`, `acceptedFrames: 0`으로 표시되는 것이 정상입니다. 워커는 입력 큐에서 프레임을 기다리며 종료되지 않습니다.

## 지연 최소화 방식

브라우저가 YOLO 처리 속도보다 빠르게 프레임을 보내면 큐에 오래된 화면이 쌓이지 않도록 가장 오래된 프레임을 버립니다. `/api/ingest/status`의 `droppedFrames`는 장애 횟수가 아니라 저지연 유지용 프레임 생략 횟수입니다.

드롭이 계속 빠르게 증가하면 `/mobile-camera`에서 다음 순서로 부하를 낮춥니다.

1. 10 FPS에서 5 FPS 또는 2 FPS로 변경
2. 최대 영상 폭을 960px에서 640px로 변경
3. JPEG 품질을 낮춤
4. CUDA 환경을 확인한 후 `AI_DEVICE=0` 적용

## 기존 스트림 URL 입력

스마트폰 카메라 앱의 RTSP 또는 HTTP/MJPEG 주소를 계속 사용할 수도 있습니다.

```dotenv
AI_SOURCE_TYPE=SMARTPHONE_LIVE
AI_SMARTPHONE_INPUT_MODE=STREAM_URL
AI_SMARTPHONE_STREAM_URL=http://192.168.10.50:8080/video
AI_SMARTPHONE_RECONNECT=true
```

## 테스트

```bat
pytest
ruff check .
python -m compileall app tests
```

브라우저 입력 소스, 큐 드롭, 잘못된 JPEG, 업로드 API, 용량 제한을 자동 테스트합니다.

## 장애 구분

- `/health` 실패: AI 워커 미실행 또는 8000 포트 충돌
- `/api/ingest/status`가 404: `.env`가 `BROWSER_UPLOAD`가 아니거나 이전 코드 실행 중
- 프레임 POST 413: JPEG가 2MB 제한 초과, 해상도 또는 품질 낮추기
- `acceptedFrames` 증가하지만 분석 스트림 없음: 모델 로딩·YOLO 추론 로그 확인
- `droppedFrames` 빠르게 증가: 전송 FPS/해상도를 낮추거나 GPU 사용
- 이벤트만 저장되지 않음: Spring Boot와 `AI_BACKEND_EVENT_URL` 확인

## Docker GPU 및 커스텀 모델

CPU 기본 Compose는 그대로 유지하고, NVIDIA GPU가 있는 PC에서만 루트의 `compose.gpu.yaml`을 함께 적용합니다. 모델 파일은 `models` 폴더에 배치하며 Docker 이미지에는 포함하지 않습니다.

```text
C:\VisionFlow-Drone\03_ai-server\visionflow-ai\models\yolo26n.pt
C:\VisionFlow-Drone\03_ai-server\visionflow-ai\models\best.pt
```

프로젝트 루트에서 GPU와 기본 모델을 점검합니다.

```bat
scripts\run-visionflow-gpu-preflight.bat -ModelFile yolo26n.pt
```

이 사전점검은 CUDA 가용성뿐 아니라 CUDA 텐서 연산, YOLO 모델의 실제 GPU 적재,
호스트 모델과 컨테이너 모델의 SHA-256 일치 여부까지 확인합니다.
성공하면 다음 위치에 JSON·HTML·SHA-256 증적도 함께 생성합니다.

```text
artifacts\gpu-readiness\gpu-preflight-<UTC 시각>\
```

독립 재검증 방법은 프로젝트 루트의
`docs\GPU_PREFLIGHT_EVIDENCE.md`를 확인하세요.

전체 스택을 GPU 모드로 시작합니다.

```bat
scripts\run-visionflow-gpu.bat -ModelFile yolo26n.pt
```

파인튜닝 모델로 시작할 때는 파일명만 변경합니다.

```bat
scripts\run-visionflow-gpu.bat -ModelFile best.pt
```

GPU 실행은 CUDA가 감지되지 않거나 모델이 없으면 CPU로 조용히 대체하지 않고 명확한 오류로 중단됩니다. CPU 모드는 기존 명령을 그대로 사용합니다.

```bat
docker compose --env-file .env.docker up -d --build
```
