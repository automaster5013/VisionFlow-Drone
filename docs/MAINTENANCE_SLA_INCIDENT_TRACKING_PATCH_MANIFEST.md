# VisionFlow 정비 SLA Incident 추적 패치

## 목적

정비 작업과 Incident의 연결 상태, SLA 초과 여부, 자동 상향 이력을
`/maintenance` 화면에서 한 번에 확인합니다.

## 선행 조건

- `visionflow-maintenance-sla-incident-escalation-patch-v2-20260726.zip`
  적용 완료
- 백엔드 `gradlew.bat clean build` 통과
- 프런트엔드 `npm run lint`, `npm run build` 통과

## 제공 기능

- `GET /api/maintenance/sla/incidents?windowDays=30`
- 최근 1~90일 정비 작업과 연결 Incident 조회
- 작업 수, Incident 연결 수, SLA 초과 수, 자동 상향 수 집계
- `SYSTEM_MAINTENANCE_SLA`가 기록한 `SLA_ESCALATED` 이력 추적
- Next.js 동일 출처 프록시
- `/maintenance`의 정비 우선조치 큐 아래 추적 패널
- 개별 Incident 종합 보고서 바로가기
- 독립 인수 테스트 및 JSON/HTML 증적

## 변경 파일

### Backend

- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/controller/MaintenanceSlaIncidentTrackingController.java`
- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/dto/MaintenanceSlaIncidentTrackingItemResponse.java`
- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/dto/MaintenanceSlaIncidentTrackingResponse.java`
- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/service/MaintenanceSlaIncidentTrackingService.java`
- `02_backend/visionflow-api/src/test/java/com/visionflow/api/maintenance/service/MaintenanceSlaIncidentTrackingServiceTests.java`

### Frontend

- `01_frontend/visionflow-web/src/app/api/maintenance/sla/incidents/route.ts`
- `01_frontend/visionflow-web/src/components/maintenance/maintenance-priority-panel.tsx`
- `01_frontend/visionflow-web/src/components/maintenance/maintenance-sla-incident-tracking-panel.tsx`
- `01_frontend/visionflow-web/src/types/maintenance-sla-incident-tracking.ts`

### Acceptance

- `scripts/run-visionflow-maintenance-sla-tracking-acceptance.bat`
- `scripts/visionflow_maintenance_sla_tracking_acceptance.py`

## 데이터베이스

새 테이블이나 Flyway migration은 없습니다. 기존
`maintenance_work_order`, `incident`, `incident_action_history` 데이터를
읽기 전용으로 조합합니다.

## 안전성

- 조회 API는 데이터를 수정하지 않습니다.
- 기존 KPI Repository와 우선순위 응답 모델을 변경하지 않습니다.
- 기존 정비·Incident 생성 및 처리 API의 동작을 변경하지 않습니다.
