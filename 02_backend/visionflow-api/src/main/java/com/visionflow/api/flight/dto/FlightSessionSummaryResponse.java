package com.visionflow.api.flight.dto;

import java.time.Instant;

public record FlightSessionSummaryResponse(
        String sessionId,
        Long droneId,
        String name,
        String description,
        String status,
        String sourceDeviceId,
        Instant startedAt,
        Instant endedAt,
        long durationSeconds,
        long telemetryCount,
        long aiEventCount,
        long detectionCount,
        boolean hasTelemetry,
        boolean hasAiEvents,
        boolean managed
) {
}
