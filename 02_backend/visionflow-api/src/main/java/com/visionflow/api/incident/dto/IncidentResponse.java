package com.visionflow.api.incident.dto;

import com.visionflow.api.incident.domain.Incident;
import com.visionflow.api.incident.domain.IncidentPriority;
import com.visionflow.api.incident.domain.IncidentSourceType;
import com.visionflow.api.incident.domain.IncidentStatus;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;

public record IncidentResponse(
        Long id,
        IncidentSourceType sourceType,
        Long sourceId,
        Long droneId,
        String sessionId,
        IncidentPriority priority,
        IncidentStatus status,
        String title,
        String summary,
        String assignee,
        String assignedBy,
        LocalDateTime assignedAt,
        LocalDateTime occurredAt,
        LocalDateTime resolvedAt,
        LocalDateTime closedAt,
        Instant slaDueAt,
        Instant slaBreachedAt,
        int escalationLevel,
        LocalDateTime createdAt,
        LocalDateTime updatedAt
) {
    public static IncidentResponse from(Incident incident) {
        return new IncidentResponse(
                incident.getId(),
                incident.getSourceType(),
                incident.getSourceId(),
                incident.getDroneId(),
                incident.getSessionId(),
                incident.getPriority(),
                incident.getStatus(),
                incident.getTitle(),
                incident.getSummary(),
                incident.getAssignee(),
                incident.getAssignedBy(),
                incident.getAssignedAt(),
                incident.getOccurredAt(),
                incident.getResolvedAt(),
                incident.getClosedAt(),
                toInstant(incident.getSlaDueAt()),
                toInstant(incident.getSlaBreachedAt()),
                incident.getEscalationLevel(),
                incident.getCreatedAt(),
                incident.getUpdatedAt()
        );
    }

    private static Instant toInstant(LocalDateTime value) {
        return value == null ? null : value.toInstant(ZoneOffset.UTC);
    }
}
