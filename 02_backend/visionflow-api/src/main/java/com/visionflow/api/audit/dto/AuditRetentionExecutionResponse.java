package com.visionflow.api.audit.dto;

import java.time.Instant;

public record AuditRetentionExecutionResponse(
        boolean enabled,
        String trigger,
        int retentionDays,
        int batchSize,
        Instant cutoff,
        int deletedCount,
        long remainingEligibleCount,
        Instant executedAt
) {
}
