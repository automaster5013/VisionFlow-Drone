package com.visionflow.api.flight.quality.dto;

import com.visionflow.api.flight.quality.domain.FlightQualitySeverity;

public record FlightQualityRiskResponse(
        FlightQualitySeverity severity,
        String title,
        String detail
) {
}
