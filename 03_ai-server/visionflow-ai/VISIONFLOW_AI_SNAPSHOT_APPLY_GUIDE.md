# VisionFlow AI 탐지 스냅샷 저장·조회 적용 안내

## 1. 구현 결과

객체가 탐지된 프레임마다 다음 순서로 처리됩니다.

1. Python AI 워커가 `POST /api/ai/events`로 탐지 JSON을 저장합니다.
2. Spring Boot가 반환한 이벤트 ID로 `PUT /api/ai/events/{eventId}/snapshot`에 분석 JPEG를 업로드합니다.
3. MySQL `ai_inference_event`에는 파일명·MIME 형식·크기·저장 시각이 기록됩니다.
4. 실제 JPEG는 Spring Boot 서버의 `data\ai-snapshots`에 저장됩니다.
5. 저장 완료 이벤트가 STOMP로 다시 발행됩니다.
6. Next.js 이벤트 카드에 썸네일이 나타나고 클릭하면 확대됩니다.

기존 이벤트 행에는 이미지가 없으므로 UI에 `이 이벤트에는 저장된 분석 이미지가 없습니다.`가 표시되는 것이 정상입니다. 패치 적용 후 새로 탐지된 이벤트부터 스냅샷이 생성됩니다.

## 2. Spring Boot 백엔드 적용

패치 폴더의 `src`를 다음 프로젝트의 `src`에 같은 구조로 병합합니다.

```text
C:\VisionFlow-Drone\02_backend\visionflow-api
```

이번 단계의 백엔드 파일:

```text
C:\VisionFlow-Drone\02_backend\visionflow-api\src\main\java\com\visionflow\api\ai\controller\AiInferenceEventController.java
C:\VisionFlow-Drone\02_backend\visionflow-api\src\main\java\com\visionflow\api\ai\domain\AiInferenceEvent.java
C:\VisionFlow-Drone\02_backend\visionflow-api\src\main\java\com\visionflow\api\ai\dto\AiInferenceEventResponse.java
C:\VisionFlow-Drone\02_backend\visionflow-api\src\main\java\com\visionflow\api\ai\service\AiInferenceEventService.java
C:\VisionFlow-Drone\02_backend\visionflow-api\src\main\java\com\visionflow\api\ai\service\AiSnapshotStorageService.java
C:\VisionFlow-Drone\02_backend\visionflow-api\src\main\resources\db\migration\V6__add_ai_event_snapshot_metadata.sql
```

기본 JPEG 저장 위치:

```text
C:\VisionFlow-Drone\02_backend\visionflow-api\data\ai-snapshots
```

빌드 및 실행:

```bat
cd /d C:\VisionFlow-Drone\02_backend\visionflow-api
.\gradlew.bat clean build
.\gradlew.bat bootRun
```

Flyway 로그에서 `V6__add_ai_event_snapshot_metadata.sql` 적용 성공 여부를 확인합니다.

## 3. Python AI 워커 적용

AI 패치의 다음 파일을 같은 경로에 덮어씁니다.

```text
C:\VisionFlow-Drone\03_ai\visionflow-ai\app\config.py
C:\VisionFlow-Drone\03_ai\visionflow-ai\app\main.py
C:\VisionFlow-Drone\03_ai\visionflow-ai\app\pipeline.py
C:\VisionFlow-Drone\03_ai\visionflow-ai\app\reporting.py
C:\VisionFlow-Drone\03_ai\visionflow-ai\tests\test_event_reporter.py
C:\VisionFlow-Drone\03_ai\visionflow-ai\.env.example
C:\VisionFlow-Drone\03_ai\visionflow-ai\README.md
```

기존 `.env`에 추가합니다.

```dotenv
# 개인정보 보호 기본값
AI_SNAPSHOT_POLICY=OFF
AI_SNAPSHOT_JPEG_QUALITY=85

# 통제된 탐지 이벤트에만 자동 스냅샷이 필요한 경우에만 사용합니다.
# AI_SNAPSHOT_POLICY=INCIDENT_ONLY
```

검증 및 실행:

```bat
cd /d C:\VisionFlow-Drone\03_ai\visionflow-ai
call .venv\Scripts\activate.bat
python -m pytest
ruff check .
python -m compileall app tests
python -m app.main
```

## 4. Next.js 프런트엔드 적용

프런트엔드 패치의 `src`를 다음 프로젝트의 `src`에 같은 구조로 병합합니다.

```text
C:\VisionFlow-Drone\01_frontend\visionflow-web
```

이번 단계의 프런트엔드 파일:

```text
C:\VisionFlow-Drone\01_frontend\visionflow-web\src\app\api\ai\events\[id]\snapshot\route.ts
C:\VisionFlow-Drone\01_frontend\visionflow-web\src\components\drones\ai-inference-event-panel.tsx
C:\VisionFlow-Drone\01_frontend\visionflow-web\src\types\ai-inference-event.ts
```

검증 및 실행:

```bat
cd /d C:\VisionFlow-Drone\01_frontend\visionflow-web
npm run lint
npm run build
npm run dev
```

## 5. 통합 기능 테스트

실행 순서:

1. Spring Boot: `localhost:8080`
2. Python AI 워커: `python -m app.main`
3. Next.js: `localhost:3000`

확인 URL:

```text
http://localhost:8080/api/ai/events?limit=10
http://localhost:3000/api/ai/events?limit=10
http://localhost:3000/drones
```

정상 조건:

- `AI_SNAPSHOT_POLICY=OFF` 또는 `MANUAL`이면 새 AI 이벤트의 `snapshotAvailable=false`가 정상이며 자동 JPEG 파일을 만들지 않습니다.
- `AI_SNAPSHOT_POLICY=INCIDENT_ONLY`이면 하드 이벤트 게이트를 통과한 탐지 이벤트에 한해 `snapshotAvailable=true`가 될 수 있습니다.
- 저장된 경우 `snapshotUrl`은 `/api/ai/events/{id}/snapshot` 형식이고 백엔드 `data\ai-snapshots`에 `event-{id}.jpg`가 생성됩니다.
- 저장된 스냅샷은 `/drones`에서 확인할 수 있고, 불필요하면 즉시 `스냅샷 삭제`로 제거합니다.

MySQL 확인:

```sql
SELECT id,
       drone_id,
       frame_index,
       snapshot_file_name,
       snapshot_size_bytes,
       snapshot_created_at
FROM ai_inference_event
ORDER BY id DESC
LIMIT 10;
```

## 6. 문제 구분

- `OFF`/`MANUAL`에서 `snapshotAvailable=false`: 정상입니다. 자동 JPEG 저장이 비활성화된 상태입니다.
- `INCIDENT_ONLY`인데 `snapshotAvailable=false`: AI 워커 재시작 여부, `AI_SNAPSHOT_POLICY=INCIDENT_ONLY`, 하드 이벤트 게이트 통과 여부를 확인합니다.
- Python 로그에 스냅샷 업로드 `413`: Spring의 multipart 제한을 10MB 이상으로 조정합니다.
- 이미지 API가 `404`: DB 메타데이터와 `data\ai-snapshots\event-{id}.jpg`가 함께 존재하는지 확인합니다.
- 이미지 API가 `502`: Next.js의 `BACKEND_API_URL`과 Spring Boot `8080` 실행 상태를 확인합니다.
- 기존 이벤트에만 이미지가 없음: 정상입니다. 이번 단계 이후 새 이벤트부터 JPEG가 저장됩니다.
