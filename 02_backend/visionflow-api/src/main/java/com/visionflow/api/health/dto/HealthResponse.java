package com.visionflow.api.health.dto;

import java.time.LocalDateTime;

public record HealthResponse(
        String service,
        String applicationStatus,
        String databaseStatus,
        LocalDateTime checkedAt
) {
}