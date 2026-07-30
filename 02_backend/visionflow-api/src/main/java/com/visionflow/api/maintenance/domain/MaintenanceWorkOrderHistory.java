package com.visionflow.api.maintenance.domain;

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
@Table(name = "maintenance_work_order_history")
public class MaintenanceWorkOrderHistory {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "work_order_id", nullable = false)
    private Long workOrderId;

    @Enumerated(EnumType.STRING)
    @Column(name = "action_type", nullable = false, length = 30)
    private MaintenanceWorkOrderActionType actionType;

    @Enumerated(EnumType.STRING)
    @Column(name = "previous_status", length = 20)
    private MaintenanceWorkOrderStatus previousStatus;

    @Enumerated(EnumType.STRING)
    @Column(name = "new_status", nullable = false, length = 20)
    private MaintenanceWorkOrderStatus newStatus;

    @Column(nullable = false, length = 100)
    private String actor;

    @Column(length = 1000)
    private String note;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    protected MaintenanceWorkOrderHistory() {
    }

    public static MaintenanceWorkOrderHistory create(
            Long workOrderId,
            MaintenanceWorkOrderActionType actionType,
            MaintenanceWorkOrderStatus previousStatus,
            MaintenanceWorkOrderStatus newStatus,
            String actor,
            String note
    ) {
        MaintenanceWorkOrderHistory history =
                new MaintenanceWorkOrderHistory();
        history.workOrderId = workOrderId;
        history.actionType = actionType;
        history.previousStatus = previousStatus;
        history.newStatus = newStatus;
        history.actor = actor;
        history.note = note;
        return history;
    }

    @PrePersist
    void prePersist() {
        createdAt = LocalDateTime.now(ZoneOffset.UTC);
    }

    public Long getId() {
        return id;
    }

    public Long getWorkOrderId() {
        return workOrderId;
    }

    public MaintenanceWorkOrderActionType getActionType() {
        return actionType;
    }

    public MaintenanceWorkOrderStatus getPreviousStatus() {
        return previousStatus;
    }

    public MaintenanceWorkOrderStatus getNewStatus() {
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
