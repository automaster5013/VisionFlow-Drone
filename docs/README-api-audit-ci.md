# VisionFlow API 감사 CI 게이트

기준 커밋: `1bfc957a4ad4c593838f459a93a14c25f407445b`

이 게이트는 Backend Controller, Frontend Route, AI FastAPI operation과 보안 규칙의 드리프트를 GitHub Actions에서 읽기 전용으로 검사합니다. 컨테이너·DB·서비스를 실행하거나 변경하지 않으며 비밀값과 `.env.docker`를 읽지 않습니다.

## 판정 정책

- operation 기준: Backend 70, Frontend 70, AI 9
- 계약 감사: 기존 `backend-coverage` 검토 항목 1건만 허용
- 계약 감사의 새 Advisory, `unexpected` 항목, missing target, operation 수 변경: 실패
- 보안 감사: `API_SECURITY_HEALTHY`만 허용
- 런타임 보안 검사는 CI에서 `SKIPPED`가 정상이며 정적 보안 검사는 모두 `PASS`여야 함
- AI OpenAPI inventory는 `streaming.py`의 정적 FastAPI decorator에서 매번 생성하므로 실행 중인 AI 서버가 필요하지 않음

허용 정책은 `scripts/visionflow_ci_api_audit_policy.json`에 있습니다. 정책이나 기준선을 바꾸는 작업은 API 변경 검토와 함께 별도 커밋으로 진행하세요.

## GitHub Actions

`.github/workflows/api-audit.yml`은 다음 경우 실행됩니다.

- `main`의 API·보안 관련 소스가 변경된 push
- 같은 경로를 변경하는 pull request
- 수동 `workflow_dispatch`

보고서는 성공·실패와 관계없이 `visionflow-api-audit-reports` artifact로 14일간 보관됩니다.

## Windows 로컬 등가 검사

저장소 루트에서 실행합니다.

```bat
scripts\run-visionflow-api-audit-ci.bat
```

결과는 `artifacts\api-audit-ci\local`에 생성됩니다. 이 명령은 소스와 기준선을 읽고 보고서만 기록합니다.

## 실패 시 확인 순서

1. `ai-openapi.json`에서 AI operation 추가·삭제 여부 확인
2. 계약 보고서의 `baseline-counts`, `frontend-targets`, `backend-coverage`, `ai-coverage` 확인
3. 보안 보고서의 `BLOCKED` 또는 `ADVISORY` check 확인
4. 의도된 변경이면 기존 계약·보안 기준선과 CI 정책을 함께 검토
5. 의도하지 않은 변경이면 소스의 Route, proxy target, 인증 전파, Spring Security 규칙을 수정

운영 키, AI 내부 키, 세션 쿠키는 보고서와 Actions 로그에 포함되지 않습니다.
