# VisionFlow 스마트폰 E2E 증거 및 장비 준비도 가이드

## 1. 목적

스마트폰 실기기 비행이 실제로 HTTPS 프런트엔드, GPS·방향 센서 텔레메트리, 카메라 기반
AI 이벤트 및 탐지까지 연결되었는지 서버에 저장된 한 비행 세션으로 교차 검증합니다. 성공
증거는 기존 LG GRAM 장비 준비도 프로필의 `smartphone-real-sensor-https` 항목을
`DEFERRED`에서 `PASS`로 전환합니다.

프로필은 다음 개인정보·비밀정보를 기록하지 않습니다.

- Windows 사용자명과 hostname
- 환경변수 이름·값과 `.env` 내용
- GPU 일련번호
- 모델 내용
- 정확한 GPS 좌표와 스마트폰 원본 식별자
- 운영자 키, 브라우저 세션 토큰, 원본 사진·영상

모델을 지정하면 상대 경로·파일 크기·SHA-256만 기록합니다.

## 2. 반영 파일

| 파일 | 전체 경로 |
|---|---|
| 스마트폰 증거 실행기 | `C:\VisionFlow-Drone\scripts\visionflow_mobile_evidence.py` |
| 스마트폰 증거 배치 | `C:\VisionFlow-Drone\scripts\run-visionflow-mobile-evidence.bat` |
| 스마트폰 증거 단위 테스트 | `C:\VisionFlow-Drone\scripts\tests\test_visionflow_mobile_evidence.py` |
| 프로필·비교 실행기 | `C:\VisionFlow-Drone\scripts\visionflow_machine_readiness.py` |
| 프로필 배치 | `C:\VisionFlow-Drone\scripts\run-visionflow-machine-profile.bat` |
| 비교 배치 | `C:\VisionFlow-Drone\scripts\run-visionflow-machine-compare.bat` |
| 단위 테스트 | `C:\VisionFlow-Drone\scripts\tests\test_visionflow_machine_readiness.py` |

## 3. 패치 적용

ZIP을 `C:\VisionFlow-Drone`에 풀어 같은 상대 경로의 파일을 추가 또는 덮어씁니다.
`artifacts`의 기존 비행·인증서 자료와 애플리케이션 소스 파일은 삭제하지 않습니다.

스크립트만 변경되므로 MySQL·백엔드·AI 서버를 다시 빌드할 필요는 없습니다. 증거를 생성할
때는 다음 프로세스가 실행 중이어야 합니다.

- 모바일 HTTPS Next.js: 3000
- Spring Boot 백엔드: 8080
- Python AI 서버: 8000

## 4. 스마트폰 검증 비행 준비

스마트폰에서 실제 비행을 하나 완료합니다.

1. `https://<현재 LAN IP>:3000/operator-login?next=/mobile-flight`로 로그인합니다.
2. 카메라와 위치 권한을 허용합니다.
3. 비행을 시작하고 위치·방향 센서값이 여러 번 전송되도록 10초 이상 유지합니다.
4. YOLO가 탐지할 수 있는 사람 또는 물체를 카메라에 보여 AI 탐지를 1건 이상 만듭니다.
5. 화면에서 비행을 정상 완료합니다.

운영자 보안이 활성화되어 있다면 명령을 실행할 같은 터미널에 기존 acceptance용 OPERATOR 또는
ADMIN 키가 설정되어 있어야 합니다. 키 값은 보고서에 저장되지 않습니다.

```bat
set VISIONFLOW_ACCEPTANCE_OPERATOR_KEY=<실제 OPERATOR 또는 ADMIN 키>
```

`<...>`를 포함한 예시 문구를 그대로 입력하지 말고 실제 키를 사용합니다.

## 5. 스마트폰 E2E 증거 생성

가장 최근의 조건 충족 완료 세션을 자동 선택합니다.

```bat
scripts\run-visionflow-mobile-evidence.bat
```

특정 세션을 검증하려면 화면 또는 API에서 확인한 실제 UUID를 지정합니다.

