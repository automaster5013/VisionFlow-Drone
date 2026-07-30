package com.visionflow.api.geofence.dto;

import com.visionflow.api.geofence.domain.DroneGeofence;
import com.visionflow.api.geofence.domain.GeofenceRule;

import java.math.BigDecimal;
import java.time.LocalDateTime;

public record GeofenceResponse(
        Long id,
        String name,
        GeofenceRule ruleType,
        BigDecimal centerLatitude,
        BigDecimal centerLongitude,
        BigDecimal radiusMeters,
        boolean active,
        LocalDateTime createdAt,
        LocalDateTime updatedAt
) {
    public static GeofenceResponse from(DroneGeofence geofence) {
        return new GeofenceResponse(
                geofence.getId(),
                geofence.getName(),
                geofence.getRuleType(),
                geofence.getCenterLatitude(),
                geofence.getCenterLongitude(),
                geofence.getRadiusMeters(),
                geofence.isActive(),
                geofence.getCreatedAt(),
                geofence.getUpdatedAt()
        );
    }
}