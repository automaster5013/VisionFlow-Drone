package com.visionflow.api.common.security;

import java.time.Instant;
import java.util.UUID;

public record OperatorSessionSummary(
        UUID sessionId,
        String username,
        OperatorRole role,
        Instant issuedAt,
        Instant lastSeenAt,
        Instant idleExpiresAt,
        Instant expiresAt,
        String clientFingerprint,
        boolean current
) {
}
