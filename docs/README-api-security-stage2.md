# VisionFlow API 보안 Stage 2

> 기준 커밋: `083e386a4b9e12b1da4893695763ec254730e22d`<br>
> 범위: AI API 내부 서비스 인증 8건과 same-origin MJPEG 프록시<br>
> 제외: Backend 잔여 민감 공개 조회 22건

## 목표

AI 서버의 `/health`만 공개 상태로 유지하고 다음 8개 operation을 내부 서비스 키로 보호합니다.

- `GET /api/streams/status`
- `GET /api/metrics/status`
- `POST /api/metrics/reset`
- `GET /api/models/status`
- `GET /api/streams/latest.jpg`
- `GET /api/streams/annotated.mjpeg`
- `GET /api/ingest/status`
- `POST /api/ingest/frame`

브라우저는 내부 키를 알지 못합니다. Next.js 서버 Route Handler가 `X-VisionFlow-AI-Key`를 AI 서버에만 전달합니다. MJPEG 영상도 `/api/ai/stream/annotated`를 통해 같은 출처로 중계하므로 HTTPS 스마트폰에서 `localhost:8000`이나 mixed-content 주소를 사용하지 않습니다.

## 키 준비

내부 키는 운영자 로그인 키와 다른 서비스 간 비밀입니다. 사용자가 로그인 화면에 입력하거나 스마트폰으로 복사하지 않습니다.

먼저 상태를 확인합니다.

```bat
scripts\run-visionflow-ai-internal-key.bat plan
```

키가 없거나 placeholder이면 다음 명령으로 48자 키를 생성합니다.

```bat
scripts\run-visionflow-ai-internal-key.bat ensure --apply --confirm ENSURE_VISIONFLOW_AI_INTERNAL_KEY
```

도구는 `.env.docker`를 원자적으로 갱신하고 기존 파일을 `artifacts\config-backups\ai-internal-key-*`에 백업합니다. 키 값은 화면이나 operation report에 출력하지 않습니다. 유효한 기존 키가 있으면 `ensure`는 교체하지 않습니다.

의도적으로 키를 교체할 때만 다음 명령을 사용합니다.

```bat
scripts\run-visionflow-ai-internal-key.bat rotate --apply --confirm ROTATE_VISIONFLOW_AI_INTERNAL_KEY
```

## 적용

키를 준비한 뒤 AI와 Frontend를 함께 다시 빌드·생성합니다.

```bat
docker compose --env-file .env.docker -f compose.yaml -f compose.gpu.yaml -f compose.mobile-https.yaml config --quiet
docker compose --env-file .env.docker -f compose.yaml -f compose.gpu.yaml -f compose.mobile-https.yaml up -d --build --force-recreate --no-deps ai-server frontend-web
```

두 컨테이너가 `running / healthy`가 될 때까지 기다립니다.

```bat
docker inspect visionflow-ai visionflow-frontend --format "{{.Name}}: {{.State.Status}} / {{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}"
```

## 검증

```bat
scripts\run-visionflow-acceptance.bat -FrontendUrl https://localhost:3443 -RunRbac -RunSession
scripts\run-visionflow-api-contract-audit.bat
scripts\run-visionflow-api-security-audit.bat
```

예상 결과는 다음과 같습니다.

- API operation 수: Backend 70, Frontend 71, AI 9
- AI 공개 health: HTTP 200
- AI 민감 API의 키 누락·오류: HTTP 401
- 올바른 내부 키를 사용하는 Next.js AI proxy: HTTP 200
- API 보안 감사 `ai-auth-exposure`: PASS, 공개 민감 AI API 0건
- Backend 민감 GET은 인증으로 보호되며 승인된 LOW 공개 예외 1건만 유지

## 롤백

코드를 기준 커밋 상태로 되돌린 뒤, 키를 새로 만들었다면 백업된 `.env.docker`를 수동 복원하고 AI·Frontend를 다시 빌드합니다. 개인키나 AI 내부 키를 Git에 추가하지 마십시오.
