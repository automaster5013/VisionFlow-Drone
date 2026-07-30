package com.visionflow.api.incident.dto;

import com.visionflow.api.incident.domain.IncidentLocationSource;

import java.math.BigDecimal;
import java.time.Instant;

public record IncidentContextResponse(
        Long incidentId,
        Long droneId,
        String sessionId,
        Instant occurredAt,
        boolean replayAvailable,
        IncidentLocationSource locationSource,
        BigDecimal latitude,
        BigDecimal longitude,
        BigDecimal altitude,
        Instant locationRecordedAt,
        Long aiEventId,
        boolean snapshotAvailable,
        String snapshotUrl
) {
}
