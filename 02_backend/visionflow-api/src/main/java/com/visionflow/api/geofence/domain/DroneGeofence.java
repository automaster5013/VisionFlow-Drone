package com.visionflow.api.geofence.domain;

import jakarta.persistence.*;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@Entity
@Table(name = "drone_geofence")
public class DroneGeofence {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 100)
    private String name;

    @Enumerated(EnumType.STRING)
    @Column(name = "rule_type", nullable = false, length = 20)
    private GeofenceRule ruleType;

    @Column(name = "center_latitude", nullable = false, precision = 10, scale = 7)
    private BigDecimal centerLatitude;

    @Column(name = "center_longitude", nullable = false, precision = 10, scale = 7)
    private BigDecimal centerLongitude;

    @Column(name = "radius_meters", nullable = false, precision = 10, scale = 2)
    private BigDecimal radiusMeters;

    @Column(nullable = false)
    private boolean active;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    protected DroneGeofence() {
    }

    public static DroneGeofence create(
            String name,
            GeofenceRule ruleType,
            BigDecimal centerLatitude,
            BigDecimal centerLongitude,
            BigDecimal radiusMeters,
            boolean active
    ) {
        DroneGeofence geofence = new DroneGeofence();
        geofence.name = name;
        geofence.ruleType = ruleType;
        geofence.centerLatitude = centerLatitude;
        geofence.centerLongitude = centerLongitude;
        geofence.radiusMeters = radiusMeters;
        geofence.active = active;
        return geofence;
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

    public String getName() {
        return name;
    }

    public GeofenceRule getRuleType() {
        return ruleType;
    }

    public BigDecimal getCenterLatitude() {
        return centerLatitude;
    }

    public BigDecimal getCenterLongitude() {
        return centerLongitude;
    }

    public BigDecimal getRadiusMeters() {
        return radiusMeters;
    }

    public boolean isActive() {
        return active;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }

    public void update(
            String name,
            GeofenceRule ruleType,
            BigDecimal centerLatitude,
            BigDecimal centerLongitude,
            BigDecimal radiusMeters
    ) {
        this.name = name;
        this.ruleType = ruleType;
        this.centerLatitude = centerLatitude;
        this.centerLongitude = centerLongitude;
        this.radiusMeters = radiusMeters;
    }

    public void changeActive(boolean active) {
        this.active = active;
    }
}