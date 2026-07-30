# VisionFlow 발표 시연 자동화 패치

이 패치는 발표 중 한 화면에서 아래의 실제 애플리케이션 흐름을 순서대로
재현합니다.

1. 비행 세션 생성
2. 가상 드론 텔레메트리 5건 저장
3. `DUMMY_VIDEO` 화재 탐지 이벤트 생성
4. 기존 `AiAlertService`를 통한 CRITICAL AI 경보 생성
5. 기존 `IncidentService`를 통한 Incident 자동 생성
6. JPEG 탐지 증거 저장
7. 해당 Incident만 SLA 초과 처리하고 에스컬레이션 레벨 증가
8. 관제 담당자 해결 처리와 비행 세션 종료
9. 관제 지도 재생 및 Incident 보고서 바로가기 제공

> 이 기능은 발표 흐름을 안정적으로 재현하기 위한 **결정론적 시연
> fallback**입니다. 실제 스마트폰 영상 → Python AI 서버 → YOLO 추론 흐름을
> 대체하지 않습니다. 실제 추론 시연이 가능한 환경에서는 기존 라이브 분석
> 화면을 우선 사용하고, 이 콘솔은 발표 중 네트워크·장치 문제에 대비해
> 사용하세요.

## 1. 백엔드 파일 반영

ZIP의 `backend` 아래 파일을 다음 프로젝트 루트에 같은 상대 경로로
덮어씁니다.

`C:\VisionFlow-Drone\02_backend\visionflow-api`

주요 파일:

- `src\main\java\com\visionflow\api\common\config\SecurityConfig.java`
- `src\main\java\com\visionflow\api\incident\service\IncidentSlaEscalationService.java`
- `src\main\java\com\visionflow\api\demo\controller\DemoScenarioController.java`
- `src\main\java\com\visionflow\api\demo\domain\DemoScenario.java`
- `src\main\java\com\visionflow\api\demo\domain\DemoScenarioStage.java`
- `src\main\java\com\visionflow\api\demo\dto\DemoScenarioStartRequest.java`
- `src\main\java\com\visionflow\api\demo\dto\DemoScenarioResponse.java`
- `src\main\java\com\visionflow\api\demo\repository\DemoScenarioRepository.java`
- `src\main\java\com\visionflow\api\demo\service\DemoScenarioService.java`
- `src\main\resources\db\migration\V14__create_demo_scenario.sql`

`V14`는 앞 단계의 `V13__add_incident_sla_escalation.sql`이 이미 반영된
프로젝트를 기준으로 합니다.

## 2. 시연 API 활성화 및 백엔드 실행

기본값은 비활성화입니다. PowerShell에서는 다음처럼 실행합니다.

```powershell
cd C:\VisionFlow-Drone\02_backend\visionflow-api
$env:VISIONFLOW_DEMO_ENABLED="true"
.\gradlew.bat clean bootRun
```

CMD에서는 다음을 사용합니다.

```bat
cd C:\VisionFlow-Drone\02_backend\visionflow-api
set VISIONFLOW_DEMO_ENABLED=true
gradlew.bat clean bootRun
```

시연이 끝나면 환경 변수를 제거하거나 `false`로 되돌립니다. 비활성 상태에서
`/api/demo/**`는 404가 정상입니다.

## 3. 프런트엔드 파일 반영

ZIP의 `frontend` 아래 파일을 다음 프로젝트 루트에 같은 상대 경로로
덮어씁니다.

`C:\VisionFlow-Drone\01_frontend\visionflow-web`

주요 파일:

- `src\app\demo-scenario\page.tsx`
- `src\app\api\demo\scenarios\route.ts`
- `src\app\api\demo\scenarios\[id]\route.ts`
- `src\app\api\demo\scenarios\[id]\[action]\route.ts`
- `src\components\demo\demo-scenario-console.tsx`
- `src\components\dashboard\incident-operations-panel.tsx`
- `src\lib\server\demo-scenario-proxy.ts`
- `src\types\demo-scenario.ts`

실행 및 정적 검증:

