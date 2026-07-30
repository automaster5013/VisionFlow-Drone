# VisionFlow 보존 정책 복구 리허설 가이드

## 1. 목적

이 단계는 보존기간 초과 후보를 잠시 격리한 상태에서도 VisionFlow 핵심 기능이 정상인지 확인하고,
검증 결과와 관계없이 원본 파일을 다시 복원할 수 있는지 연습합니다.

실행 흐름:

```text
감사·백업·후보 재검증 → 임시 격리 → acceptance → 항상 복원 → SHA-256 확인
```

영구 삭제, MySQL 변경, 스마트폰 HTTPS 검증, GPU/`best.pt`, DJI 연동은 포함하지 않습니다.

## 2. 반영 파일

저장소 루트가 `C:\VisionFlow-Drone`일 때 다음 경로로 복사합니다.

| 파일 | 전체 경로 |
|---|---|
| 리허설 실행기 | `C:\VisionFlow-Drone\scripts\visionflow_retention_drill.py` |
| Windows 배치 | `C:\VisionFlow-Drone\scripts\run-visionflow-retention-drill.bat` |
| 단위 테스트 | `C:\VisionFlow-Drone\scripts\tests\test_visionflow_retention_drill.py` |

선행 파일:

```text
scripts\visionflow_retention.py
scripts\run-visionflow-acceptance.bat
```

## 3. 사전 준비

MySQL, Spring Boot, AI 서버, Next.js를 모두 실행하고 기본 인수 테스트가 먼저 통과해야 합니다.

```bat
scripts\run-visionflow-acceptance.bat
```

최근 24시간 이내의 `storage-audit.json`과 최근 7일 이내의 정상 백업 ZIP을 준비합니다.
감사 후 후보 파일을 변경했다면 저장공간 감사를 다시 실행합니다.

## 4. 1차: 계획 모드

먼저 `--execute` 없이 실행합니다.

```bat
scripts\run-visionflow-retention-drill.bat --audit artifacts\storage-audit\storage-audit-{실제시각}\storage-audit.json --backup backups\visionflow-backup-{실제시각}.zip
```

정상 결과:

```text
VisionFlow retention recovery drill: PLAN_COMPLETE
```

후보가 없다면 다음 결과도 정상입니다.

```text
VisionFlow retention recovery drill: NO_CANDIDATES
```

계획 모드에서는 원본 파일을 이동하지 않습니다. 결과 JSON의 `PREFLIGHT` 단계와
`eligibleCount`, `eligibleBytes`를 확인합니다.

## 5. 2차: 실제 격리·복원 리허설

계획 결과와 기본 인수 테스트가 정상일 때만 실행합니다.

```bat
scripts\run-visionflow-retention-drill.bat --audit artifacts\storage-audit\storage-audit-{실제시각}\storage-audit.json --backup backups\visionflow-backup-{실제시각}.zip --execute --confirm RUN_RESTORE_DRILL
```

도구는 다음 순서로 동작합니다.

1. 감사·백업·후보를 다시 검증합니다.
2. 후보를 `artifacts\retention-quarantine` 아래로 격리합니다.
3. `scripts\run-visionflow-acceptance.bat`을 최대 300초 실행합니다.
4. acceptance 성공·실패·예외·시간초과와 관계없이 원위치 복원을 시도합니다.
5. 복원 파일의 크기와 SHA-256을 manifest와 비교합니다.

정상 완료:

```text
VisionFlow retention recovery drill: PASSED
```

결과 위치:

```text
artifacts\retention-drill\drill-{시각}\retention-recovery-drill.json
artifacts\retention-drill\drill-{시각}\acceptance.log
```

## 6. 결과 판정

| 최종 상태 | 의미 | 조치 |
|---|---|---|
| `PASSED` | 격리 상태 acceptance와 원위치 복원 성공 | 다음 단계 진행 가능 |
| `NO_CANDIDATES` | 연습할 보존기간 초과 후보 없음 | 정상 종료 |
| `ACCEPTANCE_FAILED_RESTORED` | 기능 검증은 실패했지만 원본 복원 성공 | 로그 확인 후 문제 수정 |
| `INTERRUPTED_RESTORED` | 사용자 중단 후 원본 복원 성공 | 보고서 확인 후 재실행 |
| `QUARANTINE_FAILED` | 실제 격리 전후 과정 실패 | 감사 보고서를 새로 생성 |
| `RESTORE_FAILED` | 자동 복원 또는 복원 무결성 실패 | 영구 삭제 금지, 수동 복원 수행 |

`RESTORE_FAILED`에서는 다음 manifest를 찾아 기존 복원 배치를 실행합니다.

```bat
scripts\run-visionflow-retention-restore.bat --manifest artifacts\retention-quarantine\retention-{실제시각}\quarantine-manifest.json --confirm RESTORE_FILES
```

프로세스 강제 종료, Windows 재부팅, 전원 차단처럼 Python의 정리 구문이 실행될 수 없는 상황에서도
위 수동 복원 명령을 사용합니다.

## 7. 도구 테스트

```bat
python -m unittest discover -s scripts\tests -p "test_visionflow_retention*.py" -v
python -m compileall scripts\visionflow_retention.py scripts\visionflow_retention_drill.py
```

리허설 통과 후에도 격리 파일의 영구 삭제는 아직 진행하지 않습니다.
