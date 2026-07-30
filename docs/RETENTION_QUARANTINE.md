# VisionFlow 보존 정책 실행·복구 가이드

> 모델 릴리스 증적 폴더와 프로젝트 루트의 패치 `*.sha256` 정리는
> `docs/CHECKSUM_RETENTION.md`의 전용 도구를 사용합니다. 증적
> 사이드카만 개별 삭제하지 마세요.

## 1. 목적

이 단계는 저장공간 감사에서 계산된 오래된 AI 출력·백업·자동 보고서를 즉시 삭제하지 않고,
프로젝트 내부 격리 폴더로 이동합니다. 스마트폰, GPU, `best.pt`, DJI 기체와 무관합니다.

핵심 안전 원칙:

- 최근 24시간 이내의 저장공간 감사 보고서만 사용
- 최근 7일 이내의 정상 VisionFlow 백업 ZIP 필수
- `CRITICAL` 감사 결과에서는 실행 금지
- 후보 경로·현재 크기·현재 보존기간 재검증
- 최신 보호 백업과 실행에 사용한 안전 백업 격리 금지
- 기본 실행은 드라이런이며 파일 이동 없음
- `--apply --confirm QUARANTINE`이 함께 있어야 격리
- 파일별 SHA-256과 원래 수정 시각 기록
- 이동 실패 시 자동 롤백
- 영구 삭제 기능 없음

## 2. 선행 조건

앞 단계에서 다음 파일이 존재해야 합니다.

```text
scripts\visionflow_backup.py
scripts\visionflow_storage_audit.py
artifacts\storage-audit\storage-audit-{시각}\storage-audit.json
backups\visionflow-backup-{시각}.zip
```

감사 보고서와 백업 ZIP은 현재 프로젝트에서 새로 생성한 실제 경로를 사용합니다.

## 3. 반영 파일

저장소 루트가 `C:\VisionFlow-Drone`일 때 다음 새 파일을 복사합니다.

| 파일 | 전체 경로 |
|---|---|
| 보존 정책 실행기 | `C:\VisionFlow-Drone\scripts\visionflow_retention.py` |
| 드라이런·격리 배치 | `C:\VisionFlow-Drone\scripts\run-visionflow-retention.bat` |
| 격리 복원 배치 | `C:\VisionFlow-Drone\scripts\run-visionflow-retention-restore.bat` |
| 단위 테스트 | `C:\VisionFlow-Drone\scripts\tests\test_visionflow_retention.py` |

백엔드, 프런트엔드, AI, MySQL, migration과 Compose 변경은 없습니다.

## 4. 1차: 격리 계획 드라이런

실제 파일명으로 실행합니다.

```bat
scripts\run-visionflow-retention.bat --audit artifacts\storage-audit\storage-audit-{실제시각}\storage-audit.json --backup backups\visionflow-backup-{실제시각}.zip
```

정상 결과는 후보 존재 여부에 따라 다음 중 하나입니다.

```text
VisionFlow retention: DRY_RUN_COMPLETE
```

```text
VisionFlow retention: NO_CHANGES
```

결과 파일:

```text
artifacts\retention-quarantine\retention-{시각}\retention-plan.json
```

`DRY_RUN_COMPLETE`에서도 원본 파일은 이동되지 않습니다. 다음을 확인합니다.

- `blockedCount`가 0
- 모든 후보의 `status`가 `ELIGIBLE`
- `eligibleBytes`가 예상 범위
- 감사 보고서와 백업 SHA-256이 기록됨

`BLOCKED`, `CHANGED_SIZE`, `TOO_NEW`, `PROTECTED_LATEST_BACKUP`,
`SELECTED_SAFETY_BACKUP` 등이 나오면 파일을 이동하지 말고 저장공간 감사를 다시 실행합니다.

## 5. 2차: 복구 가능한 격리 적용

드라이런 결과를 확인한 후에만 같은 감사·백업 파일로 실행합니다.

```bat
scripts\run-visionflow-retention.bat --audit artifacts\storage-audit\storage-audit-{실제시각}\storage-audit.json --backup backups\visionflow-backup-{실제시각}.zip --apply --confirm QUARANTINE
```

격리 위치:

```text
artifacts\retention-quarantine\retention-{시각}\files\...
```

생성되는 `quarantine-manifest.json`에는 다음이 기록됩니다.

- 원래 상대 경로
- 격리 상대 경로
- 파일 크기와 SHA-256
- 원래 수정 시각과 이동 시각
- 사용한 감사 보고서와 안전 백업

후보가 0개라면 `--apply`를 사용해도 `NO_CHANGES`로 종료되며 이동은 발생하지 않습니다.

## 6. 격리 파일 복원

격리 후 UI·시연·acceptance 검증에서 문제가 발견되면 실제 manifest 경로로 복원합니다.

```bat
scripts\run-visionflow-retention-restore.bat --manifest artifacts\retention-quarantine\retention-{실제시각}\quarantine-manifest.json --confirm RESTORE_FILES
```

복원 전 검증:

- manifest가 프로젝트 격리 폴더 내부인지 확인
- 격리 파일 크기와 SHA-256 확인
- 원래 경로가 다른 파일로 다시 만들어지지 않았는지 확인
- 허용된 `ai-output`, `backups`, 자동 보고서 경로인지 확인

원래 경로가 이미 존재하면 덮어쓰지 않고 전체 복원을 중단합니다. 복원 중 실패하면 복원한
파일을 다시 격리 폴더로 이동하여 롤백합니다.

## 7. 격리 후 검증

```bat
scripts\run-visionflow-acceptance.bat
scripts\run-visionflow-storage-audit.bat
```

확인 항목:

- `/dashboard`, `/drones`, `/demo` 정상
- AI 탐지 스냅샷 정상 표시
- MySQL 테이블과 DB 참조 스냅샷 변화 없음
- 새 저장공간 감사에서 후보와 관리 용량이 예상대로 변경됨
- 격리 manifest가 보존됨

격리 폴더는 같은 디스크에 있으므로 이동만으로 실제 여유 공간이 증가하지 않습니다. 이번
단계의 목적은 안전한 정책 검증입니다. 영구 정리는 시연·acceptance·복원 연습까지 통과한
후 별도 승인 단계에서 진행합니다.

## 8. 도구 자체 테스트

```bat
python -m unittest discover -s scripts\tests -p "test_*.py" -v
python -m compileall scripts\visionflow_retention.py
```

테스트는 드라이런 무변경, 명시적 확인 차단, 변경 후보 전체 차단, 격리·SHA 기록 및 원위치
복원을 검증합니다.
