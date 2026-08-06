const DEFAULT_WEBSOCKET_URL = "ws://localhost:8080/ws";
const SAME_ORIGIN_WEBSOCKET_PATH = "/ws";

interface BrowserLocation {
    protocol: string;
    host: string;
}

function isSecureWebSocketUrl(value: string): boolean {
    try {
        return new URL(value).protocol === "wss:";
    } catch {
        return false;
    }
}

/**
 * Resolves the browser STOMP endpoint without allowing an HTTPS page to fall
 * back to an insecure, cross-origin ws:// URL.
 *
 * The local HTTP development server keeps using the configured backend URL.
 * The HTTPS entry point uses the current browser origin so Caddy can terminate
 * TLS and proxy /ws to the backend WebSocket endpoint.
 */
export function resolveWebSocketUrl(
    configuredUrl = process.env.NEXT_PUBLIC_WEBSOCKET_URL?.trim(),
    browserLocation: BrowserLocation | null =
        typeof window === "undefined" ? null : window.location,
): string {
    if (browserLocation?.protocol === "https:") {
        if (configuredUrl && isSecureWebSocketUrl(configuredUrl)) {
            return configuredUrl;
        }

        return `wss://${browserLocation.host}${SAME_ORIGIN_WEBSOCKET_PATH}`;
    }

    return configuredUrl || DEFAULT_WEBSOCKET_URL;
}
