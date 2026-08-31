# Phase 3 DJI Android Provisioning / Keystore Device Gate

이 Gate는 실제 DJI 기체 연결 전에 Android Bridge provisioning 저장 경계와
Android Keystore AES/GCM round-trip을 실제 Android 디바이스에서 검증합니다.

## 범위

검증 대상:

```text
DjiBridgeRuntimeConfig validation
private SharedPreferences profile storage
Android Keystore AES/GCM DJI bridge credential storage
credential decrypt round-trip
DjiEncodedStreamUploader construction
isolated diagnostics storage cleanup
```

검증하지 않는 항목:

```text
DJI MSDK registration success
Mini 4 Pro product connection
actual H.264/H.265 MSDK byte framing
AI server network upload
flight-session lifecycle
```

따라서 이 Gate가 PASS해도 물리 DJI runtime은 계속 `SKIPPED`입니다.

## 사용자 provisioning 보호

Self-test는 production provisioning namespace를 사용하지 않습니다.

```text
production:
  visionflow_dji_bridge_runtime
  visionflow_dji_bridge_secret
  visionflow_dji_bridge_runtime_key_v1

self-test:
  위 이름 + _adb_self_test suffix
```

Gate 시작과 종료 시 self-test namespace만 clear하므로 사용자가 UI에서 저장한
실제 Edge AI URL, droneId, sourceId, DJI Bridge key는 변경하지 않습니다.

## 실행

```bat
scripts\phase3-dji-simulator\run-phase3-dji-provisioning-device-gate.bat
```

기본 실행은 software build까지만 수행하고 `WAIT`로 종료합니다. 연결된 Android
device가 있어도 APK를 설치하거나 앱을 실행하지 않습니다.

실제 Android 기기 검증을 의도적으로 시작할 때만:

```bat
scripts\phase3-dji-simulator\run-phase3-dji-provisioning-device-gate.bat --run-device
```

기기가 반드시 연결되어 있어야 하는 strict 검증에서는:

```bat
scripts\phase3-dji-simulator\run-phase3-dji-provisioning-device-gate.bat --run-device --require-device
```

여러 Android device가 연결된 경우:

```bat
scripts\phase3-dji-simulator\run-phase3-dji-provisioning-device-gate.bat --serial <ADB_SERIAL>
```

이미 debug APK를 설치해 둔 경우 `--skip-install`, 이미 build한 경우
`--skip-build`를 사용할 수 있습니다.

## PASS 기준

```text
Git whitespace PASS
Android unit test + assembleDebug PASS
authorized arm64 Android device
debug APK install PASS
debug-only provisioning self-test Activity launch PASS
Android Keystore save/decrypt round-trip PASS
isolated runtime profile save/load PASS
DjiEncodedStreamUploader construction PASS
self-test namespace cleanup PASS
```

Evidence:

```text
artifacts\phase3-dji-provisioning-device\<UTC_RUN_ID>\summary.json
artifacts\phase3-dji-provisioning-device\<UTC_RUN_ID>\selftest-log.txt
```

Self-test는 bridge credential 원문을 logcat 또는 evidence에 기록하지 않습니다.
