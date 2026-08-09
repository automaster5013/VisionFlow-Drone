# VisionFlow 운영자 QR 기기 페어링

## 목적

스마트폰에서 VIEWER / OPERATOR / ADMIN 장기 KEY를 직접 입력하거나 메신저로
옮기지 않고, 이미 로그인된 PC 브라우저 세션이 5분짜리 일회용 QR을 발급하여
별도의 스마트폰 세션을 안전하게 생성한다.

## 인증 흐름

```text
PC 로그인 세션
   |
   | target role 선택
   v
2분 일회용 Pairing 생성
   |
   | QR: /operator-pair#pairingId=...&token=...&returnTo=...
   v
스마트폰 QR 스캔
   |
   | 기기 이름 + 256-bit token
   v
CLAIMED
   |
   | 양쪽 6자리 코드 비교
   v
PC APPROVE
   |
   | 같은 one-time token 교환
   v
스마트폰 전용 OperatorSession 발급
   |
   v
HttpOnly + SameSite=Lax + Secure cookie
   |
   v
/mobile-flight
```

## 보안 원칙

- QR에는 장기 역할 KEY를 포함하지 않는다.
- PC의 기존 session token도 QR에 포함하지 않는다.
- Pairing token은 32 random bytes(256-bit)이다.
- Backend 메모리에는 token 원문이 아닌 SHA-256 digest만 저장한다.
- 기본 TTL은 5분이다.
- QR secret은 URL query가 아니라 `#fragment`에 넣는다.
- 스마트폰 페이지는 fragment를 읽은 직후 `history.replaceState()`로 주소창에서 제거한다.
- PC 승인 전 exchange는 `409 OPERATOR_PAIRING_APPROVAL_REQUIRED`로 차단한다.
- 성공한 token은 `CONSUMED`가 되고 재사용은 `410 OPERATOR_PAIRING_ALREADY_USED`로 거부한다.
- VIEWER는 VIEWER, OPERATOR는 VIEWER/OPERATOR, ADMIN은 VIEWER/OPERATOR/ADMIN만 발급 가능하다.
- 생성·상태조회·승인·취소는 Pairing을 생성한 정확한 browser session ID와 일치해야 한다.
- Frontend mutation Route에는 same-origin 검사를 적용한다.
- Pairing 자체는 DB에 저장하지 않는다. Backend 재시작 시 미사용 pairing은 모두 자동 무효화된다.
- 감사 로그에는 역할, 기기 이름, 발급된 session ID, 상태만 기록하고 QR token과 장기 KEY는 기록하지 않는다.

## 사용자 사용법

1. PC VisionFlow에서 기존 방식으로 한 번 로그인한다.
2. 상단 `QR 로그인` 버튼을 누른다.
3. 스마트폰 접속용 HTTPS 주소를 확인한다.
4. 스마트폰에 부여할 역할을 고른다.
5. `5분 일회용 QR 생성`을 누른다.
6. 스마트폰 카메라로 QR을 스캔한다.
7. 스마트폰에서 기기 이름을 확인하고 `PC에 연결 요청`을 누른다.
8. PC와 스마트폰의 6자리 코드가 같은지 확인한다.
9. PC에서 승인한다.
10. 스마트폰은 자동으로 새 HttpOnly session cookie를 받고 지정 화면으로 이동한다.
11. 로그아웃은 기존 상단 `로그아웃` 버튼을 그대로 사용한다.

## 역할 위임 규칙

| PC 역할 | 스마트폰에 발급 가능 |
|---|---|
| VIEWER | VIEWER |
| OPERATOR | VIEWER, OPERATOR |
| ADMIN | VIEWER, OPERATOR, ADMIN |

## 비상 로그인

장기 KEY 방식은 삭제하지 않는다. 초기 부트스트랩, 장애 복구, QR을 발급할 PC 세션이
없는 경우를 위해 `/operator-login`의 `비상·초기 설정용 KEY 로그인`으로 유지한다.

## 자동 회귀 검증

`visionflow-acceptance.ps1 -RunSession`은 다음을 검증한다.

- ADMIN 임시 issuer session 생성
- OPERATOR pairing 생성
- 모바일 claim 및 6자리 코드 일치
- PC 승인 전 exchange 차단
- 승인 성공
- 별도 OPERATOR session 발급
- 발급 세션 role 확인
- 동일 QR token 재사용 410 차단
- VIEWER가 ADMIN pairing을 생성하려 할 때 403 차단

## 향후 Passkey

고정 도메인과 신뢰 가능한 TLS 구성이 완료되면 WebAuthn / Passkey를 주 인증으로
추가할 수 있다. QR pairing은 새 기기 등록 및 cross-device 보조 인증 경로로 유지한다.
