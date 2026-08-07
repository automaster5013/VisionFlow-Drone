# VisionFlow-Drone API 현행화 문서

> 기준일: 2026-08-03<br>
> 소스 기준 Git 커밋: `f670b101682a1129e8e258b553300f9ca0dfd0b6`<br>
> 프로젝트: VisionFlow-Drone — 지능형 드론 관제 및 무선 Vision AI 표준 파이프라인<br>
> 팀·담당: PyvaOps / 이명휘

## 1. 목적과 조사 범위

이 문서는 실행 중인 AI OpenAPI, Spring Controller 매핑, Next.js Route Handler 소스를 교차 대조해 현재 API 구조를 한 곳에 정리한 기준 문서다.

- Backend: Spring Boot Controller 19개
- Frontend Proxy: Next.js `app/api` Route Handler 60개 파일
- AI: FastAPI OpenAPI 3.1.0, 애플리케이션 버전 0.6.0
- 조사 대상: HTTP API와 Next.js 내부 로컬 API
- 제외 대상: STOMP/WebSocket 메시지 세부 destination, 요청·응답 DTO 전체 필드, 비밀 환경값

Backend의 `/v3/api-docs`는 HTTP 401이 반환됐다. 이는 Backend 장애가 아니라 현재 보안 정책에서 `/v3/api-docs/**`가 허용되지 않은 결과다. 따라서 Backend 목록은 기준 커밋의 Controller 어노테이션 원문으로 확정했다.

## 2. 전체 요약

| 계층 | 파일/Controller | HTTP Operation | GET | POST | PUT | PATCH | DELETE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Spring Backend | 19 Controller | 70 | 35 | 16 | 4 | 11 | 4 |
| Next.js Frontend API | 60 route 파일 | 71 | 40 | 13 | 3 | 11 | 4 |
| FastAPI AI | OpenAPI 0.6.0 | 9 | 7 | 2 | 0 | 0 | 0 |
| 합계 | 계층별 구현 합계 | 150 | 82 | 31 | 7 | 22 | 8 |

150은 외부에 공개되는 고유 업무 API 수가 아니라 각 계층에 구현된 operation의 합계다. 다수의 Next.js API는 Backend 또는 AI API를 중계한다.

```text
Browser / Smartphone
        |
        | same-origin /api/*
        v
Next.js Route Handler :3000
        |                         \
        | BACKEND_API_URL          \ AI_STREAM_API_URL
        v                           v
Spring Backend :8080          FastAPI AI :8000
        ^                           |
        | AI event + snapshot       |
        +---------------------------+
                    |
                    v
                 MySQL
```

## 3. 인증·권한 기준

운영자 보안이 활성화된 현재 기준은 다음과 같다.

| 표기 | 의미 |
| --- | --- |
| Public | 인증 없이 접근 가능 |
| Device ingress | 장치·AI 입력을 위해 인증 없이 허용된 쓰기 API |
| VIEWER+ | VIEWER, OPERATOR, ADMIN |
| OPERATOR+ | OPERATOR, ADMIN |
| ADMIN | ADMIN만 허용 |
| Current session | 현재 유효한 운영자 세션 필요 |

주요 보안 동작:

- Backend key header: `X-VisionFlow-Operator-Key`
- Backend session header: `X-VisionFlow-Operator-Session`
- 브라우저는 Next.js가 HttpOnly 세션 쿠키를 읽어 Backend session header로 변환한다.
- 변경 요청은 원칙적으로 Next.js same-origin 검사와 Backend RBAC를 모두 통과해야 한다.
- 예외적으로 카메라 ingest, 드론 telemetry, AI event·snapshot은 장치 입력을 위해 Public 쓰기로 열려 있다.
- 로그인은 동일 클라이언트 기준 10분 동안 5회 실패하면 15분 잠긴다. 응답은 HTTP 429와 `Retry-After`를 제공한다.

## 4. Spring Backend API — 70 operations

### 4.1 AI 이벤트·알림

