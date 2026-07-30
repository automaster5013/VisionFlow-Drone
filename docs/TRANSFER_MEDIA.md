# VisionFlow HP OMEN 이관 매체 스테이징

## 목적

최종 이관 패키지를 외장 SSD에 수동으로 복사할 때 발생할 수 있는 다음 오류를
차단합니다.

- 잘못된 최신 ZIP 선택
- 패키지 `.sha256` sidecar 누락
- HP OMEN 체크포인트·복원 실행에 필요한 Python·배치 파일 누락
- 복사 중 파일 손상
- `.env`, 운영자 키, 인증서 개인키, 모델 가중치의 의도하지 않은 혼입

이 도구는 최종 이관 패키지의 모든 중첩 manifest와 MySQL 백업을 먼저 검증하고,
존재하지 않는 새 대상 폴더에만 원자적으로 복사한 뒤 복사본을 다시 검증합니다.

## 적용 파일

```text
C:\VisionFlow-Drone\scripts\visionflow_transfer_media.py
C:\VisionFlow-Drone\scripts\run-visionflow-transfer-media.bat
C:\VisionFlow-Drone\scripts\run-visionflow-transfer-media-verify.bat
C:\VisionFlow-Drone\scripts\tests\test_visionflow_transfer_media.py
C:\VisionFlow-Drone\docs\TRANSFER_MEDIA.md
```

## LG GRAM에서 지금 검증

다음 명령은 파일, DB, Docker, 서비스를 변경하지 않습니다.

```bat
cd /d C:\VisionFlow-Drone
python -m unittest scripts.tests.test_visionflow_transfer_media -v
scripts\run-visionflow-transfer-media.bat plan
```

정상 결과:

```text
Ran 15 tests
OK
VisionFlow transfer media: PLAN
```

## 실제 이관 직전 매체 생성

먼저 이관 전 전체 갱신이 성공해야 합니다.

```bat
scripts\run-visionflow-pre-transfer-refresh.bat execute --confirm REFRESH_TRANSFER_CHAIN_WITH_BACKUP
```

최종 패키지의 비파괴 이관 리허설을 수행하고, 그 결과가 포함된 SOURCE 릴리스 증빙을
다시 생성합니다.

```bat
scripts\run-visionflow-transfer-rehearsal.bat execute ^
  --confirm REHEARSE_TRANSFER_MEDIA_TO_FRESH_WORKSPACE
scripts\run-visionflow-release-gate.bat
scripts\run-visionflow-release-evidence.bat
```

외장 SSD가 `D:`이고 `D:\VisionFlow-Transfer-20260725`가 아직 존재하지 않는
새 경로라면 다음처럼 실행합니다.

```bat
scripts\run-visionflow-transfer-media.bat stage ^
  --destination "D:\VisionFlow-Transfer-20260725" ^
  --confirm STAGE_VERIFIED_TRANSFER_MEDIA
```

정상 결과:

```text
VisionFlow transfer media: TRANSFER_MEDIA_READY_WITH_DEFERRED
```

자동 선택은 최신 `artifacts\transfer-package\visionflow-transfer-package-*.zip`을
검증하고, 최신 `artifacts\release-evidence\visionflow-release-evidence-*.zip`과
sidecar도 함께 복사합니다. 최신 파일이 손상됐을 때 과거 파일로 조용히 후퇴하지
않습니다.

특정 패키지를 고정하려면 실제 파일명을 지정합니다.

```bat
scripts\run-visionflow-transfer-media.bat stage ^
  --package "artifacts\transfer-package\visionflow-transfer-package-{실제시각}.zip" ^
  --destination "D:\VisionFlow-Transfer-20260725" ^
  --confirm STAGE_VERIFIED_TRANSFER_MEDIA
```

중괄호가 들어간 예시를 그대로 사용하지 말고 실제 파일명으로 바꾸세요.

## 외장 SSD 복사본 재검증

매체를 분리하기 전에 다음 명령을 실행합니다.

```bat
scripts\run-visionflow-transfer-media-verify.bat ^
  --media "D:\VisionFlow-Transfer-20260725"
```

