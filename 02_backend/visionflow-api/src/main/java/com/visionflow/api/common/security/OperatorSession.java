package com.visionflow.api.common.security;

import java.time.Instant;
import java.util.UUID;

public record OperatorSession(
        String token,
        UUID sessionId,
        OperatorPrincipal principal,
        Instant issuedAt,
        Instant expiresAt
) {
}
