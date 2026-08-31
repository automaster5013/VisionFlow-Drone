# Phase 3 DJI Physical Encoded-Stream Gate

이 Gate는 DJI Mini 4 Pro/RC-N2와 Android 기기를 사용해 다음 실제 영상 경로를
통제된 bench test로 검증합니다.

```text
Mini 4 Pro camera
  -> DJI MSDK ReceiveStreamListener
  -> Android DjiEncodedStreamUploader
  -> HTTPS :3443 /api/ingest/dji/stream
  -> Edge AI ANDROID_BRIDGE
  -> FFmpeg H.264/H.265 decode
  -> DJI_LIVE decoded frames
```

## 안전 경계

이 Gate는 모터 시동, 이륙, 비행 제어, gimbal/camera 제어, DJI telemetry 전송,
Backend event 생성 또는 DB 변경을 수행하지 않습니다. 기체를 평평한 곳에 고정하고
가능하면 프로펠러를 분리한 상태에서 전원과 영상 연결만 확인합니다.

기본 실행은 ADB나 네트워크 요청을 실행하지 않고 `WAIT`로 끝납니다.

```bat
scripts\phase3-dji-simulator\run-phase3-dji-physical-stream-gate.bat
```

실기체 실행은 반드시 `--run-device --require-device`를 함께 지정합니다.

## 사전 조건

아래 항목을 먼저 완료합니다.

```text
1. Android arm64 기기 USB debugging 및 ADB authorization
2. VisionFlow DJI Bridge debug APK 설치
3. DJI MSDK_REGISTER_SUCCESS
4. Android debug 기기에 mkcert Root CA 설치
5. 앱에서 현재 Edge PC HTTPS URL, droneId, sourceId, sessionId,
   DJI Bridge 전용 key provisioning 완료
6. Edge PC certificate SAN에 현재 LAN IPv4 포함
7. mobile-https/Caddy와 AI를 DJI_LIVE + ANDROID_BRIDGE profile로 통제 전환
8. .env.docker의 VISIONFLOW_DJI_BRIDGE_KEY와 Android provisioning key 일치
9. network readiness Gate PASS
```

APK 설치와 MSDK 등록은 기존 Gate를 사용합니다.

```bat
scripts\phase3-dji-simulator\run-phase3-dji-msdk-registration-gate.bat --run-device --require-device
scripts\phase3-dji-simulator\run-phase3-dji-provisioning-device-gate.bat --run-device --require-device
```

AI/Caddy 전환은 별도 승인을 받은 통제 절차로 수행합니다. 이 physical stream Gate는
Docker container를 생성·재시작·변경하지 않으며, 실행 중인 HTTPS/AI 상태만 읽습니다.

## RC-N2 / Mini 4 Pro 준비 순서

```text
1. Edge PC와 Android 기기를 같은 신뢰 LAN/Wi-Fi에 연결
2. RC-N2와 Mini 4 Pro의 배터리 확인
3. 기체를 고정하고 모터/이륙 조작 금지
4. Mini 4 Pro 전원 ON
5. RC-N2 전원 ON 후 기체 연결 확인
6. Android 기기를 RC-N2에 데이터 지원 USB 케이블로 연결
7. Android USB accessory 및 ADB authorization 요청 승인
8. Gate 실행
```

현재 Edge PC LAN IPv4가 `192.168.46.7`이고 authorized ADB transport가 하나일 때:

```bat
scripts\phase3-dji-simulator\run-phase3-dji-physical-stream-gate.bat --run-device --require-device --host-ip 192.168.46.7
```

USB/Wireless ADB가 동시에 보이면 serial을 명시합니다.

```bat
scripts\phase3-dji-simulator\run-phase3-dji-physical-stream-gate.bat --run-device --require-device --host-ip 192.168.46.7 --serial <ADB_SERIAL>
```

`.env.docker`가 아닌 runtime env 파일을 사용하는 경우에만 다음 옵션을 추가합니다.

```text
--env-file <non-tracked-runtime-env-file>
```

Bridge key 자체는 command line 인자로 전달하지 않습니다. Gate는 기본적으로 process
environment 또는 runtime env 파일의 `VISIONFLOW_DJI_BRIDGE_KEY`를 읽고 값은 출력하거나
evidence에 기록하지 않습니다.

## PASS 계약

Android logcat에서 다음 흐름을 확인합니다.

```text
MSDK_INIT_START
MSDK_INITIALIZE_COMPLETE
MSDK_REGISTER_APP_REQUESTED
MSDK_REGISTER_SUCCESS
MSDK_CAMERA_LISTENER_READY
MSDK_PRODUCT_CONNECT
MSDK_CAMERA_AVAILABLE
MSDK_STREAM_LISTENER_ATTACHED
DJI_BRIDGE_UPLOAD_START
MSDK_ENCODED_STREAM_FIRST
MSDK_ENCODED_STREAM_PROGRESS
```

동시에 인증된 HTTPS `/api/ingest/dji/status`에서 다음을 확인합니다.

```text
inputMode = ANDROID_BRIDGE
activeStream observed = true
connections delta >= 1
encodedChunks delta >= 1
encodedBytes delta >= 4096
decodedFrames delta >= 3
decoderFailures delta = 0
codec = H264 or H265 while active
```

따라서 PASS는 실제 MSDK encoded bytes가 Edge AI에 도착해 FFmpeg가 영상 프레임으로
디코딩했다는 증거입니다. 객체탐지 정확도, DJI telemetry, 비행 제어 또는 Backend
event/DB 저장까지 증명하지는 않습니다.

## 즉시 FAIL marker

```text
MSDK_REGISTER_FAILURE
DJI_BRIDGE_WAIT_PROVISIONING
DJI_BRIDGE_UPLOAD_START_ERROR
MSDK_ENCODED_STREAM_UNSUPPORTED
MSDK_ENCODED_STREAM_RANGE_ERROR
MSDK_ENCODED_STREAM_UPLOAD_REJECTED
DJI_BRIDGE_UPLOAD_OVERFLOW
DJI_BRIDGE_UPLOAD_ERROR
FATAL EXCEPTION
AbstractMethodError
```

Gate 종료 시 Android 앱을 force-stop하여 stream을 닫습니다. 기체와 RC-N2 전원은
사용자가 직접 안전하게 종료합니다.

## Evidence

```text
artifacts\phase3-dji-physical-stream\<UTC_RUN_ID>\summary.json
artifacts\phase3-dji-physical-stream\<UTC_RUN_ID>\android-marker-log.txt
```

Evidence에는 bridge key, sourceId, sessionId 원문 또는 ADB serial 원문을 기록하지
않습니다. ADB serial은 SHA-256 prefix만 기록합니다.
