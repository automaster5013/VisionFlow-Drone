package com.visionflow.api.maintenance.dto;

import com.visionflow.api.maintenance.domain.MaintenanceFlightGateMode;

import java.time.Instant;
import java.util.List;

public record MaintenancePriorityQueueResponse(
        MaintenanceFlightGateMode mode,
        boolean enforced,
        Instant evaluatedAt,
        int totalDrones,
        int urgentDrones,
        int attentionDrones,
        int normalDrones,
        int overdueDrones,
        int dueSoonDrones,
        List<MaintenancePriorityItemResponse> priorities
) {
}
