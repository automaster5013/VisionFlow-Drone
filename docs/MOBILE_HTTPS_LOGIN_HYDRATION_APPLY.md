# 적용 및 검증 순서

## 1. 실행 중인 프런트엔드 종료

`npm run dev` 또는 기존 모바일 HTTPS 실행 창에서 `Ctrl+C`를 누릅니다.

포트 3000을 다른 Next.js 프로세스가 계속 사용한다면 다음 명령으로 PID를 확인합니다.

```bat
netstat -ano | findstr :3000
```

표시된 PID가 VisionFlow Next.js 프로세스인지 작업 관리자에서 확인한 뒤 종료합니다.

## 2. 패치 덮어쓰기

이 ZIP을 `C:\VisionFlow-Drone`에 압축 해제하고 폴더 구조를 유지한 채 파일 덮어쓰기를 허용합니다.

압축을 풀었을 때 다음 경로가 정확히 존재해야 합니다.

```text
C:\VisionFlow-Drone\01_frontend\visionflow-web\next.config.ts
C:\VisionFlow-Drone\01_frontend\visionflow-web\src\components\security\operator-login-form.tsx
C:\VisionFlow-Drone\scripts\setup-visionflow-mobile-https.ps1
C:\VisionFlow-Drone\scripts\run-visionflow-mobile-https.ps1
C:\VisionFlow-Drone\scripts\test-visionflow-mobile-https.ps1
```

## 3. 프런트엔드 정적 검증

```bat
cd /d C:\VisionFlow-Drone\01_frontend\visionflow-web
npm run lint
npm run build
```

두 명령이 성공해야 합니다.

## 4. LAN HTTPS 전용 방식으로 재기동

일반 `npm run dev`가 아니라 프로젝트 루트에서 아래 명령만 실행합니다.

```bat
cd /d C:\VisionFlow-Drone
scripts\run-visionflow-mobile-https.bat
```

출력에서 다음 항목을 확인합니다.

```text
Auth mode  : session
Dev origin : 192.168.x.x
```

이 창은 서버이므로 닫지 않습니다.

## 5. PC 로그인 검증

출력된 `Login URL`을 PC Chrome에서 엽니다. 예시는 다음과 같습니다.

```text
https://192.168.x.x:3000/operator-login?returnTo=/mobile-flight
```

패치 후 로그인 버튼은 처음부터 클릭 가능한 상태입니다. 운영자 키를 입력하고 버튼을 누릅니다.

- 빈 값으로 누르면 `운영자 인증 키를 입력하세요.`가 표시되어야 합니다.
- 유효한 키로 로그인하면 `/mobile-flight`로 이동해야 합니다.
- 운영자 키 원문은 명령 출력, 캡처, 채팅에 남기지 않습니다.

브라우저가 이전 화면을 보이면 `Ctrl+Shift+R`로 한 번 강력 새로고침합니다.

## 6. PC HTTPS 준비도 재검증

서버 창과 별도의 새 터미널에서 실행합니다.

```bat
cd /d C:\VisionFlow-Drone
scripts\run-visionflow-mobile-https-acceptance.bat
```

다음 항목을 포함해 모두 PASS여야 합니다.

```text
[PASS] Operator browser session mode - HTTP 200; enabled=true; authMode=session
VisionFlow smartphone readiness: PC_HTTPS_READY
```

## 7. 스마트폰 검증

PC와 스마트폰이 같은 Wi-Fi에 연결된 상태에서 출력된 `Login URL`을 스마트폰 Chrome으로 엽니다.

로그인 후 `/mobile-flight`에서 아래 순서로 확인합니다.

1. 드론 목록이 표시되는지 확인합니다.
2. 사용할 드론을 선택합니다.
3. 위치 권한을 `앱 사용 중에만 허용`으로 승인합니다.
4. 기기 방향 또는 동작 센서 권한 요청이 있으면 승인합니다.
5. 센서 전송을 시작합니다.

스마트폰 검증이 끝난 뒤에만 E2E 증적 스크립트를 다시 실행합니다.
