# VisionFlow 비행 품질 평가 재계산 동시성 방어

기준 커밋: `d1305af9acca0300fd8e033dbb7cebb9bf312f91`

수동 재계산, 비행 세션 종료 이벤트, 강제 백필이 같은 세션의 현재 규칙 버전
평가를 동시에 생성하거나 갱신해 결과를 덮어쓰지 않도록 공통 재계산 경로를
직렬화한다.

## 방어 범위

- `FlightQualityAssessmentService.recalculate`는 대상 `flight_session` 행을
  `PESSIMISTIC_WRITE`로 잠근 뒤 표본 조회와 평가 저장을 수행한다.
- 종료 이벤트 자동화와 백필은 모두 공통 `recalculate`를 사용하므로 같은 잠금
  순서를 따른다.
- 같은 세션의 후속 재계산은 앞선 트랜잭션 완료 뒤 최신 평가를 다시 조회해
  갱신한다.
- V16의 `uk_flight_quality_session_rule` UNIQUE 제약은
  `(session_id, rule_version)` 중복 생성의 최종 방어선으로 유지한다.
- 평가 상세·이력 조회는 기존 비잠금 읽기를 유지한다.
- API operation 수와 응답 계약은 바뀌지 않는다.

## 안전 경계

- 설치기는 소스만 변경하며 DB·컨테이너·서비스·예약 작업을 변경하지 않는다.
- 새 Flyway migration과 운영 데이터 변경은 없다.
- 기존 V16 제약을 변경하거나 재적용하지 않는다.

## 소스 검증

저장소 루트에서 실행한다.

```bat
py -3 -m py_compile scripts\visionflow_system_traceability_audit.py scripts\tests\test_visionflow_system_traceability_flight_quality_assessment.py
py -3 -m json.tool scripts\visionflow_ci_api_audit_policy.json >nul
py -3 -m unittest scripts.tests.test_visionflow_system_traceability_flight_quality_assessment scripts.tests.test_visionflow_system_traceability_demo_scenario_lifecycle scripts.tests.test_visionflow_system_traceability_geofence_event_lifecycle scripts.tests.test_visionflow_system_traceability_ai_alert_lifecycle scripts.tests.test_visionflow_system_traceability_incident_lifecycle scripts.tests.test_visionflow_system_traceability_flight_session_lifecycle -v
02_backend\visionflow-api\gradlew.bat -p 02_backend\visionflow-api test --tests "com.visionflow.api.flight.quality.service.FlightQualityAssessmentServiceConcurrencyTests" --tests "com.visionflow.api.flight.quality.service.FlightQualityAssessmentAutomationServiceTests" --tests "com.visionflow.api.flight.quality.service.FlightQualityBackfillServiceTests"
scripts\run-visionflow-system-traceability-audit.bat
scripts\run-visionflow-api-audit-ci.bat
```

정상 결과에는 다음 항목이 포함된다.

```text
[PASS] flight-quality-assessment-concurrency-policy
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
