# VisionFlow 정비 SLA Incident 자동 에스컬레이션 패치

## 목적

정비 작업지시가 SLA를 초과하면 연결된 원본 Incident를 자동으로
관제 대응 상태로 되돌리고 우선순위를 `CRITICAL`로 상향합니다.

정비 작업지시에는 이미 원본 Incident ID가 저장되어 있으므로 별도의
중복 Incident를 생성하지 않습니다. 기존 Incident가 `RESOLVED`이면
`IN_PROGRESS`로 재개하며, `OPEN` 또는 `IN_PROGRESS`이면 상태를
유지한 채 우선순위를 상향합니다.

## 자동화 규칙

- `OPEN`: 접수 후 120분 초과
- `IN_PROGRESS`: 점검 시작 후 240분 초과
- 자동 검색: 기본 30초 간격
- Incident 우선순위: `CRITICAL`
- 종료된 `CLOSED` Incident: 자동 변경하지 않고 생략
- 동일 정비 작업: `SYSTEM_MAINTENANCE_SLA` 이력을 기준으로 한 번만 처리
- 변경 결과: Incident 이력, 실시간 WebSocket, 감사 로그에 기록

## 선행 조건

- 정비 우선조치 큐 적용 완료
- 정비 SLA 및 Team PyvaOps 저작권 패치 적용 완료

## 적용

프로젝트 루트는 다음 경로입니다.

```text
C:\VisionFlow-Drone
```

패치 ZIP을 프로젝트 루트에 풀고 기존 파일 덮어쓰기를 허용합니다.
테이블이나 컬럼 변경이 없으므로 Flyway 마이그레이션은 없습니다.

## 빌드 및 재기동

```bat
cd /d C:\VisionFlow-Drone\02_backend\visionflow-api
gradlew.bat clean build

cd /d C:\VisionFlow-Drone\01_frontend\visionflow-web
npm run lint
npm run build

cd /d C:\VisionFlow-Drone
docker compose --env-file .env.docker up --build -d backend-api frontend-web
```

## 상태 API 검증

백엔드:

```bat
curl.exe -i "http://localhost:8080/api/maintenance/sla"
```

Next.js 프록시:

```bat
curl.exe -i "http://localhost:3000/api/maintenance/sla"
```

두 요청 모두 `HTTP 200`이고 다음과 같은 응답이어야 합니다.

```json
{
  "automationEnabled": true,
  "openSlaMinutes": 120,
  "inProgressSlaMinutes": 240,
  "dueSoonMinutes": 30,
  "initialDelayMs": 15000,
  "scanDelayMs": 30000
}
```

## 화면 검증

```text
http://localhost:3000/maintenance
```

`정비 우선조치 큐` 제목 아래에 다음 항목이 보여야 합니다.

```text
SLA 자동 Incident 상향 ON
OPEN 120분 · 진행 240분 · 30초 간격
```

## 설정

기본값은 자동화 활성화입니다. 필요할 때 다음 환경 변수로 제어할 수
있습니다.

```dotenv
VISIONFLOW_MAINTENANCE_SLA_AUTOMATION_ENABLED=true
VISIONFLOW_MAINTENANCE_SLA_INITIAL_DELAY_MS=15000
VISIONFLOW_MAINTENANCE_SLA_SCAN_DELAY_MS=30000
```

발표 및 릴리스 검증에서는 `AUTOMATION_ENABLED=true`를 유지합니다.

## 자동 인수 검증

```bat
cd /d C:\VisionFlow-Drone
scripts\run-visionflow-maintenance-acceptance.bat
```

정상 결과:

```text
VisionFlow maintenance acceptance: MAINTENANCE_GATE_READY
Checks: 23/23 passed
```

이후 최신 증적을 릴리스 판정에 반영합니다.

```bat
scripts\run-visionflow-release-gate.bat
```