| Method | Path | 용도 | 접근 |
| --- | --- | --- | --- |
| GET | `/api/ai/alerts` | AI 알림 목록 | Public |
| GET | `/api/ai/alerts/{alertId}` | AI 알림 상세 | Public |
| PATCH | `/api/ai/alerts/{alertId}/acknowledge` | 알림 확인 처리 | OPERATOR+ |
| PATCH | `/api/ai/alerts/{alertId}/resolve` | 알림 해결 처리 | OPERATOR+ |
| POST | `/api/ai/events` | AI 추론 이벤트 저장 | Device ingress |
| GET | `/api/ai/events` | 최근 AI 이벤트 조회 | Public |
| PUT | `/api/ai/events/{eventId}/snapshot` | 이벤트 스냅숏 업로드 | Device ingress |
| GET | `/api/ai/events/{eventId}/snapshot` | 이벤트 스냅숏 조회 | Public |

### 4.2 감사 로그

| Method | Path | 용도 | 접근 |
| --- | --- | --- | --- |
| GET | `/api/audit-logs` | 감사 로그 조회 | Public |
| GET | `/api/audit-logs/export` | 감사 로그 CSV 내보내기 | VIEWER+ |
| GET | `/api/audit-logs/retention` | 감사 로그 보존 상태 | Public |
| POST | `/api/audit-logs/retention/cleanup` | 감사 로그 보존 정리 | ADMIN + confirm |

### 4.3 운영자 보안·세션

| Method | Path | 용도 | 접근 |
| --- | --- | --- | --- |
| GET | `/api/security/me` | 현재 인증 상태·역할 조회 | Public |
| POST | `/api/security/sessions` | KEY 검증 후 세션 발급 | Public + rate limit |
| GET | `/api/security/sessions` | 활성 세션 목록 | ADMIN |
| DELETE | `/api/security/sessions/{sessionId}` | 다른 세션 강제 종료 | ADMIN |
| DELETE | `/api/security/sessions/others` | 현재 세션 외 일괄 종료 | ADMIN + `confirm=true` |
| DELETE | `/api/security/sessions/current` | 현재 세션 로그아웃 | Current session |

### 4.4 대시보드·시연 시나리오

| Method | Path | 용도 | 접근 |
| --- | --- | --- | --- |
| GET | `/api/dashboard/operations` | 운영 대시보드 집계 | Public |
| POST | `/api/demo/scenarios` | 시연 시나리오 시작 | OPERATOR+ |
| GET | `/api/demo/scenarios/{scenarioId}` | 시연 상태 조회 | Public |
| POST | `/api/demo/scenarios/{scenarioId}/detect` | AI 탐지 단계 진행 | OPERATOR+ |
| POST | `/api/demo/scenarios/{scenarioId}/escalate` | SLA 에스컬레이션 | OPERATOR+ |
| POST | `/api/demo/scenarios/{scenarioId}/resolve` | 인시던트 해결 | OPERATOR+ |
| POST | `/api/demo/scenarios/{scenarioId}/complete` | 비행·시연 완료 | OPERATOR+ |

### 4.5 드론·텔레메트리

| Method | Path | 용도 | 접근 |
| --- | --- | --- | --- |
| POST | `/api/drones` | 드론 등록 | OPERATOR+ |
| GET | `/api/drones` | 드론 목록 | Public |
| GET | `/api/drones/{id}` | 드론 상세 | Public |
| PUT | `/api/drones/{id}` | 드론 정보 수정 | OPERATOR+ |
| PATCH | `/api/drones/{id}/status` | 드론 상태 변경 | OPERATOR+ |
| PATCH | `/api/drones/{id}/telemetry` | 실시간 텔레메트리 입력 | Device ingress |
| DELETE | `/api/drones/{id}` | 드론 삭제 | ADMIN |
| GET | `/api/drones/{id}/telemetry/history` | 텔레메트리·과거 경로 조회 | Public |

