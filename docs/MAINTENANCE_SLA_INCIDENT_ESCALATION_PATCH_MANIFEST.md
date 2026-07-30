# 정비 SLA Incident 자동 에스컬레이션 패치 명세

## 추가 파일

- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/config/MaintenanceSlaAutomationProperties.java`
- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/controller/MaintenanceSlaController.java`
- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/dto/MaintenanceSlaAutomationStatusResponse.java`
- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/dto/MaintenanceSlaEscalationResultResponse.java`
- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/scheduler/MaintenanceSlaIncidentEscalationScheduler.java`
- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/service/MaintenanceSlaIncidentEscalationService.java`
- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/service/MaintenanceSlaPolicy.java`
- `02_backend/visionflow-api/src/test/java/com/visionflow/api/maintenance/service/MaintenanceSlaIncidentEscalationServiceTests.java`
- `01_frontend/visionflow-web/src/app/api/maintenance/sla/route.ts`
- `01_frontend/visionflow-web/src/types/maintenance-sla-automation.ts`
- `docs/MAINTENANCE_SLA_INCIDENT_ESCALATION_APPLY.md`
- `docs/MAINTENANCE_SLA_INCIDENT_ESCALATION_PATCH_MANIFEST.md`

## 수정 파일

- `02_backend/visionflow-api/src/main/java/com/visionflow/api/incident/repository/IncidentActionHistoryRepository.java`
- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/repository/MaintenanceWorkOrderRepository.java`
- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/service/MaintenancePriorityService.java`
- `01_frontend/visionflow-web/src/components/maintenance/maintenance-priority-panel.tsx`
- `scripts/visionflow_maintenance_acceptance.py`
- `scripts/tests/test_visionflow_maintenance_acceptance.py`

## 변경하지 않는 항목

- MySQL 테이블 및 Flyway 마이그레이션
- 기존 Incident 고유키 및 원본 연결 구조
- 정비 작업지시 상태 전이 규칙
- 비행 게이트 모드
- 스마트폰, GPU, DJI 연동 범위

## 검증 범위

- Java 구문 및 서비스 의존 타입 컴파일
- 정비 SLA 정책 및 Incident 상향 계산 실행
- TypeScript 검사 및 ESLint
- Python 단위 테스트 11개
- 정비 인수 검사 23개

별도 `.sha256` 파일은 생성하지 않으며 ZIP 해시 값은 전달 메시지에만
표시합니다.
