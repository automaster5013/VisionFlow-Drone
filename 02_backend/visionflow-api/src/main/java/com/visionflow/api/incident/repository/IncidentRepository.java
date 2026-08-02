package com.visionflow.api.incident.repository;

import com.visionflow.api.incident.domain.Incident;
import com.visionflow.api.incident.domain.IncidentPriority;
import com.visionflow.api.incident.domain.IncidentSourceType;
import com.visionflow.api.incident.domain.IncidentStatus;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import jakarta.persistence.LockModeType;

import java.time.LocalDateTime;
import java.util.Collection;
import java.util.List;
import java.util.Optional;

public interface IncidentRepository extends JpaRepository<Incident, Long> {

    Optional<Incident> findBySourceTypeAndSourceId(
            IncidentSourceType sourceType,
            Long sourceId
    );

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            SELECT incident
            FROM Incident incident
            WHERE incident.id = :incidentId
            """)
    Optional<Incident> findByIdForUpdate(
            @Param("incidentId") Long incidentId
    );

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            SELECT incident
            FROM Incident incident
            WHERE incident.sourceType = :sourceType
              AND incident.sourceId = :sourceId
            """)
    Optional<Incident> findBySourceTypeAndSourceIdForUpdate(
            @Param("sourceType") IncidentSourceType sourceType,
            @Param("sourceId") Long sourceId
    );

    @Query("""
            SELECT incident
            FROM Incident incident
            WHERE (:droneId IS NULL OR incident.droneId = :droneId)
              AND (
                    :sourceType IS NULL
                    OR incident.sourceType = :sourceType
              )
              AND (
                    :priority IS NULL
                    OR incident.priority = :priority
              )
              AND (:status IS NULL OR incident.status = :status)
              AND (
                    :assignee IS NULL
                    OR LOWER(incident.assignee) = LOWER(:assignee)
              )
              AND (
                    :fromDateTime IS NULL
                    OR incident.occurredAt >= :fromDateTime
              )
              AND (
                    :toDateTime IS NULL
                    OR incident.occurredAt <= :toDateTime
              )
            ORDER BY incident.occurredAt DESC, incident.id DESC
            """)
    List<Incident> findIncidents(
            @Param("droneId") Long droneId,
            @Param("sourceType") IncidentSourceType sourceType,
            @Param("priority") IncidentPriority priority,
            @Param("status") IncidentStatus status,
            @Param("assignee") String assignee,
            @Param("fromDateTime") LocalDateTime fromDateTime,
            @Param("toDateTime") LocalDateTime toDateTime,
            Pageable pageable
    );

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            SELECT incident
            FROM Incident incident
            WHERE incident.slaDueAt IS NOT NULL
              AND incident.slaDueAt <= :now
              AND incident.slaBreachedAt IS NULL
              AND incident.status IN :activeStatuses
            ORDER BY incident.slaDueAt ASC, incident.id ASC
            """)
    List<Incident> findOverdueForEscalationForUpdate(
            @Param("now") LocalDateTime now,
            @Param("activeStatuses")
            Collection<IncidentStatus> activeStatuses,
            Pageable pageable
    );
}
