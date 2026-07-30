# VisionFlow 스마트폰 실센서 증적 안정화 패치

## 변경 파일

- `scripts/visionflow_mobile_evidence.py`
  - `--drone-id`를 생략하면 `/api/drones`에서 전체 등록 드론을 조회합니다.
  - 전체 드론의 완료 세션을 수집하고 `startedAt`, `endedAt` 기준 최신 세션을 선택합니다.
  - 명시적인 `--drone-id`, `--session-id` 사용 방식은 그대로 지원합니다.
  - 실행 결과에 실제 선택된 드론 ID와 세션 UUID를 표시합니다.
- `scripts/tests/test_visionflow_mobile_evidence.py`
  - 전체 드론 중 최신 완료 세션 자동 선택 테스트를 추가합니다.
  - 같은 드론 안에서 최신 세션을 선택하는 테스트를 추가합니다.
  - 드론 ID 정규화 및 빈 목록 검증 테스트를 추가합니다.
- `01_frontend/visionflow-web/src/hooks/use-mobile-drone-sensors.ts`
  - 일시적인 GPS 오류 뒤 정상 좌표를 받으면 상태를 `ACTIVE`로 복구합니다.
  - 정상 좌표 수신 시 이전 GPS 오류 메시지를 제거합니다.
  - 비행 종료 시 센서 오류와 경고를 정리하고 `IDLE`로 전환합니다.

## 해결된 재현 사례

- 실제 성공 세션: 드론 3, 텔레메트리 371건
- 기존 자동 선택 결과: 드론 1, 과거 텔레메트리 5건 세션
- 기존 결과: `SMARTPHONE_E2E_BLOCKED`
- UUID 지정 결과: `SMARTPHONE_E2E_PASS`

패치 후에는 `--drone-id`, `--session-id` 없이 실행해도 전체 드론에서 최신 완료 세션을 선택합니다.
