# VisionFlow LG GRAM → HP OMEN 마이그레이션 핸드오프

## 목적

이 도구는 다음 세 산출물을 최신 파일 기준으로 선택해 교차 검증한 뒤 하나의 안전한 ZIP으로
묶습니다.

- `artifacts/source-release/visionflow-source-release-*.zip`
- `artifacts/release-evidence/visionflow-release-evidence-*.zip`
- `artifacts/machine-readiness/visionflow-machine-baseline-*.json`

최신 파일이 손상됐을 때 이전 파일로 조용히 되돌아가지 않습니다. 최신 파일을 수정하거나 명시적
인수로 정상 파일을 지정해야 합니다.

## 최초 적용 경로

ZIP 안의 파일을 `C:\VisionFlow-Drone`에 같은 상대 경로로 복사합니다.

```text
C:\VisionFlow-Drone\scripts\visionflow_migration_handoff.py
C:\VisionFlow-Drone\scripts\run-visionflow-migration-handoff.bat
C:\VisionFlow-Drone\scripts\run-visionflow-migration-handoff-verify.bat
C:\VisionFlow-Drone\scripts\tests\test_visionflow_migration_handoff.py
C:\VisionFlow-Drone\docs\MIGRATION_HANDOFF.md
```

## LG GRAM에서 최종 생성

패치 반영 후 아래 순서로 최신 산출물을 다시 만듭니다. machine baseline은 자신보다 먼저 생성된
최신 안전 소스 ZIP의 SHA-256을 기록하므로 순서를 바꾸지 않습니다.

```bat
cd /d C:\VisionFlow-Drone
scripts\run-visionflow-release-gate.bat
scripts\run-visionflow-release-evidence.bat
scripts\run-visionflow-source-release.bat
scripts\run-visionflow-machine-profile.bat
scripts\run-visionflow-migration-handoff.bat
```

예상 마지막 출력은 다음과 같습니다.

```text
VisionFlow migration handoff: CREATED
Baseline: BASELINE_READY_WITH_DEFERRED
Bundle: C:\VisionFlow-Drone\artifacts\migration-handoff\visionflow-migration-handoff-....zip
SHA-256: C:\VisionFlow-Drone\artifacts\migration-handoff\visionflow-migration-handoff-....sha256
```

최신 파일 자동 선택 대신 특정 산출물을 고정하려면 다음 인수를 사용합니다.

```bat
scripts\run-visionflow-migration-handoff.bat ^
  --source artifacts\source-release\visionflow-source-release-{TIMESTAMP}.zip ^
  --evidence artifacts\release-evidence\visionflow-release-evidence-{TIMESTAMP}.zip ^
  --baseline artifacts\machine-readiness\visionflow-machine-baseline-{TIMESTAMP}.json
```

## 생성 직후 재검증

`{TIMESTAMP}`를 실제 파일명으로 바꿉니다.

```bat
scripts\run-visionflow-migration-handoff-verify.bat ^
  --bundle artifacts\migration-handoff\visionflow-migration-handoff-{TIMESTAMP}.zip
```

성공 결과:

```text
VisionFlow migration handoff: VERIFIED
```

검증기는 바깥 `.sha256`, 핸드오프 manifest, 포함 파일 SHA-256, 중첩된 소스/증빙 manifest,
세 sidecar, baseline 소스 동일성을 모두 재검증합니다.

## 핸드오프 ZIP 구성

```text
VisionFlow-Handoff/
  README.md
  HANDOFF_MANIFEST.json
  source/
    visionflow-source-release-....zip
    visionflow-source-release-....sha256
  evidence/
    visionflow-release-evidence-....zip
    visionflow-release-evidence-....sha256
  baseline/
    visionflow-machine-baseline-....json
    visionflow-machine-baseline-....sha256
    visionflow-machine-baseline-....html
```

## 의도적으로 포함하지 않는 파일

- MySQL 백업 ZIP과 SQL dump: 릴리스 증빙의 경로·크기·SHA-256만 기록
- `.env`, 비밀값, 인증서: HP OMEN에서 안전하게 재구성
- `best.pt` 등 모델 가중치: 별도 보안 경로로 이관 후 체크섬 기록
- 원본 영상, 탐지 이미지, 대용량 데이터셋

따라서 핸드오프 ZIP만으로 데이터베이스를 복원하거나 GPU 모델을 실행할 수는 없습니다. 검증된
MySQL 백업 원본과 `best.pt`는 각각 별도로 옮겨야 합니다.

## HP OMEN 도착 후

1. 핸드오프 ZIP과 `.sha256`을 함께 복사합니다.
2. 핸드오프 검증기를 실행합니다.
3. `source/`의 소스 ZIP을 작업 폴더에 압축 해제합니다.
4. MySQL 백업 원본의 SHA-256을 `HANDOFF_MANIFEST.json`의
   `verifiedMySqlBackup.sha256`과 비교합니다.
5. `.env.docker.example` 등 예제에서 HP 전용 `.env`를 새로 작성합니다.
6. Docker/NVIDIA Container Toolkit과 GPU 런타임을 준비합니다.
7. 별도 이관한 `best.pt`의 SHA-256을 기록하고 모델 경로를 설정합니다.
8. target 프로필과 baseline 비교를 수행합니다.

target 프로필 예시:

```bat
scripts\run-visionflow-machine-profile.bat ^
  --role target ^
  --expect-gpu ^
  --expect-model ^
  --model 03_ai-server\visionflow-ai\models\best.pt
```

비교 예시:

```bat
scripts\run-visionflow-machine-compare.bat ^
  --baseline artifacts\machine-readiness\visionflow-machine-baseline-{LG_TIMESTAMP}.json ^
  --target artifacts\machine-readiness\visionflow-machine-target-{HP_TIMESTAMP}.json
```

스마트폰 HTTPS 실센서 검증과 HP OMEN GPU/`best.pt` 성능 검증은 현재 보류 상태입니다. DJI Mini
4 Pro 전용 연동은 3차 프로젝트 범위로 유지합니다.

## 개발자 검증

```bat
python -m unittest discover -s scripts\tests -p "test_visionflow_migration_handoff.py" -v
```

이 도구는 입력 파일을 수정하거나 삭제하지 않으며 `artifacts/migration-handoff`에 새 산출물만
생성합니다.
