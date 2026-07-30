package com.visionflow.api.drone.domain;

import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@Entity
@Table(
        name = "drone_telemetry_history",
        indexes = {
                @Index(
                        name = "idx_telemetry_drone_recorded_at",
                        columnList = "drone_id, recorded_at"
                ),
                @Index(
                        name = "idx_telemetry_recorded_at",
                        columnList = "recorded_at"
                ),
                @Index(
                        name = "idx_telemetry_flight_session_recorded_at",
                        columnList = "flight_session_id, recorded_at"
                )
        }
)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@Access(AccessType.FIELD)
public class DroneTelemetryHistory {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "drone_id", nullable = false)
    private Long droneId;

    @Column(precision = 10, scale = 7)
    private BigDecimal latitude;

    @Column(precision = 10, scale = 7)
    private BigDecimal longitude;

    @Column(precision = 10, scale = 2)
    private BigDecimal altitude;

    @Column(name = "battery_level")
    private Integer batteryLevel;

    @Column(precision = 6, scale = 2)
    private BigDecimal heading;

    @Column(precision = 6, scale = 2)
    private BigDecimal pitch;

    @Column(precision = 6, scale = 2)
    private BigDecimal roll;

    @Column(
            name = "ground_speed",
            precision = 10,
            scale = 2
    )
    private BigDecimal groundSpeed;

    @Column(
            name = "horizontal_accuracy",
            precision = 10,
            scale = 2
    )
    private BigDecimal horizontalAccuracy;

    @Column(
            name = "vertical_accuracy",
            precision = 10,
            scale = 2
    )
    private BigDecimal verticalAccuracy;

    @Enumerated(EnumType.STRING)
    @Column(
            name = "telemetry_source",
            nullable = false,
            length = 30
    )
    private DroneTelemetrySource telemetrySource;

    @Column(
            name = "source_device_id",
            length = 100
    )
    private String sourceDeviceId;

    @Column(
            name = "flight_session_id",
            length = 36
    )
    private String flightSessionId;

    @Column(nullable = false, length = 32)
    private String status;

    @Column(name = "recorded_at", nullable = false)
    private LocalDateTime recordedAt;

    @Column(
            name = "created_at",
            nullable = false,
            updatable = false
    )
    private LocalDateTime createdAt;

    private DroneTelemetryHistory(
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
        this.droneId = droneId;
        this.latitude = latitude;
        this.longitude = longitude;
        this.altitude = altitude;
        this.batteryLevel = batteryLevel;
        this.heading = heading;
        this.pitch = pitch;
        this.roll = roll;
        this.groundSpeed = groundSpeed;
        this.horizontalAccuracy = horizontalAccuracy;
        this.verticalAccuracy = verticalAccuracy;
        this.telemetrySource = telemetrySource;
        this.sourceDeviceId = sourceDeviceId;
        this.flightSessionId = flightSessionId;
        this.status = status;
        this.recordedAt = recordedAt;
    }

    public static DroneTelemetryHistory from(
            Drone drone,
            LocalDateTime recordedAt
    ) {
        return new DroneTelemetryHistory(
                drone.getId(),
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
                drone.getStatus().name(),
                recordedAt
        );
    }

    @PrePersist
    private void prePersist() {
        if (createdAt == null) {
            createdAt = LocalDateTime.now();
        }
    }
}
