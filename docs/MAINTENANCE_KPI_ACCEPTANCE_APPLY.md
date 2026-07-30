# VisionFlow 정비 KPI 자동 인수 패치

## 적용 위치

이 ZIP을 `C:\VisionFlow-Drone`에 경로 그대로 덮어씁니다.

## 변경 내용

- 기존 정비 비행 게이트 인수 테스트에 30일 KPI 검증을 추가합니다.
- 백엔드와 Next.js 프록시의 KPI 값 및 합계 불변식을 비교합니다.
- `windowDays=0` 요청이 양쪽에서 HTTP 400으로 차단되는지 확인합니다.
- `/maintenance` 렌더링 결과에 KPI 제목이 존재하는지 확인합니다.
- 최신 정비 인수 JSON을 릴리스 준비도의 필수 증빙으로 사용합니다.
- 릴리스 증빙 ZIP에 정비 인수 JSON을 포함합니다.

## 검증 순서

```bat
cd /d C:\VisionFlow-Drone

python -m unittest scripts.tests.test_visionflow_maintenance_acceptance -v
python -m unittest scripts.tests.test_visionflow_release_gate -v
python -m unittest scripts.tests.test_visionflow_release_evidence -v

scripts\run-visionflow-maintenance-acceptance.bat
scripts\run-visionflow-release-gate.bat
scripts\run-visionflow-release-evidence.bat

scripts\run-visionflow-presentation-gate.bat
scripts\run-visionflow-presentation-rehearsal.bat
scripts\run-visionflow-presentation-performance.bat
scripts\run-visionflow-presentation-quick-check.bat
scripts\run-visionflow-presentation-signoff.bat

scripts\run-visionflow-maintenance-presentation-gate.bat
```

정비 인수 테스트를 먼저 실행해야 릴리스 게이트가 최신 정비 증빙을 찾을 수
있습니다. 소스와 릴리스 증빙이 변경되면 이전 발표 게이트·리허설·성능·
퀵체크의 SHA-256 계보는 더 이상 최신 상태가 아니므로 위 순서대로 발표
증적을 다시 생성한 후 정비·발표 통합 게이트를 실행합니다.

## 정상 상태

- 정비 인수: `MAINTENANCE_GATE_READY`
- 정비·발표 통합 게이트:
  `MAINTENANCE_PRESENTATION_GATE_READY_WITH_DEFERRED`
- 릴리스 준비도: `READY_WITH_DEFERRED`

스마트폰 실센서, HP OMEN GPU `best.pt`, DJI Mini 4 Pro 연동은 기존 합의대로
보류 또는 3차 프로젝트 범위로 유지합니다.
