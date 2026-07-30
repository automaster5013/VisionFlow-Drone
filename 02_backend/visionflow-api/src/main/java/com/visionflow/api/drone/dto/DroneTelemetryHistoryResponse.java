package com.visionflow.api.drone.dto;

import com.visionflow.api.drone.domain.DroneTelemetryHistory;
import com.visionflow.api.drone.domain.DroneTelemetrySource;

import java.math.BigDecimal;
import java.time.LocalDateTime;

public record DroneTelemetryHistoryResponse(
        Long id,
        Long droneId,
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
        String status,
        LocalDateTime recordedAt
) {

    public static DroneTelemetryHistoryResponse from(
            DroneTelemetryHistory history
    ) {
        return new DroneTelemetryHistoryResponse(
                history.getId(),
                history.getDroneId(),
                history.getLatitude(),
                history.getLongitude(),
                history.getAltitude(),
                history.getBatteryLevel(),
                history.getHeading(),
                history.getPitch(),
                history.getRoll(),
                history.getGroundSpeed(),
                history.getHorizontalAccuracy(),
                history.getVerticalAccuracy(),
                history.getTelemetrySource(),
                history.getSourceDeviceId(),
                history.getFlightSessionId(),
                history.getStatus(),
                history.getRecordedAt()
        );
    }
}
