package com.visionflow.api.drone.repository;

import com.visionflow.api.drone.domain.Drone;
import com.visionflow.api.drone.domain.DroneStatus;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import jakarta.persistence.LockModeType;

import java.util.List;
import java.util.Optional;

public interface DroneRepository extends JpaRepository<Drone, Long> {

    Optional<Drone> findByDroneCode(String droneCode);

    Optional<Drone> findBySerialNumber(String serialNumber);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("SELECT drone FROM Drone drone WHERE drone.id = :id")
    Optional<Drone> findByIdForUpdate(@Param("id") Long id);

    List<Drone> findAllByStatusOrderByCreatedAtDesc(
            DroneStatus status
    );

    List<Drone> findAllByOrderByCreatedAtDesc();

    boolean existsByDroneCode(String droneCode);

    boolean existsBySerialNumber(String serialNumber);

    boolean existsBySerialNumberAndIdNot(
            String serialNumber,
            Long id
    );

    @Query(
            value = """
                    SELECT (
                        EXISTS(SELECT 1 FROM flight_session WHERE drone_id = :droneId)
                        + EXISTS(SELECT 1 FROM drone_telemetry_history WHERE drone_id = :droneId)
                        + EXISTS(SELECT 1 FROM ai_inference_event WHERE drone_id = :droneId)
                        + EXISTS(SELECT 1 FROM ai_alert WHERE drone_id = :droneId)
                        + EXISTS(SELECT 1 FROM drone_geofence_event WHERE drone_id = :droneId)
                        + EXISTS(SELECT 1 FROM incident WHERE drone_id = :droneId)
                        + EXISTS(SELECT 1 FROM demo_scenario WHERE drone_id = :droneId)
                        + EXISTS(SELECT 1 FROM flight_quality_assessment WHERE drone_id = :droneId)
                        + EXISTS(SELECT 1 FROM maintenance_work_order WHERE drone_id = :droneId)
                    )
                    """,
            nativeQuery = true
    )
    long countDeletionDependencies(@Param("droneId") Long droneId);
}
