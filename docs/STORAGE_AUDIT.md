# VisionFlow 저장공간 감사·보존 정책 드라이런

## 1. 목적

VisionFlow는 텔레메트리, 비행 세션, AI 이벤트, 탐지 객체, 인시던트, JPEG 스냅샷,
주석 영상과 자동 검증 보고서를 계속 누적합니다. 이번 패치는 실제 삭제 전에 다음을 확인합니다.

- MySQL 테이블별 추정 행 수와 데이터·인덱스 용량
- 백엔드 스냅샷, AI 출력, 백업, 벤치마크·검증 보고서 용량
- 전체 디스크 여유 공간
- DB가 참조하지만 실제 파일이 없는 스냅샷
- 실제 파일은 있지만 DB가 참조하지 않는 고아 스냅샷
- DB 메타데이터와 실제 파일 크기 불일치
- 보존기간을 넘긴 파일의 **삭제 없는 정리 후보 목록**

스마트폰, GPU, `best.pt`, DJI 기체와 독립적으로 실행할 수 있습니다.

## 2. 반영 파일

저장소 루트가 `C:\VisionFlow-Drone`일 때 다음 새 파일을 복사합니다.

| 파일 | 전체 경로 |
|---|---|
| 감사 본체 | `C:\VisionFlow-Drone\scripts\visionflow_storage_audit.py` |
| Windows 실행기 | `C:\VisionFlow-Drone\scripts\run-visionflow-storage-audit.bat` |
| 단위 테스트 | `C:\VisionFlow-Drone\scripts\tests\test_visionflow_storage_audit.py` |

백엔드, 프런트엔드, AI 서버, migration과 `compose.yaml`은 변경하지 않습니다.

## 3. 기본 실행

Docker 스택의 MySQL이 정상인 상태에서 저장소 루트에서 실행합니다.

```bat
scripts\run-visionflow-storage-audit.bat
```

MySQL이 꺼져 있으면 감사 도구가 MySQL 서비스만 시작합니다. 데이터 삽입·수정·삭제 SQL은
실행하지 않습니다.

결과 위치:

```text
C:\VisionFlow-Drone\artifacts\storage-audit\storage-audit-YYYYMMDDTHHMMSSZ\
```

생성 파일:

- `storage-audit.html`: 브라우저용 요약
- `storage-audit.json`: 전체 판정 및 후속 자동화용 원본
- `storage-categories.csv`: 파일 영역별 용량
- `mysql-table-sizes.csv`: MySQL 테이블별 용량
- `retention-candidates.csv`: 삭제하지 않은 정리 후보

## 4. Docker 없이 파일만 점검

```bat
scripts\run-visionflow-storage-audit.bat --filesystem-only
```

MySQL 테이블과 DB/스냅샷 참조 관계는 제외되고, 로컬 파일·디스크·보존 후보만 보고합니다.

## 5. 기본 보존 정책

기본값:

| 항목 | 후보 조건 |
|---|---|
| AI 출력 영상 | 14일 초과 |
| 백업 ZIP | 30일 초과. 단, 최신 3개는 항상 보호 |
| acceptance/benchmark/model-evaluation 보고서 | 30일 초과 |
| DB 참조 스냅샷 | 자동 정리 대상 아님 |
| 고아 스냅샷 | 경고 목록에만 표시 |

기준을 변경해 다시 계산할 수 있습니다.

```bat
scripts\run-visionflow-storage-audit.bat --ai-output-days 7 --backup-days 60 --report-days 30 --minimum-backups 5
```

어떤 값을 넣어도 이번 도구는 후보만 계산하며 파일과 DB를 삭제하지 않습니다.

## 6. 상태 판정

- `HEALTHY`: 임계값과 스냅샷 참조 관계가 정상
- `WARNING`: 디스크 여유 부족 경고, 관리 파일 용량 초과, 고아·크기 불일치·중복 스냅샷
- `CRITICAL`: 디스크 여유 10% 미만, DB 참조 파일 누락, 안전하지 않은 파일명 참조

기본 디스크 경고는 여유 20% 미만, 위험은 10% 미만입니다. 관리 대상 파일이 10GB를
넘어도 경고합니다.

```bat
scripts\run-visionflow-storage-audit.bat --warning-free-percent 25 --critical-free-percent 12 --warning-managed-gb 20
```

## 7. 자동 검증과 연결

기본 실행은 상태가 `WARNING` 또는 `CRITICAL`이어도 보고서를 생성하고 종료 코드 0을
반환합니다. 자동화에서 위험 상태를 실패로 처리하려면 다음을 사용합니다.

```bat
scripts\run-visionflow-storage-audit.bat --fail-on critical
```

경고까지 실패로 처리:

```bat
scripts\run-visionflow-storage-audit.bat --fail-on warning
```

## 8. 정상 검증 순서

```bat
python -m unittest discover -s scripts\tests -p "test_*.py" -v
python -m compileall scripts\visionflow_storage_audit.py
scripts\run-visionflow-storage-audit.bat
```

정상 조건:

- `storage-audit.html`과 JSON/CSV 보고서가 생성됨
- DB에 스냅샷이 있으면 `databaseReferenceCount`와 실제 파일 수가 비교됨
- `retention.dryRunOnly`가 `true`
- 정리 후보로 나온 원본 파일이 그대로 남아 있음

`WARNING`은 도구 오류가 아니라 점검 결과입니다. `storage-audit.json`의 `issues`와
`retention-candidates.csv`를 확인해야 합니다.

## 9. 다음 단계 입력 자료

첫 전체 감사 후 다음 파일을 제공하면 실제 정리 정책을 안전하게 확정할 수 있습니다.

- `storage-audit.json`
- `retention-candidates.csv`
- 스냅샷 문제가 있으면 `missingFiles`, `unreferencedFiles`, `sizeMismatches` 항목

실제 삭제 기능은 감사 결과와 백업 존재를 확인한 뒤 별도 단계에서 구현합니다.
