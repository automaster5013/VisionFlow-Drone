package com.visionflow.api.flight.quality.domain;

import com.visionflow.api.flight.domain.FlightSession;
import com.visionflow.api.flight.domain.FlightSessionStatus;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;

@Entity
@Table(
        name = "flight_quality_assessment",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_flight_quality_session_rule",
                columnNames = {"session_id", "rule_version"}
        ),
        indexes = {
                @Index(
                        name = "idx_flight_quality_drone_evaluated",
                        columnList = "drone_id, evaluated_at"
                ),
                @Index(
                        name = "idx_flight_quality_drone_grade",
                        columnList = "drone_id, grade, evaluated_at"
                )
        }
)
public class FlightQualityAssessment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "session_id", nullable = false, length = 36)
    private String sessionId;

    @Column(name = "drone_id", nullable = false)
    private Long droneId;

    @Column(name = "rule_version", nullable = false, length = 30)
    private String ruleVersion;

    @Enumerated(EnumType.STRING)
    @Column(name = "session_status", nullable = false, length = 20)
    private FlightSessionStatus sessionStatus;

    @Column(nullable = false)
    private Integer score;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private FlightQualityGrade grade;

    @Column(name = "data_score", nullable = false)
    private Integer dataScore;

    @Column(name = "flight_score", nullable = false)
    private Integer flightScore;

    @Column(name = "ai_score", nullable = false)
    private Integer aiScore;

    @Column(name = "telemetry_count", nullable = false)
    private Long telemetryCount;

    @Column(name = "valid_coordinate_count", nullable = false)
    private Long validCoordinateCount;

    @Column(
            name = "coordinate_coverage_percent",
            nullable = false,
            precision = 6,
            scale = 2
    )
    private BigDecimal coordinateCoveragePercent;

    @Column(
            name = "battery_coverage_percent",
            nullable = false,
            precision = 6,
            scale = 2
    )
    private BigDecimal batteryCoveragePercent;

    @Column(
            name = "max_telemetry_gap_seconds",
            precision = 12,
            scale = 3
    )
    private BigDecimal maxTelemetryGapSeconds;

    @Column(name = "unrealistic_jump_count", nullable = false)
    private Integer unrealisticJumpCount;

    @Column(name = "altitude_spike_count", nullable = false)
    private Integer altitudeSpikeCount;

    @Column(name = "battery_increase_count", nullable = false)
    private Integer batteryIncreaseCount;

    @Column(name = "minimum_battery_level")
    private Integer minimumBatteryLevel;

    @Column(name = "ai_event_count", nullable = false)
    private Long aiEventCount;

    @Column(name = "detected_event_count", nullable = false)
    private Long detectedEventCount;

    @Column(
            name = "average_inference_ms",
            precision = 12,
            scale = 3
    )
    private BigDecimal averageInferenceMs;

    @Column(
            name = "snapshot_coverage_percent",
            nullable = false,
            precision = 6,
            scale = 2
    )
    private BigDecimal snapshotCoveragePercent;

    @Column(name = "warning_count", nullable = false)
    private Integer warningCount;

    @Column(name = "critical_count", nullable = false)
    private Integer criticalCount;

    @Enumerated(EnumType.STRING)
    @Column(name = "primary_risk_severity", length = 20)
    private FlightQualitySeverity primaryRiskSeverity;

    @Column(name = "primary_risk_title", length = 120)
    private String primaryRiskTitle;

    @Column(name = "primary_risk_detail", length = 500)
    private String primaryRiskDetail;

    @Column(name = "evaluated_at", nullable = false)
    private LocalDateTime evaluatedAt;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    protected FlightQualityAssessment() {
    }

    public static FlightQualityAssessment create(
            FlightSession session,
            String ruleVersion,
            FlightQualitySnapshot snapshot,
            LocalDateTime evaluatedAt
    ) {
        FlightQualityAssessment assessment =
                new FlightQualityAssessment();
        assessment.sessionId = session.getSessionId();
        assessment.droneId = session.getDroneId();
        assessment.ruleVersion = ruleVersion;
        assessment.apply(snapshot, evaluatedAt);
        return assessment;
    }

    public void apply(
            FlightQualitySnapshot snapshot,
            LocalDateTime nextEvaluatedAt
    ) {
        sessionStatus = snapshot.sessionStatus();
        score = snapshot.score();
        grade = snapshot.grade();
        dataScore = snapshot.dataScore();
        flightScore = snapshot.flightScore();
        aiScore = snapshot.aiScore();
        telemetryCount = snapshot.telemetryCount();
        validCoordinateCount = snapshot.validCoordinateCount();
        coordinateCoveragePercent =
                decimal(snapshot.coordinateCoveragePercent(), 2);
        batteryCoveragePercent =
                decimal(snapshot.batteryCoveragePercent(), 2);
        maxTelemetryGapSeconds =
                nullableDecimal(snapshot.maxTelemetryGapSeconds(), 3);
        unrealisticJumpCount = snapshot.unrealisticJumpCount();
        altitudeSpikeCount = snapshot.altitudeSpikeCount();
        batteryIncreaseCount = snapshot.batteryIncreaseCount();
        minimumBatteryLevel = snapshot.minimumBatteryLevel();
        aiEventCount = snapshot.aiEventCount();
        detectedEventCount = snapshot.detectedEventCount();
        averageInferenceMs =
                nullableDecimal(snapshot.averageInferenceMs(), 3);
        snapshotCoveragePercent =
                decimal(snapshot.snapshotCoveragePercent(), 2);
        warningCount = snapshot.warningCount();
        criticalCount = snapshot.criticalCount();
        applyPrimaryRisk(snapshot.primaryRisk());
        evaluatedAt = nextEvaluatedAt;
    }

    private void applyPrimaryRisk(FlightQualityRisk primaryRisk) {
        if (primaryRisk == null) {
            primaryRiskSeverity = null;
            primaryRiskTitle = null;
            primaryRiskDetail = null;
            return;
        }

        primaryRiskSeverity = primaryRisk.severity();
        primaryRiskTitle = primaryRisk.title();
        primaryRiskDetail = primaryRisk.detail();
    }

    private static BigDecimal decimal(double value, int scale) {
        return BigDecimal.valueOf(value)
                .setScale(scale, RoundingMode.HALF_UP);
    }

    private static BigDecimal nullableDecimal(
            Double value,
            int scale
    ) {
        return value == null ? null : decimal(value, scale);
    }

    @PrePersist
    private void prePersist() {
        LocalDateTime now = LocalDateTime.now();
        if (createdAt == null) {
            createdAt = now;
        }
        if (updatedAt == null) {
            updatedAt = now;
        }
    }

    @PreUpdate
    private void preUpdate() {
        updatedAt = LocalDateTime.now();
    }

    public Long getId() {
        return id;
    }

    public String getSessionId() {
        return sessionId;
    }

    public Long getDroneId() {
        return droneId;
    }

    public String getRuleVersion() {
        return ruleVersion;
    }

    public FlightSessionStatus getSessionStatus() {
        return sessionStatus;
    }

    public Integer getScore() {
        return score;
    }

    public FlightQualityGrade getGrade() {
        return grade;
    }

    public Integer getDataScore() {
        return dataScore;
    }

    public Integer getFlightScore() {
        return flightScore;
    }

    public Integer getAiScore() {
        return aiScore;
    }

    public Long getTelemetryCount() {
        return telemetryCount;
    }

    public Long getValidCoordinateCount() {
        return validCoordinateCount;
    }

    public BigDecimal getCoordinateCoveragePercent() {
        return coordinateCoveragePercent;
    }

    public BigDecimal getBatteryCoveragePercent() {
        return batteryCoveragePercent;
    }

    public BigDecimal getMaxTelemetryGapSeconds() {
        return maxTelemetryGapSeconds;
    }

    public Integer getUnrealisticJumpCount() {
        return unrealisticJumpCount;
    }

    public Integer getAltitudeSpikeCount() {
        return altitudeSpikeCount;
    }

    public Integer getBatteryIncreaseCount() {
        return batteryIncreaseCount;
    }

    public Integer getMinimumBatteryLevel() {
        return minimumBatteryLevel;
    }

    public Long getAiEventCount() {
        return aiEventCount;
    }

    public Long getDetectedEventCount() {
        return detectedEventCount;
    }

    public BigDecimal getAverageInferenceMs() {
        return averageInferenceMs;
    }

    public BigDecimal getSnapshotCoveragePercent() {
        return snapshotCoveragePercent;
    }

    public Integer getWarningCount() {
        return warningCount;
    }

    public Integer getCriticalCount() {
        return criticalCount;
    }

    public FlightQualitySeverity getPrimaryRiskSeverity() {
        return primaryRiskSeverity;
    }

    public String getPrimaryRiskTitle() {
        return primaryRiskTitle;
    }

    public String getPrimaryRiskDetail() {
        return primaryRiskDetail;
    }

    public LocalDateTime getEvaluatedAt() {
        return evaluatedAt;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }
}
