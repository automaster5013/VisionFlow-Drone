package com.visionflow.api.flight.repository;

import com.visionflow.api.flight.domain.FlightSession;
import com.visionflow.api.flight.domain.FlightSessionStatus;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.LocalDateTime;
import java.util.Collection;
import java.util.List;
import java.util.Optional;

public interface FlightSessionRepository
        extends JpaRepository<FlightSession, String> {

    Optional<FlightSession> findBySessionIdAndDroneId(
            String sessionId,
            Long droneId
    );

    Optional<FlightSession>
    findFirstByDroneIdAndStatusOrderByStartedAtDesc(
            Long droneId,
            FlightSessionStatus status
    );

    long countByStatus(FlightSessionStatus status);

    List<FlightSession> findAllByOrderByUpdatedAtDesc(
            Pageable pageable
    );

    List<FlightSession> findAllByStatusOrderByEndedAtDesc(
            FlightSessionStatus status,
            Pageable pageable
    );

    List<FlightSession> findByDroneIdAndStatusInOrderByEndedAtDesc(
            Long droneId,
            Collection<FlightSessionStatus> statuses,
            Pageable pageable
    );

    @Query("""
            SELECT DISTINCT flightSession.droneId
            FROM FlightSession flightSession
            WHERE flightSession.status IN :statuses
            ORDER BY flightSession.droneId
            """)
    List<Long> findDistinctDroneIdsByStatusIn(
            @Param("statuses")
            Collection<FlightSessionStatus> statuses
    );

    @Query("""
            SELECT COUNT(flightSession)
            FROM FlightSession flightSession
            WHERE (
                    :droneId IS NULL
                    OR flightSession.droneId = :droneId
              )
              AND (
                    :status IS NULL
                    OR flightSession.status = :status
              )
              AND (
                    :fromDateTime IS NULL
                    OR COALESCE(
                        flightSession.endedAt,
                        flightSession.startedAt
                    ) >= :fromDateTime
              )
              AND (
                    :toDateTime IS NULL
                    OR flightSession.startedAt <= :toDateTime
              )
            """)
    long countDashboardSessions(
            @Param("droneId") Long droneId,
            @Param("status") FlightSessionStatus status,
            @Param("fromDateTime") LocalDateTime fromDateTime,
            @Param("toDateTime") LocalDateTime toDateTime
    );

    @Query("""
            SELECT flightSession
            FROM FlightSession flightSession
            WHERE (
                    :droneId IS NULL
                    OR flightSession.droneId = :droneId
              )
              AND (
                    :status IS NULL
                    OR flightSession.status = :status
              )
              AND (
                    :fromDateTime IS NULL
                    OR COALESCE(
                        flightSession.endedAt,
                        flightSession.startedAt
                    ) >= :fromDateTime
              )
              AND (
                    :toDateTime IS NULL
                    OR flightSession.startedAt <= :toDateTime
              )
            ORDER BY flightSession.updatedAt DESC
            """)
    List<FlightSession> findDashboardSessions(
            @Param("droneId") Long droneId,
            @Param("status") FlightSessionStatus status,
            @Param("fromDateTime") LocalDateTime fromDateTime,
            @Param("toDateTime") LocalDateTime toDateTime,
            Pageable pageable
    );

    @Query("""
            SELECT flightSession
            FROM FlightSession flightSession
            WHERE flightSession.droneId = :droneId
              AND (
                    :searchTerm IS NULL
                    OR LOWER(flightSession.sessionId)
                       LIKE LOWER(CONCAT('%', :searchTerm, '%'))
              )
            ORDER BY COALESCE(
                flightSession.endedAt,
                flightSession.startedAt
            ) DESC
            """)
    List<FlightSession> findSessionMetadata(
            @Param("droneId") Long droneId,
            @Param("searchTerm") String searchTerm,
            Pageable pageable
    );
}
