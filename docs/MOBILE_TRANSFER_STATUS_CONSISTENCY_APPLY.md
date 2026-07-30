# VisionFlow 스마트폰 완료·HP 재검증 상태 분리 패치

## 변경 목적

LG GRAM에서 스마트폰 실센서 E2E 검증이 완료됐으므로, 이관 및 프로젝트
종결 보고서에서 해당 기능을 계속 미완료로 표시하지 않도록 정리합니다.

- 완료된 기능 증적: `smartphone-real-sensor-https`
- HP OMEN 이동 후 남은 작업:
  `hp-target-smartphone-https-revalidation`
- HP에서 재검증할 내용: 새 LAN IP, mkcert 인증서, 스마트폰 HTTPS 접속
- 다시 개발하지 않는 내용: GPS·방향 센서·MOBILE_SENSOR 저장 로직

기존 이관 패키지의 예전 키는 프로젝트 종결 보고서에서 새 키로 자동
정규화하므로 이전 증적도 계속 사용할 수 있습니다.

## 적용

ZIP을 `C:\VisionFlow-Drone`에 덮어써서 압축 해제합니다.

변경되는 파일은 모두 `C:\VisionFlow-Drone\scripts` 아래에 있습니다.

## 검증 1: Python 문법

```bat
cd /d C:\VisionFlow-Drone

python -m py_compile scripts\visionflow_hp_omen_transfer_day.py scripts\visionflow_transfer_media.py scripts\visionflow_project_closeout.py scripts\visionflow_transfer_readiness.py scripts\visionflow_hp_omen_restore.py scripts\visionflow_transfer_package.py scripts\visionflow_transfer_rehearsal.py scripts\visionflow_maintenance_presentation_gate.py scripts\visionflow_transfer_day_gate.py scripts\visionflow_cold_start_rehearsal.py scripts\visionflow_migration_handoff.py
```

오류 메시지 없이 프롬프트로 돌아오면 통과입니다.

## 검증 2: 영향 범위 단위 테스트

```bat
python -m unittest scripts.tests.test_visionflow_hp_omen_transfer_day scripts.tests.test_visionflow_transfer_media scripts.tests.test_visionflow_project_closeout scripts.tests.test_visionflow_transfer_readiness scripts.tests.test_visionflow_hp_omen_restore scripts.tests.test_visionflow_transfer_package scripts.tests.test_visionflow_transfer_rehearsal scripts.tests.test_visionflow_maintenance_presentation_gate scripts.tests.test_visionflow_transfer_day_gate scripts.tests.test_visionflow_cold_start_rehearsal scripts.tests.test_visionflow_migration_handoff
```

예상 결과:

```text
Ran 131 tests
OK
```

## 검증 3: 현재 발표 보고서

서비스가 실행 중일 때 다음 명령을 실행합니다.

```bat
scripts\run-visionflow-maintenance-presentation-gate.bat
```

새 JSON의 `deferred`에는 다음 키가 표시됩니다.

```text
hp-target-smartphone-https-revalidation
```

`smartphone-real-sensor-https`가 보류 항목으로 다시 나타나면 안 됩니다.

## HP OMEN 이관 시

이관 패키지와 관련 보고서는 실제 이관 직전에 최신 증적으로 다시
생성합니다. 현재 검증을 위해 MySQL 백업이나 이관 패키지를 다시 만들
필요는 없습니다.

HP OMEN에서 전체 스택이 정상화된 뒤에는 새 LAN IP로 다음 두 명령을
다시 실행하면 됩니다.

```bat
scripts\run-visionflow-mobile-https.bat
scripts\run-visionflow-mobile-https-acceptance.bat
```

그때 `PC_HTTPS_READY`가 나오면
`hp-target-smartphone-https-revalidation`을 완료 처리할 수 있습니다.
