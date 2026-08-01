# VisionFlow 읽기 전용 API 보안·권한 감사

이 도구는 API가 존재하는지만 확인하는 계약 감사의 다음 단계입니다. 다음 원천을 자동 비교하여 실제 접근 권한 매트릭스를 만듭니다.

- Spring `SecurityConfig`의 RBAC 활성·비활성 분기와 규칙 순서
- Backend Controller 70개 operation
- Frontend Route Handler 69개의 Backend 인증 전달과 same-origin 방어
- AI OpenAPI 9개 operation과 FastAPI 인증 단서
- `compose.yaml`의 비밀값이 아닌 보안 기본값
- 실행 중인 Backend·Frontend 컨테이너의 선택된 비밀 제외 보안 모드

DB 변경, 컨테이너 변경, 서비스 재시작, 자격증명 값 수집을 하지 않습니다. JSON·HTML·Markdown 보고서만 생성합니다.

## 선행 조건

먼저 다음 API 계약 감사 파일이 적용되어 있어야 합니다.

- `scripts/visionflow_api_contract_audit.py`
- `scripts/visionflow_api_contract_baseline.json`

보안 감사기는 계약 감사기의 Controller·Route·OpenAPI 파서를 재사용합니다. 추가 Python 패키지는 필요하지 않습니다.

## 설치 파일

- `scripts/visionflow_api_security_audit.py`
- `scripts/visionflow_api_security_baseline.json`
- `scripts/run-visionflow-api-security-audit.bat`
- `docs/README-api-security-audit.md`

## 일반 실행

저장소 루트에서 실행합니다.

```bat
scripts\run-visionflow-api-security-audit.bat
```

일반 실행은 다음 읽기 전용 작업을 수행합니다.

1. AI `http://localhost:8000/openapi.json` 조회
2. `SecurityConfig`의 첫 번째 일치 규칙으로 Backend operation별 접근 등급 계산
3. Frontend 보호 대상 Proxy의 운영자 인증 전달 여부 계산
4. Frontend 변경 Route의 same-origin 방어 여부 계산
5. AI 인증 미들웨어 단서 및 공개 operation 분류
6. `docker inspect`로 아래 세 값만 조회
   - `VISIONFLOW_OPERATOR_SECURITY_ENABLED`
   - `VISIONFLOW_WEB_AUTH_MODE`
   - `VISIONFLOW_WEB_SECURE_COOKIES`

운영자 KEY, 세션 토큰, DB 비밀번호, 전체 컨테이너 환경은 수집하거나 보고서에 기록하지 않습니다. `docker compose config`도 실행하지 않습니다.

## 오프라인 실행

저장된 AI OpenAPI를 사용하고 컨테이너 검사를 생략할 수 있습니다.

```bat
scripts\run-visionflow-api-security-audit.bat --ai-openapi-file "artifacts\api-inventory-source\ai-openapi.json" --skip-runtime
```

## 보고서

기본 출력 위치는 다음과 같습니다.

```text
artifacts\api-security-audit\audit-<UTC>\
```

생성 파일:

- `visionflow-api-security-audit.json`: 자동화와 상세 증적
- `visionflow-api-security-audit.html`: 브라우저 검토
- `visionflow-api-security-matrix.md`: Backend·Frontend·AI 전체 권한표

## 접근 등급

| 등급 | 의미 |
|---|---|
| `PUBLIC` | 인증 없이 SecurityFilterChain 통과 |
| `AUTHENTICATED` | 인증된 사용자 필요 |
| `ROLES_VIEWER_OPERATOR_ADMIN` | VIEWER 이상 |
| `ROLES_OPERATOR_ADMIN` | OPERATOR 또는 ADMIN |
| `ROLE_ADMIN` | ADMIN 전용 |
| `DENY_ALL` | 명시된 허용 규칙이 없어 거부 |

Backend 표에는 RBAC 활성 모드와 비활성 모드를 모두 표시합니다. Spring 규칙은 선언 순서대로 첫 번째 일치 항목을 적용합니다.

