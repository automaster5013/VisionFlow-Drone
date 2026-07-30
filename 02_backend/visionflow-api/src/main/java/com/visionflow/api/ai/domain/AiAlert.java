package com.visionflow.api.ai.domain;

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

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.time.ZoneOffset;

@Entity
@Table(
        name = "ai_alert",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_ai_alert_event",
                columnNames = "event_id"
        )
)
public class AiAlert {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "event_id", nullable = false)
    private Long eventId;

    @Column(name = "drone_id", nullable = false)
    private Long droneId;

    @Column(name = "session_id", nullable = false, length = 36)
    private String sessionId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private AiAlertSeverity severity;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private AiAlertStatus status;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(nullable = false, length = 500)
    private String summary;

    @Column(name = "primary_class_name", nullable = false, length = 100)
    private String primaryClassName;

    @Column(name = "max_confidence", nullable = false, precision = 8, scale = 6)
    private BigDecimal maxConfidence;

    @Column(name = "detection_count", nullable = false)
    private Integer detectionCount;

    @Column(name = "captured_at", nullable = false)
    private LocalDateTime capturedAt;

    @Column(name = "acknowledged_at")
    private LocalDateTime acknowledgedAt;

    @Column(name = "acknowledged_by", length = 100)
    private String acknowledgedBy;

    @Column(name = "resolved_at")
    private LocalDateTime resolvedAt;

    @Column(name = "resolved_by", length = 100)
    private String resolvedBy;

    @Column(name = "resolution_note", length = 500)
    private String resolutionNote;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    protected AiAlert() {
    }

    public static AiAlert create(
            AiInferenceEvent event,
            AiAlertSeverity severity,
            String title,
            String summary,
            String primaryClassName,
            BigDecimal maxConfidence
    ) {
        AiAlert alert = new AiAlert();
        alert.eventId = event.getId();
        alert.droneId = event.getDroneId();
        alert.sessionId = event.getSessionId();
        alert.severity = severity;
        alert.status = AiAlertStatus.OPEN;
        alert.title = title;
        alert.summary = summary;
        alert.primaryClassName = primaryClassName;
        alert.maxConfidence = maxConfidence;
        alert.detectionCount = event.getDetectionCount();
        alert.capturedAt = event.getCapturedAt();
        return alert;
    }

    public void acknowledge(String operator, LocalDateTime acknowledgedAt) {
        if (status == AiAlertStatus.RESOLVED) {
            throw new IllegalArgumentException(
                    "이미 해결된 AI 경보는 확인 처리할 수 없습니다."
            );
        }

        if (status == AiAlertStatus.ACKNOWLEDGED) {
            return;
        }

        this.status = AiAlertStatus.ACKNOWLEDGED;
        this.acknowledgedBy = operator;
        this.acknowledgedAt = acknowledgedAt;
    }

    public void resolve(
            String operator,
            String resolutionNote,
            LocalDateTime resolvedAt
    ) {
        if (status == AiAlertStatus.RESOLVED) {
            return;
        }

        this.status = AiAlertStatus.RESOLVED;
        this.resolvedBy = operator;
        this.resolutionNote = resolutionNote;
        this.resolvedAt = resolvedAt;
    }

    @PrePersist
    void prePersist() {
        LocalDateTime now = LocalDateTime.now(ZoneOffset.UTC);
        if (createdAt == null) {
            createdAt = now;
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

    public Long getEventId() {
        return eventId;
    }

    public Long getDroneId() {
        return droneId;
    }

    public String getSessionId() {
        return sessionId;
    }

    public AiAlertSeverity getSeverity() {
        return severity;
    }

    public AiAlertStatus getStatus() {
        return status;
    }

    public String getTitle() {
        return title;
    }

    public String getSummary() {
        return summary;
    }

    public String getPrimaryClassName() {
        return primaryClassName;
    }

    public BigDecimal getMaxConfidence() {
        return maxConfidence;
    }

    public Integer getDetectionCount() {
        return detectionCount;
    }

    public LocalDateTime getCapturedAt() {
        return capturedAt;
    }

    public LocalDateTime getAcknowledgedAt() {
        return acknowledgedAt;
    }

    public String getAcknowledgedBy() {
        return acknowledgedBy;
    }

    public LocalDateTime getResolvedAt() {
        return resolvedAt;
    }

    public String getResolvedBy() {
        return resolvedBy;
    }

    public String getResolutionNote() {
        return resolutionNote;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }
}
