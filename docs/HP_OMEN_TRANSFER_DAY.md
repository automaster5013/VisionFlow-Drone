# VisionFlow HP OMEN 이관 당일 체크포인트 실행

## 목적

외장 이관 매체의 최종 패키지를 새 HP OMEN 작업공간에 준비하고, 수동 파일 배치,
안전 사전점검, DB 복원과 GPU 스택 활성화를 하나의 `resume` 흐름으로 이어갑니다.

각 상태는 다음 경로에 JSON·HTML·SHA-256 체크포인트로 보존됩니다.

```text
C:\VisionFlow-Drone\artifacts\hp-omen-transfer-day\checkpoint-<UTC>\
```

중단 후 `resume`을 다시 실행하면 최신 체크포인트와 연결된 준비·사전점검·활성화
보고서를 독립 검증합니다. 이미 성공한 단계는 반복 실행하지 않습니다.

## LG GRAM에서 안전 검증

다음 명령은 파일, DB, Docker, 서비스를 변경하지 않습니다.

```bat
cd /d C:\VisionFlow-Drone
python -m unittest scripts.tests.test_visionflow_hp_omen_transfer_day -v
scripts\run-visionflow-hp-omen-transfer-day.bat plan
```

정상 결과:

```text
Ran 8 tests
OK
VisionFlow HP OMEN transfer day: PLAN
```

계획은 7단계이며 마지막 줄은 다음과 같아야 합니다.

```text
No file, database, Docker, or service was changed.
```

## 1. 외장 매체에서 새 작업공간 준비

HP OMEN에서 이관 매체 드라이브로 이동합니다. 아래 `E:`와 패키지 파일명은 실제
값으로 바꿉니다. 대상 작업공간은 존재하지 않아야 합니다.

```bat
E:
cd \VisionFlow-Transfer-20260725
tools\scripts\run-visionflow-hp-omen-transfer-day.bat bootstrap ^
  --package "package\visionflow-transfer-package-{실제시각}.zip" ^
  --workspace "C:\VisionFlow-Drone" ^
  --confirm PREPARE_HP_OMEN_WORKSPACE
```

정상 상태:

```text
TRANSFER_DAY_MANUAL_INPUT_REQUIRED
```

패키지 검증, 새 작업공간 추출, 준비 보고서 검증과 첫 체크포인트 생성까지만
수행합니다. DB 복원과 Docker 실행은 하지 않습니다.

## 2. HP 전용 수동 파일 준비

다음 항목을 준비합니다.

1. `.env.docker.example`을 참고한 `C:\VisionFlow-Drone\.env.docker`
2. `C:\VisionFlow-Drone\03_ai-server\visionflow-ai\models\best.pt`
3. NVIDIA 드라이버, Docker Desktop과 `nvidia-smi`
4. 현재 명령 프롬프트의 VIEWER·OPERATOR·ADMIN 인수 테스트 역할 키

```bat
set VISIONFLOW_ACCEPTANCE_VIEWER_KEY=<실제 VIEWER 키>
set VISIONFLOW_ACCEPTANCE_OPERATOR_KEY=<실제 OPERATOR 키>
set VISIONFLOW_ACCEPTANCE_ADMIN_KEY=<실제 ADMIN 키>
```

키 원문을 보고서, 채팅, 화면 캡처에 노출하지 마세요.

## 3. 같은 명령으로 사전점검 재개

```bat
cd /d C:\VisionFlow-Drone
scripts\run-visionflow-hp-omen-transfer-day.bat resume ^
  --workspace "C:\VisionFlow-Drone"
```

정상 상태:

```text
TRANSFER_DAY_ACTIVATION_CONFIRMATION_REQUIRED
```

이 호출은 준비 보고서, `.env.docker`, GPU Compose, `best.pt`, 활성화 스크립트와
세 역할 키의 존재를 확인합니다. DB·Docker·서비스는 변경하지 않습니다.

아직 항목이 부족하면 상태는 다음과 같이 유지됩니다.

```text
TRANSFER_DAY_MANUAL_INPUT_REQUIRED
```

누락 항목을 보완하고 같은 `resume` 명령을 다시 실행합니다.

## 4. 명시적 확인 후 기본 런타임 활성화

이 단계는 실제 MySQL과 영속 증적을 복원하고 GPU Docker 스택을 시작합니다.

