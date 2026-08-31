from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class SystemTraceabilityWebSocketHttpsTest(unittest.TestCase):
    def test_https_uses_same_origin_secure_websocket(self) -> None:
        resolver = self.read(
            "01_frontend/visionflow-web/src/lib/websocket-url.ts"
        )

        self.assertIn('browserLocation?.protocol === "https:"', resolver)
        self.assertIn(
            "`wss://${browserLocation.host}${SAME_ORIGIN_WEBSOCKET_PATH}`",
            resolver,
        )
        self.assertIn('SAME_ORIGIN_WEBSOCKET_PATH = "/ws"', resolver)

    def test_all_realtime_hooks_use_shared_resolver(self) -> None:
        hook_paths = [
            "01_frontend/visionflow-web/src/hooks/use-ai-alert-realtime.ts",
            "01_frontend/visionflow-web/src/hooks/use-incident-realtime.ts",
            "01_frontend/visionflow-web/src/hooks/use-drone-telemetry.ts",
            "01_frontend/visionflow-web/src/hooks/use-drone-fleet-telemetry.ts",
        ]

        for relative_path in hook_paths:
            with self.subTest(path=relative_path):
                source = self.read(relative_path)
                self.assertIn(
                    'import { resolveWebSocketUrl } from "@/lib/websocket-url";',
                    source,
                )
                self.assertIn("brokerURL: resolveWebSocketUrl()", source)
                self.assertNotIn("ws://localhost:8080/ws", source)
                self.assertNotIn("NEXT_PUBLIC_WEBSOCKET_URL", source)

    def test_reconnectable_transport_failures_do_not_raise_dev_overlay(self) -> None:
        contracts = {
            "01_frontend/visionflow-web/src/hooks/use-ai-alert-realtime.ts": (
                'console.warn("AI 경보 WebSocket 연결 대기:", event)',
                'console.error("AI 경보 WebSocket 오류:", event)',
            ),
            "01_frontend/visionflow-web/src/hooks/use-incident-realtime.ts": (
                'console.warn("Incident WebSocket 연결 대기:", event)',
                'console.error("Incident WebSocket 오류:", event)',
            ),
            "01_frontend/visionflow-web/src/hooks/use-drone-fleet-telemetry.ts": (
                'console.warn("WebSocket 연결 대기:", event)',
                'console.error("WebSocket 오류:", event)',
            ),
            "01_frontend/visionflow-web/src/hooks/use-drone-telemetry.ts": (
                'console.warn(\n                "WebSocket connection pending:",',
                'console.error(\n                "WebSocket connection error:",',
            ),
        }

        for relative_path, (warning_contract, error_contract) in contracts.items():
            with self.subTest(path=relative_path):
                source = self.read(relative_path)
                self.assertIn(warning_contract, source)
                self.assertNotIn(error_contract, source)
                self.assertIn('setConnectionStatus("ERROR")', source)

    def test_caddy_routes_health_and_websocket_before_frontend(self) -> None:
        caddy = self.read("infrastructure/mobile-https/Caddyfile")

        route = "route {"
        health_matcher = "@health path /healthz"
        health_response = 'respond @health "ok" 200'
        websocket_matcher = "@backend_websocket path /ws /ws/*"
        websocket_proxy = (
            "reverse_proxy @backend_websocket host.docker.internal:8080"
        )
        frontend_proxy = "reverse_proxy host.docker.internal:3000"

        self.assertIn(route, caddy)
        self.assertIn(health_matcher, caddy)
        self.assertIn(health_response, caddy)
        self.assertIn(websocket_matcher, caddy)
        self.assertIn(websocket_proxy, caddy)
        self.assertIn(frontend_proxy, caddy)
        self.assertLess(caddy.index(route), caddy.index(health_matcher))
        self.assertLess(caddy.index(health_matcher), caddy.index(health_response))
        self.assertLess(caddy.index(health_response), caddy.index(websocket_proxy))
        self.assertLess(caddy.index(websocket_proxy), caddy.index(frontend_proxy))

    def test_backend_allows_configured_https_origins(self) -> None:
        config = self.read(
            "02_backend/visionflow-api/src/main/java/com/visionflow/api/"
            "common/config/WebSocketConfig.java"
        )
        compose = self.read("compose.yaml")

        self.assertIn(
            "visionflow.websocket.allowed-origin-patterns",
            config,
        )
        self.assertIn("https://localhost:3443", config)
        self.assertIn("https://127.0.0.1:3443", config)
        self.assertIn(
            ".setAllowedOriginPatterns(allowedOriginPatterns)",
            config,
        )
        self.assertIn(
            "VISIONFLOW_WEBSOCKET_ALLOWED_ORIGIN_PATTERNS",
            compose,
        )

    def test_no_insecure_wildcard_origin_is_allowed(self) -> None:
        config = self.read(
            "02_backend/visionflow-api/src/main/java/com/visionflow/api/"
            "common/config/WebSocketConfig.java"
        )

        self.assertIsNone(
            re.search(r'setAllowedOriginPatterns\s*\(\s*"\*"', config)
        )

    @staticmethod
    def read(relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
