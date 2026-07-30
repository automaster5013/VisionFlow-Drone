package com.visionflow.api.audit.dto;

import java.time.Instant;

public record AuditRetentionStatusResponse(
        boolean enabled,
        boolean archiveConfirmed,
        boolean dryRun,
        int retentionDays,
        int batchSize,
        String cron,
        Instant cutoff,
        long eligibleCount,
        Instant checkedAt
) {
}
