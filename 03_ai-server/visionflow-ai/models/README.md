# 모델 파일 위치

기본 CPU 설정은 Ultralytics 공식 `yolo26n.pt` 모델명을 사용합니다. 최초 실행 시 네트워크를 통해 자동으로 내려받을 수 있지만, Docker GPU 모드와 오프라인 발표에서는 반드시 이 폴더에 모델 파일을 미리 준비합니다.

커스텀 모델은 다음처럼 배치할 수 있습니다.

```text
models/best.pt
```

그리고 `.env`를 수정합니다.

```dotenv
AI_MODEL_PATH=models/best.pt
```

Docker GPU 모드에서는 루트 `.env.docker`에 파일명과 프로필만 지정합니다.

```dotenv
AI_MODEL_FILE=best.pt
AI_MODEL_PROFILE=best-gpu
```

모델 파일은 이미지에 포함되지 않고 읽기 전용 `/app/models` 볼륨으로 연결됩니다. 따라서 `best.pt`를 교체할 때 AI 이미지를 다시 만들 필요는 없지만, AI 컨테이너는 재시작해야 합니다.

```bat
scripts\run-visionflow-gpu.bat -ModelFile best.pt
```

시작 전 점검은 파일 존재 여부, 크기, SHA-256, 클래스 목록, PyTorch CUDA 인식 및 GPU 모델 로딩까지 확인합니다. 실행 후에는 다음 API에서도 같은 정보를 볼 수 있습니다.

```text
http://localhost:8000/api/models/status
```
