package com.visionflow.api.drone.repository;

import com.visionflow.api.drone.domain.DroneTelemetryHistory;
import com.visionflow.api.flight.dto.TelemetryFlightSessionSummaryProjection;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

public interface DroneTelemetryHistoryRepository
        extends JpaRepository<DroneTelemetryHistory, Long> {

    List<DroneTelemetryHistory>
    findByDroneIdOrderByRecordedAtDesc(
            Long droneId,
            Pageable pageable
    );

    List<DroneTelemetryHistory>
    findByDroneIdAndRecordedAtBetweenOrderByRecordedAtAsc(
            Long droneId,
            LocalDateTime from,
            LocalDateTime to,
            Pageable pageable
    );

    List<DroneTelemetryHistory>
    findByDroneIdAndFlightSessionIdOrderByRecordedAtAsc(
            Long droneId,
            String flightSessionId,
            Pageable pageable
    );

    long countByDroneIdAndFlightSessionId(
            Long droneId,
            String flightSessionId
    );

    Optional<DroneTelemetryHistory>
    findFirstByDroneIdAndFlightSessionIdAndRecordedAtLessThanEqualOrderByRecordedAtDesc(
            Long droneId,
            String flightSessionId,
            LocalDateTime recordedAt
    );

    Optional<DroneTelemetryHistory>
    findFirstByDroneIdAndFlightSessionIdAndRecordedAtGreaterThanEqualOrderByRecordedAtAsc(
            Long droneId,
            String flightSessionId,
            LocalDateTime recordedAt
    );

    @Query("""
            SELECT history.flightSessionId AS sessionId,
                   MIN(history.recordedAt) AS startedAt,
                   MAX(history.recordedAt) AS endedAt,
                   COUNT(history.id) AS telemetryCount
            FROM DroneTelemetryHistory history
            WHERE history.droneId = :droneId
              AND history.flightSessionId IS NOT NULL
              AND history.flightSessionId <> ''
              AND (
                    :searchTerm IS NULL
                    OR LOWER(history.flightSessionId)
                       LIKE LOWER(CONCAT('%', :searchTerm, '%'))
              )
            GROUP BY history.flightSessionId
            ORDER BY MAX(history.recordedAt) DESC
            """)
    List<TelemetryFlightSessionSummaryProjection>
    findFlightSessionSummaries(
            @Param("droneId") Long droneId,
            @Param("searchTerm") String searchTerm,
            Pageable pageable
    );
}
