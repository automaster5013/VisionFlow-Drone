# VisionFlow 프런트엔드 실행 모드 전환

이 도구는 동일한 3000번 포트를 사용하는 두 프런트엔드 실행 방식을 안전하게
구분하고 전환합니다.

- 발표·일반 검증: Docker Compose의 HTTP 프런트엔드
- 스마트폰 실센서: Next.js 개발 서버의 신뢰된 HTTPS 프런트엔드

임의의 프로세스를 자동으로 종료하지 않습니다. 정체를 확인할 수 없는 프로세스가
3000번 포트를 사용하면 PID를 표시하고 중단합니다.

## 적용

ZIP을 `C:\VisionFlow-Drone`에 덮어써서 압축 해제합니다. 기존 파일은 변경하지
않고 다음 파일만 추가됩니다.

```text
scripts\visionflow_runtime_mode.py
scripts\run-visionflow-runtime-mode.bat
scripts\tests\test_visionflow_runtime_mode.py
docs\RUNTIME_MODE_SWITCH.md
```

## 테스트

```bat
cd /d C:\VisionFlow-Drone
python -m unittest scripts.tests.test_visionflow_runtime_mode -v
```

## 현재 상태 확인

```bat
scripts\run-visionflow-runtime-mode.bat status
```

주요 판정:

```text
PRESENTATION_HTTP_READY
MOBILE_HTTPS_READY
FRONTEND_STOPPED
PORT_3000_CONFLICT
```

## 발표·자동 검증용 HTTP 모드

```bat
scripts\run-visionflow-runtime-mode.bat presentation
```

현재 Docker 이미지까지 다시 빌드하려면:

```bat
scripts\run-visionflow-runtime-mode.bat presentation --build
```

정상 결과:

```text
VisionFlow frontend mode: PRESENTATION_HTTP_READY
Dashboard: http://localhost:3000/dashboard
```

## 스마트폰 실센서 HTTPS 모드

```bat
scripts\run-visionflow-runtime-mode.bat mobile
```

이 명령은 Docker의 `frontend-web`만 안전하게 중지한 뒤 기존
`run-visionflow-mobile-https.bat`을 전면 실행합니다. backend, AI, MySQL은
계속 실행됩니다. HTTPS 서버 종료는 같은 창에서 `Ctrl+C`를 누릅니다.

LAN IP를 직접 지정하거나 기존 인증서를 그대로 사용할 수도 있습니다.

```bat
scripts\run-visionflow-runtime-mode.bat mobile --lan-ip 192.168.0.10
scripts\run-visionflow-runtime-mode.bat mobile --skip-setup
```

## HTTPS 종료 후 발표 모드 복원

1. HTTPS 실행 창에서 `Ctrl+C`
2. 다음 명령 실행

```bat
scripts\run-visionflow-runtime-mode.bat presentation
```

HTTP/HTTPS 충돌 상태에서는 프로세스를 강제 종료하지 않고 PID를 표시합니다.
해당 프로세스가 스마트폰 HTTPS 서버인지 확인한 후 원래 실행 창에서 종료하세요.

스마트폰 HTTPS 개발 서버의 첫 화면은 Next.js 컴파일 때문에 수 초가 걸릴 수
있습니다. 상태 확인은 초기 컴파일을 정상적으로 기다릴 수 있도록 프로토콜별 최대
8초까지 응답을 기다립니다.
