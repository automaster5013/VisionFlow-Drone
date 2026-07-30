package com.visionflow.api.flight.quality.domain;

public record FlightQualityRisk(
        FlightQualitySeverity severity,
        String title,
        String detail
) {
}
