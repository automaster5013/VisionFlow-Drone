# VisionFlow 배포 후 `best.pt` 소크 게이트

## 목적

`MODEL_RELEASE_ACTIVATED` 직후 `best.pt`가 고정 영상 부하를 5분 동안 안정적으로
처리하는지 확인합니다. 시작 성공만 확인하는 것이 아니라 다음 항목을 승격 당시 GPU
성능 기준과 비교합니다.

- 실제 입력·처리 FPS
- 메트릭 표본 커버리지
- 프레임 드롭률
- 평균 추론 지연
- 관측 P95 추론 지연
- CUDA 실행과 AI 런타임 상태

## 사전 설정

재현 가능한 영상을 다음 폴더 안에 둡니다.

```text
C:\VisionFlow-Drone\03_ai-server\visionflow-ai\data\dummy\soak.mp4
```

모델 릴리스 `activate`를 실행하기 전에 `.env.docker`의 입력 설정을 실제 파일과
일치시킵니다.

```dotenv
AI_SOURCE_TYPE=DUMMY_VIDEO
AI_DUMMY_VIDEO_PATH=/app/data/dummy/soak.mp4
AI_LOOP_VIDEO=true
AI_REALTIME_PLAYBACK=true
```

호스트 파일 경로와 컨테이너 경로의 파일명이 다르거나, 실행 메트릭의
`sourceType`이 `DUMMY_VIDEO`가 아니면 소크 게이트가 차단됩니다.

## LG GRAM에서 계획과 테스트만 확인

```bat
cd /d C:\VisionFlow-Drone
python -m unittest scripts.tests.test_visionflow_model_soak -v
scripts\run-visionflow-model-soak.bat plan
```

LG GRAM에서는 `run`을 실행하지 않습니다.

## HP OMEN에서 5분 소크 실행

`MODEL_RELEASE_ACTIVATED`가 나온 직후 실행합니다.

```bat
scripts\run-visionflow-model-soak.bat run ^
  --input-file 03_ai-server\visionflow-ai\data\dummy\soak.mp4
```

이 명령은 다음 작업을 수행합니다.

1. 최신 모델 릴리스 실행 보고서와 현재 `best.pt` 재검증
2. `.env.docker`의 고정 영상 설정 확인
3. AI 메트릭 측정 구간 초기화
4. 15초 워밍업 후 300초 GPU 메트릭 수집
5. 새 벤치마크 JSON이 정확히 하나 생성되었는지 확인
6. 승격 당시 후보 성능과 비교
7. JSON·HTML·SHA-256 소크 증적 생성 및 즉시 재검증

정상 결과:

```text
VisionFlow model soak: MODEL_SOAK_PASSED
```

차단 결과:

```text
VisionFlow model soak: MODEL_SOAK_BLOCKED
```

## 소크 결과 확정 및 안전 롤백

소크 명령의 종료 코드와 관계없이, 생성된 최신 소크 증적을 다음 명령으로
확정합니다.

```bat
scripts\run-visionflow-model-soak-decision.bat apply ^
  --confirm ROLLBACK_BLOCKED_MODEL_SOAK
```

`MODEL_SOAK_PASSED`이면 Docker를 변경하지 않고 다음 상태를 생성합니다.

```text
VisionFlow model soak decision: MODEL_RELEASE_STABILIZED
```

`MODEL_SOAK_BLOCKED`이면 검증된 `yolo26n.pt` 롤백 오버레이를 적용하고 기본 인수
테스트까지 실행합니다. 정상적으로 복귀했을 때의 상태는 다음과 같습니다.

```text
VisionFlow model soak decision: MODEL_SOAK_ROLLED_BACK
```

롤백 구성·기동·인수 테스트 중 하나라도 실패하면 다음 상태로 종료됩니다. 이때는
추가 모델 변경을 중단하고 Docker 로그와 결정 보고서를 먼저 확인합니다.

```text
VisionFlow model soak decision: MODEL_SOAK_ROLLBACK_FAILED
```

소크 차단 후 안전하게 롤백된 경우에도 후보 모델 릴리스가 실패한 것이므로 명령
종료 코드는 `1`입니다. `MODEL_RELEASE_STABILIZED`만 종료 코드 `0`입니다.

결정 증적 독립 검증:

```bat
scripts\run-visionflow-model-soak-decision-verify.bat ^
  --report artifacts\model-soak-decision\decision-<UTC>\visionflow-model-soak-decision.json
```

## 모델 릴리스 최종 승인

결정 결과가 생성되면 전체 증적 연결을 다시 확인하고 최소 안전 증빙 ZIP을
생성합니다.

```bat
scripts\run-visionflow-model-release-signoff.bat create
```

정상 최종 상태는 `MODEL_RELEASE_SIGNED_OFF`입니다. 자세한 결과 상태와 증빙 ZIP
구성은 `docs\MODEL_RELEASE_SIGNOFF.md`를 확인하세요.

## 기본 통과 기준

```text
측정 시간             300초 이상
평균 입력 FPS         2.0 이상
입력 대비 처리량      0.90 이상
프레임 드롭률         1.0% 이하
평균 지연 회귀        승격 기준 대비 20% 이하
P95 지연 회귀         승격 기준 대비 25% 이하
메트릭 표본 커버리지  80% 이상
최종 런타임 상태      HEALTHY
실행 장치             CUDA
입력 영상             이름·크기·SHA-256 확인
```

기준을 임의로 완화하기보다는 `MODEL_SOAK_BLOCKED` 보고서의 실패 항목과 AI·Docker
로그를 먼저 확인하세요.

## 기존 벤치마크를 직접 평가

```bat
scripts\run-visionflow-model-soak.bat evaluate ^
  --activation artifacts\model-release\activation-<UTC>\visionflow-model-release-activation.json ^
  --benchmark artifacts\model-soak\measurements\visionflow-ai-benchmark-....json
```

## 결과 독립 검증

```bat
scripts\run-visionflow-model-soak-verify.bat ^
  --report artifacts\model-soak\soak-<UTC>\visionflow-model-soak.json
```

## 안전 범위

- `evaluate`와 `plan`은 완전한 읽기 전용입니다.
- `run`은 AI 프로세스의 성능 메트릭 측정 구간만 초기화합니다.
- 모델, 입력 영상, `.env.docker`, DB, Docker 서비스를 변경하지 않습니다.
- 소크 결정은 통과 시 Docker를 변경하지 않으며, 차단 시에만 명시적 확인 토큰을
  요구한 뒤 검증된 기준 모델 오버레이를 적용합니다.
- 롤백은 모델 가중치와 `.env.docker`를 수정하지 않고 Docker 스택만 재구성합니다.
- 보고서에 영상 원본, 환경값, 운영자 키, 절대 경로를 기록하지 않습니다.
