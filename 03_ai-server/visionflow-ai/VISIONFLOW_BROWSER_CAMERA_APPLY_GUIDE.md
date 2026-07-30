# VisionFlow 브라우저 가상 드론 카메라 적용 가이드

이번 단계는 PC 또는 스마트폰 브라우저의 카메라 프레임을 Next.js 프록시를 통해 AI 서버로 전달하고, YOLO 분석 결과를 기존 `/drones` 관제 화면에 표시합니다.

현재 보류한 스마트폰 인증서 문제와 분리하여 PC의 `localhost` 웹캠으로 먼저 전체 파이프라인을 검증할 수 있습니다.

## 1. AI 워커 적용

`visionflow-ai-digital-twin` 폴더의 내용을 다음 경로에 같은 구조로 덮어씁니다.

```text
C:\VisionFlow-Drone\03_ai\visionflow-ai
```

주요 추가·수정 파일:

```text
C:\VisionFlow-Drone\03_ai\visionflow-ai\app\sources\browser_upload.py
C:\VisionFlow-Drone\03_ai\visionflow-ai\app\sources\__init__.py
C:\VisionFlow-Drone\03_ai\visionflow-ai\app\domain.py
C:\VisionFlow-Drone\03_ai\visionflow-ai\app\config.py
C:\VisionFlow-Drone\03_ai\visionflow-ai\app\main.py
C:\VisionFlow-Drone\03_ai\visionflow-ai\app\streaming.py
C:\VisionFlow-Drone\03_ai\visionflow-ai\tests\test_browser_upload_source.py
C:\VisionFlow-Drone\03_ai\visionflow-ai\.env.example
C:\VisionFlow-Drone\03_ai\visionflow-ai\README.md
```

기존 `.env`에는 다음 값을 반영합니다.

```dotenv
AI_SOURCE_TYPE=SMARTPHONE_LIVE
AI_SMARTPHONE_INPUT_MODE=BROWSER_UPLOAD
AI_DRONE_ID=1
AI_BROWSER_UPLOAD_FPS=5.0
AI_BROWSER_UPLOAD_QUEUE_CAPACITY=3
AI_BROWSER_UPLOAD_MAX_PAYLOAD_BYTES=2000000
AI_STREAM_ENABLED=true
AI_STREAM_HOST=127.0.0.1
AI_STREAM_PORT=8000
AI_SAVE_ANNOTATED_VIDEO=false
AI_MAX_FRAMES=0
```

## 2. Next.js 적용

`frontend-browser-camera-patch\src`의 내용을 다음 경로에 같은 구조로 복사합니다.

```text
C:\VisionFlow-Drone\01_frontend\visionflow-web\src
```

추가 파일 전체 경로:

```text
C:\VisionFlow-Drone\01_frontend\visionflow-web\src\app\mobile-camera\page.tsx
C:\VisionFlow-Drone\01_frontend\visionflow-web\src\app\api\ai\ingest\frame\route.ts
C:\VisionFlow-Drone\01_frontend\visionflow-web\src\app\api\ai\ingest\status\route.ts
C:\VisionFlow-Drone\01_frontend\visionflow-web\src\components\mobile\mobile-camera-streamer.tsx
C:\VisionFlow-Drone\01_frontend\visionflow-web\src\types\ai-browser-ingest.ts
```

`.env.local`을 확인합니다.

```dotenv
AI_STREAM_API_URL=http://localhost:8000
NEXT_PUBLIC_AI_STREAM_URL=http://localhost:8000/api/streams/annotated.mjpeg
```

## 3. 실행 순서

1. Spring Boot 백엔드
2. AI 워커
3. Next.js 프런트엔드

AI 워커:

```bat
cd /d C:\VisionFlow-Drone\03_ai\visionflow-ai
.venv\Scripts\activate
python -m app.main
```

Next.js:

```bat
cd /d C:\VisionFlow-Drone\01_frontend\visionflow-web
npm run lint
npm run build
npm run dev
```

## 4. PC 웹캠 검증

Chrome 또는 Edge에서 다음 주소를 엽니다.

```text
http://localhost:3000/mobile-camera
```

1. 연결할 드론을 선택합니다.
2. PC에서는 `전면 카메라`를 선택합니다.
3. 처음에는 `5 FPS`, `960px`, `JPEG 75%`를 유지합니다.
4. `카메라 전송 시작`을 누르고 카메라 권한을 허용합니다.
5. 화면 전송 및 AI 수신 프레임 수가 증가하는지 확인합니다.
6. `http://localhost:3000/drones`를 별도 탭에서 엽니다.
7. `AI 실시간 분석 영상`에 웹캠 영상과 YOLO 바운딩 박스가 표시되는지 확인합니다.
8. 객체가 탐지되면 AI 이벤트와 MySQL 이력이 생성되는지 확인합니다.

AI 입력 API 독립 확인:

```text
http://localhost:3000/api/ai/ingest/status
http://localhost:8000/api/ingest/status
```

정상 예시:

```json
{
  "enabled": true,
  "running": true,
  "queueDepth": 0,
  "acceptedFrames": 25,
  "droppedFrames": 0,
  "lastReceivedAt": "2026-07-20T10:00:00+00:00"
}
```

## 5. 스마트폰 검증 상태

스마트폰 브라우저의 카메라 접근도 신뢰된 HTTPS가 필요하므로 현재 인증서 이슈가 해결될 때까지 실기기 검증만 보류합니다. PC localhost 검증이 통과하면 카메라 업로드, AI 수신, YOLO 추론, 이벤트 저장 구현 자체는 완료된 것으로 판단할 수 있습니다.

인증서 해결 후에는 같은 `/mobile-camera` 주소를 스마트폰에서 열고 `후면 카메라`를 선택하여 그대로 검증합니다.

## 장애 구분

- 카메라 권한 창 없음: 브라우저 사이트 카메라 권한 확인
- 프레임 POST 502: AI 워커 미실행 또는 `AI_STREAM_API_URL` 오류
- `/api/ingest/status` 404: AI `.env`의 `AI_SMARTPHONE_INPUT_MODE=BROWSER_UPLOAD` 확인
- 화면 전송만 증가하고 AI 수신은 0: Next.js 프록시 및 AI 워커 로그 확인
- 큐 드롭 급증: FPS 또는 최대 폭 낮추기
- 분석 영상이 OFFLINE: YOLO 모델 로딩과 `/api/streams/status` 확인
- 분석 영상은 정상이나 이벤트 없음: 현재 화면에 탐지 대상이 있는지 확인
