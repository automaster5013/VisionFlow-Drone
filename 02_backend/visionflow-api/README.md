# VisionFlow Incident SLA 자동 에스컬레이션 패치

Incident 생성 시 우선순위별 대응 제한시간을 부여하고, 기한을 넘긴 미처리 Incident를 자동 감지해 우선순위를 상향합니다. 변경 결과는 조치 이력과 STOMP 실시간 메시지로 남으며 Dashboard와 대응 보고서에 표시됩니다.

## SLA 정책

| 우선순위 | 대응 제한시간 | 초과 시 우선순위 |
|---|---:|---|
| LOW | 60분 | MEDIUM |
| MEDIUM | 30분 | HIGH |
| HIGH | 15분 | CRITICAL |
| CRITICAL | 5분 | CRITICAL 유지 |

- 스케줄러는 기본적으로 15초마다 `OPEN`, `IN_PROGRESS` Incident를 검사합니다.
- 한 Incident는 최초 SLA 초과 시 한 번만 자동 에스컬레이션됩니다.
- `RESOLVED`, `CLOSED` Incident는 검사 대상이 아닙니다.
- 자동 조치는 `SLA_ESCALATED`, 처리자는 `SYSTEM_SLA`로 기록됩니다.
- V13 적용 전에 존재한 진행 중 Incident는 배포 즉시 초과되지 않도록 V13 적용 시각부터 새 제한시간을 받습니다.

## 선행 조건

다음 단계가 이미 적용되어 있어야 합니다.

- Incident 관리와 V11
- Incident 증거·관제 연결과 V12
- Incident 대응 보고서 API와 화면

## 1. 백엔드 적용

프로젝트 루트:

```text
C:\VisionFlow-Drone\02_backend\visionflow-api
```

패치의 `backend/src`를 프로젝트 `src`에 같은 상대 경로로 덮어씁니다.

전체 파일 경로:

```text
C:\VisionFlow-Drone\02_backend\visionflow-api\src\main\java\com\visionflow\api\incident\config\IncidentSchedulingConfig.java
C:\VisionFlow-Drone\02_backend\visionflow-api\src\main\java\com\visionflow\api\incident\domain\Incident.java
C:\VisionFlow-Drone\02_backend\visionflow-api\src\main\java\com\visionflow\api\incident\domain\IncidentActionType.java
C:\VisionFlow-Drone\02_backend\visionflow-api\src\main\java\com\visionflow\api\incident\dto\IncidentResponse.java
C:\VisionFlow-Drone\02_backend\visionflow-api\src\main\java\com\visionflow\api\incident\realtime\IncidentRealtimeAction.java
C:\VisionFlow-Drone\02_backend\visionflow-api\src\main\java\com\visionflow\api\incident\repository\IncidentRepository.java
C:\VisionFlow-Drone\02_backend\visionflow-api\src\main\java\com\visionflow\api\incident\scheduler\IncidentSlaEscalationScheduler.java
C:\VisionFlow-Drone\02_backend\visionflow-api\src\main\java\com\visionflow\api\incident\service\IncidentService.java
C:\VisionFlow-Drone\02_backend\visionflow-api\src\main\java\com\visionflow\api\incident\service\IncidentSlaEscalationService.java
C:\VisionFlow-Drone\02_backend\visionflow-api\src\main\resources\db\migration\V13__add_incident_sla_escalation.sql
```

빌드 및 실행:

```bat
cd C:\VisionFlow-Drone\02_backend\visionflow-api
.\gradlew.bat clean build
.\gradlew.bat bootRun
```

V13이 한 번 적용된 후에는 해당 SQL을 수정하지 말고 후속 변경은 새 migration으로 작성해야 합니다.

스케줄러 기본값은 별도 설정 없이 활성화됩니다. 필요할 때 `application.yml`에서 다음 값을 변경할 수 있습니다.

```yaml
visionflow:
  incident:
    sla:
      enabled: true
      initial-delay-ms: 10000
      scan-delay-ms: 15000
```

통합 테스트 등에서 자동 변경을 막으려면 해당 프로필에 `visionflow.incident.sla.enabled: false`를 지정합니다.

## 2. 프론트엔드 적용

프로젝트 루트:

```text
C:\VisionFlow-Drone\01_frontend\visionflow-web
```

패치의 `frontend/src`를 프로젝트 `src`에 같은 상대 경로로 덮어씁니다.

전체 파일 경로:

```text
C:\VisionFlow-Drone\01_frontend\visionflow-web\src\components\dashboard\incident-operations-panel.tsx
C:\VisionFlow-Drone\01_frontend\visionflow-web\src\components\incidents\incident-report-view.tsx
C:\VisionFlow-Drone\01_frontend\visionflow-web\src\types\incident-realtime.ts
C:\VisionFlow-Drone\01_frontend\visionflow-web\src\types\incident.ts
```

검증:

```bat
cd C:\VisionFlow-Drone\01_frontend\visionflow-web
npm run lint
npm run build
npm run dev
```

## 빠른 SLA 초과 검증

실제 5~60분을 기다리지 않고 로컬 DB에서 테스트할 수 있습니다. `{ID}`는 상태가 `OPEN` 또는 `IN_PROGRESS`인 실제 Incident 번호로 변경합니다.

먼저 API로 우선순위를 LOW로 설정합니다.

```bat
curl.exe -i -X PATCH "http://localhost:8080/api/incidents/{ID}/priority" -H "Content-Type: application/json" -d "{\"priority\":\"LOW\",\"actor\":\"sla-test\",\"note\":\"SLA 자동 상향 검증\"}"
```

DBeaver에서 테스트 Incident의 기한만 과거로 변경합니다.

```sql
UPDATE incident
SET sla_due_at = UTC_TIMESTAMP(6) - INTERVAL 1 SECOND,
    sla_breached_at = NULL,
    escalation_level = 0
WHERE id = {ID}
  AND status IN ('OPEN', 'IN_PROGRESS');
```

COMMIT 후 최대 15초를 기다린 다음 확인합니다.

```bat
curl.exe -s "http://localhost:8080/api/incidents/{ID}"
```

정상 결과:

- `priority`: `LOW`에서 `MEDIUM`으로 변경
- `slaBreachedAt`: `null`이 아닌 UTC 시각
- `escalationLevel`: `1`
- 조치 이력 마지막 항목: `SLA_ESCALATED`, 처리자 `SYSTEM_SLA`
- 백엔드 로그: `SLA 초과 Incident 자동 에스컬레이션: 1건`
- Dashboard: `SLA 초과` 건수와 붉은 배지 표시
- STOMP 연결 중이면 화면 새로고침 없이 우선순위와 배지 갱신
- Incident 보고서: SLA 기한 초과와 자동 에스컬레이션 횟수 표시

검증에 사용한 Incident는 테스트 후 상태를 `RESOLVED` 또는 `CLOSED`로 변경하면 추가 SLA 검사 대상에서 제외됩니다.
