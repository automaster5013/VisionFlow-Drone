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
```

Auth 단계는 `getpass`를 사용하므로 비밀번호가 화면이나 이 Gate의 Evidence에 기록되지 않습니다.
실제 DJI 기체 runtime과 AWS는 명시적으로 `SKIPPED`입니다.

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
```
