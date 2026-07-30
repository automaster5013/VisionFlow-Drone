package com.visionflow.api.flight.quality.domain;

import com.visionflow.api.flight.domain.FlightSessionStatus;

public record FlightQualitySnapshot(
        FlightSessionStatus sessionStatus,
        int score,
        FlightQualityGrade grade,
        int dataScore,
        int flightScore,
        int aiScore,
        long telemetryCount,
        long validCoordinateCount,
        double coordinateCoveragePercent,
        double batteryCoveragePercent,
        Double maxTelemetryGapSeconds,
        int unrealisticJumpCount,
        int altitudeSpikeCount,
        int batteryIncreaseCount,
        Integer minimumBatteryLevel,
        long aiEventCount,
        long detectedEventCount,
        Double averageInferenceMs,
        double snapshotCoveragePercent,
        int warningCount,
        int criticalCount,
        FlightQualityRisk primaryRisk
) {
}
