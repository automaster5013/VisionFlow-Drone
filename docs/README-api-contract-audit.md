# VisionFlow 읽기 전용 API 계약 감사

이 도구는 다음 세 계약 원천을 한 번에 비교합니다.

- Spring Backend의 `*Controller.java` 매핑
- Next.js Frontend의 `src/app/api/**/route.ts` HTTP 메서드
- FastAPI AI 서버의 OpenAPI `paths`

DB 변경, 컨테이너 변경, 서비스 재시작, 외부 쓰기를 하지 않습니다. 생성되는 것은 `artifacts/api-contract-audit/` 아래의 JSON·HTML 보고서뿐입니다.

## 설치 파일

다음 파일을 저장소의 동일한 상대 경로로 배치합니다.

- `scripts/visionflow_api_contract_audit.py`
- `scripts/visionflow_api_contract_baseline.json`
- `scripts/run-visionflow-api-contract-audit.bat`
- `docs/README-api-contract-audit.md`

Python 표준 라이브러리만 사용하므로 추가 패키지 설치는 필요하지 않습니다.

## 일반 실행

AI 서버와 Backend가 실행 중일 때 저장소 루트에서 실행합니다.

```bat
scripts\run-visionflow-api-contract-audit.bat
```

기본 동작은 다음과 같습니다.

- AI OpenAPI: `http://localhost:8000/openapi.json`을 읽어 실제 operation 수집
- Backend OpenAPI: `http://localhost:8080/v3/api-docs` 상태를 읽기 전용으로 확인
- Backend OpenAPI의 `401` 또는 `403`: 보안 정책상 보호된 상태로 인정
- 보고서: `artifacts\api-contract-audit\audit-<UTC>\`

Backend OpenAPI가 HTTP 200으로 공개된 환경에서는 Controller와 OpenAPI operation도 자동 비교합니다.

## 오프라인·재현 실행

저장한 AI OpenAPI 파일을 사용하면 AI 서버에 접속하지 않고도 같은 계약 비교를 재현할 수 있습니다.

```bat
scripts\run-visionflow-api-contract-audit.bat --ai-openapi-file "artifacts\api-inventory-source\ai-openapi.json" --skip-backend-openapi-probe
```

`--output`에 상대 경로를 주면 프로젝트 루트를 기준으로 해석합니다.

```bat
scripts\run-visionflow-api-contract-audit.bat --output "artifacts\api-contract-audit\manual-check"
```

## 판정과 종료 코드

- `API_CONTRACT_HEALTHY`: 계약 누락이나 검토 항목 없음, 종료 코드 0
- `API_CONTRACT_ADVISORY`: 기준선에 등록된 검토 항목 또는 operation 수 변화, 기본 종료 코드 0
- `API_CONTRACT_BLOCKED`: Frontend proxy 대상 부재, 파싱 문제, 중복 operation, Controller/OpenAPI 불일치, 종료 코드 1
- 실행 자체 실패: 파일·JSON·네트워크 등 입력 오류, 종료 코드 2

CI에서 `ADVISORY`도 실패로 처리하려면 `--strict`를 추가합니다.

```bat
scripts\run-visionflow-api-contract-audit.bat --strict
```

## 현재 기준선

현재 기준은 `f670b101682a1129e8e258b553300f9ca0dfd0b6`에서 세션 상세 GET proxy를 추가한 소스이며 operation 수는 다음과 같습니다.

| 계층 | Operation 수 | 메서드 분포 |
|---|---:|---|
| Backend Controller | 70 | GET 35, POST 16, PUT 4, PATCH 11, DELETE 4 |
| Frontend Route | 71 | GET 40, POST 13, PUT 3, PATCH 11, DELETE 4 |
| AI OpenAPI | 9 | GET 7, POST 2 |

현재 소스의 정상 예상 결과는 `API_CONTRACT_HEALTHY`입니다. 비행 세션 상세 GET과 AI annotated stream은 모두 인증된 same-origin Frontend proxy를 갖춤으며, Backend·AI 업무 operation의 미중계 Advisory는 0건입니다. Health, 장치·AI 내부 입력, 운영 점검 operation만 명시적 direct-only 예외로 유지합니다.

## 기준선 관리

`scripts/visionflow_api_contract_baseline.json`에는 다음 정보만 명시적으로 유지합니다.

- `expectedCounts`: 승인된 세 계층의 operation 수
- `frontendLocalOperations`: Backend·AI로 중계하지 않는 Next.js 자체 API
- `frontendSpecialMappings`: 경로 또는 대상 이름이 1:1이 아닌 proxy
- `expected*OnlyOperations`: health·내부 수집·운영 점검처럼 의도적으로 직접 호출하는 API
- `advisory*OnlyOperations`: 아직 중계가 없어서 후속 작업이 필요한 API
- `browserDirectUrlAdvisories`: 브라우저에서 위험한 직접 URL 패턴

API를 추가·삭제할 때는 먼저 보고서의 `unexpected`와 `missingTargets`를 검토합니다. 구현 변경이 의도된 것임을 확인한 뒤에만 기준선 수와 예외 사유를 함께 갱신합니다. 단순히 경고를 없애기 위해 기준선을 수정하면 안 됩니다.

## 보고서 확인

JSON은 자동화와 상세 증적용이며 HTML은 사람이 빠르게 검토하기 위한 문서입니다.

- `visionflow-api-contract-audit.json`
- `visionflow-api-contract-audit.html`

JSON의 핵심 필드는 다음과 같습니다.

- `summary.missingTargets`: Frontend가 호출하지만 실제 대상 operation이 없는 수
- `checks[].unexpected`: 기준선에 없던 미중계 operation
- `checks[].advisory`: 승인된 후속 검토 항목
- `inventory`: 세 계층의 전체 operation과 소스 위치
- `mappings`: 각 Frontend operation이 가리키는 Backend·AI 대상
- `safety`: 비변경 검사 속성
