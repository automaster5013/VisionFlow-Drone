# VisionFlow 정비 조치 SLA 및 저작권 표시 패치 명세

## 선행 조건

- 정비 우선조치 큐 패치 적용 완료
- 현재 프로젝트 루트: `C:\VisionFlow-Drone`

## 추가 파일

- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/domain/MaintenanceSlaStatus.java`
- `docs/MAINTENANCE_SLA_COPYRIGHT_APPLY.md`
- `docs/MAINTENANCE_SLA_COPYRIGHT_PATCH_MANIFEST.md`

## 수정 파일

- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/dto/MaintenancePriorityItemResponse.java`
- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/dto/MaintenancePriorityQueueResponse.java`
- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/service/MaintenancePriorityService.java`
- `02_backend/visionflow-api/src/test/java/com/visionflow/api/maintenance/service/MaintenancePriorityServiceTests.java`
- `01_frontend/visionflow-web/src/types/maintenance-priority.ts`
- `01_frontend/visionflow-web/src/components/maintenance/maintenance-priority-panel.tsx`
- `01_frontend/visionflow-web/src/components/layout/app-sidebar.tsx`
- `scripts/visionflow_maintenance_acceptance.py`
- `scripts/tests/test_visionflow_maintenance_acceptance.py`

## 변경하지 않는 항목

- MySQL 테이블 및 Flyway 마이그레이션
- 정비 작업지시의 기존 상태 전이 규칙
- 비행 게이트 강제/주의 모드
- 스마트폰 실센서, HP OMEN GPU, DJI 기체 연동

## 검증 범위

- 프런트엔드 TypeScript 검사 및 ESLint
- 백엔드 SLA 서비스 Java 컴파일 및 규칙 계산
- Python 자동 인수 테스트
- 정비 인수 검사 20개 항목

별도 `.sha256` 파일은 패치에 포함하지 않습니다. ZIP 무결성 확인용
SHA-256 값은 전달 메시지에만 제공합니다.
