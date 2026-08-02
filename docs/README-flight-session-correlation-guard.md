# VisionFlow Flight Session 상관관계 쓰기 방어

## 목적

`session_id`는 여러 테이블을 연결하는 소프트 상관키다. 물리 FK가 없는 외부
입력 경로에서 오타, 존재하지 않는 세션, 다른 Drone의 세션이 저장되면 데이터
정합성 감사의 session-orphan 또는 session-drone-mismatch finding이 다시
발생할 수 있다.

이 변경은 다음 두 외부 입력을 영속화 전에 검증한다.

- `PATCH /api/drones/{id}/telemetry`
- `POST /api/ai/events`

## 정책

- 세션 ID가 있으면 `flight_session`에서 반드시 존재해야 한다.
- 세션의 `drone_id`는 요청 Drone과 일치해야 한다.
- 존재하지 않는 세션은 HTTP 404 `RESOURCE_NOT_FOUND`로 거부한다.
- 다른 Drone 소유 세션은 HTTP 409
  `FLIGHT_SESSION_DRONE_MISMATCH`로 거부한다.
- 세션 ID가 없는 텔레메트리는 기존 동작을 유지한다.
- AI 이벤트의 중복 판정도 정규화·검증된 세션 ID를 사용한다.

AI alert와 Incident는 검증된 AI 이벤트에서 파생되고, geofence event는 검증된
텔레메트리에서 파생되므로 하위 연쇄 데이터도 동일한 상관관계를 상속한다.

## 자동 검증

Backend 단위 테스트:

```bat
02_backend\visionflow-api\gradlew.bat -p 02_backend\visionflow-api test --tests "com.visionflow.api.flight.service.FlightSessionCorrelationGuardTests" --tests "com.visionflow.api.ai.service.AiInferenceEventServiceCorrelationTests" --tests "com.visionflow.api.drone.service.DroneServiceTelemetryCorrelationTests" --tests "com.visionflow.api.drone.service.DroneServiceDeletionTests"
```

소스 정책 및 전체 API·DB 추적성 감사:

```bat
py -3 -m unittest scripts.tests.test_visionflow_system_traceability_session_correlation -v
scripts\run-visionflow-system-traceability-audit.bat
scripts\run-visionflow-api-audit-ci.bat
```

## 운영 안전

- Flyway migration과 DB 행 변경이 없다.
- 컨테이너와 서비스를 설치 단계에서 변경하지 않는다.
- 실제 적용 후에는 `backend-api`만 다시 빌드한다.
- 재빌드 전후 `DATA_INTEGRITY_HEALTHY`, Findings=0을 유지해야 한다.