정상 결과:

```text
VisionFlow transfer media: VERIFIED
Status  : TRANSFER_MEDIA_READY_WITH_DEFERRED
```

HP OMEN에 연결한 뒤에도 같은 검증 명령을 다시 실행하면 복사·이동 중 손상을
확인할 수 있습니다.

오프라인 이관 리허설과 최신 릴리스 증빙 생성까지 끝난 뒤, 외장 SSD를 분리하기 전에
SOURCE 최종 합격 게이트를 실행합니다.

```bat
scripts\run-visionflow-transfer-day-gate.bat source ^
  --media "D:\VisionFlow-Transfer-20260725"
```

정상 상태는 `SOURCE_TRANSFER_DAY_GATE_READY_WITH_DEFERRED`입니다. 자세한 절차는
`docs\TRANSFER_DAY_GATE.md`를 참조하세요.

검증 후 새 작업공간 준비는 매체 루트에서 다음처럼 시작합니다.

```bat
tools\scripts\run-visionflow-hp-omen-transfer-day.bat bootstrap ^
  --package "package\visionflow-transfer-package-{실제시각}.zip" ^
  --workspace "C:\VisionFlow-Drone" ^
  --confirm PREPARE_HP_OMEN_WORKSPACE
```

이후 절차는 `docs\HP_OMEN_TRANSFER_DAY.md`를 참고하세요.

## 실제 외장 SSD 없이 전체 경로 리허설

최종 이관 패키지가 준비된 상태라면 LG GRAM의 시스템 임시 폴더에서 매체
스테이징부터 새 HP 작업공간 준비까지 리허설할 수 있습니다.

```bat
scripts\run-visionflow-transfer-rehearsal.bat execute ^
  --confirm REHEARSE_TRANSFER_MEDIA_TO_FRESH_WORKSPACE
```

DB 복원·Docker·GPU·외장 SSD 쓰기는 수행하지 않으며 임시 데이터는 검증 후
완전히 제거합니다. 자세한 설명은 `docs\TRANSFER_REHEARSAL.md`를 참고하세요.

## 생성 구조

```text
VisionFlow-Transfer-20260725/
  README.md
  TRANSFER_MEDIA_MANIFEST.json
  package/
    visionflow-transfer-package-....zip
    visionflow-transfer-package-....sha256
  evidence/
    visionflow-release-evidence-....zip
    visionflow-release-evidence-....sha256
  tools/
    scripts/
      run-visionflow-hp-omen-transfer-day.bat
      run-visionflow-hp-omen-restore.bat
      run-visionflow-hp-omen-restore-verify.bat
      visionflow_hp_omen_transfer_day.py
      visionflow_hp_omen_restore.py
      visionflow_backup.py
      visionflow_gpu_preflight_evidence.py
      visionflow_machine_readiness.py
      visionflow_migration_handoff.py
      visionflow_transfer_package.py
```

패키지와 릴리스 증빙의 `.sha256`은 이관 중 손상 확인에 필요한 sidecar이므로
유지합니다. 이 단계는 그 외의 새 `.sha256` 파일을 만들지 않습니다. 매체
manifest의 SHA-256은 콘솔에 텍스트로만 표시합니다.

## 안전 정책

- 대상 폴더는 프로젝트 밖에 있어야 하며 기존 경로를 덮어쓰지 않습니다.
- 임시 폴더에서 전체 검증한 뒤 최종 대상 이름으로 한 번에 전환합니다.
- 원본 패키지·sidecar·스크립트를 수정하거나 삭제하지 않습니다.
- `.env*`, 운영자 키, 인증서 개인키, `best.pt`, ONNX·TensorRT 모델을 포함하지
  않습니다.
- 실제 MySQL 백업이 포함되므로 암호화된 외장 SSD나 접근 통제 저장소만 사용합니다.
- 스마트폰 실센서와 HP GPU·`best.pt` 검증은 계속 별도 후속 단계입니다.
- DJI Mini 4 Pro 전용 연동은 3차 프로젝트 범위입니다.
