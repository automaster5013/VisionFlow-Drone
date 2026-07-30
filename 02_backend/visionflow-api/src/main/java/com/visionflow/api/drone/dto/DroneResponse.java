package com.visionflow.api.drone.dto;

import com.visionflow.api.drone.domain.Drone;
import com.visionflow.api.drone.domain.DroneStatus;
import com.visionflow.api.drone.domain.DroneTelemetrySource;

import java.math.BigDecimal;
import java.time.LocalDateTime;

public record DroneResponse(
        Long id,
        String droneCode,
        String name,
        String modelName,
        String serialNumber,
        DroneStatus status,
        String rtspUrl,
        BigDecimal latitude,
        BigDecimal longitude,
        BigDecimal altitude,
        Integer batteryLevel,
        BigDecimal heading,
        BigDecimal pitch,
        BigDecimal roll,
        BigDecimal groundSpeed,
        BigDecimal horizontalAccuracy,
        BigDecimal verticalAccuracy,
        DroneTelemetrySource telemetrySource,
        String sourceDeviceId,
        String flightSessionId,
        LocalDateTime lastConnectedAt,
        LocalDateTime createdAt,
        LocalDateTime updatedAt
) {

    public static DroneResponse from(Drone drone) {
        return new DroneResponse(
                drone.getId(),
                drone.getDroneCode(),
                drone.getName(),
                drone.getModelName(),
                drone.getSerialNumber(),
                drone.getStatus(),
                drone.getRtspUrl(),
                drone.getLatitude(),
                drone.getLongitude(),
                drone.getAltitude(),
                drone.getBatteryLevel(),
                drone.getHeading(),
                drone.getPitch(),
                drone.getRoll(),
                drone.getGroundSpeed(),
                drone.getHorizontalAccuracy(),
                drone.getVerticalAccuracy(),
                drone.getTelemetrySource(),
                drone.getSourceDeviceId(),
                drone.getFlightSessionId(),
                drone.getLastConnectedAt(),
                drone.getCreatedAt(),
                drone.getUpdatedAt()
        );
    }
}
