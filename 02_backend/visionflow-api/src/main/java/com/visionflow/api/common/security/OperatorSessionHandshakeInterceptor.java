package com.visionflow.api.common.security;

import org.springframework.http.HttpHeaders;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.server.HandshakeInterceptor;

import java.util.Map;
import java.util.Optional;

/** Requires an existing operator session before opening the browser WebSocket. */
public class OperatorSessionHandshakeInterceptor implements HandshakeInterceptor {

    public static final String OPERATOR_SESSION_COOKIE = "visionflow_operator_session";
    public static final String OPERATOR_SESSION_ATTRIBUTE =
            "visionflow.operator.session-token";

    private final OperatorCredentialRegistry credentialRegistry;
    private final OperatorSessionRegistry sessionRegistry;

    public OperatorSessionHandshakeInterceptor(
            OperatorCredentialRegistry credentialRegistry,
            OperatorSessionRegistry sessionRegistry
    ) {
        this.credentialRegistry = credentialRegistry;
        this.sessionRegistry = sessionRegistry;
    }

    @Override
    public boolean beforeHandshake(
            ServerHttpRequest request,
            ServerHttpResponse response,
            WebSocketHandler wsHandler,
            Map<String, Object> attributes
    ) {
        if (!credentialRegistry.isEnabled()) {
            return true;
        }

        // Browser cookie-authenticated handshakes must carry an Origin. The
        // endpoint's allowed-origin patterns perform the actual origin check.
        String origin = request.getHeaders().getFirst(HttpHeaders.ORIGIN);
        if (origin == null || origin.isBlank()) {
            return false;
        }

        String token = findCookie(
                request.getHeaders().getFirst(HttpHeaders.COOKIE),
                OPERATOR_SESSION_COOKIE
        );
        if (token == null) {
            return false;
        }

        Optional<OperatorPrincipal> principal = sessionRegistry.resolve(token);
        if (principal.isEmpty() || principal.get().passwordChangeRequired()) {
            return false;
        }

        attributes.put("visionflow.operator.username", principal.get().username());
        attributes.put("visionflow.operator.role", principal.get().role().name());
        attributes.put(OPERATOR_SESSION_ATTRIBUTE, token);
        return true;
    }

    @Override
    public void afterHandshake(
            ServerHttpRequest request,
            ServerHttpResponse response,
            WebSocketHandler wsHandler,
            Exception exception
    ) {
        // No post-handshake work is required.
    }

    private String findCookie(String cookieHeader, String cookieName) {
        if (cookieHeader == null || cookieHeader.isBlank()) {
            return null;
        }

        for (String part : cookieHeader.split(";")) {
            int separator = part.indexOf('=');
            if (separator < 0) {
                continue;
            }
            String name = part.substring(0, separator).trim();
            if (cookieName.equals(name)) {
                String value = part.substring(separator + 1).trim();
                return value.isEmpty() ? null : value;
            }
        }
        return null;
    }
}
