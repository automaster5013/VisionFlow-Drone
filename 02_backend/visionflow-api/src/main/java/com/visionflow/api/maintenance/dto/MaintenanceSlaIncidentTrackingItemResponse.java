package com.visionflow.api.maintenance.dto;

import com.visionflow.api.incident.domain.IncidentPriority;
import com.visionflow.api.incident.domain.IncidentStatus;
import com.visionflow.api.maintenance.domain.FlightClearanceStatus;
import com.visionflow.api.maintenance.domain.MaintenanceSlaClosureStatus;
import com.visionflow.api.maintenance.domain.MaintenanceSlaResponseStatus;
import com.visionflow.api.maintenance.domain.MaintenanceSlaStatus;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrderStatus;

import java.time.Instant;

public record MaintenanceSlaIncidentTrackingItemResponse(
        Long workOrderId,
        Long incidentId,
        Long droneId,
        MaintenanceWorkOrderStatus workOrderStatus,
        FlightClearanceStatus flightClearanceStatus,
        IncidentStatus incidentStatus,
        IncidentPriority incidentPriority,
        String incidentTitle,
        String incidentAssignee,
        MaintenanceSlaStatus slaStatus,
        Instant slaDueAt,
        Long slaOverdueMinutes,
        boolean escalated,
        Instant escalatedAt,
        String escalationActor,
        String escalationNote,
        MaintenanceSlaResponseStatus responseStatus,
        String recommendedAction,
        MaintenanceSlaClosureStatus closureStatus,
        String closureRecommendedAction
) {
}
