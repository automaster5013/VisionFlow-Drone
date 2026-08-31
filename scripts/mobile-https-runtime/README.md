# VisionFlow Mobile HTTPS Runtime Agent

스마트폰 QR 로그인에서 Windows PC의 현재 LAN HTTPS 주소를 자동 입력하기 위한
host-side runtime detector입니다.

Next.js 프론트엔드는 Docker 컨테이너 안에서 실행되므로 컨테이너의
`os.networkInterfaces()`로 Windows LAN IP를 판정하지 않습니다. 이 Agent가
Windows host에서 다음 정보를 계산해 runtime JSON으로 기록합니다.

```text
current RFC1918 LAN IPv4
  -> https://<LAN-IP>:3443
  -> mobile HTTPS certificate SAN match
  -> mkcert Root CA trusted /healthz probe
  -> artifacts/mobile-https/runtime/network-profile.json
```

runtime JSON에는 비밀번호, operator key, DJI bridge key 같은 secret을 기록하지
않습니다.

## 1. 한 번만 검사

```bat
scripts\mobile-https-runtime\run-mobile-https-runtime-once.bat
```

현재 LAN IP가 인증서 SAN에 없거나 `/healthz`가 실패해도 profile은 생성되며
`BLOCKED`로 표시됩니다. 이 상태는 QR 페이지가 잘못된 자동 주소를 그대로
사용하지 않도록 하기 위한 정상적인 안전 판정입니다.

## 2. 자동 감지 Agent 시작

```bat
scripts\mobile-https-runtime\start-mobile-https-runtime-agent.bat
```

Agent는 기본 5초마다 현재 host network와 HTTPS 상태를 갱신합니다. 노트북이 다른
Wi-Fi로 이동하거나 DHCP 주소가 바뀌면 QR 페이지는 새 runtime profile을 읽을 수
있습니다.

중복 Agent는 runtime lock으로 차단됩니다. Agent를 종료하려면 최소화된
`VisionFlow Mobile HTTPS Runtime Agent` 콘솔을 닫거나 Ctrl+C로 종료합니다.

## 3. 명시적 IP 검증

자동 route 감지와 별개로 특정 IP를 검증할 때:

```bat
scripts\mobile-https-runtime\run-mobile-https-runtime-once.bat --host-ip 192.168.46.7
```

## Frontend runtime mount

Compose는 다음 host 디렉터리를 frontend container에 read-only로 전달합니다.

```text
host:
  artifacts/mobile-https/runtime

container:
  /app/artifacts/mobile-https-runtime
```

Next.js API:

```text
GET /api/mobile/runtime-network
```

운영자 인증 후 현재 profile의 freshness, certificate SAN, HTTPS health 상태만
반환합니다.
