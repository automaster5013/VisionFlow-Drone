package com.visionflow.api.maintenance.dto;

import com.visionflow.api.maintenance.domain.MaintenanceFlightGateMode;

import java.time.Instant;
import java.util.List;

public record MaintenanceFleetFlightClearanceResponse(
        MaintenanceFlightGateMode mode,
        boolean enforced,
        int totalDrones,
        int allowedDrones,
        int attentionDrones,
        int blockedDrones,
        Instant evaluatedAt,
        List<MaintenanceFlightClearanceResponse> clearances
) {
}