### 4.6 비행 세션·재생

| Method | Path | 용도 | 접근 |
| --- | --- | --- | --- |
| POST | `/api/drones/{droneId}/flight-sessions` | 비행 세션 시작 | OPERATOR+ |
| GET | `/api/drones/{droneId}/flight-sessions` | 비행 세션 목록 | Public |
| GET | `/api/drones/{droneId}/flight-sessions/{sessionId}` | 비행 세션 상세 | Public |
| PATCH | `/api/drones/{droneId}/flight-sessions/{sessionId}` | 비행 세션·텔레메트리 갱신 | OPERATOR+ |
| POST | `/api/drones/{droneId}/flight-sessions/{sessionId}/complete` | 비행 완료 | OPERATOR+ |
| POST | `/api/drones/{droneId}/flight-sessions/{sessionId}/abort` | 비행 중단 | OPERATOR+ |
| GET | `/api/drones/{droneId}/flight-sessions/{sessionId}/replay` | 비행 재생 데이터 | Public |

### 4.7 비행 품질·신뢰성

| Method | Path | 용도 | 접근 |
| --- | --- | --- | --- |
| GET | `/api/flight-quality/fleet-reliability` | 기단 신뢰성 집계 | Public |
| POST | `/api/flight-quality/fleet-reliability/incidents/synchronize` | 품질 인시던트 동기화 | OPERATOR+ |
| GET | `/api/drones/{droneId}/flight-sessions/{sessionId}/quality-assessment` | 세션 품질 평가 | Public |
| PUT | `/api/drones/{droneId}/flight-sessions/{sessionId}/quality-assessment` | 세션 품질 재계산 | OPERATOR+ |
| GET | `/api/drones/{droneId}/flight-quality-assessments` | 품질 평가 이력 | Public |
| POST | `/api/drones/{droneId}/flight-quality-assessments/backfill` | 과거 품질 평가 생성 | OPERATOR+ |

### 4.8 지오펜스

| Method | Path | 용도 | 접근 |
| --- | --- | --- | --- |
| POST | `/api/geofences` | 지오펜스 등록 | OPERATOR+ |
| GET | `/api/geofences` | 지오펜스 목록 | Public |
| GET | `/api/geofences/events` | 지오펜스 이벤트 목록 | Public |
| GET | `/api/geofences/{id}` | 지오펜스 상세 | Public |
| PUT | `/api/geofences/{id}` | 지오펜스 수정 | OPERATOR+ |
| PATCH | `/api/geofences/{id}/active` | 활성 여부 변경 | OPERATOR+ |

### 4.9 상태·인시던트

| Method | Path | 용도 | 접근 |
| --- | --- | --- | --- |
| GET | `/api/health` | Backend 상태 | Public |
| GET | `/api/incidents` | 인시던트 목록 | Public |
| GET | `/api/incidents/{incidentId}` | 인시던트 상세 | Public |
| GET | `/api/incidents/{incidentId}/report` | 인시던트 보고서 | Public |
| PATCH | `/api/incidents/{incidentId}/assignee` | 담당자 배정 | OPERATOR+ |
| PATCH | `/api/incidents/{incidentId}/priority` | 우선순위 변경 | OPERATOR+ |
| PATCH | `/api/incidents/{incidentId}/status` | 상태 변경 | OPERATOR+ |
| POST | `/api/incidents/{incidentId}/notes` | 조치 메모 추가 | OPERATOR+ |

### 4.10 정비·SLA

