# VisionFlow 읽기 전용 API 보안·권한 감사

이 도구는 API가 존재하는지만 확인하는 계약 감사의 다음 단계입니다. 다음 원천을 자동 비교하여 실제 접근 권한 매트릭스를 만듭니다.

- Spring `SecurityConfig`의 RBAC 활성·비활성 분기와 규칙 순서
- Backend Controller 83개 operation
- Frontend Route Handler 83개의 Backend 인증 전달과 same-origin 방어
- AI OpenAPI 11개 operation과 FastAPI 인증 단서
- `compose.yaml`의 비밀값이 아닌 보안 기본값
- 실행 중인 Backend·Frontend 컨테이너의 선택된 비밀 제외 보안 모드

DB 변경, 컨테이너 변경, 서비스 재시작, 자격증명 값 수집을 하지 않습니다. JSON·HTML·Markdown 보고서만 생성합니다.

GitHub Actions의 API audit workflow는 별도로 Frontend 잠금 파일을 `npm audit`으로,
테스트 환경에 실제 설치된 AI Python 패키지(고정된 PyTorch CPU 버전 포함)를 PyPA
`pip-audit`으로 검사합니다. 이 두 단계는 알려진 의존성 취약점을 CI에서 차단하며,
자동으로 패키지를 변경하지 않습니다. Backend Gradle 의존성은 현재 이 두 검사의
대상이 아니므로 `.github/workflows/gradle-dependency-submission.yml`이 기본 브랜치의
해결된 Gradle 의존성 트리를 GitHub Dependency Graph에 제출하도록 구성했습니다. 이
제출 결과는 Dependabot의 Gradle 취약성 알림 기반이 됩니다. Dependency Review는 PR에서
GitHub가 감지한 변경 의존성의 moderate 이상 취약성을 차단하도록 구성했지만, Gradle PR의
전체 전이 의존성 그래프는 기본 브랜치 제출만으로 검증되지 않습니다. CodeQL은 Backend
Java, Frontend TypeScript/JavaScript, AI Python의 코드 분석을 PR·push 및 주간 일정으로
수행하도록 `.github/workflows/api-audit.yml`에 구성되어 있으며, 기존 필수 API 감사
게이트가 CodeQL 결과에 의존하도록 연결했습니다. CodeQL 및 Dependabot 결과를 확인하고
취약성 알림을 처리해야 전체 코드·의존성 점검 종료로 판정할 수 있습니다.

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

현재 소스 기준 operation 수는 Backend 83·Frontend 83·AI 11입니다. 최신 정적 감사는
`API_SECURITY_HEALTHY`이며, 이 상태만으로 실행 중인 컨테이너·공개 HTTPS 종단점까지
검증된 것은 아닙니다. 런타임 검사를 생략한 감사 결과는 별도로 표시해야 합니다.

확인된 현재 상태:

- 핵심 ADMIN·인증 보호 규칙 실패: 0건
- 기준선에 없는 공개 변경 API: 0건
- 민감 GET: 인증 보호, 승인된 LOW 공개 예외 1건
- 보안 비활성 모드의 API 허용 범위: 일관성 PASS
- 보호된 Backend·AI로 필요한 인증을 전달하지 않는 Frontend Proxy: 0건
- Frontend 변경 요청 same-origin 방어 누락: 0건
- AI 민감 operation: 내부 서비스 키 보호, `/health`만 공개
- Compose 기본값: 운영 권장 보안 모드 PASS

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

## 런타임 보안 종료 전 확인

정적 권한 감사가 통과해도 운영 보안 확인은 별도로 필요합니다.

1. 실행 중인 Backend·Frontend·AI 컨테이너의 보안 모드와 공개 포트 경계를 확인합니다.
   감사 스크립트는 전체 환경변수나 자격증명 값을 출력하지 않는 모드로 실행합니다.
2. 공개 HTTPS 호스트(apex 및 www)에만 설정한 host-only HSTS를 배포 후 다시 확인하고,
   Report-Only CSP 증적은 인증된 보안 관리자 세션으로 수집·검토합니다. 강제 CSP 전환은
   관찰 보고서에서 실제 위반을 검토한 뒤 별도로 결정합니다. 로컬·사설 주소에는 HSTS를
   적용하지 않습니다.
3. 대화·운영 출력에 노출된 것으로 확인된 서비스 및 운영자 키를 운영자가 교체하고,
   관련 서비스에 새 키를 적용한 뒤 로그인·AI 프록시 인수 테스트를 수행합니다.
4. Docker 런타임을 사용할 수 있는 환경에서 백엔드 전체 통합 테스트와 API 런타임
   감사를 실행합니다. 데이터베이스 및 컨테이너 접근이 없는 로컬 정적 감사 결과를
   런타임 검증 완료로 간주하지 않습니다.