## 현재 기준 결과

기준 커밋은 `71d2cd3`이며 operation 수는 Backend 70·Frontend 69·AI 9입니다. 현재 정상 예상 상태는 `API_SECURITY_ADVISORY`입니다.

확인된 현재 상태:

- RBAC 활성 모드 Backend: `PUBLIC` 38, `ROLE_ADMIN` 5, `ROLES_OPERATOR_ADMIN` 26, `ROLES_VIEWER_OPERATOR_ADMIN` 1
- 민감 운영 데이터를 공개 GET으로 읽는 Backend API: 31개
- 기준선에 없는 공개 변경 API: 0개
- 핵심 ADMIN·인증 보호 규칙 실패: 0개
- RBAC 비활성 모드 누락: `/api/flight-quality/**` 계열 2개
- 보호된 Backend로 인증을 전달하지 않는 Frontend Proxy: 0개
- 명시적 same-origin 보강 대상: `DELETE /api/operator/sessions/{sessionId}` 1개
- 인증 없는 민감 AI API: 8개
- Compose 기본값: RBAC `false`, Frontend `static`, Secure Cookie `false`

31개의 공개 GET은 곧바로 31개의 독립 취약점이라는 뜻은 아닙니다. 현재 `GET /api/** permitAll` 정책이 드론 위치·사고·감사·정비·AI 이벤트 데이터까지 포함한다는 노출 범위입니다. 3차 운영 정책에서 역할별 읽기 권한을 결정할 근거로 사용합니다.

## 상태와 종료 코드

- `API_SECURITY_HEALTHY`: 검토 항목 없음, 종료 코드 0
- `API_SECURITY_ADVISORY`: 알려진 노출·기본값·보강 항목, 기본 종료 코드 0
- `API_SECURITY_BLOCKED`: 핵심 ADMIN 보호 약화, 예상 밖 공개 변경 API, 보호 대상 인증 전달 누락, 예상 밖 same-origin 누락, 종료 코드 1
- 실행 입력 오류: 종료 코드 2

`ADVISORY`도 CI 실패로 처리하려면 다음과 같이 실행합니다.

```bat
scripts\run-visionflow-api-security-audit.bat --strict
```

## 런타임 판정

권장 실행 모드는 다음과 같습니다.

- Backend: `VISIONFLOW_OPERATOR_SECURITY_ENABLED=true`
- Frontend: `VISIONFLOW_WEB_AUTH_MODE=session`
- HTTPS 운영: `VISIONFLOW_WEB_SECURE_COOKIES=true`

Backend RBAC가 꺼져 있거나 Frontend가 `static`이면 런타임 검사는 `BLOCKED`로 판정합니다. Secure Cookie가 `false`이면 HTTP 로컬 검증과의 호환 가능성을 고려해 `ADVISORY`로 판정합니다.

## 기준선 갱신 원칙

API 또는 보안 규칙 변경 후 보고서에 새 `BLOCKED`나 `ADVISORY`가 나타나면 먼저 소스 변경 의도를 확인합니다. 단순히 경고를 제거하기 위해 다음 예외 목록을 추가하면 안 됩니다.

- 공개 변경 API
- 민감 공개 GET 패턴
- same-origin 미적용 변경 Route
- 공개 AI operation

보안 결정과 완료 기준을 문서화한 뒤에만 기준선을 변경합니다.

## 권장 후속 순서

1. 현재 컨테이너가 RBAC `true`·세션 모드인지 지속 확인
2. AI 8000번 포트의 인증 또는 내부 네트워크 경계 설계
3. Backend 공개 GET 31개의 VIEWER·OPERATOR·ADMIN 읽기 정책 결정
4. 관리자 세션 강제 종료 Route의 수동 same-origin 방어 유지·검증
5. RBAC 비활성 분기에 `/api/flight-quality/**` 정책 명시
6. Compose 기본값을 안전한 값으로 전환할 시점 결정
