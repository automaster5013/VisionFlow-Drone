# 적용 및 검증 순서

## 1. 모바일 HTTPS 프런트엔드 종료

`run-visionflow-mobile-https.bat` 실행 창에서 `Ctrl+C`를 누릅니다.

MySQL, 백엔드, AI 컨테이너는 종료하지 않아도 됩니다.

## 2. 패치 적용

ZIP을 `C:\VisionFlow-Drone`에 압축 해제하고 폴더 구조를 유지한 채 덮어씁니다.

다음 파일이 정확한 위치에 있어야 합니다.

```text
C:\VisionFlow-Drone\scripts\visionflow_mobile_evidence.py
C:\VisionFlow-Drone\scripts\tests\test_visionflow_mobile_evidence.py
C:\VisionFlow-Drone\01_frontend\visionflow-web\src\hooks\use-mobile-drone-sensors.ts
```

## 3. 증적 스크립트 단위 테스트

```bat
cd /d C:\VisionFlow-Drone
py -3 -m unittest scripts.tests.test_visionflow_mobile_evidence -v
```

11개 테스트가 모두 `OK`여야 합니다.

## 4. 프런트엔드 검증

```bat
cd /d C:\VisionFlow-Drone\01_frontend\visionflow-web
npm run lint
npm run build
```

## 5. 모바일 HTTPS 프런트엔드 재기동

```bat
cd /d C:\VisionFlow-Drone
scripts\run-visionflow-mobile-https.bat
```

## 6. 기존 성공 세션 자동 선택 재검증

새 스마트폰 비행을 다시 만들 필요가 없습니다.

```bat
cd /d C:\VisionFlow-Drone
scripts\run-visionflow-mobile-evidence.bat
```

다음처럼 최근 성공 세션의 드론과 UUID가 표시되어야 합니다.

```text
VisionFlow smartphone E2E evidence: SMARTPHONE_E2E_PASS
Selected drone : 3
Selected session: 3c0b11cc-c115-45b4-9814-9ef18ada6188
```

## 선택 옵션

특정 드론의 최신 세션만 검사:

```bat
scripts\run-visionflow-mobile-evidence.bat --drone-id 3
```

특정 세션을 정확히 검사:

```bat
scripts\run-visionflow-mobile-evidence.bat --drone-id 3 --session-id 실제UUID
```

## 센서 상태 복구 확인

다음 실제 비행에서 GPS가 잠시 끊겼다가 다시 수신되면 센서 상태가 `ERROR`에 고정되지 않고 `ACTIVE`로 돌아와야 합니다. 비행 종료 후에는 `IDLE`이 정상입니다.
