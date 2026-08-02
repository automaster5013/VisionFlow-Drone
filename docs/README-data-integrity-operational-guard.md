# VisionFlow 데이터 정합성 운영 가드 연동

기준 커밋: `5e57c1f5450cc6886090c1c18cc02426b9cbee8b`

기존 `VisionFlow AI Operational Guard` 예약 작업이 30분마다 실행될 때 런타임 데이터 정합성 감사를 함께 수행한다. 새 예약 작업을 만들지 않으며, 이미 등록된 작업의 주기와 실행 계정도 바꾸지 않는다.

## 안전 경계

- `scripts/visionflow_data_integrity_audit.py`만 호출한다.
- `scripts/visionflow_data_integrity_repair.py`는 import하거나 실행하지 않는다.
- MySQL 조회는 감사기가 보장하는 `READ ONLY` transaction만 사용한다.
- DB·snapshot·컨테이너·서비스·환경값을 수정하지 않는다.
- 운영자 키·AI 내부 키·MySQL 비밀번호 값을 수집하거나 보고서에 기록하지 않는다.
- 감사 보고서의 `readOnly`와 `safety` 증명을 검증하지 못하면 운영 가드를 `CRITICAL`로 판정한다.

## 판정 연결

| 데이터 정합성 감사 | 운영 가드 |
| --- | --- |
| `DATA_INTEGRITY_HEALTHY` | `HEALTHY` |
| `DATA_INTEGRITY_ADVISORY` | `WARNING` |
| `DATA_INTEGRITY_BLOCKED` | `CRITICAL` |
| 보고서 누락·해석 실패·안전 증명 불일치 | `CRITICAL` |

감사 결과는 각 운영 가드 실행 디렉터리의 `data-integrity` 하위에 JSON·HTML·Markdown으로 함께 보존된다.

```text
artifacts\operational-guard\guard-YYYYMMDD-HHMMSS\
  operational-guard.json
  operational-guard.txt
  data-integrity\
    visionflow-data-integrity-audit.json
    visionflow-data-integrity-audit.html
    visionflow-data-integrity-audit.md
```

## 검증

구문과 상태 연결 단위시험을 실행한다.

```bat
py -3 -m py_compile scripts\visionflow_ai_operational_guard.py scripts\tests\test_visionflow_ai_operational_guard.py
py -3 -m unittest scripts.tests.test_visionflow_ai_operational_guard -v
```

실제 가드를 수동 실행한다. 이 명령은 추론을 생략하지만 읽기 전용 정합성 감사는 수행한다.

```bat
scripts\run-visionflow-ai-operational-guard.bat --root "C:\VisionFlow-Drone" --skip-inference
```

출력에 다음 항목이 있어야 한다.

```text
[HEALTHY] data_integrity: 39개 DB 관계와 5개 snapshot 규칙이 정상입니다.
```

기존 예약 작업을 확인하거나 즉시 실행하려면 다음 명령을 사용한다.

```bat
schtasks /Query /TN "VisionFlow AI Operational Guard" /V /FO LIST
schtasks /Run /TN "VisionFlow AI Operational Guard"
```

예약 실행 결과도 동일한 `artifacts\operational-guard\guard-*` 디렉터리에 남는다. 문제가 발견돼도 자동 복구하지 않으며, 별도 백업·승인·복구 절차를 따른다.
