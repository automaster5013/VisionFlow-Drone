# VisionFlow 비행 세션 수명주기 동시성 방어

기준 커밋: `23f7ffa77188e0190ab6e3e4460123462888ef47`

## 목적

기존 비행 시작은 ACTIVE 세션을 조회한 뒤 새 행을 저장했다. 같은 Drone에
동시 요청이 들어오면 두 요청이 모두 조회를 통과할 수 있고, 완료와 중단이
경합하면 마지막 갱신이 앞선 종료 상태와 후속 이벤트를 덮을 수 있다.

## 방어 계층

- 비행 시작은 `drone` 행을 `PESSIMISTIC_WRITE`로 잠근 뒤 ACTIVE 세션을 검사한다.
- 수정·완료·중단은 대상 `flight_session` 행을 `PESSIMISTIC_WRITE`로 잠근다.
- Flyway V22는 ACTIVE일 때만 Drone ID가 채워지는 생성 열과 UNIQUE 제약을
  추가해 여러 Backend 인스턴스나 직접 SQL 경합도 차단한다.
- 중복 시작은 HTTP 409 `ACTIVE_FLIGHT_SESSION_EXISTS`로 반환한다.
- 읽기 전용 데이터 정합성 감사는
  `flight-session-multiple-active-per-drone` 규칙을 추가해 총 40개 DB 규칙을
  검사한다.

## 적용 전 안전 조건

V22는 기존 중복 ACTIVE 세션이 있으면 의도적으로 실패한다. Backend 재빌드 전에
다음 감사를 먼저 실행하고 `DATA_INTEGRITY_HEALTHY`, `Findings=0`을 확인한다.

```bat
scripts\run-visionflow-data-integrity-audit.bat
```

## 검증

```bat
02_backend\visionflow-api\gradlew.bat -p 02_backend\visionflow-api test --tests "com.visionflow.api.flight.service.FlightSessionManagementServiceTests"
py -3 -m unittest scripts.tests.test_visionflow_data_integrity_audit scripts.tests.test_visionflow_system_traceability_flight_session_lifecycle -v
scripts\run-visionflow-system-traceability-audit.bat
scripts\run-visionflow-api-audit-ci.bat
```

감사가 모두 통과한 뒤 `backend-api`만 재빌드해 V22를 적용한다. Migration은
운영 행을 삭제하거나 세션 상태를 바꾸지 않는다.
