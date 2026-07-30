# VisionFlow 이관 당일 최종 합격 게이트

## 목적

LG GRAM에서 HP OMEN으로 이동하는 실제 시점을 SOURCE와 TARGET 두 게이트로 나눠
최종 판정합니다.

- SOURCE: LG 출발 직전 패키지·외장 매체·리허설·릴리스 증빙 동일성
- TARGET: HP 활성화 완료 후 READY 체크포인트·최종 릴리스 증빙 동일성

두 게이트 모두 읽기 전용입니다. DB 복원, Docker 기동, GPU 실행, 외장 매체 쓰기를
수행하지 않습니다.

## 반영 파일

```text
C:\VisionFlow-Drone\scripts\visionflow_transfer_day_gate.py
C:\VisionFlow-Drone\scripts\run-visionflow-transfer-day-gate.bat
C:\VisionFlow-Drone\scripts\tests\test_visionflow_transfer_day_gate.py
```

## LG GRAM 안전 검증

```bat
cd /d C:\VisionFlow-Drone
python -m unittest scripts.tests.test_visionflow_transfer_day_gate -v
scripts\run-visionflow-transfer-day-gate.bat plan --role source
scripts\run-visionflow-transfer-day-gate.bat plan --role target
```

정상 결과:

```text
Ran 8 tests
OK
```

SOURCE 계획은 5단계, TARGET 계획은 3단계입니다. 두 계획 모두 마지막에 다음 문장이
표시됩니다.

```text
No file, database, Docker, GPU, or external media was changed.
```

## 1. SOURCE 게이트

먼저 최신 릴리스 증빙에 오프라인 이관 리허설이 포함되도록 다시 생성합니다.

```bat
scripts\run-visionflow-release-gate.bat
scripts\run-visionflow-release-evidence.bat
```

이관 매체 드라이브와 폴더명을 실제 값으로 바꿔 실행합니다.

```bat
scripts\run-visionflow-transfer-day-gate.bat source ^
  --media "E:\VisionFlow-Transfer-Media"
```

정상 상태:

```text
SOURCE_TRANSFER_DAY_GATE_READY_WITH_DEFERRED
```

검사 항목:

1. 최신 최종 이관 패키지와 sidecar·내부 manifest
2. 외장 매체 파일 구성과 패키지 복사본
3. 오프라인 이관 리허설과 원본 패키지
4. 최신 릴리스 증빙 ZIP
5. 네 증적의 SHA-256 동일성

최신 파일이 손상되면 과거 성공 파일로 폴백하지 않습니다. 이 상태를 확인한 뒤 외장
SSD를 안전하게 분리해 HP OMEN으로 이동합니다.

## 2. TARGET 게이트

HP OMEN에서 이관 당일 오케스트레이터가 다음 상태가 될 때까지 진행합니다.

```text
TRANSFER_DAY_READY_WITH_DEFERRED
```

그다음 HP 체크포인트가 포함된 TARGET 릴리스 증빙을 다시 생성합니다. SOURCE의
오프라인 이관 리허설 증빙은 외장 매체의 `evidence` 폴더에 보존되어 있습니다.

```bat
scripts\run-visionflow-release-gate.bat
scripts\run-visionflow-release-evidence.bat
```

TARGET 게이트를 실행합니다.

```bat
scripts\run-visionflow-transfer-day-gate.bat target ^
  --source-release-evidence "E:\VisionFlow-Transfer-Media\evidence\visionflow-release-evidence-{실제시각}.zip"
```

정상 상태:

```text
TARGET_TRANSFER_DAY_GATE_READY_WITH_DEFERRED
```

검사 항목:

1. 최신 HP OMEN READY 체크포인트와 준비·사전점검·활성화 체인
2. 외장 매체의 SOURCE 릴리스 증빙과 HP 활성화 후 TARGET 릴리스 증빙
3. SOURCE 번들에는 오프라인 리허설, TARGET 번들에는 READY 체크포인트가 포함됐는지 확인

## 3. 보고서

```text
artifacts\transfer-day-gate\visionflow-transfer-day-source-gate-{UTC}.json
artifacts\transfer-day-gate\visionflow-transfer-day-source-gate-{UTC}.html
artifacts\transfer-day-gate\visionflow-transfer-day-source-gate-{UTC}.sha256

artifacts\transfer-day-gate\visionflow-transfer-day-target-gate-{UTC}.json
artifacts\transfer-day-gate\visionflow-transfer-day-target-gate-{UTC}.html
artifacts\transfer-day-gate\visionflow-transfer-day-target-gate-{UTC}.sha256
```

특정 보고서 독립 검증:

```bat
scripts\run-visionflow-transfer-day-gate.bat verify ^
  --report artifacts\transfer-day-gate\visionflow-transfer-day-source-gate-{실제시각}.json
```

## 4. BLOCKED 처리

```text
SOURCE_TRANSFER_DAY_GATE_BLOCKED
TARGET_TRANSFER_DAY_GATE_BLOCKED
```

JSON 또는 HTML 보고서의 마지막 `FAILED` 항목을 확인합니다.

- SOURCE의 `release-evidence` 또는 `source-lineage` 실패:
  릴리스 게이트·증빙을 다시 생성한 뒤 SOURCE 게이트 재실행
- TARGET의 `hp-transfer-day-checkpoint` 실패:
  이관 당일 `status` 또는 `resume`으로 READY 상태 확인
- TARGET의 `target-lineage` 실패:
  SOURCE 증빙 파일명을 확인하거나 HP READY 체크포인트 생성 후 TARGET 릴리스 증빙을 다시 생성

## 안전 및 보류 범위

- 보고서에는 프로젝트·외장 매체 절대경로를 기록하지 않습니다.
- 환경값, 운영자 인증 키, 모델 원본을 기록하지 않습니다.
- 스마트폰 실센서 E2E와 HP 모델 정확도·성능 검증은 후속 작업입니다.
- DJI Mini 4 Pro 전용 연동은 3차 프로젝트 범위입니다.
- 게이트 JSON·HTML의 `.sha256` sidecar는 실제 증적이므로 유지합니다.
