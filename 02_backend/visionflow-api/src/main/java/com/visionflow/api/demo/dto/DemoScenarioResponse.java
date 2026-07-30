package com.visionflow.api.demo.dto;

import com.visionflow.api.demo.domain.DemoScenarioStage;
import com.visionflow.api.incident.dto.IncidentContextResponse;

import java.time.Instant;

public record DemoScenarioResponse(
        String scenarioId,
        Long droneId,
        String flightSessionId,
        Long aiEventId,
        Long aiAlertId,
        Long incidentId,
        DemoScenarioStage stage,
        String lastMessage,
        Instant startedAt,
        Instant updatedAt,
        Instant completedAt,
        IncidentContextResponse incidentContext
) {
}
