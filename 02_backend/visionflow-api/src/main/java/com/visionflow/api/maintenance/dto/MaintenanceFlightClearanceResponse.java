package com.visionflow.api.maintenance.dto;

import com.visionflow.api.maintenance.domain.FlightClearanceStatus;
import com.visionflow.api.maintenance.domain.MaintenanceFlightGateMode;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrderStatus;

public record MaintenanceFlightClearanceResponse(
        Long droneId,
        MaintenanceFlightGateMode mode,
        boolean enforced,
        boolean flightAllowed,
        boolean attentionRequired,
        Long workOrderId,
        MaintenanceWorkOrderStatus workOrderStatus,
        FlightClearanceStatus clearanceStatus,
        String reason
) {
}
