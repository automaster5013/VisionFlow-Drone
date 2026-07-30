# VisionFlow 정비 조치 SLA 및 저작권 표시 패치

## 목적

정비 우선조치 큐에 작업 제한시간을 추가하여 미처리 작업을
`정상`, `임박`, `초과` 상태로 구분합니다. 동시에 모든 데스크톱 운영
화면의 공통 좌측 사이드바 하단에 다음 저작권 문구를 표시합니다.

```text
© 2026 Team PyvaOps. All rights reserved.
```

이 패치는 앞 단계의 **정비 우선조치 큐 패치가 적용된 최신 소스**를
기준으로 합니다.

## SLA 운영 규칙

| 작업 상태 | 제한시간 | 표시 |
|---|---:|---|
| `OPEN` | 작업 접수 후 120분 | `ON_TRACK`, `DUE_SOON`, `OVERDUE` |
| `IN_PROGRESS` | 점검 시작 후 240분 | `ON_TRACK`, `DUE_SOON`, `OVERDUE` |
| `COMPLETED`, `GROUNDED` | 적용하지 않음 | `NOT_APPLICABLE` |

- 남은 시간이 30분 이하이면 `DUE_SOON`입니다.
- 제한시간을 넘으면 `OVERDUE`이며 위험도에 20점을 추가합니다.
- `DUE_SOON`은 위험도에 10점을 추가합니다.
- `IN_PROGRESS`인데 시작 시각이 없는 기존 데이터는 접수 시각을
  기준으로 계산합니다.
- SLA 점수를 포함한 최종 위험도는 100점을 넘지 않습니다.

## 적용

프로젝트 루트는 다음 경로입니다.

```text
C:\VisionFlow-Drone
```

배포 ZIP을 이 경로에 풀고 기존 파일 덮어쓰기를 허용합니다. MySQL
테이블 변경이 없으므로 Flyway 마이그레이션은 추가되지 않습니다.

핵심 수정 경로:

```text
02_backend\visionflow-api\src\main\java\com\visionflow\api\maintenance\domain\MaintenanceSlaStatus.java
02_backend\visionflow-api\src\main\java\com\visionflow\api\maintenance\service\MaintenancePriorityService.java
01_frontend\visionflow-web\src\components\maintenance\maintenance-priority-panel.tsx
01_frontend\visionflow-web\src\components\layout\app-sidebar.tsx
scripts\visionflow_maintenance_acceptance.py
```

저작권은 `app-sidebar.tsx`의 공통 사이드바 최하단에 배치되어
데스크톱 운영 화면을 이동해도 같은 위치에 유지됩니다.

## 빌드 검증

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

Docker Compose를 사용하는 경우 프로젝트 루트에서 변경된 두 서비스를
다시 빌드합니다.

```bat
cd /d C:\VisionFlow-Drone
docker compose --env-file .env.docker up --build -d backend-api frontend-web
```

## API 검증

```bat
curl.exe -i "http://localhost:8080/api/maintenance/priorities"
curl.exe -i "http://localhost:3000/api/maintenance/priorities"
```

두 요청 모두 `HTTP 200`이어야 합니다. 작업이 있는 항목에는 다음 SLA
필드가 포함됩니다.

```json
{
  "slaStatus": "DUE_SOON",
  "slaDueAt": "2026-07-26T10:00:00Z",
  "slaRemainingMinutes": 30,
  "slaOverdueMinutes": 0
}
```

작업이 없거나 이미 종료된 경우에는 다음 응답이 정상입니다.

```json
{
  "slaStatus": "NOT_APPLICABLE",
  "slaDueAt": null,
  "slaRemainingMinutes": null,
  "slaOverdueMinutes": null
}
```

## 화면 검증

```text
http://localhost:3000/maintenance
```

확인 항목:

1. `정비 우선조치 큐` 상단에 `SLA 초과`, `SLA 임박` 집계가 보입니다.
2. 각 드론 항목에 SLA 상태 배지가 표시됩니다.
3. SLA 초과 작업은 즉시 조치를 안내하며 높은 위험도로 정렬됩니다.
4. 좌측 사이드바 하단에 Team PyvaOps 저작권 문구가 보입니다.

## 자동 인수 검증

```bat
cd /d C:\VisionFlow-Drone
scripts\run-visionflow-maintenance-acceptance.bat
```

정상 결과:

```text
VisionFlow maintenance acceptance: MAINTENANCE_GATE_READY
Checks: 20/20 passed
```

마지막으로 최신 증적을 릴리스 판정에 반영합니다.

```bat
scripts\run-visionflow-release-gate.bat
```
