# VisionFlow 정비 우선조치 큐 패치 명세

## 추가 파일

- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/domain/MaintenancePriorityLevel.java`
- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/dto/MaintenancePriorityItemResponse.java`
- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/dto/MaintenancePriorityQueueResponse.java`
- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/service/MaintenancePriorityService.java`
- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/controller/MaintenancePriorityController.java`
- `02_backend/visionflow-api/src/test/java/com/visionflow/api/maintenance/service/MaintenancePriorityServiceTests.java`
- `01_frontend/visionflow-web/src/app/api/maintenance/priorities/route.ts`
- `01_frontend/visionflow-web/src/types/maintenance-priority.ts`
- `01_frontend/visionflow-web/src/components/maintenance/maintenance-priority-panel.tsx`
- `docs/MAINTENANCE_PRIORITY_QUEUE_APPLY.md`
- `docs/MAINTENANCE_PRIORITY_QUEUE_PATCH_MANIFEST.md`

## 수정 파일

- `01_frontend/visionflow-web/src/components/maintenance/maintenance-work-order-board.tsx`
- `scripts/visionflow_maintenance_acceptance.py`
- `scripts/tests/test_visionflow_maintenance_acceptance.py`

## 변경하지 않는 항목

- MySQL 테이블 및 Flyway 마이그레이션
- 기존 작업지시 처리 규칙
- 비행 게이트 강제/주의 모드
- 스마트폰 실센서, HP OMEN GPU, DJI 기체 연동
