# Phase 3 DJI Android Bridge Robustness Gate

기존 `ANDROID_BRIDGE` 구현을 수정하기 전에 실제 FFmpeg 기반 회귀 테스트로 다음
세 가지를 검증합니다.

```text
1. synthetic H.265/HEVC -> FFmpeg -> DJI_LIVE FramePacket
2. invalid encoded stream 실패 -> decoder 정리 -> 다음 H.264 연결 성공
3. decoded-frame queue 포화 -> encoded byte 손상 없이 오래된 완전 프레임만 drop
```

이 Gate는 실제 DJI 기체를 사용하지 않습니다.

## 실행

기존 Android Bridge Gate가 만든 이미지가 있어야 합니다.

```bat
scripts\phase3-dji-simulator\run-phase3-dji-android-bridge-robustness.bat
```

기본 이미지:

```text
visionflow-ai-server:phase3-android-bridge-v1
```

테스트는 현재 작업트리의 AI 코드와 테스트를 read-only volume으로 mount하므로
Docker image를 다시 build하지 않습니다. FFmpeg와 Python dependency는 기존
검증 이미지에서 사용합니다.

## Backpressure 판정 기준

encoded H.264/H.265 byte 일부를 임의로 버리는 것은 허용하지 않습니다. 이번
software Gate는 Edge AI가 decoder에서 완전한 frame을 만든 뒤 inference queue가
포화될 때 기존 drop-oldest 정책으로 오래된 decoded frame만 생략하는지 확인합니다.

Android `DjiEncodedStreamUploader`의 encoded-byte queue overflow/reconnect 동작은
실제 MSDK packet cadence와 네트워크 환경을 알기 전까지 hardware WAIT 경계로
유지합니다.

## Evidence

```text
artifacts\phase3-dji-android-bridge-robustness\<UTC_RUN_ID>\summary.json
```

PASS해도 다음 항목은 검증된 것으로 간주하지 않습니다.

```text
actual MSDK H.264/H.265 byte framing
actual GOP/SPS/PPS/VPS cadence
actual Android HTTP disconnect/reconnect timing
actual LAN latency
actual uploader encoded-byte overflow
```