| Method | Path | 용도 | 접근 |
| --- | --- | --- | --- |
| GET | `/api/maintenance/flight-clearance/{droneId}` | 기체별 비행 허가 상태 | Public |
| GET | `/api/maintenance/flight-clearance` | 기단 비행 허가 상태 | Public |
| GET | `/api/maintenance/metrics` | 정비 운영 지표 | Public |
| GET | `/api/maintenance/priorities` | 정비 우선순위 | Public |
| GET | `/api/maintenance/sla` | 정비 SLA 상태 | Public |
| GET | `/api/maintenance/sla/incidents` | SLA 인시던트 추적 | Public |
| GET | `/api/maintenance/work-orders` | 정비 작업 목록 | Public |
| GET | `/api/maintenance/work-orders/{workOrderId}` | 정비 작업 상세 | Public |
| PATCH | `/api/maintenance/work-orders/{workOrderId}/start` | 점검 시작 | OPERATOR+ |
| PATCH | `/api/maintenance/work-orders/{workOrderId}/complete` | 점검 완료 | OPERATOR+ |

## 5. FastAPI AI API — 9 operations

AI OpenAPI에는 인증 scheme이 선언되어 있지 않다. 현재 네트워크에 접근할 수 있으면 모든 API를 호출할 수 있는 구조다.

| Method | Path | OpenAPI summary | Frontend same-origin proxy |
| --- | --- | --- | --- |
| GET | `/health` | Health | 없음 |
| GET | `/api/streams/status` | Stream Status | `/api/ai/stream/status` |
| GET | `/api/metrics/status` | Performance Status | `/api/ai/metrics/status` |
| POST | `/api/metrics/reset` | Reset Performance Metrics | 없음 |
| GET | `/api/models/status` | Model Status | 없음 |
| GET | `/api/streams/latest.jpg` | Latest Frame | 없음 |
| GET | `/api/streams/annotated.mjpeg` | Annotated Stream | 없음 — 브라우저가 직접 접근 중 |
| GET | `/api/ingest/status` | Ingest Status | `/api/ai/ingest/status` |
| POST | `/api/ingest/frame` | Ingest Frame | `/api/ai/ingest/frame` |

## 6. Next.js Frontend API — 69 operations

### 6.1 AI 관련 Proxy

| Method | Browser path | Target | 구분 |
| --- | --- | --- | --- |
| GET | `/api/ai/alerts` | Backend 동일 경로 | 조회 |
| GET | `/api/ai/alerts/[id]` | Backend `/api/ai/alerts/{alertId}` | 조회 |
| PATCH | `/api/ai/alerts/[id]/acknowledge` | Backend 동일 경로 | same-origin + OPERATOR+ |
| PATCH | `/api/ai/alerts/[id]/resolve` | Backend 동일 경로 | same-origin + OPERATOR+ |
| GET | `/api/ai/events` | Backend 동일 경로 | 조회 |
| GET | `/api/ai/events/[id]/snapshot` | Backend 동일 경로 | 이미지 조회 |
| POST | `/api/ai/ingest/frame` | AI `/api/ingest/frame` | 카메라 입력 |
| GET | `/api/ai/ingest/status` | AI `/api/ingest/status` | 상태 조회 |
| GET | `/api/ai/metrics/status` | AI `/api/metrics/status` | 성능 조회 |
| GET | `/api/ai/stream/status` | AI `/api/streams/status` | 스트림 상태 조회 |

### 6.2 감사·대시보드·시연

| Method | Browser path | Target |
| --- | --- | --- |
| GET | `/api/audit-logs` | Backend 동일 경로 |
| GET | `/api/audit-logs/export` | Backend 동일 경로 |
| GET | `/api/audit-logs/retention` | Backend 동일 경로 |
| POST | `/api/audit-logs/retention/cleanup` | Backend 동일 경로 |
| GET | `/api/dashboard/operations` | Backend 동일 경로 |
| POST | `/api/demo/scenarios` | Backend 동일 경로 |
| GET | `/api/demo/scenarios/[id]` | Backend `/api/demo/scenarios/{scenarioId}` |
| POST | `/api/demo/scenarios/[id]/[action]` | Backend `detect`, `escalate`, `resolve`, `complete` 중 하나 |

### 6.3 드론·비행·품질

