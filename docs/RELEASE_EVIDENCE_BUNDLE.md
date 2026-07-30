# VisionFlow 2차 프로젝트 릴리스 증빙 번들 가이드

## 1. 목적

릴리스 준비도 통과 결과를 발표 자료나 인수인계 문서와 함께 보관할 수 있는 작은 ZIP으로 만듭니다.
릴리스 게이트가 기록한 원본 크기와 SHA-256을 다시 확인하므로 판정 이후 변경된 증빙은 패키징하지
않습니다.

## 2. 번들 포함·제외 정책

포함 항목:

- 릴리스 준비도 JSON 및 HTML
- `-RunDemo` 자동 인수 테스트 JSON
- 저장공간 감사 JSON
- 격리·복원 리허설 JSON
- LG GRAM AI CPU 벤치마크 JSON
- 유효할 경우 장비·콜드 스타트·이전 준비도 보조 증빙
- 유효할 경우 오프라인 이관 리허설과 HP OMEN 이관 당일 체크포인트
- 증빙 manifest와 번들 README

제외 항목:

- MySQL 백업 ZIP과 SQL 덤프
- `.env` 및 환경·비밀 파일
- AI 모델 `*.pt`, `*.pth`, `*.onnx`
- 이미지와 영상

백업 원본은 포함하지 않지만 릴리스 게이트에서 검증한 상대 경로·크기·SHA-256을 manifest에
기록합니다.

## 3. 반영 파일

| 파일 | 전체 경로 |
|---|---|
| 증빙 생성기 | `C:\VisionFlow-Drone\scripts\visionflow_release_evidence.py` |
| Windows 실행 배치 | `C:\VisionFlow-Drone\scripts\run-visionflow-release-evidence.bat` |
| 단위 테스트 | `C:\VisionFlow-Drone\scripts\tests\test_visionflow_release_evidence.py` |

## 4. 선행 조건

먼저 릴리스 게이트를 실행합니다.

```bat
scripts\run-visionflow-release-gate.bat
```

다음 중 하나가 정상적인 입력 상태입니다.

```text
READY
READY_WITH_DEFERRED
READY_WITH_WARNINGS
```

`BLOCKED` 상태에서는 과거 통과 보고서로 우회하지 않고 최신 차단 원인을 해결해야 합니다.

## 5. 증빙 번들 생성

최신 릴리스 보고서를 자동으로 사용합니다.

```bat
scripts\run-visionflow-release-evidence.bat
```

정상 출력:

```text
VisionFlow release evidence: CREATED
```

생성 파일:

```text
artifacts\release-evidence\visionflow-release-evidence-{시각}.zip
artifacts\release-evidence\visionflow-release-evidence-{시각}.sha256
```

특정 준비도 보고서를 지정할 수도 있습니다.

```bat
scripts\run-visionflow-release-evidence.bat --report artifacts\release-readiness\visionflow-release-readiness-{실제시각}.json
```

## 6. 결과 확인

ZIP을 열어 다음 파일이 있는지 확인합니다.

```text
README.md
evidence-manifest.json
release-readiness/report.json
release-readiness/report.html
evidence/acceptance-demo.json
evidence/storage-audit.json
evidence/retention-recovery-drill.json
evidence/ai-cpu-baseline.json
supplemental/machine-readiness.json
supplemental/cold-start-rehearsal.json
supplemental/transfer-readiness.json
supplemental/offline-transfer-rehearsal.json
supplemental/hp-omen-transfer-day.json
```

`supplemental` 항목은 해당 보고서가 존재하고 원본 검증기를 통과한 경우에만 포함됩니다.
LG GRAM에서는 `hp-omen-transfer-day`가 `DEFERRED`인 것이 정상이며 HP OMEN 활성화가
완료된 뒤 릴리스 증빙을 다시 만들면 포함됩니다. 백업 ZIP, SQL, `.env`, 모델, 이미지,
영상은 없어야 정상입니다.

Windows에서 sidecar 체크섬과 ZIP을 비교할 수 있습니다.

```bat
certutil -hashfile artifacts\release-evidence\visionflow-release-evidence-{실제시각}.zip SHA256
type artifacts\release-evidence\visionflow-release-evidence-{실제시각}.sha256
```

## 7. 도구 자체 테스트

```bat
python -m unittest discover -s scripts\tests -p "test_visionflow_release_evidence.py" -v
python -m compileall scripts\visionflow_release_evidence.py
```

이 번들은 실행 환경 복원용 백업이 아닙니다. 실제 복구에는 별도로 검증된 VisionFlow 백업 ZIP을
사용합니다.
