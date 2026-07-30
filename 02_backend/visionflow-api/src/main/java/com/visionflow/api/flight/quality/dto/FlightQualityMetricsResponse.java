package com.visionflow.api.flight.quality.dto;

import java.math.BigDecimal;

public record FlightQualityMetricsResponse(
        long telemetryCount,
        long validCoordinateCount,
        BigDecimal coordinateCoveragePercent,
        BigDecimal batteryCoveragePercent,
        BigDecimal maxTelemetryGapSeconds,
        int unrealisticJumpCount,
        int altitudeSpikeCount,
        int batteryIncreaseCount,
        Integer minimumBatteryLevel,
        long aiEventCount,
        long detectedEventCount,
        BigDecimal averageInferenceMs,
        BigDecimal snapshotCoveragePercent
) {
}
