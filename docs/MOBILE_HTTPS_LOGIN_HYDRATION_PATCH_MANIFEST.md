# VisionFlow 모바일 HTTPS 로그인 Hydration 패치

## 변경 파일

- `01_frontend/visionflow-web/next.config.ts`
  - 현재 LAN IP를 Next.js `allowedDevOrigins`에 등록합니다.
  - LAN HTTPS와 WSS 개발 연결을 CSP `connect-src`에 추가합니다.
- `01_frontend/visionflow-web/src/components/security/operator-login-form.tsx`
  - 버튼 활성 여부를 React 입력 상태에 의존하지 않게 합니다.
  - 제출 시점에 `FormData`로 운영자 키를 읽어 자동완성과 Hydration 경계 문제를 피합니다.
  - 제출 중에만 입력창과 버튼을 비활성화합니다.
- `scripts/setup-visionflow-mobile-https.ps1`
  - 로그인 복귀 쿼리를 `next`에서 실제 페이지가 읽는 `returnTo`로 수정합니다.
- `scripts/run-visionflow-mobile-https.ps1`
  - 현재 LAN IP, 세션 인증 모드, Secure 쿠키 설정을 Next.js 시작 프로세스에 전달합니다.
- `scripts/test-visionflow-mobile-https.ps1`
  - `enabled=true`, `authMode=session`을 준비도 검사에 포함합니다.

## 해결 대상

- 운영자 키를 입력해도 로그인 버튼이 계속 비활성화되는 현상
- LAN HTTPS에서 `/_next/webpack-hmr` WSS 연결이 실패하는 현상
- 준비도 검사가 `static` 인증 모드를 발견하지 못하고 통과하던 문제
- 로그인 성공 후 `/mobile-flight`가 아닌 `/dashboard`로 이동하던 문제
