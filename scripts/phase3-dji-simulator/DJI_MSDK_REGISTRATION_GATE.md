# Phase 3 DJI MSDK Android Registration Gate

이 Gate는 DJI Mini 4 Pro/RC-N2를 연결하기 전에 Android 기기에서 VisionFlow DJI Bridge 앱의 DJI MSDK 초기화와 `registerApp()` 성공을 재현 가능하게 검증합니다.

## PASS 경로

```text
VisionFlowDjiApplication
  -> DjiSdkBootstrap.start()
  -> MSDK_INIT_START
  -> MSDK_INITIALIZE_COMPLETE
  -> MSDK_REGISTER_APP_REQUESTED
  -> MSDK_REGISTER_SUCCESS
```

`MSDK_REGISTER_FAILURE`가 logcat에 나타나면 즉시 FAIL입니다. 모든 PASS marker는 위 순서대로 나타나야 합니다.

## 안전 정책

기본 실행은 build까지만 수행하고 Android device에 APK를 설치하거나 앱을 실행하지 않습니다.

```bat
scripts\phase3-dji-simulator\run-phase3-dji-msdk-registration-gate.bat
```

정상 기본 결과는 `WAIT`입니다.

실제 Android MSDK 등록을 검증할 때만 명시적으로 실행합니다.

```bat
scripts\phase3-dji-simulator\run-phase3-dji-msdk-registration-gate.bat --run-device --require-device
```

USB와 Wireless ADB가 동시에 연결된 경우에는 반드시 transport를 지정합니다.

```bat
scripts\phase3-dji-simulator\run-phase3-dji-msdk-registration-gate.bat --run-device --require-device --serial <ADB_SERIAL>
```

현재 네트워크의 Wireless ADB IP는 임시값이므로 저장소나 고정 설정에 기록하지 않습니다.

## 검증 범위

검증:

```text
authorized Android ADB transport
arm64 Android device
debug APK build/install
MainActivity cold launch
DJI MSDK initialize
DJI MSDK registerApp
MSDK_REGISTER_SUCCESS
```

아직 검증하지 않음:

```text
RC-N2
DJI product connection
camera availability
encoded H.264/H.265 stream
actual bitstream framing
Edge AI upload/decode
```

따라서 Gate가 PASS해도 `physicalDJI=SKIPPED`와 `djiProductConnection=SKIPPED`를 유지합니다.

## Evidence

```text
artifacts\phase3-dji-msdk-registration\<UTC_RUN_ID>\summary.json
artifacts\phase3-dji-msdk-registration\<UTC_RUN_ID>\msdk-log.txt
```

Gate는 앱 credential, DJI Bridge key 또는 다른 secret을 log/evidence에 기록하지 않습니다.
