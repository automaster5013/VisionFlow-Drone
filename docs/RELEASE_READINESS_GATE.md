# VisionFlow 2차 프로젝트 릴리스 준비도 가이드

## 1. 목적

지금까지 개별적으로 통과한 검증 결과를 한 번에 다시 읽어 2차 프로젝트의 발표·인계 준비 상태를
JSON과 HTML로 만듭니다. `run-visionflow-release-gate.bat`의 판정 자체는 기존 증빙을
읽기만 하며 서비스 호출, 파일 이동·삭제, MySQL 변경을 수행하지 않습니다. 통합 원클릭
실행기는 그 전에 영속 데모 인수 테스트를 새로 실행하므로 검증 데이터가 추가됩니다.

## 2. 필수 판정 항목

| 항목 | 기본 유효기간 | 통과 조건 |
|---|---:|---|
| 통합 자동 인수 테스트 | 48시간 | `-RunDemo -RunRbac -RunSession`, 전체 테스트 통과 |
| VisionFlow 백업 | 7일 | manifest, MySQL 덤프, 크기, SHA-256 정상 |
| 저장공간 감사 | 24시간 | `HEALTHY` 또는 `WARNING`, 삭제 없는 보고서 |
| 격리·복원 리허설 | 24시간 | `PASSED` 또는 `NO_CANDIDATES` |
| LG GRAM AI 기준선 | 30일 | 샘플·처리 프레임·평균 추론 시간 존재 |
| CSP 관찰 증적 | 24시간 | Report-Only·제한 메모리·정제 URL·JSON/CSV/HTML SHA-256 정상 |

`WARNING`은 보고서에 표시되지만 단독으로 릴리스를 차단하지 않습니다. `FAILED` 또는 `MISSING`이
하나라도 있으면 최종 상태는 `BLOCKED`입니다.

## 3. 합의된 비차단 항목

다음 항목은 현재 2차 프로젝트 릴리스를 차단하지 않습니다.

- 스마트폰 실센서·HTTPS 인증서 검증: 스마트폰 수리 및 인증서 준비 후 재검증
- HP OMEN RTX 5060·파인튜닝 `best.pt`: 작업공간 이동과 모델 이식 후 검증
- 강제 CSP·HSTS: 스마트폰 HTTPS 인증서와 HP OMEN AI 주소 확정 후 적용
- DJI Mini 4 Pro 전용 RTSP·기체 종속 코드: 3차 프로젝트 범위

보고서에서는 앞의 세 항목을 `DEFERRED`, DJI 항목을 `OUT_OF_SCOPE`로 표시합니다.

## 4. 반영 파일

| 파일 | 전체 경로 |
|---|---|
| 준비도 생성기 | `C:\VisionFlow-Drone\scripts\visionflow_release_gate.py` |
| Windows 실행 배치 | `C:\VisionFlow-Drone\scripts\run-visionflow-release-gate.bat` |
| 통합 원클릭 실행기 | `C:\VisionFlow-Drone\scripts\run-visionflow-security-release-gate.bat` |
| 단위 테스트 | `C:\VisionFlow-Drone\scripts\tests\test_visionflow_release_gate.py` |

선행 패치의 `C:\VisionFlow-Drone\scripts\visionflow_retention.py`도 필요합니다.

## 5. 증빙 생성 순서

기존 증빙이 유효기간을 지났거나 없는 경우 다음 순서로 새로 생성합니다.

```bat
scripts\run-visionflow-acceptance.bat -RunDemo -RunRbac -RunSession
scripts\run-visionflow-csp-evidence.bat
scripts\run-visionflow-backup.bat
scripts\run-visionflow-storage-audit.bat
```

그다음 최신 감사·백업 경로를 사용해 복구 리허설을 실행합니다.

```bat
scripts\run-visionflow-retention-drill.bat --audit artifacts\storage-audit\storage-audit-{실제시각}\storage-audit.json --backup backups\visionflow-backup-{실제시각}.zip --execute --confirm RUN_RESTORE_DRILL
```

AI 벤치마크 기준선이 30일을 지났다면 다음을 실행합니다.

```bat
scripts\run-visionflow-ai-benchmark.bat
```

## 6. 릴리스 게이트 실행

서비스가 실행 중이고 수락 테스트용 VIEWER·OPERATOR·ADMIN 키 환경변수가 준비되어
있다면 다음 한 명령으로 통합 인수 테스트, CSP 증적 생성, 릴리스 판정을 순서대로
실행합니다.

