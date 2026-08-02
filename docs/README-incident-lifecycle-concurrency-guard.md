# VisionFlow Incident lifecycle concurrency guard

## 목적

운영자 변경, SLA 예약 작업, 비행 품질 자동화, 반복 비행 차단 자동화가 같은
Incident를 동시에 변경할 때 마지막 저장이 앞선 변경을 덮어쓰거나 동일한
이력이 중복 기록되는 것을 차단한다.

## 적용 정책

- 단건 변경은 `IncidentRepository.findByIdForUpdate`로 행 잠금을 획득한다.
- 원본 기반 생성·동기화는
  `findBySourceTypeAndSourceIdForUpdate`를 사용한다.
- 일반 SLA 배치는 잠금이 적용된 overdue 조회를 사용한다.
- 정비 SLA는 Incident 잠금 뒤 `SLA_ESCALATED` 이력을 재검사한다.
- 비행 품질·비행 게이트 자동화의 기존 Drone 잠금 순서를 보존한다.
- 상세·검색·보고서는 읽기 전용 조회를 유지한다.

## 보호되는 쓰기 경로

1. 운영자 담당자 지정
2. 운영자 우선순위 변경
3. 운영자 상태 전이
4. 운영자 조치 메모 추가
5. AI Alert·Geofence 원본 상태 동기화
6. Incident SLA 자동 상향
7. 정비 SLA 자동 상향
8. 비행 품질 Incident 생성·갱신
9. 반복 비행 차단 Incident 생성·재개·해제
10. 통합 시연 SLA 초과 상태 준비

## 데이터베이스 경계

새 스키마 변경은 없다. 기존 `incident` 테이블의
`uk_incident_source(source_type, source_id)` UNIQUE 제약이 원본 기반 생성의
최종 중복 방어선으로 유지된다. 행 잠금은 트랜잭션 종료 시 자동 해제된다.

## 검증

```bat
02_backend\visionflow-api\gradlew.bat -p 02_backend\visionflow-api test --tests "com.visionflow.api.incident.service.IncidentServiceConcurrencyTests" --tests "com.visionflow.api.incident.service.IncidentSlaEscalationServiceConcurrencyTests" --tests "com.visionflow.api.maintenance.service.MaintenanceSlaIncidentEscalationServiceTests" --tests "com.visionflow.api.flight.quality.service.FlightQualityIncidentAutomationServiceTests" --tests "com.visionflow.api.maintenance.service.FlightGateIncidentAutomationServiceTests"
py -3 -m unittest scripts.tests.test_visionflow_system_traceability_incident_lifecycle -v
scripts\run-visionflow-system-traceability-audit.bat
scripts\run-visionflow-api-audit-ci.bat
```

모든 검사는 소스와 테스트 범위에서 수행되며 데이터베이스 행, 컨테이너,
서비스, 예약 작업을 변경하지 않는다.
