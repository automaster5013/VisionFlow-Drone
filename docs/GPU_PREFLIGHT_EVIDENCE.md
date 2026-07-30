# VisionFlow HP OMEN GPU 사전점검 증적

HP OMEN에서 CUDA, PyTorch, `best.pt`가 실제로 함께 동작하는지를 검증하고 결과를
JSON·HTML·SHA-256으로 보존합니다. 모델 내용, 절대 경로, 운영자 키, 환경변수 값,
GPU 일련번호는 기록하지 않습니다.

## 실행 전

```text
C:\VisionFlow-Drone\03_ai-server\visionflow-ai\models\best.pt
```

위 위치에 파인튜닝 모델을 복사하고 NVIDIA 드라이버와 Docker Desktop을 시작합니다.

## 실행

```bat
cd /d C:\VisionFlow-Drone
scripts\run-visionflow-gpu-preflight.bat -ModelFile best.pt
```

정상 결과:

```text
[PASS] VisionFlow GPU preflight completed.
VisionFlow GPU evidence: GPU_MODEL_READY
```

증적 위치:

```text
artifacts\gpu-readiness\gpu-preflight-<UTC 시각>\
  visionflow-gpu-preflight.json
  visionflow-gpu-preflight.html
  visionflow-gpu-preflight.sha256
```

## 독립 재검증

실제 생성된 JSON 경로를 사용합니다.

```bat
scripts\run-visionflow-gpu-preflight-verify.bat ^
  --report artifacts\gpu-readiness\gpu-preflight-<UTC 시각>\visionflow-gpu-preflight.json
```

정상 결과:

```text
VisionFlow GPU evidence: VERIFIED
Status: GPU_MODEL_READY
```

검증기는 JSON·HTML sidecar뿐 아니라 현재 `models\best.pt`의 크기와 SHA-256도
다시 비교합니다.

## 전체 스택까지 시작

사전점검과 증적 생성이 성공한 뒤에만 다음 옵션을 사용합니다.

```bat
scripts\run-visionflow-gpu-preflight.bat -ModelFile best.pt -StartStack
```

LG GRAM에서는 실제 GPU 명령을 실행하지 않습니다. 코드 단위 테스트만 수행합니다.
