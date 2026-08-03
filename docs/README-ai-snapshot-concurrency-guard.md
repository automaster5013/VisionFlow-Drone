# VisionFlow AI 스냅샷 첨부 동시성 방어

기준 커밋: `27a37c7b8482e4e634e13c3bf9cfd5d186dcd282`

같은 AI 추론 이벤트에 여러 스냅샷 첨부 요청이 겹칠 때 파일 저장과 이벤트
메타데이터 변경이 서로의 영속 상태를 비동기적으로 덮어쓰지 않도록 첨부 경로를
직렬화한다.

## 방어 범위

- `attachSnapshot`은 대상 `ai_inference_event` 행을
  `PESSIMISTIC_WRITE`로 잠근 뒤 파일 저장과 메타데이터 변경을 수행한다.
- 잠금은 파일 저장 전에 획득하므로 같은 이벤트의 첨부 쓰기 전체가 한 순서로
  실행된다.
- 이벤트 목록·스냅샷 다운로드는 기존 비잠금 읽기를 유지한다.
- V5의 `(source_id, session_id, frame_index)` UNIQUE 제약은 AI 프레임 중복
  생성의 최종 방어선으로 유지한다.
- API operation 수와 응답 계약은 바뀌지 않는다.

## 안전 경계

- 설치기는 소스만 변경하며 DB·컨테이너·서비스·예약 작업을 변경하지 않는다.
- 새 Flyway migration과 운영 데이터 변경은 없다.
- 스냅샷 JPEG 검증·파일명·저장 위치·실시간 이벤트 발행 순서는 변경하지 않는다.

## 소스 검증

저장소 루트에서 실행한다.

```bat
py -3 -m py_compile scripts\visionflow_system_traceability_audit.py scripts\tests\test_visionflow_system_traceability_ai_snapshot_concurrency.py
py -3 -m json.tool scripts\visionflow_ci_api_audit_policy.json >nul
py -3 -m unittest scripts.tests.test_visionflow_system_traceability_ai_snapshot_concurrency scripts.tests.test_visionflow_system_traceability_drone_mutation scripts.tests.test_visionflow_system_traceability_flight_quality_assessment scripts.tests.test_visionflow_system_traceability_demo_scenario_lifecycle scripts.tests.test_visionflow_system_traceability_geofence_event_lifecycle scripts.tests.test_visionflow_system_traceability_ai_alert_lifecycle scripts.tests.test_visionflow_system_traceability_incident_lifecycle scripts.tests.test_visionflow_system_traceability_flight_session_lifecycle -v
02_backend\visionflow-api\gradlew.bat -p 02_backend\visionflow-api test --tests "com.visionflow.api.ai.service.AiInferenceEventServiceConcurrencyTests" --tests "com.visionflow.api.ai.service.AiInferenceEventServiceCorrelationTests"
scripts\run-visionflow-system-traceability-audit.bat
scripts\run-visionflow-api-audit-ci.bat
```

정상 결과에는 다음 항목이 포함된다.

```text
[PASS] ai-snapshot-concurrency-policy
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