```bat
scripts\run-visionflow-hp-omen-transfer-day.bat resume ^
  --workspace "C:\VisionFlow-Drone" ^
  --confirm-activate ACTIVATE_HP_OMEN_WITH_DB_RESTORE
```

정상 상태:

```text
TRANSFER_DAY_READY_WITH_DEFERRED
```

이미 활성화 보고서 생성까지 끝난 뒤 체크포인트 작성 전에 터미널이 중단되었더라도,
다음 `resume`은 성공 보고서를 검증해 READY 체크포인트만 작성합니다. DB 복원이나
Docker 기동을 다시 실행하지 않습니다.

READY 체크포인트가 생성되면 최종 릴리스 증빙을 다시 만들 수 있습니다.

```bat
scripts\run-visionflow-release-gate.bat
scripts\run-visionflow-release-evidence.bat
```

생성된 릴리스 증빙 ZIP에는 다음 경로가 추가됩니다.

```text
supplemental/offline-transfer-rehearsal.json
supplemental/hp-omen-transfer-day.json
```

두 파일은 원본 증적 체인을 독립 검증한 뒤 포함되며 환경값, 운영자 키, 모델 원본은
포함하지 않습니다.

마지막으로 TARGET 합격 게이트를 실행합니다.

```bat
scripts\run-visionflow-transfer-day-gate.bat target ^
  --source-release-evidence "E:\VisionFlow-Transfer-Media\evidence\visionflow-release-evidence-{실제시각}.zip"
```

최종 정상 상태:

```text
TARGET_TRANSFER_DAY_GATE_READY_WITH_DEFERRED
```

상세 절차는 `docs\TRANSFER_DAY_GATE.md`를 참조하세요.

## 5. 현재 상태 확인

```bat
scripts\run-visionflow-hp-omen-transfer-day.bat status ^
  --workspace "C:\VisionFlow-Drone"
```

특정 체크포인트는 다음처럼 독립 검증합니다.

```bat
scripts\run-visionflow-hp-omen-transfer-day.bat verify ^
  --workspace "C:\VisionFlow-Drone" ^
  --report artifacts\hp-omen-transfer-day\checkpoint-{실제시각}\visionflow-hp-omen-transfer-day.json
```

최신 체크포인트가 손상되면 이전 체크포인트로 자동 폴백하지 않고 중단합니다.

## 6. 활성화 실패 상태

활성화가 실패하면 다음 상태가 기록됩니다.

```text
TRANSFER_DAY_RECOVERY_REQUIRED
```

출력된 실제 실패 활성화 보고서로 별도 복구 명령을 실행합니다.

```bat
scripts\run-visionflow-hp-omen-restore.bat recover ^
  --report artifacts\hp-omen-restore\activation-{실제시각}\visionflow-hp-omen-activation.json ^
  --confirm RECOVER_FAILED_HP_OMEN_ACTIVATION
```

복구가 `HP_OMEN_PRE_ACTIVATION_STATE_RECOVERED`로 끝난 후 이관 당일 `resume`을
다시 실행하면 수동 입력 확인 단계부터 안전하게 재개됩니다. 자동 복구는 하지
않습니다.

## 상태표

| 상태 | 의미 | 다음 작업 |
|---|---|---|
| `TRANSFER_DAY_MANUAL_INPUT_REQUIRED` | 수동 HP 파일 또는 키 준비 필요 | 준비 후 `resume` |
| `TRANSFER_DAY_ACTIVATION_CONFIRMATION_REQUIRED` | 안전 사전점검 통과 | 확인 문자열과 `resume` |
| `TRANSFER_DAY_READY_WITH_DEFERRED` | HP 기본 런타임 준비 완료 | 모델 정확도·성능 검증 |
| `TRANSFER_DAY_RECOVERY_REQUIRED` | 활성화 실패 | 명시적 `recover` |

## 안전 원칙

- 기존 작업공간을 덮어쓰거나 자동 삭제하지 않습니다.
- 활성화 확인 문자열 없이는 DB·Docker 변경을 수행하지 않습니다.
- 실패 후 자동 복구하지 않습니다.
- 최신 체크포인트가 손상되면 이전 체크포인트로 폴백하지 않습니다.
- 환경값, 운영자 키, 모델 원본, 절대 경로를 체크포인트에 기록하지 않습니다.
- 스마트폰 실센서 E2E는 별도 후속 작업입니다.
- DJI Mini 4 Pro 전용 연동은 3차 프로젝트 범위입니다.
