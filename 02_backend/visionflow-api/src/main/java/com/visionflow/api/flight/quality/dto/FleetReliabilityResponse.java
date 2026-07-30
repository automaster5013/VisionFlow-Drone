package com.visionflow.api.flight.quality.dto;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record FleetReliabilityResponse(
        Instant generatedAt,
        String ruleVersion,
        int limitPerDrone,
        int droneCount,
        int assessmentCount,
        BigDecimal fleetAverageScore,
        int attentionDroneCount,
        List<Long> backfillCandidateDroneIds,
        List<DroneReliabilityResponse> drones
) {
}
