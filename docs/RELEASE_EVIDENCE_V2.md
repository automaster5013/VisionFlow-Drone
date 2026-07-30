# VisionFlow 최종 릴리스 증거 번들 v2

## 목적

2차 프로젝트의 필수 릴리스 증거와 이전 준비 증거를 한 ZIP에 안전하게 모읍니다. 스마트폰
실센서 설정, HP OMEN GPU·`best.pt`, 강제 CSP·HSTS는 보류 상태로 표시되며 현재 릴리스를
차단하지 않습니다. DJI Mini 4 Pro 연동은 3차 프로젝트 범위입니다.

## 필수 증거

- 통합 acceptance: 서비스, 영속 데모, RBAC, 브라우저 세션·CSRF, 보안 헤더
- 검증된 MySQL 백업 메타데이터
- 저장공간 감사
- 격리·복원 리허설
- LG GRAM CPU AI 벤치마크
- CSP Report-Only 관찰 증거

MySQL 백업 원본은 ZIP에 넣지 않고 경로, 크기, SHA-256만 기록합니다.

## 보조 증거

다음 최신 JSON이 존재하면 sidecar와 정책을 검증한 뒤 포함합니다.

- `artifacts\machine-readiness\visionflow-machine-baseline-*.json`
- `artifacts\cold-start-rehearsal\visionflow-cold-start-rehearsal-*.json`
- `artifacts\transfer-readiness\visionflow-transfer-readiness-*.json`
- `artifacts\transfer-rehearsal\visionflow-transfer-rehearsal-*.json`
- `artifacts\hp-omen-transfer-day\checkpoint-*\visionflow-hp-omen-transfer-day.json`

보조 증거가 없으면 `DEFERRED`로 기록하고 계속 진행합니다. 파일이 존재하지만 체크섬이
불일치하거나 상태가 `BLOCKED`이면 변조·오인 가능성을 막기 위해 번들 생성이 중단됩니다.
오프라인 이관 리허설은 원본 이관 패키지까지 다시 검증하며, HP OMEN 이관 당일 항목은
최신 READY 체크포인트와 연결된 준비·사전점검·활성화 보고서 체인을 검증합니다.

## 실행 순서

프로젝트 루트에서 실행합니다.

```bat
scripts\run-visionflow-release-gate.bat
scripts\run-visionflow-release-evidence.bat
```

정상 결과:

```text
VisionFlow release readiness: READY_WITH_DEFERRED
VisionFlow release evidence: CREATED
Readiness: READY_WITH_DEFERRED
```

생성 파일:

```text
artifacts\release-readiness\visionflow-release-readiness-{시각}.json
artifacts\release-readiness\visionflow-release-readiness-{시각}.html
artifacts\release-evidence\visionflow-release-evidence-{시각}.zip
artifacts\release-evidence\visionflow-release-evidence-{시각}.sha256
```

ZIP에서 확인할 대표 경로:

```text
evidence/acceptance-demo.json
evidence/storage-audit.json
evidence/retention-recovery-drill.json
evidence/ai-cpu-baseline.json
evidence/csp-report-only-observation.json
supplemental/machine-readiness.json
supplemental/cold-start-rehearsal.json
supplemental/transfer-readiness.json
supplemental/offline-transfer-rehearsal.json
supplemental/hp-omen-transfer-day.json
```

보조 경로는 각각 유효한 보고서가 있을 때만 포함됩니다. HP OMEN 이관 전 LG GRAM에서는
`offline-transfer-rehearsal.json`까지만 포함되고 `hp-omen-transfer-day`는 `DEFERRED`가
정상입니다. 이 SOURCE 릴리스 증빙 ZIP은 이관 매체의 `evidence` 폴더에 함께
복사됩니다. HP에서 오프라인 리허설 원본 보고서를 별도로 복사하지 않은 경우 TARGET
합격 게이트가 외장 매체의 SOURCE 번들과 HP에서 새로 만든 TARGET 번들을 각각
검증합니다. 스마트폰의
`SMARTPHONE_E2E_BLOCKED` 보고서는 통과 증거로 포장하지 않고 릴리스 README의 보류 사유로만
남깁니다.

## 자체 검증

```bat
python -m unittest discover -s scripts\tests -p "test_visionflow_release_gate.py" -v
python -m unittest discover -s scripts\tests -p "test_visionflow_release_evidence.py" -v
python -m compileall scripts\visionflow_release_gate.py scripts\visionflow_release_evidence.py
```
