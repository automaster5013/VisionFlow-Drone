# Phase 3 DJI Video Replay

실제 DJI Mini 4 Pro를 사용하지 않고 녹화 MP4를 `DJI_LIVE` 입력으로 재생하여
VisionFlow Phase 3 AI → Backend → MySQL 경로를 검증합니다.

## Adapter boundary

```text
DJI_LIVE
├─ REPLAY_FILE       # 현재 구현: MP4 기반 software E2E
└─ ANDROID_BRIDGE    # 다음 단계: DJI MSDK encoded stream
```

Replay는 `DummyVideoSource`의 OpenCV/FPS/loop/pacing 동작을 재사용하지만
FramePacket의 `sourceType`은 `DJI_LIVE`로 유지합니다.

## Safety

- 기존 `visionflow-ai` 컨테이너를 재시작하거나 수정하지 않습니다.
- 기존 compose 파일을 수정하지 않습니다.
- one-off GPU 컨테이너는 `--rm`으로 자동 삭제됩니다.
- Phase 3 Event URL은 Docker 내부의 `visionflow-backend:8080`으로 고정합니다.
- 기존 ACTIVE Flight Session은 재사용하되 complete/abort하지 않습니다.
- Replay가 직접 만든 Flight Session만 complete/abort합니다.

## Unit test

```bat
docker run --rm -e PYTHONPATH=/workspace ^
  -v "C:\VisionFlow-Drone\03_ai-server\visionflow-ai:/workspace:ro" ^
  -w /workspace visionflow-ai-server ^
  python -m pytest tests/test_dji_replay_source.py tests/test_dummy_video_source.py -q -p no:cacheprovider
```

Cmder에서는 한 줄로 실행해도 됩니다.

## E2E

기본 테스트 영상:

```text
03_ai-server/visionflow-ai/data/dummy/sample.mp4
```

실행:

```bat
scripts\phase3-dji-simulator\run-phase3-dji-video-replay.bat
```

다른 MP4:

```bat
scripts\phase3-dji-simulator\run-phase3-dji-video-replay.bat --video "C:\path\test.mp4"
```

영상에 사람/PPE trigger가 없으면 AI frame/PPE 처리는 성공하더라도 E2E는
`NO_PHASE3_EVENT`로 종료됩니다. 이 경우 Evidence를 보존하고 trigger가 포함된
다른 MP4로 재검증합니다.