```bat
scripts\run-visionflow-mobile-evidence.bat --drone-id 1 --session-id 7e39ad3e-9969-455c-b606-a5923c5a122a
```

기본 프런트엔드 URL은
`artifacts\mobile-https\certificates\visionflow-mobile-https.json`의 `mobileUrl`에서
자동으로 읽습니다. LAN IP를 바꿨다면 먼저 다음 명령으로 인증서를 갱신합니다.

```bat
scripts\run-visionflow-mobile-https.bat
```

정상 결과:

```text
VisionFlow smartphone E2E evidence: SMARTPHONE_E2E_PASS
```

생성 파일:

```text
artifacts\mobile-readiness\visionflow-smartphone-e2e-{시각}.json
artifacts\mobile-readiness\visionflow-smartphone-e2e-{시각}.html
artifacts\mobile-readiness\visionflow-smartphone-e2e-{시각}.sha256
```

검증은 GET 요청만 사용하며 데이터베이스를 변경하지 않습니다.

## 6. 장비 준비도에 PASS 반영

스마트폰 증거 생성 직후 다음을 실행합니다.

```bat
scripts\run-visionflow-machine-profile.bat
```

전체 프로필 상태는 GPU·`best.pt`가 아직 보류되어 있으므로 계속
`BASELINE_READY_WITH_DEFERRED`일 수 있습니다. 이는 정상입니다. 최신 JSON의 개별 항목은
다음과 같아야 합니다.

```text
smartphone-real-sensor-https  PASS
gpu-best-model               DEFERRED
dji-mini4-pro                OUT_OF_SCOPE
```

PowerShell에서 최신 프로필을 확인하는 명령:

```powershell
$f=Get-ChildItem artifacts\machine-readiness\visionflow-machine-baseline-*.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$p=Get-Content $f.FullName -Raw | ConvertFrom-Json
$p.deferred | Format-Table key,status,reason -AutoSize
```

스마트폰 증거는 SHA-256 sidecar가 일치하고, 모든 세부 검증이 `PASS`이며, 30일 이내에
생성되었을 때만 장비 프로필에서 인정됩니다.

## 7. 실패 시 확인

- `완료된 스마트폰 비행 세션을 찾지 못했습니다`: 스마트폰 비행을 정상 완료하거나 실제
  `--session-id`를 지정합니다.
- `ai-events` 또는 `ai-detections`만 `BLOCKED`: 탐지 가능한 물체를 보여 새 비행을 완료합니다.
- `mobile-sensor-source` 또는 `orientation-values`가 `BLOCKED`: 스마트폰 위치·동작 센서 권한과
  브라우저 화면의 실센서 상태를 확인합니다.
- HTTPS 메타데이터 오류: `scripts\run-visionflow-mobile-https.bat`를 다시 실행합니다.
- HTTP 401/403: `VISIONFLOW_ACCEPTANCE_OPERATOR_KEY`에 실제 OPERATOR/ADMIN 키를 설정합니다.
- LAN IP 변경 후 인증서 오류: 모바일 HTTPS 인증서를 현재 IP로 재발급하고 스마트폰 신뢰
  상태를 다시 확인합니다.

## 8. LG GRAM 기준선 준비

이번 패치를 설치한 후 안전 소스 ZIP을 다시 생성합니다. 그래야 장비 준비도 실행기도 HP OMEN으로
이동할 소스 manifest에 포함됩니다.

```bat
scripts\run-visionflow-source-release.bat
```

Docker Desktop을 실행합니다. MySQL·백엔드·프런트엔드·AI 서버는 실행 중이면 포트가
`REACHABLE`, 중지되어 있으면 `NOT_REACHABLE`로 기록되지만 기준선 생성을 차단하지 않습니다.

## 9. LG GRAM 기준선 생성

```bat
scripts\run-visionflow-machine-profile.bat
```

현재 정상 상태:

```text
VisionFlow machine readiness: BASELINE_READY_WITH_DEFERRED
```

