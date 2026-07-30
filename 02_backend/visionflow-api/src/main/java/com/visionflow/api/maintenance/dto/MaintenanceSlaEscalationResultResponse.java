package com.visionflow.api.maintenance.dto;

import java.time.Instant;

public record MaintenanceSlaEscalationResultResponse(
        Instant evaluatedAt,
        int scannedWorkOrders,
        int overdueWorkOrders,
        int escalatedIncidents,
        int alreadyEscalatedIncidents,
        int skippedIncidents
) {
}