| Method | Browser path | Target |
| --- | --- | --- |
| GET | `/api/drones` | Backend 동일 경로 |
| POST | `/api/drones` | Backend 동일 경로 |
| GET | `/api/drones/[id]` | Backend `/api/drones/{id}` |
| PUT | `/api/drones/[id]` | Backend `/api/drones/{id}` |
| DELETE | `/api/drones/[id]` | Backend `/api/drones/{id}` |
| PATCH | `/api/drones/[id]/status` | Backend 동일 경로 |
| PATCH | `/api/drones/[id]/telemetry` | Backend 동일 경로 |
| GET | `/api/drones/[id]/telemetry/history` | Backend 동일 경로 |
| GET | `/api/drones/[id]/flight-sessions` | Backend 동일 경로 |
| POST | `/api/drones/[id]/flight-sessions` | Backend 동일 경로 |
| GET | `/api/drones/[id]/flight-sessions/[sessionId]` | Backend 동일 경로 |
| PATCH | `/api/drones/[id]/flight-sessions/[sessionId]` | Backend 동일 경로 |
| POST | `/api/drones/[id]/flight-sessions/[sessionId]/[action]` | Backend `complete` 또는 `abort` |
| GET | `/api/drones/[id]/flight-sessions/[sessionId]/replay` | Backend 동일 경로 |
| GET | `/api/drones/[id]/flight-sessions/[sessionId]/quality-assessment` | Backend 동일 경로 |
| PUT | `/api/drones/[id]/flight-sessions/[sessionId]/quality-assessment` | Backend 동일 경로 |
| GET | `/api/drones/[id]/flight-quality-assessments` | Backend 동일 경로 |
| POST | `/api/drones/[id]/flight-quality-assessments/backfill` | Backend 동일 경로 |
| GET | `/api/flight-quality/fleet-reliability` | Backend 동일 경로 |
| POST | `/api/flight-quality/fleet-reliability/incidents/synchronize` | Backend 동일 경로 |

### 6.4 지오펜스·인시던트

| Method | Browser path | Target |
| --- | --- | --- |
| GET | `/api/geofences` | Backend 동일 경로 |
| POST | `/api/geofences` | Backend 동일 경로 |
| GET | `/api/geofences/events` | Backend 동일 경로 |
| GET | `/api/geofences/[id]` | Backend `/api/geofences/{id}` |
| PUT | `/api/geofences/[id]` | Backend `/api/geofences/{id}` |
| PATCH | `/api/geofences/[id]/active` | Backend 동일 경로 |
| GET | `/api/incidents` | Backend 동일 경로 |
| GET | `/api/incidents/[id]` | Backend `/api/incidents/{incidentId}` |
| GET | `/api/incidents/[id]/report` | Backend 동일 경로 |
| PATCH | `/api/incidents/[id]/assignee` | Backend 동일 경로 |
| PATCH | `/api/incidents/[id]/priority` | Backend 동일 경로 |
| PATCH | `/api/incidents/[id]/status` | Backend 동일 경로 |
| POST | `/api/incidents/[id]/notes` | Backend 동일 경로 |

### 6.5 정비·SLA

| Method | Browser path | Target |
| --- | --- | --- |
| GET | `/api/maintenance/flight-clearance` | Backend 동일 경로 |
| GET | `/api/maintenance/flight-clearance/[droneId]` | Backend 동일 경로 |
| GET | `/api/maintenance/metrics` | Backend 동일 경로 |
| GET | `/api/maintenance/priorities` | Backend 동일 경로 |
| GET | `/api/maintenance/sla` | Backend 동일 경로 |
| GET | `/api/maintenance/sla/incidents` | Backend 동일 경로 |
| GET | `/api/maintenance/work-orders` | Backend 동일 경로 |
| GET | `/api/maintenance/work-orders/[id]` | Backend `/api/maintenance/work-orders/{workOrderId}` |
| PATCH | `/api/maintenance/work-orders/[id]/start` | Backend 동일 경로 |
| PATCH | `/api/maintenance/work-orders/[id]/complete` | Backend 동일 경로 |

