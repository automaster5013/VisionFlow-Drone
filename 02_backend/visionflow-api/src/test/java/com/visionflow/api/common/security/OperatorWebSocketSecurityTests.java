package com.visionflow.api.common.security;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.WebSocketSession;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.HashMap;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class OperatorWebSocketSecurityTests {

    private OperatorCredentialRegistry credentialRegistry;
    private OperatorSessionRegistry sessionRegistry;
    private OperatorSessionHandshakeInterceptor interceptor;
    private MutableClock clock;

    @BeforeEach
    void setUp() {
        credentialRegistry = enabledCredentialRegistry();
        clock = new MutableClock(Instant.parse("2026-09-13T00:00:00Z"));
        sessionRegistry = new OperatorSessionRegistry(
                Duration.ofHours(1),
                Duration.ofMinutes(30),
                10,
                clock
        );
        interceptor = new OperatorSessionHandshakeInterceptor(
                credentialRegistry,
                sessionRegistry
        );
    }

    @Test
    void handshakeAcceptsOriginWithLiveOperatorSession() throws Exception {
        var issued = sessionRegistry.issue(
                new OperatorPrincipal("operator-test", OperatorRole.OPERATOR)
        );
        var request = mockRequest(
                "https://visionflow.example",
                OperatorSessionHandshakeInterceptor.OPERATOR_SESSION_COOKIE
                        + "=" + issued.token()
        );
        Map<String, Object> attributes = new HashMap<>();

        boolean accepted = interceptor.beforeHandshake(
                request,
                mock(ServerHttpResponse.class),
                mock(WebSocketHandler.class),
                attributes
        );

        assertThat(accepted).isTrue();
        assertThat(attributes)
                .containsEntry("visionflow.operator.username", "operator-test")
                .containsEntry("visionflow.operator.role", "OPERATOR");
    }

    @Test
    void handshakeRejectsMissingOriginOrSession() throws Exception {
        var noOrigin = mockRequest(
                null,
                OperatorSessionHandshakeInterceptor.OPERATOR_SESSION_COOKIE
                        + "=arbitrary-token"
        );
        var noSession = mockRequest("https://visionflow.example", null);

        assertThat(interceptor.beforeHandshake(
                noOrigin,
                mock(ServerHttpResponse.class),
                mock(WebSocketHandler.class),
                new HashMap<>()
        )).isFalse();
        assertThat(interceptor.beforeHandshake(
                noSession,
                mock(ServerHttpResponse.class),
                mock(WebSocketHandler.class),
                new HashMap<>()
        )).isFalse();
    }

    @Test
    void establishedWebSocketClosesAfterOperatorSessionIsRevoked() throws Exception {
        var issued = sessionRegistry.issue(
                new OperatorPrincipal("operator-test", OperatorRole.OPERATOR)
        );
        Map<String, Object> attributes = new HashMap<>();
        attributes.put(
                OperatorSessionHandshakeInterceptor.OPERATOR_SESSION_ATTRIBUTE,
                issued.token()
        );
        WebSocketSession session = mock(WebSocketSession.class);
        when(session.getId()).thenReturn("ws-test-session");
        when(session.getAttributes()).thenReturn(attributes);
        when(session.isOpen()).thenReturn(true);

        OperatorWebSocketSessionTracker tracker =
                new OperatorWebSocketSessionTracker(credentialRegistry, sessionRegistry);
        WebSocketHandler decorated = tracker.decorate(mock(WebSocketHandler.class));
        decorated.afterConnectionEstablished(session);
        sessionRegistry.revoke(issued.token());

        tracker.closeSessionsWithoutValidOperatorSession();

        verify(session).close(CloseStatus.POLICY_VIOLATION);
    }

    @Test
    void periodicWebSocketChecksDoNotRefreshIdleSession() throws Exception {
        var issued = sessionRegistry.issue(
                new OperatorPrincipal("operator-test", OperatorRole.OPERATOR)
        );
        Map<String, Object> attributes = new HashMap<>();
        attributes.put(
                OperatorSessionHandshakeInterceptor.OPERATOR_SESSION_ATTRIBUTE,
                issued.token()
        );
        WebSocketSession session = mock(WebSocketSession.class);
        when(session.getId()).thenReturn("ws-idle-session");
        when(session.getAttributes()).thenReturn(attributes);
        when(session.isOpen()).thenReturn(true);

        OperatorWebSocketSessionTracker tracker =
                new OperatorWebSocketSessionTracker(credentialRegistry, sessionRegistry);
        tracker.decorate(mock(WebSocketHandler.class))
                .afterConnectionEstablished(session);

        clock.advance(Duration.ofMinutes(25));
        tracker.closeSessionsWithoutValidOperatorSession();
        clock.advance(Duration.ofMinutes(6));
        tracker.closeSessionsWithoutValidOperatorSession();

        verify(session).close(CloseStatus.POLICY_VIOLATION);
    }

    @Test
    void disabledSecurityKeepsLocalWebSocketDevelopmentAvailable() throws Exception {
        OperatorSessionHandshakeInterceptor openInterceptor =
                new OperatorSessionHandshakeInterceptor(
                        disabledCredentialRegistry(),
                        sessionRegistry
                );
        var request = mockRequest(null, null);

        assertThat(openInterceptor.beforeHandshake(
                request,
                mock(ServerHttpResponse.class),
                mock(WebSocketHandler.class),
                new HashMap<>()
        )).isTrue();
    }

    private static OperatorCredentialRegistry enabledCredentialRegistry() {
        return new OperatorCredentialRegistry(
                true,
                "viewer",
                "viewer-test-key-12345678901234567890",
                "operator",
                "operator-test-key-12345678901234567890",
                "admin",
                "admin-test-key-12345678901234567890"
        );
    }

    private static ServerHttpRequest mockRequest(String origin, String cookie) {
        HttpHeaders headers = new HttpHeaders();
        if (origin != null) {
            headers.add(HttpHeaders.ORIGIN, origin);
        }
        if (cookie != null) {
            headers.add(HttpHeaders.COOKIE, cookie);
        }
        ServerHttpRequest request = mock(ServerHttpRequest.class);
        when(request.getHeaders()).thenReturn(headers);
        return request;
    }

    private static OperatorCredentialRegistry disabledCredentialRegistry() {
        return new OperatorCredentialRegistry(
                false,
                "viewer",
                "",
                "operator",
                "",
                "admin",
                ""
        );
    }

    private static final class MutableClock extends Clock {

        private Instant instant;

        private MutableClock(Instant instant) {
            this.instant = instant;
        }

        private void advance(Duration duration) {
            instant = instant.plus(duration);
        }

        @Override
        public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            return this;
        }

        @Override
        public Instant instant() {
            return instant;
        }
    }
}
