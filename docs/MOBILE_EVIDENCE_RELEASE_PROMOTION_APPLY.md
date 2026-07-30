# VisionFlow 스마트폰 E2E 릴리스 증적 승격 패치

## 목적

`artifacts/mobile-readiness`의 최신 `SMARTPHONE_E2E_PASS` 보고서를
릴리스 준비도, 릴리스 증빙 ZIP, 발표 게이트에 정식 반영합니다.

- 유효한 스마트폰 증적과 SHA-256 sidecar가 있으면 필수 검증 `PASS`
- 증적이 없거나 무효하면 기존처럼 `DEFERRED`
- HP OMEN GPU/best.pt는 계속 `DEFERRED`
- DJI Mini 4 Pro 연동은 계속 `OUT_OF_SCOPE`

## 적용 경로

ZIP을 `C:\VisionFlow-Drone`에 덮어써서 압축 해제합니다.

- `C:\VisionFlow-Drone\scripts\visionflow_release_gate.py`
- `C:\VisionFlow-Drone\scripts\visionflow_release_evidence.py`
- `C:\VisionFlow-Drone\scripts\visionflow_presentation_gate.py`
- `C:\VisionFlow-Drone\scripts\tests\test_visionflow_release_gate.py`
- `C:\VisionFlow-Drone\scripts\tests\test_visionflow_release_evidence.py`
- `C:\VisionFlow-Drone\scripts\tests\test_visionflow_presentation_gate.py`

## 1. 단위 테스트

```bat
cd /d C:\VisionFlow-Drone
python -m unittest scripts.tests.test_visionflow_release_gate scripts.tests.test_visionflow_release_evidence scripts.tests.test_visionflow_presentation_gate -v
```

예상 결과는 `Ran 41 tests`와 `OK`입니다.

## 2. 릴리스 준비도 재생성

```bat
scripts\run-visionflow-release-gate.bat
```

`READY_WITH_DEFERRED`는 정상입니다. 아직 HP OMEN GPU/best.pt와
강제 CSP·HSTS가 보류되어 있기 때문입니다.

최신 JSON에서 스마트폰 항목을 확인합니다.

```bat
powershell -NoProfile -Command "$p=Get-ChildItem '.\artifacts\release-readiness\visionflow-release-readiness-*.json'|Sort-Object LastWriteTime -Descending|Select-Object -First 1; $r=Get-Content -LiteralPath $p.FullName -Raw -Encoding UTF8|ConvertFrom-Json; $r.checks|Where-Object key -eq 'smartphone-real-sensor-https'|Format-List key,status,detail,metrics; $r.deferred|Where-Object key -eq 'smartphone-real-sensor-https'|Format-List"
```

정상 결과:

- `checks`에 `smartphone-real-sensor-https`
- `status : PASS`
- 같은 키가 `deferred`에는 없음

## 3. 새 릴리스 증빙 ZIP 생성

```bat
scripts\run-visionflow-release-evidence.bat
```

생성된 ZIP에는 다음 파일이 포함됩니다.

```text
evidence/smartphone-real-sensor-https.json
```

## 4. 발표 게이트 갱신

릴리스 준비도와 증빙 번들이 새로 만들어진 뒤 기존 발표 게이트 명령을
실행합니다.

```bat
scripts\run-visionflow-presentation-gate.bat
```

스마트폰 항목은 더 이상 발표 게이트의 보류 목록에 나타나지 않습니다.

## 문제 발생 시

스마트폰 항목이 계속 `DEFERRED`라면 가장 최근 모바일 증적이
`SMARTPHONE_E2E_PASS`인지, 같은 이름의 `.sha256` 파일이 존재하는지
확인합니다.

```bat
dir /O-D C:\VisionFlow-Drone\artifacts\mobile-readiness\visionflow-smartphone-e2e-*
```

이번 실센서 증적의 기본 유효 기간은 30일입니다. 오래된 경우 스마트폰
비행을 다시 실행한 뒤 `scripts\run-visionflow-mobile-evidence.bat`로
증적을 갱신합니다.
