package com.visionflow.api.flight.quality.dto;

import com.visionflow.api.flight.domain.FlightSessionStatus;

import java.time.Instant;

public record FleetReliabilityTrendPointResponse(
        String sessionId,
        String sessionName,
        FlightSessionStatus sessionStatus,
        Instant startedAt,
        Instant endedAt,
        long durationSeconds,
        FlightQualityAssessmentResponse quality
) {
}
