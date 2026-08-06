# VisionFlow HTTPS WebSocket same-origin guard

## Purpose

The browser control pages are served through Caddy at
`https://localhost:3443`. An HTTPS page must not fall back to the direct
`ws://localhost:8080/ws` backend address. That bypasses the TLS entry point,
creates a cross-origin handshake, and leaves live telemetry in
`DISCONNECTED` state.

## Connection paths

- HTTP local development keeps the configured
  `NEXT_PUBLIC_WEBSOCKET_URL` value. Its default is
  `ws://localhost:8080/ws`.
- HTTPS browser sessions use the current browser host with the secure path
  `wss://<current-host>/ws`.
- Caddy handles `/healthz` locally, then proxies `/ws` to
  `host.docker.internal:8080/ws`, before its general frontend proxy. All
  three handlers share one ordered route so the health probe cannot fall
  through to the Next.js catch-all.
- Spring accepts only the configured origin list. Local defaults cover
  `http://localhost:3000`, `http://127.0.0.1:3000`,
  `https://localhost:3443`, and `https://127.0.0.1:3443`.

For a smartphone or another LAN host, set an explicit origin before rebuilding
the backend. Do not use a wildcard:

```env
VISIONFLOW_WEBSOCKET_ALLOWED_ORIGIN_PATTERNS=http://localhost:3000,http://127.0.0.1:3000,https://localhost:3443,https://127.0.0.1:3443,https://192.168.0.10:3443
```

Replace `192.168.0.10` with the HTTPS host encoded in the mobile certificate.

## Verification

1. Rebuild both `backend-api` and `frontend-web`, then recreate the mobile
   HTTPS proxy so it loads the updated Caddyfile.
2. Verify `https://localhost:3443/healthz` returns HTTP 200 with body `ok`
   and the `mobile-https` container becomes healthy.
3. Open `https://localhost:3443/drones` and verify the page reports
   `CONNECTED`.
4. In browser developer tools, verify the WebSocket request URL is
   `wss://localhost:3443/ws` and the handshake status is `101 Switching
   Protocols`.
5. Verify STOMP messages or heartbeats appear and the browser does not retry
   an insecure `ws://localhost:8080/ws` connection.

The change does not add an API, database migration, write path, or credential.
