package com.visionflow.api.geofence.repository;

import com.visionflow.api.geofence.domain.DroneGeofence;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import jakarta.persistence.LockModeType;

import java.util.List;
import java.util.Optional;

public interface DroneGeofenceRepository
        extends JpaRepository<DroneGeofence, Long> {

    boolean existsByNameIgnoreCase(String name);

    boolean existsByNameIgnoreCaseAndIdNot(
            String name,
            Long id
    );

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            SELECT geofence
            FROM DroneGeofence geofence
            WHERE geofence.id = :geofenceId
            """)
    Optional<DroneGeofence> findByIdForUpdate(
            @Param("geofenceId") Long geofenceId
    );

    List<DroneGeofence> findAllByOrderByCreatedAtDesc();

    List<DroneGeofence> findAllByActiveTrueOrderByCreatedAtDesc();
}
