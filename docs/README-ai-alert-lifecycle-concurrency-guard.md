# VisionFlow AI Alert 수명주기 동시성 방어

기준 커밋: `76ba2aab869c11ef6dfe3dabf87000c2e9d0ee24`

## 목적

동일한 AI 경보에 운영자 확인과 해결 요청이 동시에 도착할 때 오래된 트랜잭션이
앞선 상태·처리자·해결 메모를 덮지 않도록 변경 경로를 직렬화한다.

## 정책

- `acknowledge`와 `resolve`는 `ai_alert` 대상 행에
  `PESSIMISTIC_WRITE` 잠금을 획득한 뒤 변경한다.
- 경보 상세·목록 조회는 기존 비잠금 읽기를 유지한다.
- 경보 변경 뒤 Incident 동기화와 실시간 발행은 기존 트랜잭션 경계를 유지한다.
- 통합 시연의 해결 경로도 공통 `AiAlertService.resolve`를 사용한다.
- 이벤트별 경보 생성은 기존 `uk_ai_alert_event` UNIQUE 제약을 최종 중복 방어로
  유지한다.
- DB migration, 데이터 수정, 컨테이너 및 예약 작업 변경은 없다.

## 소스 검증

```bat
py -3 -m py_compile scripts\visionflow_system_traceability_audit.py scripts\tests\test_visionflow_system_traceability_ai_alert_lifecycle.py
py -3 -m json.tool scripts\visionflow_ci_api_audit_policy.json >nul
py -3 -m unittest scripts.tests.test_visionflow_system_traceability_ai_alert_lifecycle scripts.tests.test_visionflow_system_traceability_incident_lifecycle scripts.tests.test_visionflow_system_traceability_flight_session_lifecycle -v
02_backend\visionflow-api\gradlew.bat -p 02_backend\visionflow-api test --tests "com.visionflow.api.ai.service.AiAlertServiceConcurrencyTests"
scripts\run-visionflow-system-traceability-audit.bat
scripts\run-visionflow-api-audit-ci.bat
```

정상 결과에는 다음 항목이 포함된다.

```text
[PASS] ai-alert-lifecycle-concurrency-policy
VisionFlow API audit CI gate: PASS
```

## 런타임 적용

소스 검증이 모두 통과한 뒤 Backend만 재빌드한다.

```bat
docker compose --env-file .env.docker -f compose.yaml -f compose.gpu.yaml -f compose.mobile-https.yaml config --quiet
docker compose --env-file .env.docker -f compose.yaml -f compose.gpu.yaml -f compose.mobile-https.yaml up -d --build --force-recreate --no-deps backend-api
```

Backend가 `running/healthy`가 되면 데이터 정합성 감사와 인수 테스트를 실행한다.

```bat
scripts\run-visionflow-data-integrity-audit.bat
scripts\run-visionflow-acceptance.bat -FrontendUrl https://localhost:3443 -RunRbac -RunSession
scripts\run-visionflow-ai-operational-guard.bat --root "C:\VisionFlow-Drone" --skip-inference
```
