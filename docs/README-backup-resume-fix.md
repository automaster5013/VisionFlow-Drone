# VisionFlow 일관성 백업 서비스 재개 수정

## 수정 대상

`scripts/visionflow_backup.py`

기존 배치 파일 두 개와 Compose 파일은 변경하지 않았습니다.

## 원인

기존 스크립트는 항상 `compose.yaml` 하나만 사용했습니다. `--consistent`
백업 후 서비스를 재개할 때 `docker compose up -d --wait`를 실행했기 때문에,
GPU 오버레이로 만들어진 `visionflow-ai` 컨테이너를 기본 CPU 구성으로
재생성할 수 있었습니다. `mobile-https`가 현재 Compose 구성에서 빠져 고아
컨테이너 경고도 발생했습니다.

## 변경 내용

- 기본적으로 다음 파일을 모두 사용합니다.
  - `compose.yaml`
  - `compose.gpu.yaml` (존재할 때)
  - `compose.mobile-https.yaml` (존재할 때)
- 서비스 중지 전에 병합 Compose 구성을 `docker compose config --quiet`로 검증합니다.
- 백업 후 `up` 대신 `start`를 사용해 기존 컨테이너만 재개합니다.
- 중지 전후 컨테이너 ID가 동일한지 검증합니다.
- 백엔드 → AI → 프론트엔드 순서로 시작하고 각각 health 상태를 기다립니다.
- 백업 ZIP 성공과 서비스 재개 실패를 서로 구분해 보고합니다.
- 백업 manifest에 사용한 Compose 파일과 재개 방식을 기록합니다.
- 필요하면 `--compose-file`을 반복 지정하여 기본 목록을 명시적으로 대체할 수 있습니다.

## 설치

프로젝트 루트 `C:\VisionFlow-Drone`에서 기존 파일을 먼저 보관합니다.

```bat
powershell -NoProfile -Command "Copy-Item -LiteralPath 'C:\VisionFlow-Drone\scripts\visionflow_backup.py' -Destination 'C:\VisionFlow-Drone\scripts\visionflow_backup.py.backup-20260801' -Force"
```

ZIP의 `visionflow_backup.py`를 다음 위치에 덮어씁니다.

```text
C:\VisionFlow-Drone\scripts\visionflow_backup.py
```

## 안전한 재시험

먼저 새 옵션이 표시되는지 확인합니다.

```bat
scripts\run-visionflow-backup.bat --help
```

이후 일관성 백업을 실행합니다.

```bat
scripts\run-visionflow-backup.bat --consistent
```

정상 실행에서는 다음 핵심 출력이 나타납니다.

```text
[COMPOSE] ...compose.yaml, ...compose.gpu.yaml, ...compose.mobile-https.yaml
[PRESERVED] backend-api: container identity unchanged
[PRESERVED] ai-server: container identity unchanged
[PRESERVED] frontend-web: container identity unchanged
[PASS] VisionFlow backup completed
```

마지막으로 상태와 GPU 요청을 확인합니다.

```bat
docker compose ps
docker inspect visionflow-ai --format "{{.State.Status}} / {{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}"
docker inspect visionflow-ai --format "{{json .HostConfig.DeviceRequests}}"
```

`DeviceRequests`에는 `Driver: nvidia`와 `Capabilities: [[gpu]]`가 남아 있어야
합니다. 이번 수정 검증에서는 `restore` 명령을 실행하지 않습니다.

## 되돌리기

스크립트 자체를 되돌릴 필요가 있을 때만 다음을 실행합니다.

```bat
powershell -NoProfile -Command "Copy-Item -LiteralPath 'C:\VisionFlow-Drone\scripts\visionflow_backup.py.backup-20260801' -Destination 'C:\VisionFlow-Drone\scripts\visionflow_backup.py' -Force"
```
