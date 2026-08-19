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

이번 단계에서는 `DjiSdkBootstrap.kt`의 실기체 WIP에 uploader를 연결하지 않습니다.
실제 Mini 4 Pro camera packet을 확인한 뒤 callback의 byte-array/length 계약과
codec 값을 검증하고 연결합니다.

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
