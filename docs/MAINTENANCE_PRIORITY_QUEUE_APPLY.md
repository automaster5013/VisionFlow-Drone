# VisionFlow 정비 우선조치 큐 패치

## 목적

현재 함대 비행 허가 상태와 드론별 최신 점검 작업지시를 결합하여
`/maintenance` 화면에 위험도가 높은 드론부터 표시합니다.

이 점수는 AI 예측값이 아니라 설명 가능한 운영 규칙 기반 점수입니다.

- 비행 차단: 위험도 100
- 운항 중지: 최소 95
- 점검 대기: 최소 65
- 점검 진행: 최소 50
- 장기 미처리 작업: 대기 일수에 따라 최대 20점 추가

## 적용

프로젝트 루트는 다음 경로입니다.

```text
C:\VisionFlow-Drone
```

배포 ZIP을 이 경로에 풀고 기존 파일 덮어쓰기를 허용합니다. DB 스키마
변경은 없으므로 Flyway 마이그레이션은 추가되지 않습니다.

주요 추가 경로:

```text
02_backend\visionflow-api\src\main\java\com\visionflow\api\maintenance\controller\MaintenancePriorityController.java
02_backend\visionflow-api\src\main\java\com\visionflow\api\maintenance\service\MaintenancePriorityService.java
01_frontend\visionflow-web\src\app\api\maintenance\priorities\route.ts
01_frontend\visionflow-web\src\components\maintenance\maintenance-priority-panel.tsx
01_frontend\visionflow-web\src\types\maintenance-priority.ts
```

기존 파일 중 다음 두 파일은 수정됩니다.

```text
01_frontend\visionflow-web\src\components\maintenance\maintenance-work-order-board.tsx
scripts\visionflow_maintenance_acceptance.py
```

## 로컬 개발 검증

백엔드:

```bat
cd /d C:\VisionFlow-Drone\02_backend\visionflow-api
gradlew.bat clean build
```

프런트엔드:

```bat
cd /d C:\VisionFlow-Drone\01_frontend\visionflow-web
npm run lint
npm run build
```

서비스를 로컬 프로세스로 실행 중이라면 백엔드와 프런트엔드를 각각
재시작합니다. Docker Compose를 사용한다면 프로젝트 루트에서 다음을
실행합니다.

```bat
docker compose --env-file .env.docker up --build -d backend-api frontend-web
```

## API 검증

```bat
curl.exe -i "http://localhost:8080/api/maintenance/priorities"
curl.exe -i "http://localhost:3000/api/maintenance/priorities"
```

두 요청 모두 `HTTP 200`이어야 하며 핵심 응답은 다음 형태입니다.

```json
{
  "totalDrones": 3,
  "urgentDrones": 0,
  "attentionDrones": 0,
  "normalDrones": 3,
  "priorities": [
    {
      "droneId": 1,
      "priority": "LOW",
      "riskScore": 0
    }
  ]
}
```

현재 정비 작업이 없다면 모든 드론이 `LOW`로 표시되는 것이 정상입니다.
점검 대기 또는 운항 중지 작업이 생기면 해당 드론이 목록 상단으로
이동합니다.

## 화면 검증

```text
http://localhost:3000/maintenance
```

확인 항목:

1. `정비 운영 현황` 아래에 `정비 우선조치 큐`가 표시됩니다.
2. 긴급·높음, 주의, 정상 드론 수의 합이 전체 드론 수와 같습니다.
3. 위험도 점수가 큰 드론이 먼저 표시됩니다.
4. 작업이 있는 드론은 `작업 열기`, 없는 드론은 `관제 확인` 버튼이
   표시됩니다.
5. Incident 동기화 또는 점검 시작·완료 후 큐가 자동 갱신됩니다.

## 자동 인수 검증

```bat
cd /d C:\VisionFlow-Drone
scripts\run-visionflow-maintenance-acceptance.bat
```

정상 결과:

```text
VisionFlow maintenance acceptance: MAINTENANCE_GATE_READY
Checks: 19/19 passed
```

이후 릴리스 준비도에 새 정비 증빙을 반영하려면 다음을 실행합니다.

```bat
scripts\run-visionflow-release-gate.bat
```
