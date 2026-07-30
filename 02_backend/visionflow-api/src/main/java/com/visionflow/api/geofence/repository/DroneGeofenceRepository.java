package com.visionflow.api.geofence.repository;

import com.visionflow.api.geofence.domain.DroneGeofence;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface DroneGeofenceRepository
        extends JpaRepository<DroneGeofence, Long> {

    boolean existsByNameIgnoreCase(String name);

    boolean existsByNameIgnoreCaseAndIdNot(
            String name,
            Long id
    );

    List<DroneGeofence> findAllByOrderByCreatedAtDesc();

    List<DroneGeofence> findAllByActiveTrueOrderByCreatedAtDesc();
}