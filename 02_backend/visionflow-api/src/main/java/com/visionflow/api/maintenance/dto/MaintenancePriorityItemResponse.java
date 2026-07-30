package com.visionflow.api.maintenance.dto;

import com.visionflow.api.maintenance.domain.FlightClearanceStatus;
import com.visionflow.api.maintenance.domain.MaintenancePriorityLevel;
import com.visionflow.api.maintenance.domain.MaintenanceSlaStatus;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrderStatus;

import java.time.Instant;

public record MaintenancePriorityItemResponse(
        Long droneId,
        MaintenancePriorityLevel priority,
        int riskScore,
        boolean flightAllowed,
        boolean attentionRequired,
        Long workOrderId,
        MaintenanceWorkOrderStatus workOrderStatus,
        FlightClearanceStatus clearanceStatus,
        Instant openedAt,
        Long waitingMinutes,
        MaintenanceSlaStatus slaStatus,
        Instant slaDueAt,
        Long slaRemainingMinutes,
        Long slaOverdueMinutes,
        String recommendedAction,
        String reason
) {
}
