package com.visionflow.api.audit.repository;

import com.visionflow.api.audit.domain.AuditAction;
import com.visionflow.api.audit.domain.AuditEntityType;
import com.visionflow.api.audit.domain.AuditLog;
import jakarta.persistence.LockModeType;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.LocalDateTime;
import java.util.List;

public interface AuditLogRepository extends JpaRepository<AuditLog, Long> {

    @Query("""
            SELECT auditLog
            FROM AuditLog auditLog
            WHERE (:action IS NULL OR auditLog.action = :action)
              AND (:entityType IS NULL OR auditLog.entityType = :entityType)
              AND (:entityId IS NULL OR auditLog.entityId = :entityId)
              AND (:actor IS NULL OR LOWER(auditLog.actor) LIKE LOWER(CONCAT('%', :actor, '%')))
              AND (:fromTime IS NULL OR auditLog.occurredAt >= :fromTime)
              AND (:toTime IS NULL OR auditLog.occurredAt <= :toTime)
            """)
    Page<AuditLog> search(
            @Param("action") AuditAction action,
            @Param("entityType") AuditEntityType entityType,
            @Param("entityId") String entityId,
            @Param("actor") String actor,
            @Param("fromTime") LocalDateTime fromTime,
            @Param("toTime") LocalDateTime toTime,
            Pageable pageable
    );

    long countByOccurredAtBefore(LocalDateTime cutoff);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            SELECT auditLog
            FROM AuditLog auditLog
            WHERE auditLog.occurredAt < :cutoff
            ORDER BY auditLog.occurredAt ASC, auditLog.id ASC
            """)
    List<AuditLog> findRetentionCandidatesForUpdate(
            @Param("cutoff") LocalDateTime cutoff,
            Pageable pageable
    );
}
