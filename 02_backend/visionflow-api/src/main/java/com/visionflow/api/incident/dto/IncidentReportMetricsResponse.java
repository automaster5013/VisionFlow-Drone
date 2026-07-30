package com.visionflow.api.incident.dto;

import java.time.Instant;

public record IncidentReportMetricsResponse(
        Instant responseStartedAt,
        Instant resolvedAt,
        Instant closedAt,
        Long firstResponseSeconds,
        Long resolutionSeconds,
        int actionCount,
        int noteCount,
        boolean evidenceAvailable
) {
}
