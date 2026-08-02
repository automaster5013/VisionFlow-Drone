# VisionFlow API 보안 Stage 3

## 목적

Backend의 남은 MEDIUM 민감 공개 조회를 운영자 역할 기반 인증으로 전환합니다. API 경로와 응답 계약은 변경하지 않으며, Frontend Proxy가 기존 HttpOnly 운영자 세션을 Backend 인증으로 전달합니다.

## 보호 범위

- Dashboard 운영 요약 1건
- 드론·텔레메트리·비행 세션·비행 품질 조회 9건
- Geofence 및 발생 이벤트 조회 3건
- Maintenance 작업·SLA·비행 허가 조회 8건

위 21개 GET API는 `VIEWER`, `OPERATOR`, `ADMIN` 역할에 허용됩니다. 인증이 없으면 `401 OPERATOR_AUTHENTICATION_REQUIRED`를 반환합니다.

## 승인된 공개 예외

`GET /api/demo/scenarios/{scenarioId}`는 발표 시연 진행 상태를 인증 전 화면에서도 조회할 수 있도록 LOW 공개 예외로 유지합니다. 보안 감사 기준선에 이유와 범위를 명시하여 다른 공개 조회와 구분합니다.

## 보안 비활성 모드

`VISIONFLOW_OPERATOR_SECURITY_ENABLED=false`일 때 `/api/flight-quality/**`도 다른 업무 API와 동일하게 공개됩니다. 이 변경은 비활성 모드의 의미를 일관되게 만들며, 기본 운영 권장값인 `true`에는 영향을 주지 않습니다.

## 검증

```bat
docker compose --env-file .env.docker -f compose.yaml -f compose.gpu.yaml -f compose.mobile-https.yaml up -d --build --force-recreate --no-deps backend-api frontend-web

scripts\run-visionflow-acceptance.bat -FrontendUrl https://localhost:3443 -RunRbac -RunSession
scripts\run-visionflow-api-contract-audit.bat
scripts\run-visionflow-api-security-audit.bat
```

보안 감사의 기대 결과는 다음과 같습니다.

- `backend-critical-protections`: PASS
- `backend-sensitive-public-reads`: PASS, 승인된 LOW 공개 예외 1건
- `security-disabled-consistency`: PASS
- `frontend-auth-propagation`: PASS

## 안전 속성

- DB 데이터 변경 없음
- 운영자 키·AI 내부 키 변경 없음
- `.env.docker` 변경 없음
- 적용 도구는 기존 파일 해시를 확인하고 백업 후 원자적으로 교체
- 서비스 재빌드와 재시작은 사용자가 검증 단계에서 명시적으로 수행