```bat
cd C:\VisionFlow-Drone\01_frontend\visionflow-web
npm run lint
npm run build
npm run dev
```

## 4. 화면 검증

1. MySQL, Spring Boot, Next.js를 실행합니다.
2. 드론 ID 1에 진행 중인 비행 세션이 없어야 합니다. 진행 중인 세션이
   있다면 먼저 정상 종료하거나 중단하세요.
3. `http://localhost:3000/demo-scenario`에 접속합니다.
4. 드론 ID와 시작 좌표를 확인합니다.
5. `전체 시연 자동 실행`을 누릅니다.
6. 아래 단계가 차례로 완료되는지 확인합니다.
   `READY → DETECTED → ESCALATED → RESOLVED → COMPLETED`
7. 화재 탐지 이미지, 관제 지도 바로가기, Incident 보고서 링크를
   확인합니다.
8. `/dashboard`의 `통합 Incident 관제` 우측 `발표 시연 콘솔` 버튼도
   확인합니다.

수동으로 각 단계를 보여주려면 `새 시연 수동 시작` 후 오른쪽 단계 버튼을
하나씩 누릅니다.

## 5. API 단독 검증

시나리오 시작:

```bat
curl.exe -i -X POST "http://localhost:8080/api/demo/scenarios" ^
  -H "Content-Type: application/json" ^
  -d "{\"droneId\":1,\"latitude\":37.5665,\"longitude\":126.9780}"
```

응답의 `scenarioId`를 실제 UUID로 바꿔 아래 요청을 순서대로 실행합니다.
중괄호 문자열 `{UUID}`를 그대로 입력하면 안 됩니다.

```bat
curl.exe -i -X POST "http://localhost:8080/api/demo/scenarios/실제_UUID/detect"
curl.exe -i -X POST "http://localhost:8080/api/demo/scenarios/실제_UUID/escalate"
curl.exe -i -X POST "http://localhost:8080/api/demo/scenarios/실제_UUID/resolve"
curl.exe -i -X POST "http://localhost:8080/api/demo/scenarios/실제_UUID/complete"
curl.exe -i "http://localhost:8080/api/demo/scenarios/실제_UUID"
```

## 6. DB 확인 SQL

```sql
SELECT scenario_id, drone_id, flight_session_id, ai_event_id,
       ai_alert_id, incident_id, stage, started_at, completed_at
FROM demo_scenario
ORDER BY started_at DESC
LIMIT 10;

SELECT id, priority, status, sla_due_at, sla_breached_at,
       escalation_level
FROM incident
WHERE id = 시나리오의_incident_id;

SELECT incident_id, action_type, actor, note, created_at
FROM incident_action_history
WHERE incident_id = 시나리오의_incident_id
ORDER BY id;

SELECT drone_id, flight_session_id, latitude, longitude,
       altitude, recorded_at
FROM drone_telemetry_history
WHERE flight_session_id = '시나리오의_flight_session_id'
ORDER BY recorded_at;
```

기대 결과:

- `demo_scenario.stage = COMPLETED`
- Incident `status = RESOLVED`
- `sla_breached_at`이 NULL이 아님
- `escalation_level = 1`
- 조치 이력에 `SLA_ESCALATED`, `SOURCE_SYNCHRONIZED`가 존재
- 동일 비행 세션의 텔레메트리 이력이 5건 이상 존재

## 7. 흔한 오류

- **404 `/api/demo/scenarios`**: 백엔드를
  `VISIONFLOW_DEMO_ENABLED=true`로 다시 실행합니다.
- **502 프록시 오류**: Spring Boot가 8080 포트에서 실행 중인지와
  프런트 `.env.local`의 백엔드 URL을 확인합니다.
- **이미 진행 중인 비행 세션**: 해당 드론의 기존 ACTIVE 세션을 먼저
  완료 또는 중단합니다.
- **Flyway V14 실패**: V13 적용 여부와 `flyway_schema_history`를
  확인합니다. 기존 migration 파일의 내용을 수정하지 마세요.
- **단계 순서 오류**: 현재 단계에서 제공되는 버튼을 사용하거나 새
  시나리오를 시작합니다.
