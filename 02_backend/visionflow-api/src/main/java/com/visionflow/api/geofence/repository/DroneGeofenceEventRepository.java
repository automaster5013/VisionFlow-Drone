package com.visionflow.api.geofence.repository;

import com.visionflow.api.geofence.domain.DroneGeofenceEvent;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface DroneGeofenceEventRepository
        extends JpaRepository<DroneGeofenceEvent, Long> {

    Optional<DroneGeofenceEvent>
    findFirstByDroneIdAndGeofenceIdAndResolvedAtIsNullOrderByDetectedAtDesc(
            Long droneId,
            Long geofenceId
    );

    List<DroneGeofenceEvent>
    findByResolvedAtIsNullOrderByDetectedAtDesc(Pageable pageable);

    List<DroneGeofenceEvent>
    findAllByOrderByDetectedAtDesc(Pageable pageable);

    List<DroneGeofenceEvent>
    findAllByGeofenceIdAndResolvedAtIsNull(
            Long geofenceId
    );
}