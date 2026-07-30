package com.visionflow.api.flight.quality.dto;

import com.visionflow.api.flight.quality.domain.FleetReliabilityStatus;
import com.visionflow.api.flight.quality.domain.FlightQualityIncidentSyncAction;
import com.visionflow.api.incident.dto.IncidentResponse;

public record FlightQualityIncidentSyncItemResponse(
        Long droneId,
        FleetReliabilityStatus reliabilityStatus,
        FlightQualityIncidentSyncAction action,
        IncidentResponse incident
) {
}
