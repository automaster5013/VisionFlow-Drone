# VisionFlow 발표 성능 판정표

성공한 발표 시연 반복 리허설의 시간 데이터를 읽어 발표 당일 병목과
변동성을 판정하는 읽기 전용 절차입니다. 데모를 다시 실행하거나 DB·서비스를
변경하지 않습니다.

## 분석 실행

프로젝트 루트 `C:\VisionFlow-Drone`에서 실행합니다.

```bat
scripts\run-visionflow-presentation-performance.bat
```

도구는 `artifacts\presentation-rehearsal`의 최신 JSON을 선택하고, 원본
리허설·HTML·SHA-256·인수 증적까지 독립 검증한 뒤 분석합니다. 최신 보고서가
BLOCKED이면 과거 성공 보고서로 자동 후퇴하지 않고 중단합니다.

특정 성공 리허설을 분석하려면 실제 파일명을 지정합니다.

```bat
scripts\run-visionflow-presentation-performance.bat --rehearsal artifacts\presentation-rehearsal\visionflow-presentation-rehearsal-<UTC 시각>.json
```

기본 주의 기준:

- 회차 또는 단계의 최대 시간이 원래 허용 예산의 70% 초과
- 평균 250ms 이상인 항목의 변동계수가 60% 초과
- 평균 250ms 미만인 짧은 단계는 작은 네트워크 흔들림으로 변동계수가
  과장될 수 있어 변동성 주의 판정에서 제외

정상 결과:

```text
VisionFlow presentation performance: PRESENTATION_PERFORMANCE_READY_WITH_DEFERRED
Bottleneck: <가장 느린 단계> (<평균> ms avg)
Run budget usage: <사용률>%
Watch stages: 0
```

`PRESENTATION_PERFORMANCE_REVIEW_REQUIRED`는 기존 리허설 실패를 의미하지
않습니다. 통과 한도 안이지만 발표 전에 확인할 시간 여유 또는 변동성 항목이
있다는 뜻입니다.

## 생성 파일

`artifacts\presentation-performance`:

- `visionflow-presentation-performance-<UTC 시각>.json`
- `visionflow-presentation-performance-<UTC 시각>.html`
- `visionflow-presentation-performance-<UTC 시각>.sha256`

HTML에는 전체 시간 예산 사용률, 가장 느린 단계, 단계별 평균·P95·최대,
단계 비중과 주의 판정이 표시됩니다.

## 독립 재검증

실제 생성된 JSON 파일명을 사용합니다.

```bat
scripts\run-visionflow-presentation-performance-verify.bat --report artifacts\presentation-performance\visionflow-presentation-performance-<UTC 시각>.json
```

정상 결과:

```text
VisionFlow presentation performance: VERIFIED
Status: PRESENTATION_PERFORMANCE_READY_WITH_DEFERRED
```

분석기는 환경변수 값, 역할 키, 인증서 개인키, GPS 원본 좌표와 절대경로를
기록하지 않습니다. HP OMEN GPU·`best.pt`, 스마트폰 실센서, DJI 전용 연동도
실행하지 않습니다.
