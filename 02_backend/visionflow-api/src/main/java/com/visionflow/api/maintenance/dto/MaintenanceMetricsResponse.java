package com.visionflow.api.maintenance.dto;

import com.visionflow.api.maintenance.domain.MaintenanceFlightGateMode;

import java.time.Instant;

public record MaintenanceMetricsResponse(
        int windowDays,
        Instant windowStartedAt,
        Instant generatedAt,
        long totalWorkOrders,
        long openWorkOrders,
        long inProgressWorkOrders,
        long completedWorkOrders,
        long groundedWorkOrders,
        long resolvedWorkOrders,
        double resolutionRatePercent,
        Long averageStartDelayMinutes,
        Long averageResolutionMinutes,
        MaintenanceFlightGateMode gateMode,
        boolean gateEnforced,
        int totalDrones,
        int allowedDrones,
        int attentionDrones,
        int blockedDrones
) {
}
