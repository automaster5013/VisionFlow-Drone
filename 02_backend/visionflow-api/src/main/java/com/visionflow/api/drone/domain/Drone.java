package com.visionflow.api.drone.domain;

import jakarta.persistence.*;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@Entity
@Table(
        name = "drone",
        uniqueConstraints = {
                @UniqueConstraint(
                        name = "uk_drone_code",
                        columnNames = "drone_code"
                ),
                @UniqueConstraint(
                        name = "uk_drone_serial_number",
                        columnNames = "serial_number"
                )
        }
)
public class Drone {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(
            name = "drone_code",
            nullable = false,
            length = 50
    )
    private String droneCode;

    @Column(
            name = "name",
            nullable = false,
            length = 100
    )
    private String name;

    @Column(
            name = "model_name",
            length = 100
    )
    private String modelName;

    @Column(
            name = "serial_number",
            length = 100
    )
    private String serialNumber;

    @Enumerated(EnumType.STRING)
    @Column(
            name = "status",
            nullable = false,
            length = 30
    )
    private DroneStatus status;

    @Column(
            name = "rtsp_url",
            length = 500
    )
    private String rtspUrl;

    @Column(
            name = "latitude",
            precision = 10,
            scale = 7
    )
    private BigDecimal latitude;

    @Column(
            name = "longitude",
            precision = 10,
            scale = 7
    )
    private BigDecimal longitude;

    @Column(
            name = "altitude",
            precision = 10,
            scale = 2
    )
    private BigDecimal altitude;

    @Column(name = "battery_level")
    private Integer batteryLevel;

    @Column(
            name = "heading",
            precision = 6,
            scale = 2
    )
    private BigDecimal heading;

    @Column(
            name = "pitch",
            precision = 6,
            scale = 2
    )
    private BigDecimal pitch;

    @Column(
            name = "roll",
            precision = 6,
            scale = 2
    )
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

    @Column(name = "last_connected_at")
    private LocalDateTime lastConnectedAt;

    @Column(
            name = "created_at",
            nullable = false,
            updatable = false
    )
    private LocalDateTime createdAt;

    @Column(
            name = "updated_at",
            nullable = false
    )
    private LocalDateTime updatedAt;

    protected Drone() {
    }

    public Drone(
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
            LocalDateTime lastConnectedAt
    ) {
        this.droneCode = droneCode;
        this.name = name;
        this.modelName = modelName;
        this.serialNumber = serialNumber;
        this.status = status != null
                ? status
                : DroneStatus.OFFLINE;
        this.rtspUrl = rtspUrl;
        this.latitude = latitude;
        this.longitude = longitude;
        this.altitude = altitude;
        this.batteryLevel = batteryLevel;
        this.lastConnectedAt = lastConnectedAt;
    }

    @PrePersist
    protected void onCreate() {
        LocalDateTime now = LocalDateTime.now();

        this.createdAt = now;
        this.updatedAt = now;

        if (this.status == null) {
            this.status = DroneStatus.OFFLINE;
        }

        if (this.telemetrySource == null) {
            this.telemetrySource = DroneTelemetrySource.API;
        }
    }

    @PreUpdate
    protected void onUpdate() {
        this.updatedAt = LocalDateTime.now();
    }

    public Long getId() {
        return id;
    }

    public String getDroneCode() {
        return droneCode;
    }

    public String getName() {
        return name;
    }

    public String getModelName() {
        return modelName;
    }

    public String getSerialNumber() {
        return serialNumber;
    }

    public DroneStatus getStatus() {
        return status;
    }

    public String getRtspUrl() {
        return rtspUrl;
    }

    public BigDecimal getLatitude() {
        return latitude;
    }

    public BigDecimal getLongitude() {
        return longitude;
    }

    public BigDecimal getAltitude() {
        return altitude;
    }

    public Integer getBatteryLevel() {
        return batteryLevel;
    }

    public BigDecimal getHeading() {
        return heading;
    }

    public BigDecimal getPitch() {
        return pitch;
    }

    public BigDecimal getRoll() {
        return roll;
    }

    public BigDecimal getGroundSpeed() {
        return groundSpeed;
    }

    public BigDecimal getHorizontalAccuracy() {
        return horizontalAccuracy;
    }

    public BigDecimal getVerticalAccuracy() {
        return verticalAccuracy;
    }

    public DroneTelemetrySource getTelemetrySource() {
        return telemetrySource;
    }

    public String getSourceDeviceId() {
        return sourceDeviceId;
    }

    public String getFlightSessionId() {
        return flightSessionId;
    }

    public LocalDateTime getLastConnectedAt() {
        return lastConnectedAt;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }

    public void updateBasicInformation(
            String name,
            String modelName,
            String serialNumber,
            String rtspUrl
    ) {
        this.name = name;
        this.modelName = modelName;
        this.serialNumber = serialNumber;
        this.rtspUrl = rtspUrl;
    }

    public void updateStatus(DroneStatus status) {
        this.status = status;
    }

    public void updateTelemetry(
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
            LocalDateTime lastConnectedAt
    ) {
        if (latitude != null) {
            this.latitude = latitude;
        }

        if (longitude != null) {
            this.longitude = longitude;
        }

        if (altitude != null) {
            this.altitude = altitude;
        }

        if (batteryLevel != null) {
            this.batteryLevel = batteryLevel;
        }

        if (heading != null) {
            this.heading = heading;
        }

        if (pitch != null) {
            this.pitch = pitch;
        }

        if (roll != null) {
            this.roll = roll;
        }

        if (groundSpeed != null) {
            this.groundSpeed = groundSpeed;
        }

        if (horizontalAccuracy != null) {
            this.horizontalAccuracy = horizontalAccuracy;
        }

        if (verticalAccuracy != null) {
            this.verticalAccuracy = verticalAccuracy;
        }

        if (telemetrySource != null) {
            this.telemetrySource = telemetrySource;
            this.sourceDeviceId = sourceDeviceId;
        } else if (sourceDeviceId != null) {
            this.sourceDeviceId = sourceDeviceId;
        }

        // 세션 ID가 없는 일반 텔레메트리는 이전 세션 연결을 제거합니다.
        this.flightSessionId = flightSessionId;

        if (lastConnectedAt != null) {
            this.lastConnectedAt = lastConnectedAt;
        }
    }
}
