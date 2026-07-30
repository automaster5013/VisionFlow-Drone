package com.visionflow.api.flight.quality.dto;

import java.util.List;

public record FlightQualityBackfillResponse(
        Long droneId,
        String ruleVersion,
        boolean force,
        int candidateCount,
        int evaluatedCount,
        int skippedCount,
        int failedCount,
        List<Failure> failures
) {

    public record Failure(
            String sessionId,
            String message
    ) {
    }
}
