# VisionFlow 드론 이력 삭제 방지

기준 커밋: `27183e961dab47164e5a656801385d302358813f`

## 문제 경계

`DELETE /api/drones/{id}`는 Drone 행을 직접 삭제한다. 기존 `flight_session.drone_id` 외래 키가 `ON DELETE CASCADE`였기 때문에 Drone 삭제 시 세션은 함께 사라질 수 있었다. AI 이벤트·경보·Incident 등은 운영 증적 보존을 위해 일부 상관관계를 물리 FK 대신 ID로 유지하므로, 세션만 삭제되면 고아 데이터가 생길 수 있다.

이번 변경은 이미 복구한 이력 데이터를 다시 잃지 않도록 Drone 삭제를 세 겹으로 방어한다.

1. Drone 행을 `PESSIMISTIC_WRITE`로 잠근다.
2. `SERIALIZABLE` transaction에서 9개 운영 이력 범주를 검사한다.
3. Drone 소유 물리 이력 FK를 `ON DELETE RESTRICT`로 변경한다.

DB 경계에서 변경되는 FK는 다음 세 개다. 기존
`maintenance_work_order.drone_id`는 삭제 규칙 생략 시 MySQL의
`RESTRICT` 동작을 이미 사용하므로 그대로 유지한다.

- `drone_telemetry_history.drone_id → drone.id`
- `flight_session.drone_id → drone.id`
- `flight_quality_assessment.drone_id → drone.id`

## 삭제 허용 조건

다음 테이블 어디에도 대상 `drone_id`가 없을 때만 Drone을 물리 삭제한다.

- `flight_session`
- `drone_telemetry_history`
- `ai_inference_event`
- `ai_alert`
- `drone_geofence_event`
- `incident`
- `demo_scenario`
- `flight_quality_assessment`
- `maintenance_work_order`

이력이 하나라도 있으면 다음 응답을 반환하고 어떤 행도 삭제하지 않는다.

```text
HTTP 409
code=DRONE_HISTORY_DELETE_DENIED
```

운영 중이거나 이력이 있는 Drone은 삭제하지 않고 상태를 `OFFLINE`으로 변경해 보존한다. 운영 이력이 전혀 없는 잘못 등록된 Drone만 기존과 같이 삭제할 수 있다.

## 검증

Backend 단위시험과 빌드를 실행한다.

```bat
02_backend\visionflow-api\gradlew.bat -p 02_backend\visionflow-api test --tests "com.visionflow.api.drone.service.DroneServiceDeletionTests"
02_backend\visionflow-api\gradlew.bat -p 02_backend\visionflow-api clean build
```

서비스를 재빌드한 뒤 전체 수용시험을 실행한다.

```bat
scripts\run-visionflow-acceptance.bat -FrontendUrl https://localhost:3443 -RunRbac -RunSession
```

전체 수용시험은 기존 기능과 인증 경계의 회귀 여부를 확인하지만 실제 Drone
`DELETE` 요청은 보내지 않는다. 보호 결함이 있을 때 운영 데이터를 지우는 시험이
되지 않도록 삭제 거부 경계는 `DroneServiceDeletionTests`와 Flyway 정책 감사로
검증한다.

마지막으로 추적성 감사와 데이터 정합성 감사를 다시 실행한다.

```bat
scripts\run-visionflow-system-traceability-audit.bat
scripts\run-visionflow-data-integrity-audit.bat
```

정상 기준은 `SYSTEM_TRACEABILITY_HEALTHY`, `DATA_INTEGRITY_HEALTHY`,
`Findings=0`이다. 추적성 감사의 `drone-history-delete-policy` 검사는 Drone 소유
물리 이력 FK 네 개가 모두 `RESTRICT`인지 확인한다.
