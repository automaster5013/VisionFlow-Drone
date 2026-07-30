package com.visionflow.api.common.security;

import java.time.Instant;
import java.util.UUID;

public record OperatorSessionResponse(
        String token,
        UUID sessionId,
        String username,
        String role,
        Instant issuedAt,
        Instant expiresAt
) {
    public static OperatorSessionResponse from(OperatorSession session) {
        return new OperatorSessionResponse(
                session.token(),
                session.sessionId(),
                session.principal().username(),
                session.principal().role().name(),
                session.issuedAt(),
                session.expiresAt()
        );
    }
}
