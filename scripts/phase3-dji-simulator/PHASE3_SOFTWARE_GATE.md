# Phase 3 Software Gate

실기 DJI Mini 4 Pro와 AWS를 제외하고 로컬에서 검증 가능한 Phase 3 DJI
software path를 한 명령으로 회귀 검증합니다.

```bat
scripts\phase3-dji-simulator\run-phase3-software-gate.bat
```

검증 순서:

```text
git diff --check
  -> DJI telemetry/event simulator E2E
  -> negative-path/idempotency regression
  -> deterministic PPE fixture
  -> DJI_LIVE video replay E2E
  -> full AI pytest suite
```

이 Gate는 실제 DJI hardware와 AWS를 사용하지 않습니다. 기존 ACTIVE Flight
Session이 있으면 각 하위 Runner의 안전 규칙에 따라 재사용하며 임의로
complete/abort하지 않습니다.

각 실행은 telemetry와 Phase 3 test event를 DB에 기록할 수 있습니다.
결과와 단계별 로그는 다음에 저장됩니다.

```text
artifacts/phase3-software-gate/<UTC_RUN_ID>/
├── 01.log
├── 02.log
├── 03.log
├── 04.log
├── 05.log
├── 06.log
└── summary.json
```

첫 실패가 발생하면 이후 의존 단계는 `SKIPPED` 처리되어 실제 실패 지점을
명확히 남깁니다.
