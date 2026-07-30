package com.visionflow.api.incident.dto;

import com.visionflow.api.incident.domain.IncidentActionHistory;
import com.visionflow.api.incident.domain.IncidentActionType;
import com.visionflow.api.incident.domain.IncidentStatus;

import java.time.LocalDateTime;

public record IncidentActionHistoryResponse(
        Long id,
        IncidentActionType actionType,
        IncidentStatus previousStatus,
        IncidentStatus newStatus,
        String actor,
        String note,
        LocalDateTime createdAt
) {
    public static IncidentActionHistoryResponse from(
            IncidentActionHistory history
    ) {
        return new IncidentActionHistoryResponse(
                history.getId(),
                history.getActionType(),
                history.getPreviousStatus(),
                history.getNewStatus(),
                history.getActor(),
                history.getNote(),
                history.getCreatedAt()
        );
    }
}
