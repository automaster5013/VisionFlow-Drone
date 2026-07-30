# VisionFlow SHA-256 증적 정리

## 결론

`*.sha256` 파일은 모두 같은 용도가 아닙니다.

| 위치 | 용도 | 개별 삭제 |
|---|---|---|
| 프로젝트 루트의 패치 ZIP 옆 | 다운로드 직후 ZIP 무결성 확인 | 확인을 끝냈다면 가능 |
| `artifacts` 증적 실행 폴더 안 | JSON·HTML·ZIP이 변조되지 않았음을 재검증 | 금지 |

따라서 `del /s *.sha256`처럼 전체를 한 번에 지우면 안 됩니다. 증적
사이드카가 사라지면 릴리스·모델 검증 명령이 정상 파일도 검증할 수
없습니다.

이 도구는 파일을 영구 삭제하지 않습니다. 다음 두 종류만
`artifacts\checksum-quarantine` 아래로 이동합니다.

- 14일 이상 지난 프로젝트 루트의 패치 체크섬
- 종류별 최신 3개를 제외한 14일 이상 된 모델 증적 실행 폴더

모델 증적은 `.sha256` 하나만 옮기지 않고 JSON·HTML·ZIP과 함께 폴더
전체를 이동합니다. 최신 승인 보고서 등 다른 JSON이 참조하는 증적은
정리 후보에서 자동 제외합니다.

## 1. 정리 후보만 확인

전체 체크섬 무결성과 정리 후보를 HTML에서 먼저 보려면 다음 명령을
사용합니다.

```bat
scripts\run-visionflow-evidence-catalog.bat
```

자세한 사용법은 `docs\EVIDENCE_CATALOG.md`에 있습니다.

```bat
cd /d C:\VisionFlow-Drone
scripts\run-visionflow-checksum-retention.bat plan
```

이 명령은 파일을 만들거나 이동하지 않습니다. 정상 결과는 다음 중
하나입니다.

```text
VisionFlow checksum retention: READY
```

`REVIEW_REQUIRED`라면 모델 증적 폴더의 체크섬이 누락·변경되었으므로
격리를 진행하지 말고 출력된 `Broken items`를 먼저 확인합니다.

기본 정책을 바꾸려면 다음처럼 실행할 수 있습니다.

```bat
scripts\run-visionflow-checksum-retention.bat plan --min-age-days 30 --keep-per-family 5
```

루트 패치 체크섬을 검사하지 않으려면
`--exclude-patch-sidecars`를 추가합니다.

## 2. 후보를 복원 가능한 격리소로 이동

후보 목록을 확인한 뒤에만 실행합니다.

```bat
scripts\run-visionflow-checksum-retention.bat apply --confirm QUARANTINE_CHECKSUM_EVIDENCE
```

정상 결과는 `COMPLETED` 또는 정리 대상이 없는 `NO_CANDIDATES`입니다.
실제 이동이 있으면 다음 manifest가 생성됩니다.

```text
artifacts\checksum-quarantine\quarantine-{UTC}\quarantine-manifest.json
```

manifest에는 원래 경로, 크기, SHA-256이 기록됩니다. 이동 도중 문제가
발생하면 이미 이동한 항목을 원위치로 되돌립니다.

## 3. 격리 항목 복원

```bat
scripts\run-visionflow-checksum-retention-restore.bat ^
  --manifest artifacts\checksum-quarantine\quarantine-{실제시각}\quarantine-manifest.json ^
  --confirm RESTORE_CHECKSUM_EVIDENCE
```

복원 전 모든 격리 파일의 크기와 SHA-256을 재검증합니다. 원래 위치에
같은 이름의 파일이나 폴더가 있으면 덮어쓰지 않고 중단합니다.

## 루트 패치 체크섬 분류

- `VERIFIED_REDUNDANT`: 대상 ZIP이 존재하며 기록된 SHA-256과 일치
- `UNVERIFIED_OR_ORPHANED`: ZIP이 이미 없거나 기록과 현재 파일이 다름

두 분류 모두 14일이 지난 경우에만 복원 가능한 격리 대상으로
처리합니다. 프로젝트 증적 폴더의 손상된 체크섬은 자동 격리하지 않고
반드시 `REVIEW_REQUIRED`로 중단합니다.

## 검증

```bat
python -m unittest scripts.tests.test_visionflow_checksum_retention -v
```

정상 결과는 `Ran 11 tests`와 `OK`입니다.
