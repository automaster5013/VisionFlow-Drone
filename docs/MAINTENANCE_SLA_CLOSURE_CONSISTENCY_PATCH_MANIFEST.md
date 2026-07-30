# VisionFlow 정비 SLA 마감 정합성 감시 패치

## 목적

Incident 조치 종료 이후 정비 작업과 비행 허가가 함께 올바르게
마감됐는지 한 화면에서 확인합니다. 서로 맞지 않는 상태 조합은
자동 변경하지 않고 운영자의 수동 점검 대상으로 분류합니다.

## 선행 조건

- 정비 SLA Incident 추적 패치 적용 완료
- 정비 SLA 인라인 대응 시작·조치 완료 패치 적용 완료
- 정비 작업 마감·비행 허가 패치 적용 및 검증 완료

## 제공 기능

- Incident·정비 작업·비행 허가 상태를 결합한 마감 정합성 판정
- 정비 마감 필요, 재운항 확인, 운항 중지, 수동 점검 건수 집계
- 정합성 상태별 권장 조치와 우선순위 표시
- 불일치 및 미완료 항목을 목록 상단에 우선 배치
- 정비 마감이 필요한 항목에서 기존 정비 작업 화면으로 이동
- Backend와 Next.js 프록시 응답의 정합성 자동 검증
- 서버 렌더링 화면에 정합성 패널이 포함되는지 자동 검증

## 정합성 상태

| 상태 | 의미 |
| --- | --- |
| `RESPONSE_ACTIVE` | Incident 대응과 정비 작업이 아직 진행 중 |
| `WORK_ORDER_PENDING` | Incident는 해결됐지만 정비 작업 마감이 남음 |
| `RETURN_TO_SERVICE_CONFIRMED` | 정비 작업 완료 및 비행 허가 확인 |
| `GROUNDED_CONFIRMED` | 운항 중지 작업 및 비행 금지 상태 확인 |
| `REVIEW_REQUIRED` | Incident·정비 작업·비행 허가 조합이 일치하지 않음 |

## 변경 파일

### Backend

- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/domain/MaintenanceSlaClosureStatus.java`
- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/dto/MaintenanceSlaIncidentTrackingItemResponse.java`
- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/dto/MaintenanceSlaIncidentTrackingResponse.java`
- `02_backend/visionflow-api/src/main/java/com/visionflow/api/maintenance/service/MaintenanceSlaIncidentTrackingService.java`
- `02_backend/visionflow-api/src/test/java/com/visionflow/api/maintenance/service/MaintenanceSlaIncidentTrackingServiceTests.java`

### Frontend

- `01_frontend/visionflow-web/src/types/maintenance-sla-incident-tracking.ts`
- `01_frontend/visionflow-web/src/components/maintenance/maintenance-sla-incident-tracking-panel.tsx`

### Acceptance

- `scripts/visionflow_maintenance_sla_tracking_acceptance.py`

### Documentation

- `docs/MAINTENANCE_SLA_CLOSURE_CONSISTENCY_PATCH_MANIFEST.md`
- `docs/MAINTENANCE_SLA_CLOSURE_CONSISTENCY_APPLY.md`

## 변경하지 않는 범위

- MySQL 테이블과 Flyway migration
- Incident 및 정비 작업 상태 변경 규칙
- 비행 게이트 판정 규칙
- 기존 운영자 권한과 감사 로그

## 안전 규칙

- 이 기능은 조회와 진단만 수행합니다.
- `REVIEW_REQUIRED` 상태를 자동 보정하지 않습니다.
- 재운항 승인과 운항 중지 결정은 기존 운영자 확인 절차를 따릅니다.
- 집계가 0건이어도 조회 기간에 해당 작업이 없다면 정상입니다.
