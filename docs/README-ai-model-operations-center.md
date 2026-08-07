# VisionFlow AI 모델 운영 센터

기준 커밋: `e7f1c50eff9f39f7b40983728875f1d1149c47f6`

`/models`는 왼쪽 사이드바의 **AI 모델** 메뉴를 실제 읽기 전용 운영 화면으로
연결합니다. 모델 파일을 업로드·교체·활성화하지 않으며 현재 AI 런타임이 제공하는
검증 정보만 표시합니다.

## 표시 범위

- 모델 프로필, 로컬 파일 여부, 크기, SHA-256 축약값, 클래스 목록
- confidence·IOU·입력 이미지 크기
- 실제 적용 장치, GPU 이름·메모리·Compute Capability
- PyTorch·CUDA·cuDNN 버전
- 처리 FPS, 평균·P95·최대 추론 지연, 누적 프레임·탐지 수
- 입력 큐 깊이·수용량·드롭률과 최신 입력 시각
- 분석 스트림의 최신 프레임·기체·탐지·연결 클라이언트 상태
- 최근 AI 경보 최대 100건의 대응 상태와 정보·주의·긴급 분포

`정보`는 오타가 아니라 조치가 필요하지 않은 informational 위험도입니다.

## 데이터와 보안 경계

브라우저는 다음 same-origin GET 경로만 호출합니다.

- `/api/ai/models/status`
- `/api/ai/metrics/status`
- `/api/ai/ingest/status`
- `/api/ai/stream/status`
- `/api/ai/alerts?limit=100`

새 모델 상태 Route Handler는 운영자 인증 상태를 먼저 확인하고 AI 내부 서비스
키로 `/api/models/status`를 조회합니다. 응답에서 `requestedPath`와
`resolvedPath`는 제거하므로 모델의 호스트·컨테이너 절대 경로가 브라우저에
노출되지 않습니다. 비밀 키나 환경 변수 값도 반환하지 않습니다.

## 갱신과 장애 처리

- 30초 자동 갱신과 수동 갱신을 제공합니다.
- 숨겨진 브라우저 탭에서는 자동 갱신을 생략합니다.
- 새 요청은 이전 요청을 `AbortController`로 취소합니다.
- 다섯 소스는 `Promise.allSettled`로 격리합니다.
- 일부 소스 실패 시 마지막 정상 데이터를 유지하고 해당 소스 상태만 경고합니다.
- 모든 응답은 화면 상태에 넣기 전에 엄격한 파서로 검증합니다.

## 변경하지 않는 범위

- Backend API와 AI API operation은 변경하지 않습니다.
- DB migration, 테이블, 컨테이너, 서비스, 예약 작업을 변경하지 않습니다.
- 모델 업로드·교체·활성화·성능 초기화 요청을 제공하지 않습니다.
- 기존 운영자 RBAC와 AI 내부 인증 경계를 유지합니다.

## 검증

```bat
npm --prefix 01_frontend\visionflow-web run lint
npm --prefix 01_frontend\visionflow-web run build
py -3 -m unittest scripts.tests.test_visionflow_system_traceability_ai_model_operations_center -v
scripts\run-visionflow-api-audit-ci.bat
```

정상 기준은 Frontend operation 72개와
`ai-model-operations-center-ui-policy: PASS`입니다.
