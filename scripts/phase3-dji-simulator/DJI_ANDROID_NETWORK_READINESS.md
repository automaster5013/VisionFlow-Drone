# Phase 3 DJI Android HTTPS / Network Readiness

실제 DJI 기체를 연결하기 전에 Android Bridge의 HTTPS 경로를 준비합니다.

## 목표 경로

```text
Android DJI Bridge
  -> https://<EDGE_LAN_IP>:3443/api/ingest/dji/stream
  -> Caddy
  -> host.docker.internal:8000
  -> AI ANDROID_BRIDGE source
```

기존 VisionFlow runtime은 기본적으로 `SMARTPHONE_LIVE`를 유지합니다.
DJI 실기체 검증 시에만 `compose.dji-bridge.yaml`을 추가합니다.

```bat
docker compose --env-file .env.docker -f compose.yaml -f compose.dji-bridge.yaml -f compose.mobile-https.yaml config
```

GPU 모드가 필요한 경우 기존 `compose.gpu.yaml`과 모델 override를 함께 사용합니다.

## TLS 인증서

Android는 Edge PC의 LAN 주소로 접속하므로 현재 LAN IPv4가
`visionflow-mobile.pem` SAN에 있어야 합니다.

예를 들어 Edge PC가 `192.168.46.7`일 때:

```bat
mkdir "C:\VisionFlow-Drone_Backup\20260819\mobile-https-cert-pre-192.168.46.7"

copy /Y "C:\VisionFlow-Drone\artifacts\mobile-https\certs\visionflow-mobile.pem" "C:\VisionFlow-Drone_Backup\20260819\mobile-https-cert-pre-192.168.46.7\visionflow-mobile.pem"
copy /Y "C:\VisionFlow-Drone\artifacts\mobile-https\certs\visionflow-mobile-key.pem" "C:\VisionFlow-Drone_Backup\20260819\mobile-https-cert-pre-192.168.46.7\visionflow-mobile-key.pem"

mkcert -cert-file "C:\VisionFlow-Drone\artifacts\mobile-https\certs\visionflow-mobile.pem" -key-file "C:\VisionFlow-Drone\artifacts\mobile-https\certs\visionflow-mobile-key.pem" localhost DESKTOP-7LN9JEL DESKTOP-7LN9JEL.local 192.168.46.7 127.0.0.1 ::1
```

DHCP로 LAN IP가 다시 바뀌면 인증서를 다시 발급하거나 라우터에서 Edge PC의
DHCP lease를 고정합니다.

## Android trust

Release/default trust는 system CA만 사용하고 cleartext HTTP는 금지합니다.

Debug build에서만 Android 사용자가 직접 설치한 CA를 추가로 신뢰하도록
`debug-overrides`를 사용합니다. mkcert Root CA 파일은 PC의 다음 위치에 있습니다.

```text
C:\Users\kaiser\AppData\Local\mkcert\rootCA.pem
```

Root CA 파일은 Git에 복사하거나 커밋하지 않습니다.

실제 Android 기기에서는 debug APK 테스트 전에 이 Root CA를 사용자 CA로
설치해야 합니다. 설치 여부는 software-only Gate에서 자동 증명할 수 없으므로
`WAIT`로 남깁니다.

## Caddy 적용

Caddy route 변경과 인증서 재발급 후 Caddy만 다시 생성합니다.

```bat
docker compose --env-file .env.docker -f compose.yaml -f compose.mobile-https.yaml up -d --no-deps --force-recreate mobile-https
```

PC에서 mkcert Root CA와 hostname/IP 검증까지 포함해 확인합니다.

```bat
curl --ssl-revoke-best-effort --cacert "C:\Users\kaiser\AppData\Local\mkcert\rootCA.pem" https://192.168.46.7:3443/healthz
```

`ok`가 반환되어야 합니다.

## Readiness Gate

```bat
scripts\phase3-dji-simulator\run-phase3-dji-network-readiness.bat 192.168.46.7
```

Gate 검증:

```text
certificate SAN contains host LAN IP
Caddy DJI route exists
Caddy config validates
trusted-CA HTTPS /healthz runtime probe
direct AI vs HTTPS/Caddy DJI status response parity
Caddy Via header confirmation
Android cleartext denied
Android debug user-CA trust configured
DJI compose override exists
running AI profile recorded (switch itself is deferred)
```

Gate의 runtime HTTPS probe는 Python `ssl` + mkcert Root CA를 사용하므로
Windows Schannel의 로컬 개발 CA revocation 조회 문제에 의존하지 않습니다.
수동 `curl` 검증에서는 위 예제처럼 `--ssl-revoke-best-effort`를 사용합니다.

Evidence:

```text
artifacts\phase3-dji-network-readiness\<UTC_RUN_ID>\summary.json
```

실제 Android CA 설치, 실제 DJI MSDK stream, 실제 LAN latency/reconnect는 계속
hardware/runtime Gate로 남습니다.
