package com.visionflow.api.flight.dto;

import java.time.LocalDateTime;

public interface TelemetryFlightSessionSummaryProjection {

    String getSessionId();

    LocalDateTime getStartedAt();

    LocalDateTime getEndedAt();

    Long getTelemetryCount();
}
