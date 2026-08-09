# VisionFlow API·시스템 추적성 감사 CI 게이트

기준 커밋: `4d4b8693cda6ecb4ba2d322ed617750525a17580`

이 게이트는 Backend Controller, Frontend Route, AI FastAPI operation, 보안 규칙, Flyway 테이블, JPA Entity·Repository, 물리 FK와 기능 흐름의 드리프트를 GitHub Actions에서 읽기 전용으로 검사합니다. 컨테이너·DB·서비스를 실행하거나 변경하지 않으며 비밀값과 `.env.docker`를 읽지 않습니다.

## 판정 정책

- operation 기준: Backend 76, Frontend 78, AI 9
- 계약 감사: `API_CONTRACT_HEALTHY`만 허용; 허용 Advisory 0건
- 계약 감사의 Advisory, `unexpected` 항목, missing target, operation 수 변경: 실패
- 보안 감사: `API_SECURITY_HEALTHY`만 허용
- 런타임 보안 검사는 CI에서 `SKIPPED`가 정상이며 정적 보안 검사는 모두 `PASS`여야 함
- 시스템 추적성 감사: `SYSTEM_TRACEABILITY_HEALTHY`만 허용
- 데이터 기준: Table 16, Entity 15, Repository 15, 물리 FK 12, 기능 흐름 13, 소프트 상관관계 4
- 추적성 감사의 28개 검사키가 정확히 존재하고 모두 `PASS`여야 함
- Drone 변경 검사는 기본정보·상태·삭제·텔레메트리 쓰기의 행 잠금과 비잠금 읽기 경계를 함께 확인
- AI 이벤트 수집 검사는 세션 행 잠금, 프레임 멱등 조회·생성 순서와 V5 UNIQUE 최종 방어를 함께 확인
- AI 경보 생성 검사는 추론 이벤트 행 잠금, event 멱등 조회·생성 순서와 V10 UNIQUE 최종 방어를 함께 확인
- AI 스냅샷 검사는 첨부 쓰기의 추론 이벤트 행 잠금과 비잠금 조회 경계를 함께 확인
- 감사 로그 보존 검사는 수동·예약 정리의 대상 행 잠금과 비잠금 상태 조회 경계를 함께 확인
- 비행 세션 생명주기 검사는 Drone·Session 행 잠금, ACTIVE 세션 DB UNIQUE 제약, 읽기 전용 중복 탐지 규칙을 함께 확인
- 비행 품질 평가 검사는 수동·종료 이벤트·백필 재계산의 Session 행 잠금, V16 평가 UNIQUE 제약, 비잠금 읽기 경계를 함께 확인
- 정비 작업지시 검사는 자동 동기화·점검 시작·완료의 Work Order 잠금과 정비 SLA의 Incident→Work Order 잠금·재평가 순서, V19 UNIQUE 최종 방어를 함께 확인
- GitHub Actions 런타임 검사는 `checkout@v6`, `setup-python@v6`, `upload-artifact@v7`의 Node.js 24 실행 경계와 push·PR 추적성 회귀 테스트를 함께 확인
- Frontend 산출물 파일 추적 검사는 모바일 증적 후보 경로의 프로젝트 내부 기본값, Docker 읽기 전용 마운트, 동적 보고서·체크섬 경로의 Turbopack 추적 제외를 함께 확인
- 정비 작전 현황 UI 검사는 SLA·전체 함대 인증 프록시, 두 응답 파서,
  30초 자동 갱신, 판정 시각 신선도·소스 시차, 단계·함대 비행 준비·
  기체별 판정 필터·사유·긴급 큐 시각화, 읽기 전용 관제 상세 드로어와
  함대 게이트→작업지시→Incident·SLA→최종 판정의 4단계 근거 흐름,
  접근성 있는 닫기·포커스 복귀 및 기체·작업·Incident 링크를 함께 확인
- 통합 이벤트 관제 UI 검사는 AI 추론·AI 경보·지오펜스 위반·Incident의
  기존 인증 프록시와 엄격한 응답 파서, 15초 자동 갱신, AbortController 기반
  오래된 요청 차단, 소스별 부분 장애 격리와 마지막 정상 데이터 유지,
  소스·기체·위험도·대응 상태·시간 필터, 통합 타임라인, modal dialog 의미
  구조·Escape·Tab 포커스 순환·포커스 복귀 및 기체·리플레이·Incident 링크를
  함께 확인
- 운영 통계 UI 검사는 비행 세션·AI 런타임·함대 신뢰도·정비 KPI의 기존
  same-origin 인증 읽기 프록시와 응답 파서, 7·30·90일 범위, 30초 자동 갱신,
  숨김 탭 조회 생략, AbortController 기반 요청 경합 방지, 부분 장애 시 마지막
  정상 데이터 유지와 상세 화면 링크를 함께 확인
- AI 모델 운영 UI 검사는 인증된 모델 상태 프록시의 경로 비공개 정제,
  모델·GPU·성능·입력 큐·스트림·최근 경보 파서, 30초 자동 갱신,
  부분 장애 시 마지막 정상 데이터 유지와 읽기 전용 경계를 함께 확인
- 운영 설정 UI 검사는 허용 목록 기반 브라우저 저장 파서, 설정 저장·복원,
  이벤트·통계·AI 모델 화면의 초기값 적용, 네트워크·서버 변경 부재와
  비밀값·키·모델 경로 비저장 경계를 함께 확인
- AI OpenAPI inventory는 `streaming.py`의 정적 FastAPI decorator에서 매번 생성하므로 실행 중인 AI 서버가 필요하지 않음

허용 정책은 `scripts/visionflow_ci_api_audit_policy.json`에 있습니다. 정책이나 기준선을 바꾸는 작업은 API 변경 검토와 함께 별도 커밋으로 진행하세요.

## GitHub Actions

`.github/workflows/api-audit.yml`은 다음 경우 실행됩니다.

- `main`의 API·보안·Flyway·추적성·데이터 정합성 정책 관련 소스가 변경된 push
- 같은 경로를 변경하는 pull request
- 수동 `workflow_dispatch`

보고서는 성공·실패와 관계없이 `visionflow-api-and-traceability-audit-reports` artifact로 14일간 보관됩니다.
workflow의 JavaScript Action은 Node.js 24 기반 major만 사용하며, 시스템 추적성 정책 단위 테스트는 정적 감사 전에 실행됩니다.

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
4. 추적성 보고서의 삭제·Drone 변경·세션 상관관계·AI 이벤트 수집·AI 경보 생성·AI 스냅샷·감사 로그 보존·세션 생명주기·비행 품질 평가·정비 작업지시 동시성·GitHub Actions Node.js 24·Frontend 산출물 파일 추적·정비 작전 현황·통합 이벤트 관제·운영 통계·AI 모델 운영·운영 설정 UI 정책 검사 및 `baseline-counts`, `migration-tables`, `entity-repository-mapping`, `foreign-key-contract`, `flow-operation-coverage`, `flow-table-coverage` 확인
5. 의도된 변경이면 기존 계약·보안·추적성 기준선과 CI 정책을 함께 검토
6. 의도하지 않은 변경이면 Route, proxy target, 인증 전파, Spring Security, Flyway, Entity·Repository 또는 기능 흐름 기준을 수정

운영 키, AI 내부 키, 세션 쿠키는 보고서와 Actions 로그에 포함되지 않습니다.
