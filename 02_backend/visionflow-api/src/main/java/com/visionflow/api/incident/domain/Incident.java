package com.visionflow.api.incident.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.Objects;

@Entity
@Table(
        name = "incident",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_incident_source",
                columnNames = {"source_type", "source_id"}
        )
)
public class Incident {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(name = "source_type", nullable = false, length = 30)
    private IncidentSourceType sourceType;

    @Column(name = "source_id", nullable = false)
    private Long sourceId;

    @Column(name = "drone_id", nullable = false)
    private Long droneId;

    @Column(name = "session_id", length = 36)
    private String sessionId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private IncidentPriority priority;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private IncidentStatus status;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(nullable = false, length = 1000)
    private String summary;

    @Column(length = 100)
    private String assignee;

    @Column(name = "assigned_by", length = 100)
    private String assignedBy;

    @Column(name = "assigned_at")
    private LocalDateTime assignedAt;

    @Column(name = "occurred_at", nullable = false)
    private LocalDateTime occurredAt;

    @Column(name = "resolved_at")
    private LocalDateTime resolvedAt;

    @Column(name = "closed_at")
    private LocalDateTime closedAt;

    @Column(name = "sla_due_at")
    private LocalDateTime slaDueAt;

    @Column(name = "sla_breached_at")
    private LocalDateTime slaBreachedAt;

    @Column(name = "escalation_level", nullable = false)
    private int escalationLevel;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    protected Incident() {
    }

    public static Incident create(
            IncidentSourceType sourceType,
            Long sourceId,
            Long droneId,
            String sessionId,
            IncidentPriority priority,
            IncidentStatus status,
            String title,
            String summary,
            LocalDateTime occurredAt,
            LocalDateTime sourceResolvedAt
    ) {
        Incident incident = new Incident();
        incident.sourceType = sourceType;
        incident.sourceId = sourceId;
        incident.droneId = droneId;
        incident.sessionId = sessionId;
        incident.priority = priority;
        incident.status = status;
        incident.title = title;
        incident.summary = summary;
        incident.occurredAt = occurredAt;

        if (status == IncidentStatus.RESOLVED) {
            incident.resolvedAt = sourceResolvedAt == null
                    ? occurredAt
                    : sourceResolvedAt;
        }
        if (status == IncidentStatus.CLOSED) {
            incident.closedAt = occurredAt;
        }

        return incident;
    }

    public boolean assign(
            String assignee,
            String actor,
            LocalDateTime assignedAt
    ) {
        if (assignee.equals(this.assignee)) {
            return false;
        }

        this.assignee = assignee;
        this.assignedBy = actor;
        this.assignedAt = assignedAt;
        return true;
    }

    public boolean changePriority(
            IncidentPriority priority,
            LocalDateTime changedAt
    ) {
        if (this.priority == priority) {
            return false;
        }

        this.priority = priority;
        if (slaBreachedAt == null && isActiveStatus()) {
            slaDueAt = calculateSlaDueAt(priority, changedAt);
        }
        return true;
    }

    public boolean markSlaBreached(LocalDateTime breachedAt) {
        if (!isActiveStatus()
                || slaDueAt == null
                || slaBreachedAt != null
                || slaDueAt.isAfter(breachedAt)) {
            return false;
        }

        slaBreachedAt = breachedAt;
        escalationLevel += 1;
        priority = escalatePriority(priority);
        updatedAt = breachedAt;
        return true;
    }

    public boolean changeStatus(
            IncidentStatus nextStatus,
            LocalDateTime changedAt
    ) {
        if (status == nextStatus) {
            return false;
        }

        this.status = nextStatus;
        applyStatusTimestamp(nextStatus, changedAt);
        return true;
    }

    public boolean synchronizeStatus(
            IncidentStatus nextStatus,
            LocalDateTime changedAt
    ) {
        if (status == IncidentStatus.CLOSED || status == nextStatus) {
            return false;
        }

        if (
                status == IncidentStatus.RESOLVED
                        && nextStatus == IncidentStatus.IN_PROGRESS
        ) {
            return false;
        }

        this.status = nextStatus;
        applyStatusTimestamp(nextStatus, changedAt);
        return true;
    }

