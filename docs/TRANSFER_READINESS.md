# VisionFlow 최종 이관 Go/No-Go 게이트

## 목적

LG GRAM에서 만든 최신 마이그레이션 핸드오프와 콜드 스타트 복원 리허설 결과를 교차 검증해 HP
OMEN 이동 전 최종 판정을 만듭니다. 이 단계는 파일을 읽고 보고서만 생성하며 외부 전송이나 서버
기동을 수행하지 않습니다.

## 적용 경로

ZIP 안의 파일을 `C:\VisionFlow-Drone`에 같은 상대 경로로 복사합니다.

```text
C:\VisionFlow-Drone\scripts\visionflow_transfer_readiness.py
C:\VisionFlow-Drone\scripts\run-visionflow-transfer-readiness.bat
C:\VisionFlow-Drone\scripts\tests\test_visionflow_transfer_readiness.py
C:\VisionFlow-Drone\docs\TRANSFER_READINESS.md
```

## 실행

```bat
cd /d C:\VisionFlow-Drone
scripts\run-visionflow-transfer-readiness.bat
```

정상 결과:

```text
VisionFlow transfer readiness: TRANSFER_READY_WITH_DEFERRED
JSON report: C:\VisionFlow-Drone\artifacts\transfer-readiness\visionflow-transfer-readiness-....json
HTML report: C:\VisionFlow-Drone\artifacts\transfer-readiness\visionflow-transfer-readiness-....html
SHA-256: C:\VisionFlow-Drone\artifacts\transfer-readiness\visionflow-transfer-readiness-....sha256
```

## 판정 항목

- 핸드오프 ZIP sidecar와 내부 전체 파일 무결성
- 콜드 스타트 JSON sidecar와 HTML 상태 일치
- 콜드 스타트가 최신 핸드오프 ZIP의 SHA-256을 가리키는지 확인
- 핸드오프와 콜드 스타트의 안전 소스 ZIP SHA-256 일치
- 양쪽의 `SOURCE_MANIFEST.json` SHA-256 일치
- 콜드 스타트 상태와 차단 항목 수
- LG baseline 상태
- 릴리스 증빙 준비 상태
- MySQL 백업 원본 미포함 및 체크섬 메타데이터 존재
- Docker·DB·원본 핸드오프를 변경하지 않은 비파괴 리허설 여부
- 콜드 스타트 보고서 생성 후 경과 시간

## 24시간 유효시간

기본적으로 콜드 스타트 보고서는 24시간 이내여야 합니다. 시간이 지났다면 콜드 스타트부터 다시
실행하는 것이 권장됩니다.

```bat
scripts\run-visionflow-cold-start-rehearsal.bat
scripts\run-visionflow-transfer-readiness.bat
```

발표 보관본처럼 의도적으로 유효시간을 늘려야 할 때만 다음 옵션을 사용합니다.

```bat
scripts\run-visionflow-transfer-readiness.bat --max-age-hours 72
```

## 특정 파일 지정

최신 파일 자동 선택 대신 실제 타임스탬프를 지정할 수 있습니다.

```bat
scripts\run-visionflow-transfer-readiness.bat ^
  --handoff artifacts\migration-handoff\visionflow-migration-handoff-{HANDOFF_TIMESTAMP}.zip ^
  --cold-start artifacts\cold-start-rehearsal\visionflow-cold-start-rehearsal-{REHEARSAL_TIMESTAMP}.json
```

최신 파일이 손상됐을 때 이전 파일로 자동 후퇴하지 않습니다. 올바른 파일을 명시하거나 최신
산출물을 다시 생성해야 합니다.

## `BLOCKED`일 때

JSON 보고서의 `checks` 배열에서 `status`가 `BLOCKED`인 항목을 확인합니다. 구조적으로 손상된
ZIP이나 sidecar는 안전상 보고서를 만들지 않고 즉시 실패합니다.

## 보류 및 범위

`TRANSFER_READY_WITH_DEFERRED`는 LG GRAM에서 가능한 이관 준비가 완료됐다는 의미입니다.
다음 항목의 실제 성공을 의미하지는 않습니다.

- HP OMEN에서 Docker 서비스 재구축과 MySQL 복원
- RTX 5060 GPU 및 파인튜닝 `best.pt` 추론
- 수리 후 스마트폰 HTTPS 실센서 연동
- DJI Mini 4 Pro 기체 종속 연동: 3차 프로젝트 범위

## 개발자 테스트

```bat
python -m unittest discover -s scripts\tests -p "test_visionflow_transfer_readiness.py" -v
```
