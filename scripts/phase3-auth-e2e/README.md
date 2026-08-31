# Phase 3 Auth / RBAC E2E Gate

실기 DJI 또는 AWS 없이 운영자 개인 계정 인증과 RBAC 경계를 실행 중인
Backend/Frontend에 대해 검증합니다.

검증 항목:

- Backend health
- `/operator-login`, `/operator-password-change` route
- 미인증 및 잘못된 session token 차단
- VIEWER / OPERATOR / ADMIN 개인 계정 password login
- DB Role 자동 적용
- `passwordChangeRequired=false`
- 세 역할의 drone read
- ADMIN 전용 session-list 경계
- VIEWER vs OPERATOR/ADMIN mutation authorization 경계
- logout 후 기존 session token 거부

Mutation 경계는 `droneId=0`을 사용해 OPERATOR/ADMIN도 controller validation에서
안전하게 4xx로 끝나도록 하며 실제 Flight Session을 만들지 않습니다.

## 비밀번호

기본 실행은 Python `getpass`를 사용하므로 입력값이 화면에 표시되지 않습니다.
비밀번호와 session token은 Evidence에 저장되지 않습니다.

실행:

```bat
scripts\phase3-auth-e2e\run-phase3-auth-e2e.bat
```

비대화형 CI에서만 다음 프로세스 환경변수를 사용할 수 있습니다.

```text
VISIONFLOW_E2E_VIEWER_PASSWORD
VISIONFLOW_E2E_OPERATOR_PASSWORD
VISIONFLOW_E2E_ADMIN_PASSWORD
```

이 값들은 `.env`나 Git 파일에 기록하지 마세요.

Evidence:

```text
artifacts/phase3-auth-e2e/latest-summary.json
```
