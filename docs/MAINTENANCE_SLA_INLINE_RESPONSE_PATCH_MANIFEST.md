# VisionFlow 정비 SLA 인라인 대응 패치

## 목적

정비 SLA 운영자 대응 큐의 `담당자 지정 필요` 항목에서 다른 화면으로
이동하지 않고 현재 로그인한 운영자를 담당자로 지정하고 Incident
대응을 바로 시작합니다.

## 선행 조건

- 정비 SLA 운영자 대응 큐 패치 적용 및 검증 완료
- 브라우저 운영자 세션과 Incident 변경 프록시 적용 완료
- `/operator-login`에서 OPERATOR 또는 ADMIN 로그인 가능

## 제공 기능

- `ASSIGNMENT_REQUIRED` 항목에 `내가 담당·대응 시작` 버튼 표시
- 현재 브라우저 세션의 운영자 이름을 Incident 담당자로 지정
- Incident 상태를 `IN_PROGRESS`로 전환하고 대응 시작 이력 기록
- 성공 또는 실패 후 SLA 추적 큐를 즉시 다시 조회
- VIEWER 또는 비로그인 사용자의 버튼 비활성화와 사유 안내
- 기존 보안 프록시를 재사용하므로 원본 운영자 키를 화면에 재입력하지 않음
- 자동 인수 테스트에서 인라인 UI 표식과 두 Incident 변경 프록시 확인

## 변경 파일

### Frontend

- `01_frontend/visionflow-web/src/components/maintenance/maintenance-sla-incident-tracking-panel.tsx`

### Acceptance

- `scripts/visionflow_maintenance_sla_tracking_acceptance.py`

### Documentation

- `docs/MAINTENANCE_SLA_INLINE_RESPONSE_PATCH_MANIFEST.md`
- `docs/MAINTENANCE_SLA_INLINE_RESPONSE_APPLY.md`

## 변경하지 않는 범위

- Backend Java 코드
- Flyway migration 및 MySQL 스키마
- 기존 Incident 담당자·상태 변경 API 계약
- 브라우저 운영자 세션 보안 정책

## 실패 복구

Incident 상태 전환을 먼저 수행하고 담당자를 지정합니다. 담당자 지정이
실패하더라도 항목은 `담당자 지정 필요` 상태로 남아 운영자가 다시
시도할 수 있으며, 화면은 서버 상태를 즉시 다시 조회합니다.
