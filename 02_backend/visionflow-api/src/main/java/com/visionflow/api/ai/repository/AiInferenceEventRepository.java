package com.visionflow.api.ai.repository;

import com.visionflow.api.ai.domain.AiInferenceEvent;
import com.visionflow.api.flight.dto.AiFlightSessionSummaryProjection;
import jakarta.persistence.LockModeType;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

public interface AiInferenceEventRepository
        extends JpaRepository<AiInferenceEvent, Long> {

    Optional<AiInferenceEvent> findBySourceIdAndSessionIdAndFrameIndex(
            String sourceId,
            String sessionId,
            Long frameIndex
    );

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            SELECT inferenceEvent
            FROM AiInferenceEvent inferenceEvent
            WHERE inferenceEvent.id = :id
            """)
    Optional<AiInferenceEvent> findByIdForUpdate(
            @Param("id") Long id
    );

    List<AiInferenceEvent> findAllByOrderByCapturedAtDesc(
            Pageable pageable
    );

    List<AiInferenceEvent> findAllByDroneIdOrderByCapturedAtDesc(
            Long droneId,
            Pageable pageable
    );

    List<AiInferenceEvent>
    findAllByDroneIdAndSessionIdOrderByCapturedAtAsc(
            Long droneId,
            String sessionId,
            Pageable pageable
    );

    long countByDroneIdAndSessionId(
            Long droneId,
            String sessionId
    );

    long countByDetectionCountGreaterThan(Integer detectionCount);

    List<AiInferenceEvent>
    findAllByDetectionCountGreaterThanOrderByCapturedAtDesc(
            Integer detectionCount,
            Pageable pageable
    );

    @Query("""
            SELECT COALESCE(SUM(inferenceEvent.detectionCount), 0)
            FROM AiInferenceEvent inferenceEvent
            """)
    Long sumDetectionCount();

    @Query("""
            SELECT COUNT(inferenceEvent)
            FROM AiInferenceEvent inferenceEvent
            WHERE (
                    :droneId IS NULL
                    OR inferenceEvent.droneId = :droneId
              )
              AND (
                    :fromDateTime IS NULL
                    OR inferenceEvent.capturedAt >= :fromDateTime
              )
              AND (
                    :toDateTime IS NULL
                    OR inferenceEvent.capturedAt <= :toDateTime
              )
            """)
    long countDashboardEvents(
            @Param("droneId") Long droneId,
            @Param("fromDateTime") LocalDateTime fromDateTime,
            @Param("toDateTime") LocalDateTime toDateTime
    );

    @Query("""
            SELECT COUNT(inferenceEvent)
            FROM AiInferenceEvent inferenceEvent
            WHERE inferenceEvent.detectionCount > 0
              AND (
                    :droneId IS NULL
                    OR inferenceEvent.droneId = :droneId
              )
              AND (
                    :fromDateTime IS NULL
                    OR inferenceEvent.capturedAt >= :fromDateTime
              )
              AND (
                    :toDateTime IS NULL
                    OR inferenceEvent.capturedAt <= :toDateTime
              )
            """)
    long countDashboardDetectedEvents(
            @Param("droneId") Long droneId,
            @Param("fromDateTime") LocalDateTime fromDateTime,
            @Param("toDateTime") LocalDateTime toDateTime
    );

    @Query("""
            SELECT COALESCE(SUM(inferenceEvent.detectionCount), 0)
            FROM AiInferenceEvent inferenceEvent
            WHERE (
                    :droneId IS NULL
                    OR inferenceEvent.droneId = :droneId
              )
              AND (
                    :fromDateTime IS NULL
                    OR inferenceEvent.capturedAt >= :fromDateTime
              )
              AND (
                    :toDateTime IS NULL
                    OR inferenceEvent.capturedAt <= :toDateTime
              )
            """)
    Long sumDashboardDetections(
            @Param("droneId") Long droneId,
            @Param("fromDateTime") LocalDateTime fromDateTime,
            @Param("toDateTime") LocalDateTime toDateTime
    );

    @Query("""
            SELECT inferenceEvent
            FROM AiInferenceEvent inferenceEvent
            WHERE inferenceEvent.detectionCount > 0
              AND (
                    :droneId IS NULL
                    OR inferenceEvent.droneId = :droneId
              )
              AND (
                    :fromDateTime IS NULL
                    OR inferenceEvent.capturedAt >= :fromDateTime
              )
              AND (
                    :toDateTime IS NULL
                    OR inferenceEvent.capturedAt <= :toDateTime
              )
            ORDER BY inferenceEvent.capturedAt DESC
            """)
    List<AiInferenceEvent> findDashboardAlerts(
            @Param("droneId") Long droneId,
            @Param("fromDateTime") LocalDateTime fromDateTime,
            @Param("toDateTime") LocalDateTime toDateTime,
            Pageable pageable
    );

    @Query("""
            SELECT inferenceEvent.sessionId AS sessionId,
                   MIN(inferenceEvent.capturedAt) AS startedAt,
                   MAX(inferenceEvent.capturedAt) AS endedAt,
                   COUNT(inferenceEvent.id) AS aiEventCount,
                   SUM(inferenceEvent.detectionCount) AS detectionCount
            FROM AiInferenceEvent inferenceEvent
            WHERE inferenceEvent.droneId = :droneId
              AND inferenceEvent.sessionId IS NOT NULL
              AND inferenceEvent.sessionId <> ''
              AND (
                    :searchTerm IS NULL
                    OR LOWER(inferenceEvent.sessionId)
                       LIKE LOWER(CONCAT('%', :searchTerm, '%'))
              )
            GROUP BY inferenceEvent.sessionId
            ORDER BY MAX(inferenceEvent.capturedAt) DESC
            """)
    List<AiFlightSessionSummaryProjection>
    findFlightSessionSummaries(
            @Param("droneId") Long droneId,
            @Param("searchTerm") String searchTerm,
            Pageable pageable
    );
}
