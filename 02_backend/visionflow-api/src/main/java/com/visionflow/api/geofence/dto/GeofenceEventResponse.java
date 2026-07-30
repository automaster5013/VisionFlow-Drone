package com.visionflow.api.geofence.dto;

import com.visionflow.api.geofence.domain.DroneGeofenceEvent;
import com.visionflow.api.geofence.domain.GeofenceEventState;
import com.visionflow.api.geofence.domain.GeofenceRule;

import java.math.BigDecimal;
import java.time.LocalDateTime;

public record GeofenceEventResponse(
        Long id,
        Long droneId,
        String droneCode,
        Long geofenceId,
        String geofenceName,
        GeofenceRule ruleType,
        GeofenceEventState state,
        BigDecimal latitude,
        BigDecimal longitude,
        BigDecimal altitude,
        BigDecimal distanceMeters,
        LocalDateTime detectedAt,
        LocalDateTime resolvedAt
) {
    public static GeofenceEventResponse from(DroneGeofenceEvent event) {
        GeofenceEventState state = event.getResolvedAt() == null
                ? GeofenceEventState.ACTIVE
                : GeofenceEventState.RESOLVED;

        return new GeofenceEventResponse(
                event.getId(),
                event.getDroneId(),
                event.getDroneCode(),
                event.getGeofenceId(),
                event.getGeofenceName(),
                event.getRuleType(),
                state,
                event.getLastLatitude(),
                event.getLastLongitude(),
                event.getLastAltitude(),
                event.getDistanceMeters(),
                event.getDetectedAt(),
                event.getResolvedAt()
        );
    }
}