### 6.6 운영자 세션·Frontend 로컬 API

| Method | Browser path | Target/용도 |
| --- | --- | --- |
| GET | `/api/operator/session` | Backend `/api/security/me`; 브라우저 인증 상태 |
| POST | `/api/operator/session` | Backend `/api/security/sessions`; 로그인 |
| DELETE | `/api/operator/session` | Backend `/api/security/sessions/current`; 로그아웃 |
| GET | `/api/operator/sessions` | Backend `/api/security/sessions`; ADMIN 세션 목록 |
| DELETE | `/api/operator/sessions/[sessionId]` | Backend `/api/security/sessions/{sessionId}` |
| DELETE | `/api/operator/sessions/others` | Backend `/api/security/sessions/others` |
| GET | `/api/mobile/evidence/status` | Next.js 로컬 증적 파일 상태 |
| GET | `/api/security/csp-report` | Next.js 메모리의 CSP 관측 현황 |
| POST | `/api/security/csp-report` | 브라우저 CSP report 수집 |

## 7. 계층 간 대조 결과

### 7.1 Backend에만 존재하는 API

| Method | Path | 판정 |
| --- | --- | --- |
| GET | `/api/health` | Backend 직접 상태 점검용; Frontend proxy 없음 |
| POST | `/api/ai/events` | AI 서버가 Backend에 저장하는 내부 입력; Frontend proxy 불필요 |
| PUT | `/api/ai/events/{eventId}/snapshot` | AI 서버 스냅숏 업로드; Frontend proxy 불필요 |

### 7.2 AI에만 존재하거나 브라우저 proxy가 없는 API

| Method | Path | 판정 |
| --- | --- | --- |
| GET | `/health` | 컨테이너 직접 health check |
| POST | `/api/metrics/reset` | 운영·성능 도구 전용 |
| GET | `/api/models/status` | 운영·모델 점검 전용 |
| GET | `/api/streams/latest.jpg` | 단일 최신 프레임; proxy 없음 |

### 7.3 Frontend 로컬 전용 API

- `/api/mobile/evidence/status`: 증적 파일 상태를 읽는 Next.js 로컬 API
- `/api/security/csp-report`: bounded process memory 기반 CSP 관측 API

### 7.4 경로 변환 규칙

- Frontend의 `[id]`, `[sessionId]`는 Backend의 `{id}`, `{droneId}`, `{sessionId}`로 변환된다.
- Frontend `/api/ai/stream/status`는 AI `/api/streams/status`로 변환된다.
- Frontend `/api/operator/**`는 Backend `/api/security/**`로 변환된다.
- 동적 `[action]`은 허용 목록으로 제한된다.
  - Demo: `detect`, `escalate`, `resolve`, `complete`
  - Flight session: `complete`, `abort`
- 대조 결과 Backend나 AI 대상이 존재하지 않는 업무 Proxy는 발견되지 않았다.

## 8. 확인된 위험과 개선 우선순위

### 완료 — AI MJPEG same-origin HTTPS Proxy

AI annotated stream은 `/api/ai/stream/annotated`를 통해 내부 서비스 키를 전달하고 same-origin으로 중계된다. 브라우저는 `localhost:8000`을 직접 참조하지 않으며 HTTPS 스마트폰 경로에서도 mixed-content 경계를 유지한다.

### P1 — Device ingress 인증·제한

다음 쓰기 API는 현재 인증 없이 호출할 수 있다.

- AI `/api/ingest/frame`
- Backend `/api/drones/{id}/telemetry`
- Backend `/api/ai/events`
- Backend `/api/ai/events/{eventId}/snapshot`

3차 프로젝트에서는 장치별 단기 토큰, 세션 결합, 요청 크기 제한, rate limit, timestamp·nonce 또는 서명을 검토한다. 운영자 장기 KEY를 장치 인증에 재사용하지 않는다.

### P1 — Backend OpenAPI 접근 정책

