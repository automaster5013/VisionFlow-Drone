# VisionFlow 통합 증적 카탈로그

## 목적

프로젝트에 누적된 `*.sha256`과 해당 JSON·HTML·CSV·ZIP의 무결성을
한 번에 확인합니다. 모델 증적 폴더의 누락·손상과 복원 가능한 정리
후보도 함께 보여줍니다.

이 카탈로그는 파생 보고서입니다.

- 원본 증적을 수정하거나 삭제하지 않음
- 새 `*.sha256`을 생성하지 않음
- 매번 같은 JSON·HTML 두 파일만 갱신
- GPU, `best.pt`, 스마트폰, 실행 중인 서버가 필요하지 않음

## 실행

```bat
cd /d C:\VisionFlow-Drone
scripts\run-visionflow-evidence-catalog.bat
```

다음 두 파일이 생성되거나 갱신됩니다.

```text
C:\VisionFlow-Drone\artifacts\evidence-catalog\visionflow-evidence-catalog.json
C:\VisionFlow-Drone\artifacts\evidence-catalog\visionflow-evidence-catalog.html
```

HTML은 브라우저에서 열어 확인할 수 있습니다.

파일을 전혀 만들지 않고 콘솔 검사만 하려면 다음처럼 실행합니다.

```bat
scripts\run-visionflow-evidence-catalog.bat --check-only
```

## 상태 해석

### `HEALTHY`

발견된 체크섬의 대상과 SHA-256이 모두 일치하고 현재 정리 후보가
없습니다.

### `CLEANUP_RECOMMENDED`

다음과 같은 복원 가능한 정리 후보가 있습니다.

- 14일 이상 지난 프로젝트 루트의 패치 체크섬
- 대상 ZIP이 사라진 루트 패치 체크섬
- 종류별 최신 3개를 제외한 오래된 모델 증적 폴더

무결성 오류는 아니므로 명령 종료 코드는 `0`입니다. HTML의 후보를
확인한 다음 필요하면 다음 명령을 사용합니다.

```bat
scripts\run-visionflow-checksum-retention.bat plan
scripts\run-visionflow-checksum-retention.bat apply --confirm QUARANTINE_CHECKSUM_EVIDENCE
```

### `REVIEW_REQUIRED`

`artifacts` 또는 `backups` 내부에서 다음 중 하나가 발견된 상태입니다.

- 체크섬 형식 오류
- 대상 파일 누락
- SHA-256 불일치
- 모델 증적 폴더의 sidecar 누락 또는 파일 목록 불일치

이 상태에서는 명령 종료 코드가 `1`입니다. 해당 파일을 임의 삭제하지
말고 HTML의 경로와 설명을 먼저 확인합니다.

## 보고서에서 확인할 항목

- 체크섬 전체 개수와 검증 완료 개수
- 경고·오류 체크섬
- 체크섬이 보호하는 대상 파일 수와 용량
- 모델 증적 그룹 오류
- 체크섬 정리 후보와 경과 일수

JSON은 UTF-8 BOM으로 기록하므로 Windows PowerShell의
`Get-Content -Encoding UTF8 | ConvertFrom-Json`에서도 한글을 읽을 수
있습니다.

## 검증

```bat
python -m unittest scripts.tests.test_visionflow_evidence_catalog -v
```

정상 결과:

```text
Ran 12 tests
OK
```
