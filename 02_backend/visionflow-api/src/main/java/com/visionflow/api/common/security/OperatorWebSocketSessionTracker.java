package com.visionflow.api.common.security;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.WebSocketHandlerDecorator;
import org.springframework.web.socket.handler.WebSocketHandlerDecoratorFactory;

import java.io.IOException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

/** Closes established sockets shortly after their operator session is revoked. */
@Component
public class OperatorWebSocketSessionTracker implements WebSocketHandlerDecoratorFactory {

    private final OperatorCredentialRegistry credentialRegistry;
    private final OperatorSessionRegistry sessionRegistry;
    private final ConcurrentMap<String, WebSocketSession> sessions =
            new ConcurrentHashMap<>();

    public OperatorWebSocketSessionTracker(
            OperatorCredentialRegistry credentialRegistry,
            OperatorSessionRegistry sessionRegistry
    ) {
        this.credentialRegistry = credentialRegistry;
        this.sessionRegistry = sessionRegistry;
    }

    @Override
    public WebSocketHandler decorate(WebSocketHandler handler) {
        return new WebSocketHandlerDecorator(handler) {
            @Override
            public void afterConnectionEstablished(WebSocketSession session)
                    throws Exception {
                if (credentialRegistry.isEnabled()) {
                    sessions.put(session.getId(), session);
                }
                super.afterConnectionEstablished(session);
            }

            @Override
            public void afterConnectionClosed(
                    WebSocketSession session,
                    CloseStatus closeStatus
            ) throws Exception {
                sessions.remove(session.getId());
                super.afterConnectionClosed(session, closeStatus);
            }
        };
    }

    @Scheduled(fixedDelayString = "30000")
    public void closeSessionsWithoutValidOperatorSession() {
        if (!credentialRegistry.isEnabled()) {
            return;
        }

        sessions.forEach((sessionId, session) -> {
            Object tokenValue = session.getAttributes().get(
                    OperatorSessionHandshakeInterceptor.OPERATOR_SESSION_ATTRIBUTE
            );
            if (!(tokenValue instanceof String token)
                    || !sessionRegistry.isValid(token)) {
                closeRevokedSession(sessionId, session);
            }
        });
    }

    private void closeRevokedSession(String sessionId, WebSocketSession session) {
        sessions.remove(sessionId, session);
        if (!session.isOpen()) {
            return;
        }

        try {
            session.close(CloseStatus.POLICY_VIOLATION);
        } catch (IOException exception) {
            // The peer may have closed concurrently; it must not remain tracked.
            sessions.remove(sessionId, session);
        }
    }
}
