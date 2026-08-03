# VisionFlow 정비 작업지시 수명주기 동시성 방어

기준 커밋: `cfa8096c2158cb4590f283b2a740309efba021f8`

정비 SLA 예약 실행이 비잠금 후보 조회 직후의 오래된 작업 상태를 사용해 이미
완료된 점검의 Incident를 다시 상향하지 않도록 작업지시 수명주기와 SLA 재평가
경로를 같은 잠금 정책으로 연결한다.

## 방어 범위

- 비행 품질 Incident 기반 작업 동기화는 기존 `incident_id` Work Order 잠금을
  유지한다.
- 점검 시작·완료는 기존 ID 기반 `PESSIMISTIC_WRITE` 잠금을 유지한다.
- SLA 후보 스캔은 Work Order Entity 대신 ID만 비잠금으로 조회한다.
- 각 후보는 불변 `incident_id`를 확인한 뒤 Incident를 먼저 잠그고 Work Order를
  잠가 비행 품질 자동화와 같은 잠금 순서를 사용한다.
- 두 행을 잠근 뒤 작업 상태와 SLA를 다시 평가하고, 여전히 활성·초과 상태일 때만
  Incident 상향·history·실시간 알림·감사 로그를 실행한다.
- V19 `uk_maintenance_work_order_incident` UNIQUE 제약은 Incident별 중복 작업
  생성의 최종 방어선으로 유지한다.
- 작업 목록·상세, SLA 현황과 다른 읽기 API는 기존 비잠금 조회를 유지한다.
- API operation 수와 요청·응답 계약은 바뀌지 않는다.

## 안전 경계

- 설치기는 소스만 변경하며 DB·컨테이너·서비스·예약 작업을 변경하지 않는다.
- 새 Flyway migration과 운영 데이터 변경은 없다.
- 정비 SLA 시간 기준, 작업 상태 전이, Incident 우선순위, 이력·감사·실시간 발행
  규칙은 변경하지 않는다.
- 스마트폰 실센서와 DJI 실기체 연동 범위는 변경하지 않는다.

## 소스 검증

저장소 루트에서 실행한다.

```bat
py -3 -m py_compile scripts\visionflow_system_traceability_audit.py scripts\tests\test_visionflow_system_traceability_maintenance_work_order_lifecycle.py
py -3 -m json.tool scripts\visionflow_ci_api_audit_policy.json >nul
py -3 -m unittest scripts.tests.test_visionflow_system_traceability_maintenance_work_order_lifecycle scripts.tests.test_visionflow_system_traceability_incident_lifecycle scripts.tests.test_visionflow_system_traceability_ai_alert_creation_concurrency scripts.tests.test_visionflow_system_traceability_ai_inference_ingest_concurrency scripts.tests.test_visionflow_system_traceability_session_correlation scripts.tests.test_visionflow_system_traceability_audit_retention_concurrency scripts.tests.test_visionflow_system_traceability_ai_snapshot_concurrency scripts.tests.test_visionflow_system_traceability_drone_mutation scripts.tests.test_visionflow_system_traceability_flight_quality_assessment scripts.tests.test_visionflow_system_traceability_demo_scenario_lifecycle scripts.tests.test_visionflow_system_traceability_geofence_event_lifecycle scripts.tests.test_visionflow_system_traceability_ai_alert_lifecycle scripts.tests.test_visionflow_system_traceability_flight_session_lifecycle -v
02_backend\visionflow-api\gradlew.bat -p 02_backend\visionflow-api test --tests "com.visionflow.api.maintenance.service.MaintenanceSlaWorkOrderConcurrencyTests" --tests "com.visionflow.api.maintenance.service.MaintenanceSlaIncidentEscalationServiceTests" --tests "com.visionflow.api.maintenance.domain.MaintenanceWorkOrderTests"
scripts\run-visionflow-system-traceability-audit.bat
scripts\run-visionflow-api-audit-ci.bat
```

정상 결과에는 다음 항목이 포함된다.

```text
[PASS] maintenance-work-order-lifecycle-concurrency-policy
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
