package com.visionflow.api.audit.dto;

import com.visionflow.api.audit.domain.AuditAction;
import com.visionflow.api.audit.domain.AuditEntityType;
import com.visionflow.api.audit.domain.AuditLog;

import java.time.Instant;
import java.time.ZoneOffset;

public record AuditLogResponse(
        Long id,
        Instant occurredAt,
        String actor,
        AuditAction action,
        AuditEntityType entityType,
        String entityId,
        String summary,
        String detailsJson,
        String requestMethod,
        String requestPath,
        String traceId
) {

    public static AuditLogResponse from(AuditLog auditLog) {
        return new AuditLogResponse(
                auditLog.getId(),
                auditLog.getOccurredAt().toInstant(ZoneOffset.UTC),
                auditLog.getActor(),
                auditLog.getAction(),
                auditLog.getEntityType(),
                auditLog.getEntityId(),
                auditLog.getSummary(),
                auditLog.getDetailsJson(),
                auditLog.getRequestMethod(),
                auditLog.getRequestPath(),
                auditLog.getTraceId()
        );
    }
}
