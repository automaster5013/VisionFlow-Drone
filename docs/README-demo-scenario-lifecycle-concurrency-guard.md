# VisionFlow Demo Scenario 수명주기 동시성 방어

기준 커밋: `1d35edbebfcb8e7ef6bebeddfbff5781d1228863`

통합 시연의 탐지·에스컬레이션·해결·완료 요청이 동시에 실행돼도 같은 단계의 외부 연쇄 쓰기와 시나리오 상태 변경이 중복 실행되지 않도록 직렬화한다.

## 방어 범위

- `detect`, `escalate`, `resolve`, `complete`는 대상 `demo_scenario` 행을 `PESSIMISTIC_WRITE`로 잠근다.
- 단계 검증과 AI 이벤트·경보·Incident·비행 세션 변경은 잠금 획득 뒤에 실행한다.
- 첫 요청이 단계를 변경하면 대기하던 동일 요청은 최신 단계를 확인하고 기존 단계 검증에서 차단된다.
- 단건 조회는 기존 비잠금 읽기를 유지한다.
- 새 테이블·열·인덱스는 필요하지 않으며 Flyway migration도 추가하지 않는다.

## 안전 경계

- 설치기는 소스만 변경하며 DB·컨테이너·서비스·예약 작업을 변경하지 않는다.
- 기존 시연 데이터와 운영 데이터는 수정·삭제하지 않는다.
- 외부 연쇄 쓰기의 업무 순서와 API 계약은 바꾸지 않는다.

## 소스 검증

저장소 루트에서 실행한다.

```bat
py -3 -m py_compile scripts\visionflow_system_traceability_audit.py scripts\tests\test_visionflow_system_traceability_demo_scenario_lifecycle.py
py -3 -m json.tool scripts\visionflow_ci_api_audit_policy.json >nul
py -3 -m unittest scripts.tests.test_visionflow_system_traceability_demo_scenario_lifecycle scripts.tests.test_visionflow_system_traceability_geofence_event_lifecycle scripts.tests.test_visionflow_system_traceability_ai_alert_lifecycle scripts.tests.test_visionflow_system_traceability_incident_lifecycle -v
02_backend\visionflow-api\gradlew.bat -p 02_backend\visionflow-api test --tests "com.visionflow.api.demo.service.DemoScenarioServiceConcurrencyTests"
```

## 런타임 검증

소스 검증 후 Backend만 재빌드한다.

```bat
docker compose --env-file .env.docker -f compose.yaml -f compose.gpu.yaml -f compose.mobile-https.yaml config --quiet
docker compose --env-file .env.docker -f compose.yaml -f compose.gpu.yaml -f compose.mobile-https.yaml up -d --build --force-recreate --no-deps backend-api
```

Backend가 `running/healthy`가 되면 시스템 추적성, API 감사 CI, 데이터 정합성, 수용 시험, 운영 가드를 실행한다. 다음 항목을 포함해 모두 정상이어야 커밋한다.

```text
[PASS] demo-scenario-lifecycle-concurrency-policy
VisionFlow API audit CI gate: PASS
VisionFlow data integrity audit: DATA_INTEGRITY_HEALTHY
VisionFlow acceptance test PASSED.
VisionFlow AI Operational Guard: HEALTHY
```
