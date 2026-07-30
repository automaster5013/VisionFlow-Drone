# VisionFlow 정비 SLA 인라인 조치 완료 패치

## 목적

정비 SLA 운영자 대응 큐에서 담당자 지정과 대응 시작뿐 아니라 조치
메모 입력과 Incident 해결 처리까지 한 화면에서 완료합니다.

## 선행 조건

- 정비 SLA 운영자 대응 큐 패치 적용 완료
- 정비 SLA 인라인 담당자 지정·대응 시작 패치 적용 및 검증 완료
- `/operator-login`에서 OPERATOR 또는 ADMIN 로그인 가능

## 제공 기능

- `IN_RESPONSE` 항목에 `조치 완료` 버튼 표시
- 조치 완료 폼에서 원인과 처리 결과를 3~200자로 입력
- 기존 Incident 상태 변경 프록시로 `RESOLVED` 처리
- 조치 메모에 `정비 SLA 조치 완료` 문맥과 현재 운영자 기록
- 성공 후 대응 큐를 다시 조회하여 `조치 종료` 상태로 갱신
- 변경 성공 후 화면 갱신만 실패한 경우 성공 결과와 갱신 오류를 구분
- API 실패 시 작성한 메모를 유지하여 다시 시도 가능
- VIEWER 또는 비로그인 사용자의 조치 완료 버튼 비활성화
- 성공 메시지와 실패 메시지의 시각적·접근성 상태 구분

## 변경 파일

### Frontend

- `01_frontend/visionflow-web/src/components/maintenance/maintenance-sla-incident-tracking-panel.tsx`

### Acceptance

- `scripts/visionflow_maintenance_sla_tracking_acceptance.py`

### Documentation

- `docs/MAINTENANCE_SLA_INLINE_RESOLUTION_PATCH_MANIFEST.md`
- `docs/MAINTENANCE_SLA_INLINE_RESOLUTION_APPLY.md`

## 변경하지 않는 범위

- Backend Java 코드
- Flyway migration 및 MySQL 스키마
- 기존 Incident 상태 변경 API와 운영자 세션 정책
- 정비 작업 자체의 완료 상태 및 비행 허가 상태

Incident 해결은 정비 작업 완료와 별개의 운영 조치입니다. 실제 정비가
끝난 경우 기존 정비 작업 화면에서 작업 상태와 비행 허가 상태도 현재
운영 절차에 맞게 갱신합니다.
