# VisionFlow 2차 프로젝트 인수 기준

| 영역 | 검증 항목 | 성공 기준 | 데이터 변경 |
|---|---|---|---|
| Backend | `/api/health` | HTTP 200 | 없음 |
| Backend | `/api/drones` | HTTP 200 | 없음 |
| Frontend | `/dashboard` | HTTP 200 | 없음 |
| Frontend | `/drones` | HTTP 200 | 없음 |
| Frontend | `/demo-scenario` | HTTP 200 | 없음 |
| AI | `/api/ingest/status` | HTTP 200 | 없음 |
| AI | `/api/streams/status` | HTTP 200 | 없음 |
| Proxy | `/api/ai/ingest/status` | HTTP 200 | 없음 |
| Proxy | `/api/ai/stream/status` | HTTP 200 | 없음 |
| Demo | 시작 | `READY` | 세션·텔레메트리 생성 |
| Demo | AI 탐지 | `DETECTED` | 이벤트·경보·Incident·JPEG 생성 |
| Demo | SLA | `ESCALATED` | SLA 조치 이력 생성 |
| Demo | 해결 | `RESOLVED` | AI 경보·Incident 해결 |
| Demo | 종료 | `COMPLETED` | 비행 세션 종료 |
| Demo | 영속 상태 재조회 | HTTP 200 | 없음 |
| Evidence | AI JPEG | HTTP 200 | 없음 |
| Reporting | Incident 보고서 | HTTP 200 | 없음 |
| Presentation | 전체 보안 인수 | Demo·RBAC·Session 모두 PASS | 데모 데이터 생성 |
| Presentation | 릴리스 준비도·증빙 | 차단 0, ZIP·sidecar·manifest 유효 | 보고서·증빙 생성 |
| Presentation | 2차 프로젝트 종결 | `SECOND_PROJECT_CLOSED_WITH_DEFERRED` | 없음 |
| Presentation | 최종 운영 게이트 | `PRESENTATION_READY_WITH_DEFERRED` | 판정 보고서 생성 |
| Presentation | 반복 안정성 리허설 | 기본 3회 연속 PASS | 데모 데이터·판정 보고서 생성 |
| Presentation | 성능·병목 판정 | `PRESENTATION_PERFORMANCE_READY_WITH_DEFERRED` | 읽기 전용 판정 보고서 생성 |
| Presentation | 발표 당일 퀵체크 | 핵심 GET 경로 10개 PASS | 읽기 전용 상태 보고서 생성 |
| Presentation | 최종 사인오프 | `PRESENTATION_SIGNOFF_READY_WITH_DEFERRED` | 안전 증적 ZIP 생성 |
| Presentation | 휴대형 사인오프 검증 | `PORTABLE_VERIFIED`, 4/4 단계 연결 | 없음 |

## 최종 판정

- `scripts\prepare-visionflow-presentation.bat`의 필수 항목이 모두 PASS이고
  `PRESENTATION_READY_WITH_DEFERRED`이면 2차 프로젝트 발표 사전 점검 통과
- 한 항목이라도 FAIL이면 보고서의 메시지와 HTTP 상태를 기준으로 원인 분석
- 스마트폰 HTTPS 실센서 검증 보류 항목은 별도 리스크로 기록
- DJI Mini 4 Pro RTSP·기체 SDK는 3차 프로젝트 백로그로 유지
