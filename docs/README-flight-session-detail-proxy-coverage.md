# VisionFlow Flight Session 상세 Proxy 계약 커버리지

> 소스 기준: `f670b101682a1129e8e258b553300f9ca0dfd0b6`
> 범위: 비행 세션 상세 조회의 Frontend same-origin proxy와 API 감사 기준선
> 제외: Backend·DB·Flyway·AI·스케줄 작업 변경

## 목표

Backend `GET /api/drones/{droneId}/flight-sessions/{sessionId}`를 Next.js의 동일한 브라우저 경로로 중계합니다. 추가된 GET handler는 드론·세션 ID를 검증하고, HttpOnly 운영자 세션을 Backend 인증으로 변환하며, `no-store`와 10초 timeout을 적용합니다.

이 변경으로 최종 `backend-coverage` Advisory를 제거하고 계약 감사의 정상 예상 상태를 `API_CONTRACT_HEALTHY`로 올립니다.

## 정책 경계

- operation 기준: Backend 70, Frontend 71, AI 9
- Backend health, AI 내부 입력, 운영 점검 API만 direct-only 예외로 유지
- 허용된 계약 Advisory: 0건
- 보안 기준: 세션 상세 proxy는 `withBackendOperatorAuth` 필수
- 변경 요청이 아닌 GET이므로 same-origin mutation guard는 적용 대상이 아님

## 검증

저장소 루트에서 다음을 순서대로 실행합니다.

```bat
py -3 -m py_compile scripts\visionflow_ci_api_audit_gate.py scripts\visionflow_system_traceability_audit.py scripts\tests\test_visionflow_flight_session_detail_proxy_coverage.py
py -3 -m json.tool scripts\visionflow_api_contract_baseline.json >nul
py -3 -m json.tool scripts\visionflow_api_security_baseline.json >nul
py -3 -m json.tool scripts\visionflow_system_traceability_baseline.json >nul
py -3 -m json.tool scripts\visionflow_ci_api_audit_policy.json >nul
py -3 -m unittest scripts.tests.test_visionflow_flight_session_detail_proxy_coverage -v
npm --prefix 01_frontend\visionflow-web run lint
scripts\run-visionflow-api-audit-ci.bat
```

예상 결과:

- `API_CONTRACT_HEALTHY`
- `API_SECURITY_HEALTHY`
- `SYSTEM_TRACEABILITY_HEALTHY`
- `VisionFlow API audit CI gate: PASS`

## 반영과 확인

Frontend만 다시 빌드합니다.

```bat
docker compose --env-file .env.docker -f compose.yaml -f compose.gpu.yaml -f compose.mobile-https.yaml config --quiet
docker compose --env-file .env.docker -f compose.yaml -f compose.gpu.yaml -f compose.mobile-https.yaml up -d --build --force-recreate --no-deps frontend-web
docker inspect visionflow-frontend --format "{{.State.Status}}/{{.State.Health.Status}}"
scripts\run-visionflow-acceptance.bat -FrontendUrl https://localhost:3443 -RunRbac -RunSession
```

새 GET는 조회 전용이며 DB, Backend 서비스, AI 서비스, 스케줄 작업을 변경하지 않습니다.
