package com.visionflow.api.flight.quality.dto;

import com.visionflow.api.flight.quality.domain.FleetReliabilityStatus;

import java.math.BigDecimal;
import java.util.List;

public record DroneReliabilityResponse(
        Long droneId,
        String droneCode,
        String droneName,
        String modelName,
        FleetReliabilityStatus status,
        int assessmentCount,
        BigDecimal averageScore,
        int minimumScore,
        int latestScore,
        Integer previousScore,
        int completedCount,
        int abortedCount,
        long totalDurationSeconds,
        int criticalCount,
        int warningCount,
        FlightQualityAssessmentResponse latestAssessment,
        List<FleetReliabilityTrendPointResponse> trend
) {
}
