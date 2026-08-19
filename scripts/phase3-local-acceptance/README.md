# Phase 3 Local Acceptance Gate

실기 DJI Mini 4 Pro runtime과 AWS를 제외하고 로컬에서 가능한 주요 Phase 3 검증을 한 명령으로 실행합니다.

```bat
scripts\phase3-local-acceptance\run-phase3-local-acceptance.bat
```

기본 검증:

```text
Docker 5-service health
  -> git diff --check
  -> Backend test
  -> Frontend lint
  -> Frontend production build
  -> Android DJI Bridge assembleDebug
  -> Auth/RBAC runtime E2E
  -> DJI software-only integration gate
  -> DJI Android Bridge H.264/H.265 encoded ingress gate
  -> DJI Android Bridge H.265/reconnect/backpressure robustness gate
```

Auth 단계는 `getpass`를 사용하므로 비밀번호가 화면이나 이 Gate의 Evidence에 기록되지 않습니다.
실제 DJI 기체 runtime과 AWS는 명시적으로 `SKIPPED`입니다.

Android Bridge encoded-ingress 단계는 기본적으로
`visionflow-ai-server:phase3-android-bridge-v1` 이미지를 현재 소스에서 다시
빌드합니다. 방금 동일 소스로 이미지를 검증했고 빠른 재실행만 필요한 경우에는
`--reuse-dji-android-bridge-image`를 사용합니다.

Evidence:

```text
artifacts\phase3-local-acceptance\<UTC_RUN_ID>\summary.json
```

선택적 skip:

```bat
run-phase3-local-acceptance.bat --skip-backend-tests
run-phase3-local-acceptance.bat --skip-frontend-build
run-phase3-local-acceptance.bat --skip-android-build
run-phase3-local-acceptance.bat --skip-auth-gate
run-phase3-local-acceptance.bat --skip-dji-software-gate
run-phase3-local-acceptance.bat --skip-dji-android-bridge-gate
run-phase3-local-acceptance.bat --skip-dji-android-bridge-robustness
run-phase3-local-acceptance.bat --reuse-dji-android-bridge-image
```

`--reuse-dji-android-bridge-image`는 기존 이미지가 현재 소스와 동일하다는 확신이
있을 때만 사용합니다. 정식 Acceptance에서는 옵션 없이 실행해 이미지를 다시
빌드하는 것이 기준입니다.
