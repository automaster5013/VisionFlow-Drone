package com.visionflow.api.maintenance.dto;

import java.time.Instant;
import java.util.List;

public record MaintenanceSlaIncidentTrackingResponse(
        Instant evaluatedAt,
        int windowDays,
        int totalWorkOrders,
        int connectedIncidents,
        int overdueWorkOrders,
        int escalatedIncidents,
        int monitoringWorkOrders,
        int escalationPendingIncidents,
        int assignmentRequiredIncidents,
        int inResponseIncidents,
        int completedResponses,
        int pendingWorkOrderClosures,
        int returnToServiceConfirmed,
        int groundedClosures,
        int closureConsistencyAlerts,
        List<MaintenanceSlaIncidentTrackingItemResponse> items
) {
}
