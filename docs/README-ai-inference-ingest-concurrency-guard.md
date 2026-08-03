# VisionFlow AI 추론 이벤트 수집 동시성 방어

기준 커밋: `66a2bd4cc11e1c3ef9cb9910f0b1cfeaf4bf5872`

동일한 AI 프레임 이벤트 생성 요청이 겹칠 때 두 요청이 모두 멱등 조회를 통과한
뒤 같은 이벤트를 삽입해 한 요청이 DB UNIQUE 예외로 끝나거나 탐지·경보 연쇄
쓰기를 중복 실행하지 않도록 수집 경로를 직렬화한다.

## 방어 범위

- AI 이벤트 생성은 대상 Flight Session을 `PESSIMISTIC_WRITE`로 잠근다.
- 세션 잠금 획득 뒤 `(source_id, session_id, frame_index)` 멱등 조회를 수행하고,
  기존 이벤트가 없을 때만 이벤트·탐지·경보를 생성한다.
- 동일 프레임의 후속 요청은 앞선 트랜잭션 완료 뒤 기존 이벤트를 반환한다.
- V5의 `uk_ai_event_frame` UNIQUE 제약은 중복 이벤트 생성의 최종 방어선으로
  유지한다.
- 이벤트 목록·스냅샷 조회는 기존 비잠금 읽기를 유지한다.
- API operation 수와 요청·응답 계약은 바뀌지 않는다.

## 안전 경계

- 설치기는 소스만 변경하며 DB·컨테이너·서비스·예약 작업을 변경하지 않는다.
- 새 Flyway migration과 운영 데이터 변경은 없다.
- 세션 소유권 오류, AI 이벤트 검증, 탐지 저장, 경보 생성, 실시간 발행 순서는
  변경하지 않는다.
- 스마트폰 실센서와 DJI 실기체 연동 범위는 변경하지 않는다.

## 소스 검증

저장소 루트에서 실행한다.

```bat
py -3 -m py_compile scripts\visionflow_system_traceability_audit.py scripts\tests\test_visionflow_system_traceability_ai_inference_ingest_concurrency.py
py -3 -m json.tool scripts\visionflow_ci_api_audit_policy.json >nul
py -3 -m unittest scripts.tests.test_visionflow_system_traceability_ai_inference_ingest_concurrency scripts.tests.test_visionflow_system_traceability_session_correlation scripts.tests.test_visionflow_system_traceability_audit_retention_concurrency scripts.tests.test_visionflow_system_traceability_ai_snapshot_concurrency scripts.tests.test_visionflow_system_traceability_drone_mutation scripts.tests.test_visionflow_system_traceability_flight_quality_assessment scripts.tests.test_visionflow_system_traceability_demo_scenario_lifecycle scripts.tests.test_visionflow_system_traceability_geofence_event_lifecycle scripts.tests.test_visionflow_system_traceability_ai_alert_lifecycle scripts.tests.test_visionflow_system_traceability_incident_lifecycle scripts.tests.test_visionflow_system_traceability_flight_session_lifecycle -v
02_backend\visionflow-api\gradlew.bat -p 02_backend\visionflow-api test --tests "com.visionflow.api.ai.service.AiInferenceEventIngestConcurrencyTests" --tests "com.visionflow.api.ai.service.AiInferenceEventServiceCorrelationTests"
scripts\run-visionflow-system-traceability-audit.bat
scripts\run-visionflow-api-audit-ci.bat
```

정상 결과에는 다음 항목이 포함된다.

```text
[PASS] ai-inference-ingest-concurrency-policy
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