    public boolean synchronizeFlightQuality(
            String nextSessionId,
            IncidentPriority nextPriority,
            IncidentStatus nextStatus,
            String nextTitle,
            String nextSummary,
            LocalDateTime nextOccurredAt,
            LocalDateTime changedAt
    ) {
        IncidentStatus previousStatus = status;
        IncidentPriority previousPriority = priority;
        boolean changed =
                !Objects.equals(sessionId, nextSessionId)
                        || priority != nextPriority
                        || status != nextStatus
                        || !Objects.equals(title, nextTitle)
                        || !Objects.equals(summary, nextSummary)
                        || !Objects.equals(occurredAt, nextOccurredAt);

        if (!changed) {
            return false;
        }

        sessionId = nextSessionId;
        priority = nextPriority;
        title = nextTitle;
        summary = nextSummary;
        occurredAt = nextOccurredAt;

        if (status != nextStatus) {
            status = nextStatus;
            applyStatusTimestamp(nextStatus, changedAt);
        }

        boolean reopened = !isActive(previousStatus)
                && isActive(nextStatus);
        if (reopened) {
            slaBreachedAt = null;
            escalationLevel = 0;
            slaDueAt = calculateSlaDueAt(nextPriority, changedAt);
        } else if (
                isActive(nextStatus)
                        && previousPriority != nextPriority
                        && slaBreachedAt == null
        ) {
            slaDueAt = calculateSlaDueAt(nextPriority, changedAt);
        }

        updatedAt = changedAt;
        return true;
    }

    public boolean reopenFromFlightGate(
            IncidentPriority nextPriority,
            String nextTitle,
            String nextSummary,
            LocalDateTime nextOccurredAt,
            LocalDateTime changedAt
    ) {
        if (isActiveStatus()) {
            return false;
        }

        sessionId = null;
        priority = nextPriority;
        status = IncidentStatus.OPEN;
        title = nextTitle;
        summary = nextSummary;
        occurredAt = nextOccurredAt;
        resolvedAt = null;
        closedAt = null;
        slaBreachedAt = null;
        escalationLevel = 0;
        slaDueAt = calculateSlaDueAt(nextPriority, changedAt);
        updatedAt = changedAt;
        return true;
    }

    public void touch(LocalDateTime changedAt) {
        this.updatedAt = changedAt;
    }

    private void applyStatusTimestamp(
            IncidentStatus nextStatus,
            LocalDateTime changedAt
    ) {
        if (nextStatus == IncidentStatus.OPEN
                || nextStatus == IncidentStatus.IN_PROGRESS) {
            resolvedAt = null;
            closedAt = null;
            return;
        }

        if (nextStatus == IncidentStatus.RESOLVED) {
            resolvedAt = changedAt;
            closedAt = null;
            return;
        }

        if (nextStatus == IncidentStatus.CLOSED) {
            if (resolvedAt == null) {
                resolvedAt = changedAt;
            }
            closedAt = changedAt;
        }
    }

    @PrePersist
    void prePersist() {
        LocalDateTime now = LocalDateTime.now(ZoneOffset.UTC);
        if (createdAt == null) {
            createdAt = now;
        }
        if (slaDueAt == null && isActiveStatus()) {
            slaDueAt = calculateSlaDueAt(priority, now);
        }
        updatedAt = now;
    }

    @PreUpdate
    void preUpdate() {
        updatedAt = LocalDateTime.now(ZoneOffset.UTC);
    }

    public Long getId() {
        return id;
    }

    public IncidentSourceType getSourceType() {
        return sourceType;
    }

    public Long getSourceId() {
        return sourceId;
    }

    public Long getDroneId() {
        return droneId;
    }

    public String getSessionId() {
        return sessionId;
    }

    public IncidentPriority getPriority() {
        return priority;
    }

    public IncidentStatus getStatus() {
        return status;
    }

    public String getTitle() {
        return title;
    }

    public String getSummary() {
        return summary;
    }

    public String getAssignee() {
        return assignee;
    }

    public String getAssignedBy() {
        return assignedBy;
    }

    public LocalDateTime getAssignedAt() {
        return assignedAt;
    }

    public LocalDateTime getOccurredAt() {
        return occurredAt;
    }

    public LocalDateTime getResolvedAt() {
        return resolvedAt;
    }

    public LocalDateTime getClosedAt() {
        return closedAt;
    }

    public LocalDateTime getSlaDueAt() {
        return slaDueAt;
    }

    public LocalDateTime getSlaBreachedAt() {
        return slaBreachedAt;
    }

    public int getEscalationLevel() {
        return escalationLevel;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }

    private boolean isActiveStatus() {
        return isActive(status);
    }

    private boolean isActive(IncidentStatus candidate) {
        return candidate == IncidentStatus.OPEN
                || candidate == IncidentStatus.IN_PROGRESS;
    }

    private LocalDateTime calculateSlaDueAt(
            IncidentPriority priority,
            LocalDateTime baseTime
    ) {
        long minutes = switch (priority) {
            case CRITICAL -> 5;
            case HIGH -> 15;
            case MEDIUM -> 30;
            case LOW -> 60;
        };

        return baseTime.plusMinutes(minutes);
    }

    private IncidentPriority escalatePriority(IncidentPriority priority) {
        return switch (priority) {
            case LOW -> IncidentPriority.MEDIUM;
            case MEDIUM -> IncidentPriority.HIGH;
            case HIGH, CRITICAL -> IncidentPriority.CRITICAL;
        };
    }
}
