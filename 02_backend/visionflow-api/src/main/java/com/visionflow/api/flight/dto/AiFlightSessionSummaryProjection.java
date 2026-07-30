package com.visionflow.api.flight.dto;

import java.time.LocalDateTime;

public interface AiFlightSessionSummaryProjection {

    String getSessionId();

    LocalDateTime getStartedAt();

    LocalDateTime getEndedAt();

    Long getAiEventCount();

    Long getDetectionCount();
}
