# VisionFlow API 보안 1단계

## 목적

API 보안 감사에서 HIGH로 분류된 Backend 민감 조회 9건을 운영자 역할로 보호합니다. 장치 수집 API와 기존 공개 드론·대시보드 조회 범위는 이번 단계에서 변경하지 않습니다.

## 보호 범위

| API 그룹 | 작업 수 | 허용 역할 |
| --- | ---: | --- |
| 감사 로그·보존 설정 조회 | 2 | ADMIN |
| AI 경보 조회 | 2 | VIEWER, OPERATOR, ADMIN |
| AI 이벤트·스냅숏 조회 | 2 | VIEWER, OPERATOR, ADMIN |
| Incident 조회·보고서 | 3 | VIEWER, OPERATOR, ADMIN |

감사 로그 CSV 내보내기는 기존 정책대로 인증된 세 역할 모두 사용할 수 있습니다. 감사 로그 정리와 세션 관리 같은 관리자 작업도 기존 ADMIN 경계를 유지합니다.

## Frontend 변경

AI 이벤트 목록과 이벤트 스냅숏 Proxy가 브라우저의 HttpOnly 운영자 세션을 Backend 요청에 전달합니다. 키나 세션 값은 Browser JavaScript 응답에 노출하지 않습니다.

## 기대 결과

- `backend-critical-protections`: `PASS`
- `frontend-auth-propagation`: `PASS`
- Backend 민감 공개 조회: `31`건에서 `22`건으로 감소
- 남은 Backend HIGH 공개 조회: `0`건
- AI 무인증 API 8건은 2단계 내부 서비스 키 작업에서 처리

## 런타임 검증

```bat
scripts\run-visionflow-api-security-audit.bat
scripts\run-visionflow-acceptance.bat -FrontendUrl https://localhost:3443 -RunRbac -RunSession
```

RBAC 인수 테스트는 무인증 민감 조회 거부, VIEWER·OPERATOR 민감 조회 허용, 감사 로그의 ADMIN 전용 경계를 추가로 확인합니다.
