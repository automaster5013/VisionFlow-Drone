# VisionFlow 오프라인 이관 전체 리허설

## 목적

HP OMEN이나 `best.pt`가 아직 없어도 LG GRAM에서 다음 경로를 실제 파일로 끝까지
검증합니다.

```text
최종 이관 패키지
  → 임시 오프라인 매체 스테이징·재검증
  → 존재하지 않는 새 HP 작업공간 준비·재검증
  → 임시 매체와 작업공간 완전 정리
```

DB 복원, Docker 기동, GPU 실행, 외장 SSD 쓰기는 수행하지 않습니다. 성공·실패
보고서만 `artifacts\transfer-rehearsal`에 남습니다.

## 적용 파일

```text
C:\VisionFlow-Drone\scripts\visionflow_transfer_rehearsal.py
C:\VisionFlow-Drone\scripts\run-visionflow-transfer-rehearsal.bat
C:\VisionFlow-Drone\scripts\run-visionflow-transfer-rehearsal-verify.bat
C:\VisionFlow-Drone\scripts\tests\test_visionflow_transfer_rehearsal.py
C:\VisionFlow-Drone\docs\TRANSFER_REHEARSAL.md
```

선행 단계로 이관 매체 스테이징 패치와 HP OMEN 복원 도구가 적용되어 있어야
합니다.

## 계획 확인

다음 명령은 어떤 파일도 생성하지 않습니다.

```bat
cd /d C:\VisionFlow-Drone
scripts\run-visionflow-transfer-rehearsal.bat plan
```

## 단위 테스트

```bat
python -m unittest scripts.tests.test_visionflow_transfer_rehearsal -v
```

정상 결과:

```text
Ran 11 tests
OK
```

## 전체 리허설 실행

최신 최종 이관 패키지가 존재할 때 실행합니다.

```bat
scripts\run-visionflow-transfer-rehearsal.bat execute ^
  --confirm REHEARSE_TRANSFER_MEDIA_TO_FRESH_WORKSPACE
```

정상 결과:

```text
VisionFlow offline transfer rehearsal: OFFLINE_TRANSFER_REHEARSAL_READY_WITH_DEFERRED
```

특정 패키지를 사용하려면 중괄호 예시를 실제 파일명으로 바꿉니다.

```bat
scripts\run-visionflow-transfer-rehearsal.bat execute ^
  --package "artifacts\transfer-package\visionflow-transfer-package-{실제시각}.zip" ^
  --confirm REHEARSE_TRANSFER_MEDIA_TO_FRESH_WORKSPACE
```

## 독립 재검증

실제 생성된 JSON 파일명을 사용합니다.

```bat
scripts\run-visionflow-transfer-rehearsal-verify.bat ^
  --report "artifacts\transfer-rehearsal\visionflow-transfer-rehearsal-{실제시각}.json"
```

정상 결과:

```text
VisionFlow offline transfer rehearsal: VERIFIED
Status: OFFLINE_TRANSFER_REHEARSAL_READY_WITH_DEFERRED
```

## 실행 단계

1. 최종 이관 패키지·sidecar·중첩 manifest 검증
2. 시스템 임시 폴더에 오프라인 매체 스테이징
3. 임시 매체 복사본 독립 재검증
4. 존재하지 않는 새 HP 작업공간 준비
5. 추출 소스·릴리스 증적·LG baseline·MySQL 백업 교차 검증
6. 임시 매체와 HP 작업공간 완전 정리

최신 패키지가 손상됐을 때 과거 정상본으로 조용히 후퇴하지 않습니다. 중간 단계가
실패하면 이후 검증을 건너뛰고 임시 폴더를 우선 정리한 뒤 실패 보고서를 남깁니다.

## 안전과 보류 범위

- 원본 소스·최종 패키지·백업을 수정하거나 삭제하지 않습니다.
- MySQL 복원과 Docker·GPU 실행을 하지 않습니다.
- 환경값, 운영자 키, 모델 원본을 보고서에 기록하지 않습니다.
- 성공 보고서의 `.sha256`은 JSON·HTML을 묶어 검증하는 필수 sidecar입니다.
- 오래된 리허설 보고서는 기존 체크섬 보존 도구로 그룹 단위 격리할 수 있습니다.
- 스마트폰 실센서와 HP OMEN GPU·`best.pt` 검증은 계속 보류합니다.
- DJI Mini 4 Pro 전용 연동은 3차 프로젝트 범위입니다.
