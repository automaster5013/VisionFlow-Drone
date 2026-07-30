package com.visionflow.api.maintenance.domain;

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
        name = "maintenance_work_order",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_maintenance_work_order_incident",
                columnNames = "incident_id"
        )
)
public class MaintenanceWorkOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "incident_id", nullable = false)
    private Long incidentId;

    @Column(name = "drone_id", nullable = false)
    private Long droneId;

    @Column(name = "session_id", length = 36)
    private String sessionId;

    @Column(name = "source_assessment_id")
    private Long sourceAssessmentId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private MaintenanceWorkOrderStatus status;

    @Enumerated(EnumType.STRING)
    @Column(name = "clearance_status", nullable = false, length = 30)
    private FlightClearanceStatus clearanceStatus;

    @Column(length = 100)
    private String assignee;

    @Column(length = 1000)
    private String finding;

    @Column(name = "resolution_note", length = 1000)
    private String resolutionNote;

    @Column(name = "opened_at", nullable = false)
    private LocalDateTime openedAt;

    @Column(name = "started_at")
    private LocalDateTime startedAt;

    @Column(name = "completed_at")
    private LocalDateTime completedAt;

    @Column(name = "cleared_at")
    private LocalDateTime clearedAt;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    protected MaintenanceWorkOrder() {
    }

    public static MaintenanceWorkOrder open(
            Long incidentId,
            Long droneId,
            String sessionId,
            Long sourceAssessmentId,
            LocalDateTime openedAt
    ) {
        MaintenanceWorkOrder order = new MaintenanceWorkOrder();
        order.incidentId = incidentId;
        order.droneId = droneId;
        order.sessionId = sessionId;
        order.sourceAssessmentId = sourceAssessmentId;
        order.status = MaintenanceWorkOrderStatus.OPEN;
        order.clearanceStatus =
                FlightClearanceStatus.PENDING_INSPECTION;
        order.openedAt = openedAt;
        return order;
    }

    public boolean synchronizeRisk(
            String nextSessionId,
            Long nextAssessmentId,
            LocalDateTime changedAt
    ) {
        boolean sourceChanged =
                !Objects.equals(sessionId, nextSessionId)
                        || !Objects.equals(
                                sourceAssessmentId,
                                nextAssessmentId
                        );
        sessionId = nextSessionId;
        sourceAssessmentId = nextAssessmentId;

        if (
                status == MaintenanceWorkOrderStatus.COMPLETED
                        && clearanceStatus
                        == FlightClearanceStatus.CLEARED
        ) {
            status = MaintenanceWorkOrderStatus.OPEN;
            clearanceStatus =
                    FlightClearanceStatus.PENDING_INSPECTION;
            openedAt = changedAt;
            startedAt = null;
            completedAt = null;
            clearedAt = null;
            assignee = null;
            finding = null;
            resolutionNote = null;
            return true;
        }

        return sourceChanged;
    }

    public void startInspection(
            String nextAssignee,
            LocalDateTime changedAt
    ) {
        if (status == MaintenanceWorkOrderStatus.IN_PROGRESS) {
            if (!nextAssignee.equals(assignee)) {
                assignee = nextAssignee;
            }
            return;
        }
        status = MaintenanceWorkOrderStatus.IN_PROGRESS;
        clearanceStatus =
                FlightClearanceStatus.PENDING_INSPECTION;
        assignee = nextAssignee;
        startedAt = changedAt;
        completedAt = null;
        clearedAt = null;
    }

    public void complete(
            MaintenanceCompletionDecision decision,
            String nextFinding,
            String nextResolutionNote,
            LocalDateTime changedAt
    ) {
        if (status != MaintenanceWorkOrderStatus.IN_PROGRESS) {
            throw new IllegalArgumentException(
                    "진행 중인 점검 작업만 완료할 수 있습니다."
            );
        }
        finding = nextFinding;
        resolutionNote = nextResolutionNote;
        completedAt = changedAt;

        if (
                decision
                        == MaintenanceCompletionDecision.RETURN_TO_SERVICE
        ) {
            status = MaintenanceWorkOrderStatus.COMPLETED;
            clearanceStatus = FlightClearanceStatus.CLEARED;
            clearedAt = changedAt;
            return;
        }

        status = MaintenanceWorkOrderStatus.GROUNDED;
        clearanceStatus = FlightClearanceStatus.GROUNDED;
        clearedAt = null;
    }

    @PrePersist
    void prePersist() {
        LocalDateTime now = LocalDateTime.now(ZoneOffset.UTC);
        if (openedAt == null) {
            openedAt = now;
        }
        createdAt = now;
        updatedAt = now;
    }

    @PreUpdate
    void preUpdate() {
        updatedAt = LocalDateTime.now(ZoneOffset.UTC);
    }

    public Long getId() {
        return id;
    }

    public Long getIncidentId() {
        return incidentId;
    }

    public Long getDroneId() {
        return droneId;
    }

    public String getSessionId() {
        return sessionId;
    }

    public Long getSourceAssessmentId() {
        return sourceAssessmentId;
    }

    public MaintenanceWorkOrderStatus getStatus() {
        return status;
    }

    public FlightClearanceStatus getClearanceStatus() {
        return clearanceStatus;
    }

    public String getAssignee() {
        return assignee;
    }

    public String getFinding() {
        return finding;
    }

    public String getResolutionNote() {
        return resolutionNote;
    }

    public LocalDateTime getOpenedAt() {
        return openedAt;
    }

    public LocalDateTime getStartedAt() {
        return startedAt;
    }

    public LocalDateTime getCompletedAt() {
        return completedAt;
    }

    public LocalDateTime getClearedAt() {
        return clearedAt;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }
}