생성 파일:

```text
artifacts\machine-readiness\visionflow-machine-baseline-{시각}.json
artifacts\machine-readiness\visionflow-machine-baseline-{시각}.html
artifacts\machine-readiness\visionflow-machine-baseline-{시각}.sha256
```

JSON은 Windows PowerShell 5.1에서도 한글을 올바르게 읽을 수 있도록 UTF-8 BOM으로 생성됩니다.
Node.js의 npm은 Windows에서 `npm.cmd` shim을 사용해 검사합니다.

GPU가 없거나 사용하지 않는 LG GRAM에서는 `nvidia-smi`가 `DEFERRED`여도 정상입니다. 필수 도구나
안전 소스 ZIP의 체크섬이 실패하면 `BLOCKED`가 됩니다.

소스 ZIP·`.sha256`과 함께 baseline JSON·`.sha256`을 별도 안전 경로에 보관합니다. HTML은 사람이
읽기 위한 자료이며 비교 입력은 JSON입니다.

## 10. HP OMEN에서 대상 프로필 생성

이 단계는 HP OMEN과 `best.pt`가 준비된 뒤 실행합니다. 지금 LG GRAM에서는 실행하지 않습니다.

1. 안전 소스 ZIP과 sidecar 체크섬을 확인합니다.
2. ZIP의 `VisionFlow-Drone` 폴더를 새 작업공간으로 풉니다.
3. NVIDIA 드라이버, Docker, Java, Node, Python을 설치합니다.
4. `best.pt`를 프로젝트 내부 모델 폴더에 복사합니다.
5. 프로젝트 루트에서 다음을 실행합니다.

```bat
scripts\run-visionflow-machine-profile.bat --role target --expect-gpu --expect-model --model 03_ai-server\visionflow-ai\models\best.pt
```

정상 상태:

```text
VisionFlow machine readiness: TARGET_READY
```

GPU 검사에는 이름·드라이버·메모리만 사용하며 일련번호는 요청하지 않습니다.

## 11. LG와 HP 비교

LG baseline JSON과 `.sha256`을 HP 프로젝트의 `artifacts\machine-readiness` 폴더로 복사합니다.
HP target JSON과 `.sha256`도 같은 폴더에 있어야 합니다.

실제 파일명으로 실행합니다.

```bat
scripts\run-visionflow-machine-compare.bat --baseline artifacts\machine-readiness\visionflow-machine-baseline-{실제시각}.json --target artifacts\machine-readiness\visionflow-machine-target-{실제시각}.json
```

판정:

- `COMPATIBLE`: 소스 manifest와 도구 버전이 일치
- `COMPATIBLE_WITH_VERSION_DIFFERENCES`: 소스는 같고 설치 도구 버전만 다름
- `BLOCKED`: 소스 manifest 불일치, 대상 필수 도구·GPU·모델 누락

버전 차이는 자동 실패가 아닙니다. HP OMEN에서 Docker 빌드와 acceptance·AI 벤치마크를 실행해
실제 호환성을 최종 확인합니다.

## 12. HP 이동 후 기능 검증 순서

```bat
docker compose --env-file .env.docker up --build -d
scripts\run-visionflow-acceptance.bat -RunDemo
scripts\run-visionflow-ai-benchmark.bat
scripts\run-visionflow-release-gate.bat
```

그다음 `best.pt` 정확도 평가와 yolo26n/yolo26m/best.pt 비교를 진행합니다. 스마트폰 E2E
증거는 이번 단계에서 완료하며, DJI Mini 4 Pro는 3차 프로젝트 범위를 유지합니다.

## 13. 도구 자체 테스트

```bat
python -m unittest discover -s scripts\tests -p "test_visionflow_*evidence.py" -v
python -m unittest discover -s scripts\tests -p "test_visionflow_machine_readiness.py" -v
python -m compileall scripts\visionflow_mobile_evidence.py scripts\visionflow_machine_readiness.py
```
