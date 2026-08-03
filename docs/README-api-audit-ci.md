# VisionFlow API·시스템 추적성 감사 CI 게이트

기준 커밋: `4d4b8693cda6ecb4ba2d322ed617750525a17580`

이 게이트는 Backend Controller, Frontend Route, AI FastAPI operation, 보안 규칙, Flyway 테이블, JPA Entity·Repository, 물리 FK와 기능 흐름의 드리프트를 GitHub Actions에서 읽기 전용으로 검사합니다. 컨테이너·DB·서비스를 실행하거나 변경하지 않으며 비밀값과 `.env.docker`를 읽지 않습니다.

## 판정 정책

- operation 기준: Backend 70, Frontend 71, AI 9
- 계약 감사: `API_CONTRACT_HEALTHY`만 허용; 허용 Advisory 0건
- 계약 감사의 Advisory, `unexpected` 항목, missing target, operation 수 변경: 실패
- 보안 감사: `API_SECURITY_HEALTHY`만 허용
- 런타임 보안 검사는 CI에서 `SKIPPED`가 정상이며 정적 보안 검사는 모두 `PASS`여야 함
- 시스템 추적성 감사: `SYSTEM_TRACEABILITY_HEALTHY`만 허용
- 데이터 기준: Table 16, Entity 15, Repository 15, 물리 FK 12, 기능 흐름 13, 소프트 상관관계 4
- 추적성 감사의 16개 검사키가 정확히 존재하고 모두 `PASS`여야 함
- Drone 변경 검사는 기본정보·상태·삭제·텔레메트리 쓰기의 행 잠금과 비잠금 읽기 경계를 함께 확인
- 비행 세션 생명주기 검사는 Drone·Session 행 잠금, ACTIVE 세션 DB UNIQUE 제약, 읽기 전용 중복 탐지 규칙을 함께 확인
- 비행 품질 평가 검사는 수동·종료 이벤트·백필 재계산의 Session 행 잠금, V16 평가 UNIQUE 제약, 비잠금 읽기 경계를 함께 확인
- AI OpenAPI inventory는 `streaming.py`의 정적 FastAPI decorator에서 매번 생성하므로 실행 중인 AI 서버가 필요하지 않음

허용 정책은 `scripts/visionflow_ci_api_audit_policy.json`에 있습니다. 정책이나 기준선을 바꾸는 작업은 API 변경 검토와 함께 별도 커밋으로 진행하세요.

## GitHub Actions

`.github/workflows/api-audit.yml`은 다음 경우 실행됩니다.

- `main`의 API·보안·Flyway·추적성·데이터 정합성 정책 관련 소스가 변경된 push
- 같은 경로를 변경하는 pull request
- 수동 `workflow_dispatch`

보고서는 성공·실패와 관계없이 `visionflow-api-and-traceability-audit-reports` artifact로 14일간 보관됩니다.

## Windows 로컬 등가 검사

저장소 루트에서 실행합니다.

```bat
scripts\run-visionflow-api-audit-ci.bat
```

결과는 `artifacts\api-audit-ci\local`의 `contract`, `security`, `traceability`에 생성됩니다. 이 명령은 소스와 기준선을 읽고 보고서만 기록합니다.

## 실패 시 확인 순서

1. `ai-openapi.json`에서 AI operation 추가·삭제 여부 확인
2. 계약 보고서의 `baseline-counts`, `frontend-targets`, `backend-coverage`, `ai-coverage` 확인
3. 보안 보고서의 `BLOCKED` 또는 `ADVISORY` check 확인
4. 추적성 보고서의 삭제·Drone 변경·세션 상관관계·세션 생명주기·비행 품질 평가 동시성 정책 검사와 `baseline-counts`, `migration-tables`, `entity-repository-mapping`, `foreign-key-contract`, `flow-operation-coverage`, `flow-table-coverage` 확인
5. 의도된 변경이면 기존 계약·보안·추적성 기준선과 CI 정책을 함께 검토
6. 의도하지 않은 변경이면 Route, proxy target, 인증 전파, Spring Security, Flyway, Entity·Repository 또는 기능 흐름 기준을 수정

운영 키, AI 내부 키, 세션 쿠키는 보고서와 Actions 로그에 포함되지 않습니다.
