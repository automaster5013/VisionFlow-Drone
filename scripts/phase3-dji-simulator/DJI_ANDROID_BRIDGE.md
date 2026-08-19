# Phase 3 DJI Android Bridge Software Gate

실제 DJI 기체 없이 다음 경계를 검증합니다.

```text
synthetic raw H.264
  -> FastAPI /api/ingest/dji/stream
  -> FFmpeg decoder
  -> decoded-frame queue
  -> FramePacket(sourceType=DJI_LIVE)
```

Android의 `DjiEncodedStreamUploader.kt`가 Debug APK에 컴파일되는지도 함께
확인합니다.

실행:

```bat
scripts\phase3-dji-simulator\run-phase3-dji-android-bridge-gate.bat
```

Gate는 현재 실행 중인 5개 서비스 컨테이너를 교체하지 않습니다. 별도 로컬 이미지
`visionflow-ai-server:phase3-android-bridge-v1`을 build한 뒤 isolated test
container만 실행합니다.

첫 build 뒤 코드가 바뀌지 않았다면:

```bat
scripts\phase3-dji-simulator\run-phase3-dji-android-bridge-gate.bat --skip-build
```

Evidence:

```text
artifacts\phase3-dji-android-bridge\<UTC_RUN_ID>\summary.json
```

이 Gate가 PASS해도 실제 MSDK byte framing, 실기체 latency/reconnect, Android
network policy는 검증하지 않으며 `physicalDjiRuntime=SKIPPED`로 남습니다.