현재 터미널에 키가 없다면 실제 발급값으로 먼저 설정합니다.

```bat
set VISIONFLOW_ACCEPTANCE_VIEWER_KEY=<발급된 VIEWER 키>
set VISIONFLOW_ACCEPTANCE_OPERATOR_KEY=<발급된 OPERATOR 키>
set VISIONFLOW_ACCEPTANCE_ADMIN_KEY=<발급된 ADMIN 키>
```

```bat
scripts\run-visionflow-security-release-gate.bat
```

기본 드론은 `1`입니다. 다른 드론을 사용하려면 첫 번째 인수로 ID를 지정합니다.

```bat
scripts\run-visionflow-security-release-gate.bat 2
```

선택한 드론에 ACTIVE 비행 세션이 남아 있으면 영속 데모가 안전하게 중단되므로,
실행 전에 해당 세션을 완료하거나 중단해야 합니다.

이 명령의 `-RunDemo` 단계는 검증용 비행·AI 탐지·Incident·SLA·해결·비행 종료
데이터를 MySQL에 추가합니다. 이후 게이트 판정 자체는 읽기 전용입니다.

이미 최신 증적이 존재할 때는 읽기 전용 게이트만 실행합니다.

최신 증빙은 자동 탐색되므로 저장소 루트에서 짧은 명령으로 실행합니다.

```bat
scripts\run-visionflow-release-gate.bat
```

정상적인 현재 결과:

```text
VisionFlow release readiness: READY_WITH_DEFERRED
```

이는 2차 프로젝트 필수 검증은 통과했고, 사전에 합의한 스마트폰, HP OMEN 및
강제 CSP·HSTS 전환이 남아 있다는 뜻입니다. 해당 보류 항목은 `BLOCKED`가 아닙니다.
자동 테스트가 만든 CSP 가상 보고서가 포함된 `CSP_OBSERVATION_REVIEW_REQUIRED`도
`WARNING`으로 표시될 뿐 릴리스를 차단하지 않습니다.

결과 파일:

```text
artifacts\release-readiness\visionflow-release-readiness-{시각}.json
artifacts\release-readiness\visionflow-release-readiness-{시각}.html
```

HTML 파일을 브라우저로 열면 필수 검증, 증빙 경로, 보류 사유를 한 화면에서 확인할 수 있습니다.

## 7. 증빙 경로 직접 지정

자동 탐색 대신 특정 결과를 고정하려면 프로젝트 내부 경로를 지정합니다.

```bat
scripts\run-visionflow-release-gate.bat ^
  --acceptance artifacts\visionflow-acceptance\visionflow-acceptance-{실제시각}.json ^
  --backup backups\visionflow-backup-{실제시각}.zip ^
  --audit artifacts\storage-audit\storage-audit-{실제시각}\storage-audit.json ^
  --drill artifacts\retention-drill\drill-{실제시각}\retention-recovery-drill.json ^
  --benchmark artifacts\ai-benchmark\visionflow-ai-benchmark-{실제시각}.json ^
  --csp artifacts\csp-observability\visionflow-csp-observation-{실제시각}.json
```

각 증빙은 정해진 프로젝트 폴더 밖의 경로를 사용할 수 없습니다.

## 8. `BLOCKED` 해결 순서

생성된 HTML 또는 JSON에서 `FAILED`·`MISSING` 항목만 확인합니다.

1. `acceptance-demo`: 전체 서버 실행 후 `-RunDemo` 재실행
2. `verified-backup`: 새 백업 생성 및 백업 명령 오류 확인
3. `storage-audit`: 새 저장공간 감사 생성
4. `retention-recovery-drill`: 새 감사·백업으로 리허설 재실행
5. `ai-cpu-baseline`: AI 서버와 프런트엔드 실행 후 벤치마크 재실행
6. `csp-report-only-observation`: `scripts\run-visionflow-csp-evidence.bat` 재실행

## 9. 도구 자체 테스트

```bat
python -m unittest discover -s scripts\tests -p "test_visionflow_release_gate.py" -v
python -m compileall scripts\visionflow_release_gate.py
```

이 단계가 통과해도 영구 삭제는 승인되지 않으며, 격리 파일 정리는 별도의 명시적 작업으로 남습니다.
