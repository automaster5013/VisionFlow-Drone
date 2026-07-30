package com.visionflow.api.geofence.domain;

import com.visionflow.api.drone.domain.Drone;
import jakarta.persistence.*;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@Entity
@Table(name = "drone_geofence_event")
public class DroneGeofenceEvent {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "drone_id", nullable = false)
    private Long droneId;

    @Column(name = "drone_code", nullable = false, length = 100)
    private String droneCode;

    @Column(name = "flight_session_id", length = 36)
    private String flightSessionId;

    @Column(
            name = "detected_latitude",
            nullable = false,
            precision = 10,
            scale = 7
    )
    private BigDecimal detectedLatitude;

    @Column(
            name = "detected_longitude",
            nullable = false,
            precision = 10,
            scale = 7
    )
    private BigDecimal detectedLongitude;

    @Column(
            name = "detected_altitude",
            precision = 10,
            scale = 2
    )
    private BigDecimal detectedAltitude;

    @Column(name = "geofence_id", nullable = false)
    private Long geofenceId;

    @Column(name = "geofence_name", nullable = false, length = 100)
    private String geofenceName;

    @Enumerated(EnumType.STRING)
    @Column(name = "rule_type", nullable = false, length = 20)
    private GeofenceRule ruleType;

    @Column(name = "last_latitude", nullable = false, precision = 10, scale = 7)
    private BigDecimal lastLatitude;

    @Column(name = "last_longitude", nullable = false, precision = 10, scale = 7)
    private BigDecimal lastLongitude;

    @Column(name = "last_altitude", precision = 10, scale = 2)
    private BigDecimal lastAltitude;

    @Column(name = "distance_meters", nullable = false, precision = 12, scale = 2)
    private BigDecimal distanceMeters;

    @Column(name = "detected_at", nullable = false)
    private LocalDateTime detectedAt;

    @Column(name = "resolved_at")
    private LocalDateTime resolvedAt;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    protected DroneGeofenceEvent() {
    }

    public static DroneGeofenceEvent start(
            Drone drone,
            DroneGeofence geofence,
            BigDecimal distanceMeters,
            LocalDateTime detectedAt
    ) {
        DroneGeofenceEvent event = new DroneGeofenceEvent();

        event.droneId = drone.getId();
        event.droneCode = drone.getDroneCode();
        event.flightSessionId = drone.getFlightSessionId();
        event.detectedLatitude = drone.getLatitude();
        event.detectedLongitude = drone.getLongitude();
        event.detectedAltitude = drone.getAltitude();
        event.geofenceId = geofence.getId();
        event.geofenceName = geofence.getName();
        event.ruleType = geofence.getRuleType();
        event.applyTelemetry(drone, distanceMeters);
        event.detectedAt = detectedAt;

        return event;
    }

    public void applyTelemetry(Drone drone, BigDecimal distanceMeters) {
        this.lastLatitude = drone.getLatitude();
        this.lastLongitude = drone.getLongitude();
        this.lastAltitude = drone.getAltitude();
        this.distanceMeters = distanceMeters;
    }

    public void resolve(
            Drone drone,
            BigDecimal distanceMeters,
            LocalDateTime resolvedAt
    ) {
        applyTelemetry(drone, distanceMeters);
        this.resolvedAt = resolvedAt;
    }

    public void resolve(LocalDateTime resolvedAt) {
        if (this.resolvedAt != null) {
            return;
        }

        this.resolvedAt = resolvedAt;
    }

    @PrePersist
    void prePersist() {
        LocalDateTime now = LocalDateTime.now();
        createdAt = now;
        updatedAt = now;
    }

    @PreUpdate
    void preUpdate() {
        updatedAt = LocalDateTime.now();
    }

    public Long getId() {
        return id;
    }

    public Long getDroneId() {
        return droneId;
    }

    public String getDroneCode() {
        return droneCode;
    }

    public String getFlightSessionId() {
        return flightSessionId;
    }

    public BigDecimal getDetectedLatitude() {
        return detectedLatitude;
    }

    public BigDecimal getDetectedLongitude() {
        return detectedLongitude;
    }

    public BigDecimal getDetectedAltitude() {
        return detectedAltitude;
    }

    public Long getGeofenceId() {
        return geofenceId;
    }

    public String getGeofenceName() {
        return geofenceName;
    }

    public GeofenceRule getRuleType() {
        return ruleType;
    }

    public BigDecimal getLastLatitude() {
        return lastLatitude;
    }

    public BigDecimal getLastLongitude() {
        return lastLongitude;
    }

    public BigDecimal getLastAltitude() {
        return lastAltitude;
    }

    public BigDecimal getDistanceMeters() {
        return distanceMeters;
    }

    public LocalDateTime getDetectedAt() {
        return detectedAt;
    }

    public LocalDateTime getResolvedAt() {
        return resolvedAt;
    }
}
