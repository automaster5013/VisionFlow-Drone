package com.visionflow.api.flight.quality.service;

import com.visionflow.api.ai.domain.AiInferenceEvent;
import com.visionflow.api.drone.domain.DroneTelemetryHistory;
import com.visionflow.api.flight.domain.FlightSessionStatus;
import com.visionflow.api.flight.quality.domain.FlightQualityGrade;
import com.visionflow.api.flight.quality.domain.FlightQualitySeverity;
import com.visionflow.api.flight.quality.domain.FlightQualitySnapshot;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class FlightQualityCalculatorTests {

    private final FlightQualityCalculator calculator =
            new FlightQualityCalculator();

    @Test
    void completeSessionWithHealthyEvidenceScoresOneHundred() {
        LocalDateTime startedAt =
                LocalDateTime.of(2026, 7, 25, 1, 0);
        DroneTelemetryHistory first = telemetry(
                startedAt,
                "37.5665000",
                "126.9780000",
                "40.00",
                90
        );
        DroneTelemetryHistory second = telemetry(
                startedAt.plusSeconds(1),
                "37.5665100",
                "126.9780100",
                "40.50",
                89
        );
        AiInferenceEvent event = aiEvent(
                startedAt,
                "120.000",
                1,
                "snapshot-1.jpg"
        );

        FlightQualitySnapshot result = calculator.calculate(
                FlightSessionStatus.COMPLETED,
                List.of(first, second),
                List.of(event)
        );

        assertThat(result.score()).isEqualTo(100);
        assertThat(result.grade())
                .isEqualTo(FlightQualityGrade.EXCELLENT);
        assertThat(result.dataScore()).isEqualTo(40);
        assertThat(result.flightScore()).isEqualTo(30);
        assertThat(result.aiScore()).isEqualTo(30);
        assertThat(result.warningCount()).isZero();
        assertThat(result.criticalCount()).isZero();
        assertThat(result.primaryRisk()).isNull();
    }

    @Test
    void missingTelemetryProducesCriticalRiskAndRiskGrade() {
        FlightQualitySnapshot result = calculator.calculate(
                FlightSessionStatus.COMPLETED,
                List.of(),
                List.of()
        );

        assertThat(result.score()).isEqualTo(20);
        assertThat(result.grade())
                .isEqualTo(FlightQualityGrade.RISK);
        assertThat(result.criticalCount()).isEqualTo(1);
        assertThat(result.warningCount()).isEqualTo(1);
        assertThat(result.primaryRisk()).isNotNull();
        assertThat(result.primaryRisk().severity())
                .isEqualTo(FlightQualitySeverity.CRITICAL);
        assertThat(result.primaryRisk().title())
                .isEqualTo("텔레메트리 표본 부족");
    }

    @Test
    void abortedSessionCapsOtherwiseHealthyScoreAtSeventyFour() {
        LocalDateTime startedAt =
                LocalDateTime.of(2026, 7, 25, 1, 0);
        DroneTelemetryHistory first = telemetry(
                startedAt,
                "37.5665000",
                "126.9780000",
                "40.00",
                90
        );
        DroneTelemetryHistory second = telemetry(
                startedAt.plusSeconds(1),
                "37.5665100",
                "126.9780100",
                "40.50",
                89
        );
        AiInferenceEvent event = aiEvent(
                startedAt,
                "120.000",
                1,
                "snapshot-1.jpg"
        );

        FlightQualitySnapshot result = calculator.calculate(
                FlightSessionStatus.ABORTED,
                List.of(first, second),
                List.of(event)
        );

        assertThat(result.score()).isEqualTo(74);
        assertThat(result.grade())
                .isEqualTo(FlightQualityGrade.CAUTION);
        assertThat(result.criticalCount()).isEqualTo(1);
        assertThat(result.primaryRisk().title())
                .isEqualTo("중단된 비행 세션");
    }

    private DroneTelemetryHistory telemetry(
            LocalDateTime recordedAt,
            String latitude,
            String longitude,
            String altitude,
            Integer batteryLevel
    ) {
        DroneTelemetryHistory telemetry =
                mock(DroneTelemetryHistory.class);
        when(telemetry.getRecordedAt()).thenReturn(recordedAt);
        when(telemetry.getLatitude())
                .thenReturn(new BigDecimal(latitude));
        when(telemetry.getLongitude())
                .thenReturn(new BigDecimal(longitude));
        when(telemetry.getAltitude())
                .thenReturn(new BigDecimal(altitude));
        when(telemetry.getBatteryLevel())
                .thenReturn(batteryLevel);
        return telemetry;
    }

    private AiInferenceEvent aiEvent(
            LocalDateTime capturedAt,
            String inferenceMs,
            Integer detectionCount,
            String snapshotFileName
    ) {
        AiInferenceEvent event = mock(AiInferenceEvent.class);
        when(event.getCapturedAt()).thenReturn(capturedAt);
        when(event.getInferenceMs())
                .thenReturn(new BigDecimal(inferenceMs));
        when(event.getDetectionCount())
                .thenReturn(detectionCount);
        when(event.getSnapshotFileName())
                .thenReturn(snapshotFileName);
        return event;
    }
}
