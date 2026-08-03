# VisionFlow 감사 로그 보존 정리 동시성 방어

기준 커밋: `e0c1c1699c3f92914ea7948b52097792e573f6e2`

관리자 수동 정리와 예약 정리가 겹칠 때 같은 오래된 감사 로그 배치를 동시에
선택·삭제하거나 각 실행의 삭제 건수를 중복 집계하지 않도록 정리 경로를
직렬화한다.

## 방어 범위

- `AuditRetentionService.cleanup`은 오래된 `audit_log` 행을 발생 시각·ID 순서로
  조회하면서 `PESSIMISTIC_WRITE` 잠금을 획득한다.
- 잠긴 대상에서 ID를 추출한 뒤 같은 트랜잭션에서 배치 삭제·flush·잔여 건수
  조회를 순서대로 수행한다.
- 수동 API와 UTC 예약 작업은 같은 잠금 정리 경로를 사용한다.
- 보존 상태 조회는 기존 비잠금 개수 조회를 유지한다.
- API operation 수와 응답 계약은 바뀌지 않는다.

## 안전 경계

- 설치기는 소스만 변경하며 DB·컨테이너·서비스·예약 작업을 변경하지 않는다.
- 새 Flyway migration과 운영 데이터 변경은 없다.
- 보존 정책 활성화, CSV 백업 확인, 보존 일수, 배치 크기, cron, 수동 확인
  게이트는 변경하지 않는다.
- 실제 정리는 기존처럼 활성화와 백업 확인 조건을 모두 충족해야 실행된다.

## 소스 검증

저장소 루트에서 실행한다.

```bat
py -3 -m py_compile scripts\visionflow_system_traceability_audit.py scripts\tests\test_visionflow_system_traceability_audit_retention_concurrency.py
py -3 -m json.tool scripts\visionflow_ci_api_audit_policy.json >nul
py -3 -m unittest scripts.tests.test_visionflow_system_traceability_audit_retention_concurrency scripts.tests.test_visionflow_system_traceability_ai_snapshot_concurrency scripts.tests.test_visionflow_system_traceability_drone_mutation scripts.tests.test_visionflow_system_traceability_flight_quality_assessment scripts.tests.test_visionflow_system_traceability_demo_scenario_lifecycle scripts.tests.test_visionflow_system_traceability_geofence_event_lifecycle scripts.tests.test_visionflow_system_traceability_ai_alert_lifecycle scripts.tests.test_visionflow_system_traceability_incident_lifecycle scripts.tests.test_visionflow_system_traceability_flight_session_lifecycle -v
02_backend\visionflow-api\gradlew.bat -p 02_backend\visionflow-api test --tests "com.visionflow.api.audit.service.AuditRetentionServiceConcurrencyTests"
scripts\run-visionflow-system-traceability-audit.bat
scripts\run-visionflow-api-audit-ci.bat
```

정상 결과에는 다음 항목이 포함된다.

```text
[PASS] audit-retention-concurrency-policy
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