- `/v3/api-docs`는 현재 401이며 운영 API 장애는 아니다.
- 개발 환경에서만 OpenAPI를 허용하거나, 빌드 단계에서 정적 OpenAPI 파일을 생성하는 방식을 권장한다.
- 운영 환경에서 무조건 공개하는 방식은 피한다.

### P1 — 읽기 API 공개 범위 재검토

현재 보안 활성 모드에서는 일부 예외를 제외한 `GET /api/**`가 익명 접근 가능하다. 이에 따라 드론·텔레메트리·인시던트뿐 아니라 감사 로그 목록, 감사 로그 보존 상태, AI 이벤트·알림과 스냅숏도 로그인 없이 조회할 수 있다.

- 교육·로컬 관제 환경에서 의도한 정책인지 확인한다.
- 운영 환경에서는 데이터 민감도에 따라 VIEWER 이상으로 제한할 API를 분류한다.
- 최소 검토 대상: `/api/audit-logs`, `/api/incidents/**`, `/api/ai/events/**`, `/api/ai/alerts/**`, 텔레메트리 이력.
- Frontend 화면 숨김만으로 보호하지 말고 Backend 권한 정책에서 강제한다.

### P1 — 보안 비활성 모드의 `/api/flight-quality/**`

`SecurityConfig`의 보안 비활성 분기에는 여러 API가 `permitAll`로 선언되어 있지만 `/api/flight-quality/**`가 포함되지 않는다. 반면 보안 활성 모드에서는 GET은 공개되고 POST는 OPERATOR+로 동작한다.

- 운영자 보안을 항상 활성화할 계획이면 이를 명시한다.
- 비활성 로컬 모드도 지원한다면 `/api/flight-quality/**` 정책을 다른 업무 API와 일관되게 맞춘다.

### 완료 — 비행 세션 상세 Frontend Proxy

`GET /api/drones/[id]/flight-sessions/[sessionId]`가 Backend 상세 API를 인증된 same-origin 경로로 중계한다. ID 검증, 10초 timeout, `no-store`, upstream 상태·본문 전달을 적용한다.

### P2 — API 계약 자동 검증

- Backend Controller 또는 OpenAPI와 Next.js proxy의 method/path를 CI에서 비교한다.
- AI OpenAPI와 Next.js AI proxy 대상 경로를 비교한다.
- 동적 action 허용 목록과 Backend endpoint를 함께 검사한다.
- 공개 Device ingress 목록은 별도 allowlist로 고정하고 변경 시 보안 검토를 요구한다.

## 9. 권장 완료 기준

- [x] Backend 70, Frontend 72, AI 9 operation 수가 승인된 기준선과 일치한다.
- [x] 모든 Frontend 업무 Proxy가 실제 Backend 또는 AI target을 가진다.
- [x] MJPEG 영상이 PC·스마트폰 모두 same-origin HTTPS로 표시된다.
- [ ] 공개 쓰기 API가 명시적 Device ingress allowlist와 제한을 가진다.
- [ ] Backend OpenAPI를 비밀값 없이 재생성할 수 있다.
- [ ] API 변경 시 이 문서와 자동 계약 검사가 함께 갱신된다.
- [ ] acceptance 및 RBAC·Session acceptance가 통과한다.

## 10. 다음 작업 제안

스마트폰 로그인 검증은 계속 보류한다. API 현행화 이후의 비스마트폰 우선 작업은 다음 순서가 적절하다.

1. API inventory 파일을 저장소 `docs/VISIONFLOW-API-INVENTORY.md`에 반영
2. Controller·Next Route·AI OpenAPI를 비교하는 읽기 전용 API 계약 검사 스크립트 작성
3. Backend OpenAPI 정적 산출 방법 마련
4. Device ingress 보안 설계 문서 작성
5. MJPEG same-origin proxy는 별도 변경 작업으로 분리해 구현·검증

---

이 문서는 API 추가·삭제·경로 변경 시 기준 커밋, operation 수, 접근 정책과 함께 갱신한다.
