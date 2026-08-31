# DJI Android Bridge Encoded Stream Contract

이 문서는 DJI MSDK `ReceiveStreamListener`와 Edge AI 서버 사이의 Phase 3
encoded-video 전송 계약을 고정합니다.

## Runtime path

```text
Mini 4 Pro camera
  -> DJI MSDK ReceiveStreamListener
  -> DjiEncodedStreamUploader
  -> POST /api/ingest/dji/stream
  -> FFmpeg H.264/H.265 decoder
  -> bounded decoded-frame queue
  -> FramePacket(sourceType=DJI_LIVE)
  -> existing YOLO / PPE / Depth / Phase3 Reporter
```

`DjiSdkBootstrap.kt`는 MSDK 등록 성공 시
`DjiCameraStreamBridgeRuntime.start()`를 호출합니다. runtime은 available-camera
listener에서 선택한 camera에 `ReceiveStreamListener`를 연결하고, H.264/H.265
packet을 `DjiEncodedStreamUploader`로 전달합니다. 이 소프트웨어 wiring은
구현됐지만 실제 Mini 4 Pro packet의 byte-array/offset/length, codec 및
Annex-B framing 호환성은 실기체 Gate에서 검증합니다.

## AI runtime

```dotenv
AI_SOURCE_TYPE=DJI_LIVE
AI_DJI_INPUT_MODE=ANDROID_BRIDGE
AI_DJI_BRIDGE_FPS=10.0
AI_DJI_BRIDGE_QUEUE_CAPACITY=8
AI_DJI_BRIDGE_FFMPEG=ffmpeg
AI_DJI_BRIDGE_DECODER_LOG_LEVEL=warning
```

## HTTP contract

```text
POST https://<EDGE_LAN_IP>:3443/api/ingest/dji/stream
  ?droneId=<positive integer>
  &sourceId=<1..100 chars>
  &sessionId=<1..36 chars>
  &codec=H264|H265
```

Headers:

```text
Content-Type: video/h264
# H265:
Content-Type: video/h265
# video/hevc is also accepted by Edge AI.

X-VisionFlow-DJI-Key: <runtime DJI bridge key>
```

Body는 한 camera stream 동안 지속되는 H.264/H.265 elementary-stream bytes입니다.
연결이 끝나면 해당 FFmpeg decoder process도 종료되고, 다음 연결에서 새 decoder가
시작됩니다.

현재 receiver는 FFmpeg의 raw `h264` / `hevc` demuxer를 사용합니다. 실제 MSDK
byte framing이 Annex-B elementary stream과 다른 경우 실기체 Gate에서 framing
normalization을 추가합니다. 소프트웨어 Gate만으로 실제 MSDK framing 호환성을
단정하지 않습니다.

## Backpressure

Android uploader는 encoded bytes를 임의로 drop하지 않습니다. bounded queue가
50ms 안에 비워지지 않으면 현재 stream을 실패 처리해 연결을 종료합니다. H.264/H.265
byte 일부를 조용히 버리는 것보다 stream을 재연결하는 편이 bitstream 무결성에
안전하기 때문입니다.

AI 쪽에서는 FFmpeg가 디코딩한 완전한 영상 프레임만 bounded queue에 넣으며, 이
단계에서는 기존 BrowserUploadSource의 drop-oldest 정책을 재사용합니다. 따라서
AI 추론 지연이 증가할 때 오래된 *decoded frame*은 생략할 수 있지만 encoded bytes
일부를 임의로 생략하지는 않습니다.

## Security / Android network

`VISIONFLOW_DJI_BRIDGE_KEY`와 `X-VisionFlow-DJI-Key`는 Android DJI Bridge
전용 credential입니다. 일반 AI 내부 서비스가 사용하는
`VISIONFLOW_AI_INTERNAL_KEY` / `X-VisionFlow-AI-Key`와 반드시 다른 값을
사용하며 Git에 저장하지 않습니다.

DJI 전용 키는 `/api/ingest/dji/status`와 `/api/ingest/dji/stream`에만
사용합니다. 모델/메트릭/일반 스트림 API에는 기존 AI internal key가 필요합니다.

Android는 `https://<EDGE_LAN_IP>:3443` 경로를 사용하며 cleartext HTTP는
허용하지 않습니다. Debug build에서 mkcert 사용자 CA를 신뢰하는 절차는
`scripts/phase3-dji-simulator/DJI_ANDROID_NETWORK_READINESS.md`를 따릅니다.

## Android runtime configuration

runtime 설정은 MSDK callback과 분리된 저장 계층으로 관리됩니다.
`DjiCameraStreamBridgeRuntime`은 encoded packet을 처음 처리할 때
`DjiBridgeRuntimeConfigStore`의 준비 상태를 확인하고 uploader를 생성합니다.

```text
DjiBridgeRuntimeConfig
  edgeAiBaseUrl = https://<EDGE_LAN_IP>:3443
  droneId       = positive integer
  sourceId      = 1..100 chars

DjiBridgeRuntimeConfigStore
  non-secret profile -> private SharedPreferences
  DJI bridge key     -> Android Keystore AES/GCM encrypted payload
  sessionId          -> private SharedPreferences (1..36 chars)
```

Bridge key는 평문 SharedPreferences, source tree, Gradle property 또는 APK
resource에 저장하지 않습니다. `snapshot()`은 key 존재 여부만 반환하고 secret
값은 반환하지 않습니다.

`createUploader(sessionId)`는 저장된 HTTPS profile과 DJI 전용 key를 조합해
`DjiEncodedStreamUploader`를 생성합니다. 호출자가 sessionId를 전달하면 검증 후
사용하고, 전달하지 않으면 private SharedPreferences에 저장된 sessionId를 사용합니다.

`DjiCameraStreamBridgeRuntime`은 이 config store와 연결돼 있습니다. profile 또는
credential이 준비되지 않았으면 uploader를 시작하지 않고 WAIT marker를 남깁니다.
설정을 갱신하면 현재 uploader를 닫고 다음 encoded packet에서 새 설정으로 다시
생성합니다.

## Scope boundary

이 계약의 DJI 실기체 범위는 encoded-video 전송입니다. 현재 Android bridge에는
MSDK flight-controller telemetry key를 Backend telemetry/event 계약으로 변환해
전송하는 adapter가 포함돼 있지 않습니다. 기존 simulator 또는 Backend telemetry
검증 결과는 DJI 실기체 telemetry 연동 증거가 아니며, 해당 경로는 별도 구현과
실기체 Gate가 필요합니다.

## Hardware WAIT boundary

소프트웨어 Gate가 PASS해도 아래 항목은 실기체 검증 전까지 WAIT입니다.

```text
MSDK_REGISTER_SUCCESS
Product connected
MSDK_CAMERA_AVAILABLE
MSDK_ENCODED_STREAM_FIRST
MSDK_ENCODED_STREAM_PROGRESS
actual MSDK byte framing -> FFmpeg decode
actual latency / reconnect / cleartext-or-HTTPS behavior
```
