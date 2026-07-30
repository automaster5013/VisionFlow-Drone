package com.visionflow.api.ai.repository;

import com.visionflow.api.ai.domain.AiAlert;
import com.visionflow.api.ai.domain.AiAlertSeverity;
import com.visionflow.api.ai.domain.AiAlertStatus;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

public interface AiAlertRepository extends JpaRepository<AiAlert, Long> {

    Optional<AiAlert> findByEventId(Long eventId);

    @Query("""
            SELECT alert
            FROM AiAlert alert
            WHERE (
                    :droneId IS NULL
                    OR alert.droneId = :droneId
              )
              AND (
                    :sessionId IS NULL
                    OR alert.sessionId = :sessionId
              )
              AND (
                    :severity IS NULL
                    OR alert.severity = :severity
              )
              AND (
                    :status IS NULL
                    OR alert.status = :status
              )
              AND (
                    :fromDateTime IS NULL
                    OR alert.capturedAt >= :fromDateTime
              )
              AND (
                    :toDateTime IS NULL
                    OR alert.capturedAt <= :toDateTime
              )
            ORDER BY alert.capturedAt DESC, alert.id DESC
            """)
    List<AiAlert> findAlerts(
            @Param("droneId") Long droneId,
            @Param("sessionId") String sessionId,
            @Param("severity") AiAlertSeverity severity,
            @Param("status") AiAlertStatus status,
            @Param("fromDateTime") LocalDateTime fromDateTime,
            @Param("toDateTime") LocalDateTime toDateTime,
            Pageable pageable
    );
}
