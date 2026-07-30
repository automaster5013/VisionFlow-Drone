package com.visionflow.api.maintenance.dto;

import com.visionflow.api.maintenance.domain.MaintenanceWorkOrderActionType;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrderHistory;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrderStatus;

import java.time.LocalDateTime;

public record MaintenanceWorkOrderHistoryResponse(
        Long id,
        MaintenanceWorkOrderActionType actionType,
        MaintenanceWorkOrderStatus previousStatus,
        MaintenanceWorkOrderStatus newStatus,
        String actor,
        String note,
        LocalDateTime createdAt
) {
    public static MaintenanceWorkOrderHistoryResponse from(
            MaintenanceWorkOrderHistory history
    ) {
        return new MaintenanceWorkOrderHistoryResponse(
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
