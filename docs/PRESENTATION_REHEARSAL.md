# VisionFlow 발표 시연 반복 안정성 리허설

발표 운영 게이트가 한 번 통과한 뒤, 영속 데모를 기본 3회 연속 실행해 실제 발표
흐름의 반복 성공률과 단계별 시간을 증명하는 절차입니다.

## 전제 조건

- Docker 통합 서비스가 실행 중이어야 합니다.
- 최신 발표 운영 게이트가 `PRESENTATION_READY_WITH_DEFERRED`여야 합니다.
- `.env.docker`에 VIEWER·OPERATOR·ADMIN 실제 역할 키가 있어야 합니다.
- 선택한 드론에 종료되지 않은 비행 세션이 없어야 합니다.

## 실행 계획 확인

DB나 서비스를 변경하지 않고 계획만 확인합니다.

```bat
py -3 scripts\visionflow_presentation_rehearsal.py plan
```

## 기본 3회 리허설

프로젝트 루트 `C:\VisionFlow-Drone`에서 실행합니다.

```bat
scripts\run-visionflow-presentation-rehearsal.bat
```

드론 ID가 1이 아니라면:

```bat
scripts\run-visionflow-presentation-rehearsal.bat --drone-id 3
```

반복 횟수를 변경하려면 1~10 범위에서 지정합니다.

```bat
scripts\run-visionflow-presentation-rehearsal.bat --runs 5
```

기본 판정 기준:

- 3회 모두 영속 데모 `COMPLETED`
- 세션 로그인·로그아웃, AI·스냅샷·Incident 보고서 포함 필수 10단계 모두 PASS
- 각 회차 전체 30초 이하
- 각 필수 단계 10초 이하
- 한 회차라도 실패하면 즉시 중단

정상 결과:

```text
VisionFlow presentation stability rehearsal: PRESENTATION_REHEARSAL_READY_WITH_DEFERRED
Runs: 3/3 passed
```

각 회차는 MySQL에 새로운 비행 세션, 텔레메트리, AI 탐지, 인시던트와 해결
증적을 생성합니다. 실제 삭제나 초기화 작업은 하지 않습니다.

## 생성 파일

`artifacts\presentation-rehearsal`:

- `visionflow-presentation-rehearsal-<UTC 시각>.json`
- `visionflow-presentation-rehearsal-<UTC 시각>.html`
- `visionflow-presentation-rehearsal-<UTC 시각>.sha256`

보고서에는 회차별 성공 여부, 전체 시간, 필수 단계별 평균·P95·최대 시간이
기록됩니다. 역할 키, 환경변수 값, 인증서 개인키, GPS 원본 좌표와 절대경로는
기록하지 않습니다.

## 독립 재검증

실제 생성된 JSON 파일명을 사용합니다.

```bat
scripts\run-visionflow-presentation-rehearsal-verify.bat --report artifacts\presentation-rehearsal\visionflow-presentation-rehearsal-<UTC 시각>.json
```

정상 결과:

```text
VisionFlow presentation stability rehearsal: VERIFIED
Status: PRESENTATION_REHEARSAL_READY_WITH_DEFERRED
```

재검증기는 다음을 확인합니다.

- 리허설 JSON·HTML의 SHA-256 sidecar
- 원본 발표 운영 게이트의 무결성과 READY 상태
- 각 회차 인수 테스트 JSON의 경로·크기·SHA-256
- 필수 데모 단계와 시간 제한 재평가
- 회차별 결과와 전체 통계·최종 판정 일치

## 실패 시

- `Active flight session exists`: 표시된 세션을 완료·중단하거나 다른
  `--drone-id`를 사용합니다.
- `발표 운영 게이트가 READY가 아닙니다`: 먼저
  `scripts\prepare-visionflow-presentation.bat`을 다시 실행합니다.
- 시간 초과만 발생: 서비스 부하를 확인한 뒤 일시적 이상인지 재실행합니다.
  기준 변경은 발표 환경 성능을 확인한 뒤 명시적으로 지정합니다.

HP OMEN GPU·`best.pt`, 스마트폰 실센서 원본, DJI 전용 연동은 이 리허설에서
실행하지 않으며 기존 보류·범위 외 판정을 유지합니다.
