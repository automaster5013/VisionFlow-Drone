package com.visionflow.api.common.security;

import java.time.Instant;
import java.util.UUID;

public record OperatorSessionResponse(
        String token,
        UUID sessionId,
        String username,
        String role,
        boolean passwordChangeRequired,
        Instant issuedAt,
        Instant expiresAt
) {
    public static OperatorSessionResponse from(OperatorSession session) {
        return new OperatorSessionResponse(
                session.token(),
                session.sessionId(),
                session.principal().username(),
                session.principal().role().name(),
                session.principal().passwordChangeRequired(),
                session.issuedAt(),
                session.expiresAt()
        );
    }
}
