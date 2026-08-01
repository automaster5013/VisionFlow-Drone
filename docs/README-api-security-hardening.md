# VisionFlow API 보안 기본 모드 강화

## 목적

첫 번째 API 보안 감사에서 확인된 기본 설정 편차를 안전하게 정리합니다.

- Backend 운영자 보안 기본값: `true`
- Frontend 인증 모드 기본값: `session`
- Frontend 운영자 세션 쿠키 기본값: `Secure=true`
- 현재 `.env.docker`의 `VISIONFLOW_WEB_SECURE_COOKIES` 값만 `true`로 변경
- 기존 관리자 세션 강제 종료 Route의 수동 Same-Origin 방어를 감사기가 정상 인식

관리자 세션 강제 종료 Route에는 이미 `isSameOriginRequest()` 검사가 있습니다. 이 작업은 Route를 변경하거나 방어를 약화하지 않습니다.

## 안전 원칙

- `.env.docker`의 다른 환경값을 출력하지 않습니다.
- 운영자 KEY, DB 비밀번호 및 기타 자격증명을 수집하지 않습니다.
- DB를 변경하지 않습니다.
- 기본 실행은 계획만 표시합니다.
- 실제 적용에는 확인 문자열이 필요합니다.
- 컨테이너 재생성은 `--restart-frontend`를 명시한 경우 Frontend에만 수행합니다.
- 작업 기록에는 변경 전후 비밀값 대신 파일 SHA-256과 비밀 제외 설정값만 저장합니다.

## 계획 확인

```bat
scripts\run-visionflow-secure-cookie-mode.bat
```

예상 결과는 현재값 `false`, 목표값 `true`, 상태 `READY`입니다.

## 적용 및 Frontend 재생성

```bat
scripts\run-visionflow-secure-cookie-mode.bat --apply --confirm ENABLE_SECURE_OPERATOR_COOKIES --restart-frontend
```

이 명령은 다음 작업만 수행합니다.

1. `.env.docker`의 `VISIONFLOW_WEB_SECURE_COOKIES=true` 적용
2. 활성 Compose 파일을 사용해 `frontend-web`만 강제 재생성
3. `visionflow-frontend`가 `running/healthy`인지 대기
4. 컨테이너의 해당 비밀 제외 환경값이 `true`인지 확인
5. `artifacts/api-security-hardening` 아래에 작업 기록 저장

## 검증

```bat
docker inspect visionflow-frontend --format "{{range .Config.Env}}{{println .}}{{end}}" | findstr /B "VISIONFLOW_WEB_SECURE_COOKIES="
scripts\run-visionflow-acceptance.bat -RunRbac -RunSession
scripts\run-visionflow-api-security-audit.bat
```

보안 감사에서 다음 항목은 `PASS`가 되어야 합니다.

- `frontend-same-origin`
- `compose-security-defaults`
- `runtime-security-mode`

전체 상태는 Backend 공개 조회 범위와 AI 공개 API 검토가 남아 있으므로 계속 `API_SECURITY_ADVISORY`가 정상입니다.

## HTTP 접근 주의

`Secure` 쿠키는 HTTPS 사용을 위한 설정입니다. 스마트폰과 LAN에서는 Caddy 주소인 `https://<현재-PC-IP>:3443/`를 사용합니다. 직접 `http://<PC-IP>:3000/`으로 접속하면 운영자 세션 쿠키가 전송되지 않는 것이 정상입니다.

PC의 `localhost` 검증은 기존 자동 인수 테스트로 확인하고, 실제 LAN 운영은 HTTPS 주소를 기준으로 합니다.
