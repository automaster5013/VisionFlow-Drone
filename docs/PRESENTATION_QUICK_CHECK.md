# VisionFlow 발표 당일 퀵체크

최종 발표 게이트·3회 반복 리허설·성능 판정까지 완료한 뒤, 발표 시작 직전에
핵심 서비스 경로만 빠르게 재확인하는 읽기 전용 점검입니다.

## 실행 전제

- 최신 발표 성능 판정이
  `PRESENTATION_PERFORMANCE_READY_WITH_DEFERRED`여야 합니다.
- MySQL·Backend·AI server·Frontend가 실행 중이어야 합니다.
- 이 명령은 데모를 생성하거나 컨테이너를 재시작하지 않습니다.

## 실행

프로젝트 루트 `C:\VisionFlow-Drone`에서 실행합니다.

```bat
scripts\run-visionflow-presentation-quick-check.bat
```

다음 10개 GET 경로를 기본 5초 제한으로 확인합니다.

- Backend health·드론 목록
- Frontend 대시보드·드론 관제·데모 화면
- Frontend 드론 API 프록시
- AI ingest·stream 직접 상태
- Frontend AI ingest·stream 프록시

정상 결과:

```text
VisionFlow presentation quick check: PRESENTATION_QUICK_CHECK_READY_WITH_DEFERRED
Checks: 10/10 passed
Diagnosis: PRESENTATION_PATHS_HEALTHY
```

## 장애 자동 분류

실패하면 다음 계층 중 하나로 분류하고 안전한 확인 명령을 출력합니다.

- `BACKEND_OR_DATABASE_UNAVAILABLE`
- `AI_SERVER_UNAVAILABLE`
- `FRONTEND_UNAVAILABLE`
- `FRONTEND_BACKEND_PROXY_FAILURE`
- `FRONTEND_AI_PROXY_FAILURE`
- `MULTIPLE_FRONTEND_PROXY_FAILURES`
- `MULTIPLE_SERVICE_FAILURES`

자동 복구·재시작은 수행하지 않습니다. 여러 서비스가 동시에 실패하면 먼저
다음 명령으로 증적을 수집합니다.

```bat
scripts\collect-visionflow-diagnostics.bat
```

## 생성 파일

`artifacts\presentation-quick-check`:

- `visionflow-presentation-quick-check-<UTC 시각>.json`
- `visionflow-presentation-quick-check-<UTC 시각>.html`
- `visionflow-presentation-quick-check-<UTC 시각>.sha256`

응답 본문, 환경변수 값, 운영자 키, 개인키와 절대경로는 기록하지 않습니다.

## 독립 재검증

```bat
scripts\run-visionflow-presentation-quick-check-verify.bat --report artifacts\presentation-quick-check\visionflow-presentation-quick-check-<UTC 시각>.json
```

정상 결과:

```text
VisionFlow presentation quick check: VERIFIED
Status: PRESENTATION_QUICK_CHECK_READY_WITH_DEFERRED
```

HP OMEN GPU·`best.pt`, 스마트폰 실센서와 DJI 전용 연동은 이 점검에서 실행하지
않습니다.
