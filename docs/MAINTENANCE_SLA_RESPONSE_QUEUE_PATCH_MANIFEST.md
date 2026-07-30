# VisionFlow 정비 SLA 운영자 대응 큐 패치

## 목적

SLA 자동 상향 여부만 확인하던 정비 화면을 운영자 대응 관점으로
확장합니다. 담당자 지정 필요, 대응 중, 조치 종료 상태를 구분하고
기존 Incident 운영 화면으로 바로 이동할 수 있습니다.

## 선행 조건

- 정비 SLA Incident 추적 패치 적용 완료
- 정비 SLA 추적 패널 SSR Hotfix 적용 및 4/4 검증 완료

## 운영 상태

- `MONITORING`: SLA 기한과 정비 상태 감시 중
- `ESCALATION_PENDING`: SLA 초과 후 자동 상향 대기 또는 연결 이상
- `ASSIGNMENT_REQUIRED`: 자동 상향 완료, Incident 담당자 미지정
- `IN_RESPONSE`: 자동 상향 완료, 담당자 지정 및 대응 중
- `COMPLETED`: Incident가 해결 또는 종료됨

## 제공 기능

- SLA Incident 추적 API에 운영자 대응 상태와 권고 조치 추가
- 감시·상향 대기·담당자 필요·대응 중·종료 집계
- `/maintenance`에 `운영자 대응 큐` 표시
- 개별 항목의 Incident 담당자와 다음 권고 조치 표시
- `운영 조치 열기`로 드론 필터가 적용된 `/dashboard` 이동
- 기존 `Incident 보고서` 링크 유지
- 자동 인수 테스트에서 응답 상태 집계와 SSR 표식 검증

## 변경 파일

### Backend

- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/domain/MaintenanceSlaResponseStatus.java`
- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/dto/MaintenanceSlaIncidentTrackingItemResponse.java`
- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/dto/MaintenanceSlaIncidentTrackingResponse.java`
- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/service/MaintenanceSlaIncidentTrackingService.java`
- `02_backend/visionflow-api/src/test/java/com/visionflow/api/maintenance/service/MaintenanceSlaIncidentTrackingServiceTests.java`

### Frontend

- `01_frontend/visionflow-web/src/components/maintenance/maintenance-sla-incident-tracking-panel.tsx`
- `01_frontend/visionflow-web/src/types/maintenance-sla-incident-tracking.ts`

### Acceptance

- `scripts/visionflow_maintenance_sla_tracking_acceptance.py`

## 데이터베이스

새 Flyway migration은 없습니다. 기존 Incident의 `status`, `assignee`와
SLA 자동 상향 이력을 읽어 운영 상태를 계산합니다.
