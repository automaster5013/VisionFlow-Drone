package com.visionflow.api.flight.quality.dto;

import com.visionflow.api.flight.domain.FlightSessionStatus;
import com.visionflow.api.flight.quality.domain.FlightQualityAssessment;
import com.visionflow.api.flight.quality.domain.FlightQualityGrade;

import java.time.Instant;
import java.time.ZoneOffset;

public record FlightQualityAssessmentResponse(
        Long id,
        Long droneId,
        String sessionId,
        FlightSessionStatus sessionStatus,
        String ruleVersion,
        int score,
        FlightQualityGrade grade,
        int dataScore,
        int flightScore,
        int aiScore,
        int warningCount,
        int criticalCount,
        FlightQualityRiskResponse primaryRisk,
        FlightQualityMetricsResponse metrics,
        Instant evaluatedAt
) {

    public static FlightQualityAssessmentResponse from(
            FlightQualityAssessment assessment
    ) {
        FlightQualityRiskResponse primaryRisk =
                assessment.getPrimaryRiskSeverity() == null
                        ? null
                        : new FlightQualityRiskResponse(
                                assessment.getPrimaryRiskSeverity(),
                                assessment.getPrimaryRiskTitle(),
                                assessment.getPrimaryRiskDetail()
                        );

        FlightQualityMetricsResponse metrics =
                new FlightQualityMetricsResponse(
                        assessment.getTelemetryCount(),
                        assessment.getValidCoordinateCount(),
                        assessment.getCoordinateCoveragePercent(),
                        assessment.getBatteryCoveragePercent(),
                        assessment.getMaxTelemetryGapSeconds(),
                        assessment.getUnrealisticJumpCount(),
                        assessment.getAltitudeSpikeCount(),
                        assessment.getBatteryIncreaseCount(),
                        assessment.getMinimumBatteryLevel(),
                        assessment.getAiEventCount(),
                        assessment.getDetectedEventCount(),
                        assessment.getAverageInferenceMs(),
                        assessment.getSnapshotCoveragePercent()
                );

        return new FlightQualityAssessmentResponse(
                assessment.getId(),
                assessment.getDroneId(),
                assessment.getSessionId(),
                assessment.getSessionStatus(),
                assessment.getRuleVersion(),
                assessment.getScore(),
                assessment.getGrade(),
                assessment.getDataScore(),
                assessment.getFlightScore(),
                assessment.getAiScore(),
                assessment.getWarningCount(),
                assessment.getCriticalCount(),
                primaryRisk,
                metrics,
                assessment.getEvaluatedAt()
                        .toInstant(ZoneOffset.UTC)
        );
    }
}
