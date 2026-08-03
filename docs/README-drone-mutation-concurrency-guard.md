# VisionFlow Drone 변경 동시성 방어

기준 커밋: `5d74c4f8d0c60bcc7b1b4b37f4b7091d2373ac44`

같은 Drone의 기본정보·운영 상태·삭제·텔레메트리 요청이 겹칠 때 오래된
트랜잭션이 앞선 변경을 덮어쓰지 않도록 모든 Drone 변경 경로를 직렬화한다.

## 방어 범위

- `updateDrone`, `updateStatus`, `deleteDrone`, `updateTelemetry`는 대상
  `drone` 행을 `PESSIMISTIC_WRITE`로 잠근 뒤 변경한다.
- Flight Session 시작과 품질·비행 게이트 Incident 자동화가 이미 사용하는
  `DroneRepository.findByIdForUpdate`를 공통 잠금 경계로 재사용한다.
- 텔레메트리는 잠금 획득 뒤 Flight Session 소유권을 검증하고 현재 상태 갱신,
  이력 저장, Geofence 평가를 기존 트랜잭션에서 수행한다.
- Drone 단건·목록 조회는 기존 비잠금 읽기를 유지한다.
- V2의 Drone 코드·시리얼 번호 UNIQUE 제약은 생성·변경 충돌의 최종 방어선으로
  유지한다.
- API operation 수와 응답 계약은 바뀌지 않는다.

## 안전 경계

- 설치기는 소스만 변경하며 DB·컨테이너·서비스·예약 작업을 변경하지 않는다.
- 새 Flyway migration과 운영 데이터 변경은 없다.
- 텔레메트리 이력·Geofence 평가·실시간 발행 순서는 변경하지 않는다.

## 소스 검증

저장소 루트에서 실행한다.

```bat
py -3 -m py_compile scripts\visionflow_system_traceability_audit.py scripts\tests\test_visionflow_system_traceability_drone_mutation.py
py -3 -m json.tool scripts\visionflow_ci_api_audit_policy.json >nul
py -3 -m unittest scripts.tests.test_visionflow_system_traceability_drone_mutation scripts.tests.test_visionflow_system_traceability_flight_quality_assessment scripts.tests.test_visionflow_system_traceability_demo_scenario_lifecycle scripts.tests.test_visionflow_system_traceability_geofence_event_lifecycle scripts.tests.test_visionflow_system_traceability_ai_alert_lifecycle scripts.tests.test_visionflow_system_traceability_incident_lifecycle scripts.tests.test_visionflow_system_traceability_flight_session_lifecycle -v
02_backend\visionflow-api\gradlew.bat -p 02_backend\visionflow-api test --tests "com.visionflow.api.drone.service.DroneServiceConcurrencyTests" --tests "com.visionflow.api.drone.service.DroneServiceTelemetryCorrelationTests" --tests "com.visionflow.api.drone.service.DroneServiceDeletionTests"
scripts\run-visionflow-system-traceability-audit.bat
scripts\run-visionflow-api-audit-ci.bat
```

정상 결과에는 다음 항목이 포함된다.

```text
[PASS] drone-mutation-concurrency-policy
VisionFlow API audit CI gate: PASS
```

## 런타임 적용

소스 검증이 모두 통과한 뒤 Backend만 재빌드한다.

```bat
docker compose --env-file .env.docker -f compose.yaml -f compose.gpu.yaml -f compose.mobile-https.yaml config --quiet
docker compose --env-file .env.docker -f compose.yaml -f compose.gpu.yaml -f compose.mobile-https.yaml up -d --build --force-recreate --no-deps backend-api
```

Backend가 `running/healthy`가 되면 최종 회귀 검증을 실행한다.

```bat
scripts\run-visionflow-data-integrity-audit.bat
scripts\run-visionflow-acceptance.bat -FrontendUrl https://localhost:3443 -RunRbac -RunSession
scripts\run-visionflow-ai-operational-guard.bat --root "C:\VisionFlow-Drone" --skip-inference
```

모든 결과가 정상일 때만 변경 파일을 선별해 커밋한다.
