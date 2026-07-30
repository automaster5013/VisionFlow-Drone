package com.visionflow.api.incident.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;

import java.time.LocalDateTime;
import java.time.ZoneOffset;

@Entity
@Table(name = "incident_action_history")
public class IncidentActionHistory {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "incident_id", nullable = false)
    private Long incidentId;

    @Enumerated(EnumType.STRING)
    @Column(name = "action_type", nullable = false, length = 30)
    private IncidentActionType actionType;

    @Enumerated(EnumType.STRING)
    @Column(name = "previous_status", length = 20)
    private IncidentStatus previousStatus;

    @Enumerated(EnumType.STRING)
    @Column(name = "new_status", length = 20)
    private IncidentStatus newStatus;

    @Column(nullable = false, length = 100)
    private String actor;

    @Column(length = 1000)
    private String note;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    protected IncidentActionHistory() {
    }

    public static IncidentActionHistory create(
            Long incidentId,
            IncidentActionType actionType,
            IncidentStatus previousStatus,
            IncidentStatus newStatus,
            String actor,
            String note
    ) {
        IncidentActionHistory history = new IncidentActionHistory();
        history.incidentId = incidentId;
        history.actionType = actionType;
        history.previousStatus = previousStatus;
        history.newStatus = newStatus;
        history.actor = actor;
        history.note = note;
        return history;
    }

    @PrePersist
    void prePersist() {
        if (createdAt == null) {
            createdAt = LocalDateTime.now(ZoneOffset.UTC);
        }
    }

    public Long getId() {
        return id;
    }

    public Long getIncidentId() {
        return incidentId;
    }

    public IncidentActionType getActionType() {
        return actionType;
    }

    public IncidentStatus getPreviousStatus() {
        return previousStatus;
    }

    public IncidentStatus getNewStatus() {
        return newStatus;
    }

    public String getActor() {
        return actor;
    }

    public String getNote() {
        return note;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }
}
