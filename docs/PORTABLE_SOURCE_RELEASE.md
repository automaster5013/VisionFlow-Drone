# VisionFlow 안전 소스 릴리스 및 HP OMEN 이동 가이드

## 1. 목적

현재 LG GRAM 작업공간에서 실행 환경을 그대로 복사하지 않고, 새 장비에서 다시 빌드할 수 있는
소스만 체크섬 기반 ZIP으로 만듭니다. 가상환경·빌드 캐시·실제 설정·데이터·모델을 제외하므로
장비나 Python 설치 경로에 종속되지 않습니다.

이 단계는 HP OMEN에서 GPU나 `best.pt`를 검증하는 단계가 아닙니다. 스마트폰 실센서 검증과 함께
해당 장비가 준비된 뒤 진행합니다. DJI Mini 4 Pro 전용 연동도 계속 3차 프로젝트 범위입니다.

## 2. 포함 범위

- `01_frontend`: Next.js 소스, `package.json`, lock 파일, 설정, `public` 소형 정적 이미지
- `02_backend`: Spring Boot 소스, Gradle 설정·Wrapper, Flyway SQL migration
- `03_ai-server`: Python 앱·테스트·의존성·설정 예시
- 루트 Compose, `.env.example`, README, 라이선스
- `scripts`, `docs`

## 3. 자동 제외 범위

- 실제 `.env`, `.env.local`, `.env.docker` 등 실행 환경파일
- `.git`, `.idea`, `.vscode`
- `.venv`, `venv`, `node_modules`, `.gradle`, `.next`, `build`, `dist`, 캐시
- `artifacts`, `backups`, 런타임 `data`, `logs`, `runs`
- MySQL 덤프·SQLite·CSV·JSONL·Parquet
- `*.pt`, `*.pth`, `*.onnx`, `*.engine`, `*.tflite`
- 런타임 이미지·영상 및 중첩 압축 파일
- 개인키·keystore·credentials·secrets 파일

예외적으로 재구축에 필수인 다음 파일은 포함합니다.

- `02_backend\visionflow-api\gradle\wrapper\gradle-wrapper.jar`
- `02_backend\visionflow-api\src\main\resources\db\migration\*.sql`
- `01_frontend\visionflow-web\public` 아래 2MB 이하 PNG/JPG

## 4. 반영 파일

| 파일 | 전체 경로 |
|---|---|
| 소스 릴리스 생성기 | `C:\VisionFlow-Drone\scripts\visionflow_source_release.py` |
| Windows 실행 배치 | `C:\VisionFlow-Drone\scripts\run-visionflow-source-release.bat` |
| 단위 테스트 | `C:\VisionFlow-Drone\scripts\tests\test_visionflow_source_release.py` |

## 5. 생성 전 검증

릴리스 준비도와 증빙 번들을 먼저 최신 상태로 만들어 둡니다.

```bat
scripts\run-visionflow-release-gate.bat
scripts\run-visionflow-release-evidence.bat
```

Git 작업 상태도 확인합니다. 이 명령은 변경하지 않고 현재 상태만 표시합니다.

```bat
git status --short
```

소스 ZIP에는 커밋되지 않은 파일도 포함될 수 있으므로, 불필요한 임시 소스가 있다면 먼저 직접
정리하거나 이름을 확인합니다.

## 6. 소스 릴리스 생성

저장소 루트에서 실행합니다.

```bat
scripts\run-visionflow-source-release.bat
```

정상 출력:

```text
VisionFlow portable source release: CREATED
```

생성 파일:

```text
artifacts\source-release\visionflow-source-release-{시각}.zip
artifacts\source-release\visionflow-source-release-{시각}.sha256
```

기본 안전 제한:

- 개별 파일 10MB
- 최대 20,000개
- 전체 소스 250MB

고신뢰 API 키·토큰·개인키 서명이 발견되면 해당 파일만 건너뛰지 않고 전체 생성을 중단합니다.
오탐 여부와 파일 내용을 직접 확인한 후 실제 비밀이면 제거·교체하고 다시 실행합니다.

## 7. ZIP 내용 확인

ZIP 최상위에는 다음 폴더가 있습니다.

```text
VisionFlow-Drone\
```

주요 파일:

```text
VisionFlow-Drone\SOURCE_MANIFEST.json
VisionFlow-Drone\README-MIGRATION.md
VisionFlow-Drone\compose.yaml
VisionFlow-Drone\01_frontend\...
VisionFlow-Drone\02_backend\...
VisionFlow-Drone\03_ai-server\...
```

`SOURCE_MANIFEST.json`에는 포함 파일의 상대 경로·크기·SHA-256과 제외된 항목·사유가 기록됩니다.

## 8. HP OMEN 이동 시 사용

HP OMEN이 준비되면 다음 순서로 진행합니다.

1. 소스 ZIP의 sidecar SHA-256을 확인하고 새 작업 폴더에 풉니다.
2. `.env.example`을 기준으로 HP OMEN 전용 `.env.docker`를 새로 만듭니다.
3. 검증된 MySQL 백업 ZIP은 별도의 안전한 경로로 복사하고 복원합니다.
4. 파인튜닝한 `best.pt`는 별도 모델 폴더로 복사하고 체크섬을 기록합니다.
5. Docker와 NVIDIA 드라이버·컨테이너 GPU 환경을 설정합니다.
6. `docker compose --env-file .env.docker up --build -d`를 실행합니다.
7. acceptance, AI 벤치마크, 릴리스 게이트를 HP OMEN에서 다시 실행합니다.

실제 이동 시점에는 GPU 호환 PyTorch·CUDA 조합을 현재 환경 기준으로 다시 확인해야 합니다.

## 9. 도구 자체 테스트

```bat
python -m unittest discover -s scripts\tests -p "test_visionflow_source_release.py" -v
python -m compileall scripts\visionflow_source_release.py
```

이 소스 ZIP은 데이터베이스와 모델을 포함하지 않으므로 단독으로 완전 복구 백업을 대체하지 않습니다.
