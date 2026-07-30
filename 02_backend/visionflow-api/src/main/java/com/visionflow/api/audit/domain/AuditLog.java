package com.visionflow.api.audit.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

@Entity
@Table(name = "audit_log")
public class AuditLog {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "occurred_at", nullable = false)
    private LocalDateTime occurredAt;

    @Column(nullable = false, length = 100)
    private String actor;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 80)
    private AuditAction action;

    @Enumerated(EnumType.STRING)
    @Column(name = "entity_type", nullable = false, length = 60)
    private AuditEntityType entityType;

    @Column(name = "entity_id", nullable = false, length = 100)
    private String entityId;

    @Column(nullable = false, length = 255)
    private String summary;

    @Column(name = "details_json", columnDefinition = "LONGTEXT")
    private String detailsJson;

    @Column(name = "request_method", length = 10)
    private String requestMethod;

    @Column(name = "request_path", length = 500)
    private String requestPath;

    @Column(name = "trace_id", nullable = false, length = 64)
    private String traceId;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    protected AuditLog() {
    }

    public static AuditLog create(
            LocalDateTime occurredAt,
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
        AuditLog auditLog = new AuditLog();
        auditLog.occurredAt = occurredAt;
        auditLog.actor = actor;
        auditLog.action = action;
        auditLog.entityType = entityType;
        auditLog.entityId = entityId;
        auditLog.summary = summary;
        auditLog.detailsJson = detailsJson;
        auditLog.requestMethod = requestMethod;
        auditLog.requestPath = requestPath;
        auditLog.traceId = traceId;
        auditLog.createdAt = occurredAt;
        return auditLog;
    }

    public Long getId() {
        return id;
    }

    public LocalDateTime getOccurredAt() {
        return occurredAt;
    }

    public String getActor() {
        return actor;
    }

    public AuditAction getAction() {
        return action;
    }

    public AuditEntityType getEntityType() {
        return entityType;
    }

    public String getEntityId() {
        return entityId;
    }

    public String getSummary() {
        return summary;
    }

    public String getDetailsJson() {
        return detailsJson;
    }

    public String getRequestMethod() {
        return requestMethod;
    }

    public String getRequestPath() {
        return requestPath;
    }

    public String getTraceId() {
        return traceId;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }
}
