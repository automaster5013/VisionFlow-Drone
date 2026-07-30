package com.visionflow.api.maintenance.dto;

import com.visionflow.api.maintenance.domain.FlightClearanceStatus;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrder;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrderStatus;

import java.time.LocalDateTime;

public record MaintenanceWorkOrderResponse(
        Long id,
        Long incidentId,
        Long droneId,
        String sessionId,
        Long sourceAssessmentId,
        MaintenanceWorkOrderStatus status,
        FlightClearanceStatus clearanceStatus,
        String assignee,
        String finding,
        String resolutionNote,
        LocalDateTime openedAt,
        LocalDateTime startedAt,
        LocalDateTime completedAt,
        LocalDateTime clearedAt,
        LocalDateTime createdAt,
        LocalDateTime updatedAt
) {
    public static MaintenanceWorkOrderResponse from(
            MaintenanceWorkOrder workOrder
    ) {
        return new MaintenanceWorkOrderResponse(
                workOrder.getId(),
                workOrder.getIncidentId(),
                workOrder.getDroneId(),
                workOrder.getSessionId(),
                workOrder.getSourceAssessmentId(),
                workOrder.getStatus(),
                workOrder.getClearanceStatus(),
                workOrder.getAssignee(),
                workOrder.getFinding(),
                workOrder.getResolutionNote(),
                workOrder.getOpenedAt(),
                workOrder.getStartedAt(),
                workOrder.getCompletedAt(),
                workOrder.getClearedAt(),
                workOrder.getCreatedAt(),
                workOrder.getUpdatedAt()
        );
    }
}
