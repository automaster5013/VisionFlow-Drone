# Phase 3 DJI Software Simulator

실제 DJI Mini 4 Pro나 AWS 없이 VisionFlow-Drone의 **DJI 입력 이후 소프트웨어 경로**를 재현하는 E2E 도구입니다.

## 검증 범위

```text
Flight Session
    ↓
DJI_DEVICE Telemetry
    ↓
Spring Boot → MySQL → Telemetry History
    ↓
DJI_LIVE Phase 3 Event
    ↓
Depth Enrichment
    ↓
Phase 3 Event 조회
    ↓
Evidence JSON
```

Simulator는 실제 MSDK가 보낼 payload와 동일한 Backend contract를 사용합니다.

- `telemetrySource = DJI_DEVICE`
- `sourceDeviceId = phase3-dji-simulator`
- 실제 Flight Session UUID를 `flightSessionId`로 사용
- Phase 3 AI Event는 `sourceType = DJI_LIVE`
- 테스트 Event Key는 `phase3-dji-sim-<UTC timestamp>-<random>` 형식

## 전제 조건

- `visionflow-backend`, `visionflow-mysql` 실행 및 healthy
- 프로젝트 루트 `.env`에 기존 `VISIONFLOW_OPERATOR_KEY` 설정
- Python 3.11+ 권장
- 기본 `droneId=1`이 존재해야 함

Simulator는 인증 키를 출력하지 않습니다.

## 1. 쓰기 없는 사전 점검

```bat
scripts\phase3-dji-simulator\run-phase3-dji-simulator.bat --check-only
```

Backend health, Operator 인증, `droneId` 존재 여부만 확인합니다.

## 2. 기본 E2E 실행

```bat
scripts\phase3-dji-simulator\run-phase3-dji-simulator.bat
```

기본값:

- `droneId=1`
- telemetry 12건
- 250ms 간격
- 서울시청 인근 좌표를 시작점으로 작은 이동 경로 생성

## 3. 샘플 수/간격 지정

```bat
scripts\phase3-dji-simulator\run-phase3-dji-simulator.bat --samples 20 --interval 0.5
```

## Flight Session 안전 정책

- 기존 ACTIVE Flight Session이 없으면 simulator 전용 Session을 생성합니다.
- simulator가 만든 Session은 정상 완료 시 `COMPLETED` 처리합니다.
- 중간 실패 시 simulator가 만든 Session만 best-effort `ABORT` 처리합니다.
- 기존 ACTIVE Session이 이미 있으면 **기본적으로 재사용하며 완료/중단하지 않습니다.**
- 반드시 새 Session으로만 검증하려면:

```bat
scripts\phase3-dji-simulator\run-phase3-dji-simulator.bat --require-new-session
```

## Evidence

성공 시 다음 위치에 JSON Evidence가 생성됩니다.

```text
artifacts/phase3-dji-simulator/<run-id>.json
```

Evidence에는 비밀키가 포함되지 않습니다.

주요 필드:

- `sessionId`
- `telemetrySamplesSent`
- `telemetryHistoryMatched`
- `phase3EventKey`
- `phase3EventId`
- `depthBucket`
- `sessionFinalState`

## 데이터 정리

Simulator가 생성한 telemetry와 Phase 3 Event는 E2E Evidence로 DB에 남습니다. 모든 데이터는 아래 식별자로 구분할 수 있습니다.

```text
sourceDeviceId = phase3-dji-simulator
eventKey       = phase3-dji-sim-...
```

발표용 데이터 정리 시 이 식별자를 기준으로 별도 cleanup을 수행합니다.
