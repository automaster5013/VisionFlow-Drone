package com.visionflow.api.flight.quality.service;

import com.visionflow.api.audit.domain.AuditAction;
import com.visionflow.api.audit.domain.AuditEntityType;
import com.visionflow.api.audit.service.AuditLogService;
import com.visionflow.api.flight.domain.FlightSessionStatus;
import com.visionflow.api.flight.event.FlightSessionClosedEvent;
import com.visionflow.api.flight.quality.domain.FlightQualityGrade;
import com.visionflow.api.flight.quality.dto.FlightQualityAssessmentResponse;
import com.visionflow.api.flight.quality.dto.FlightQualityMetricsResponse;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Instant;

import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class FlightQualityAssessmentAutomationServiceTests {

    private final FlightQualityAssessmentService assessmentService =
            mock(FlightQualityAssessmentService.class);
    private final AuditLogService auditLogService =
            mock(AuditLogService.class);
    private final FlightQualityIncidentAutomationService
            incidentAutomationService =
            mock(FlightQualityIncidentAutomationService.class);
    private final FlightQualityAssessmentAutomationService service =
            new FlightQualityAssessmentAutomationService(
                    assessmentService,
                    auditLogService,
                    incidentAutomationService
            );

    @Test
    void closedSessionIsEvaluatedAndAuditedAsSystem() {
        FlightSessionClosedEvent event = new FlightSessionClosedEvent(
                1L,
                "session-1",
                FlightSessionStatus.COMPLETED
        );
        when(assessmentService.recalculate(1L, "session-1"))
                .thenReturn(response());

        service.assessClosedSession(event);

        verify(assessmentService).recalculate(1L, "session-1");
        verify(incidentAutomationService).synchronizeDrone(
                1L,
                FlightQualityIncidentAutomationService
                        .DEFAULT_LIMIT_PER_DRONE
        );
        verify(auditLogService).record(
                eq(AuditAction.FLIGHT_QUALITY_ASSESSED),
                eq(AuditEntityType.FLIGHT_QUALITY_ASSESSMENT),
                eq("session-1"),
                eq("비행 종료 후 품질 평가 자동 저장"),
                anyMap(),
                eq("system-flight-quality-automation")
        );
    }

    @Test
    void evaluationFailureDoesNotEscapeOrWriteAuditLog() {
        FlightSessionClosedEvent event = new FlightSessionClosedEvent(
                1L,
                "session-2",
                FlightSessionStatus.ABORTED
        );
        when(assessmentService.recalculate(1L, "session-2"))
                .thenThrow(new IllegalStateException("일시 오류"));

        service.assessClosedSession(event);

        verify(auditLogService, never()).record(
                eq(AuditAction.FLIGHT_QUALITY_ASSESSED),
                eq(AuditEntityType.FLIGHT_QUALITY_ASSESSMENT),
                eq("session-2"),
                eq("비행 종료 후 품질 평가 자동 저장"),
                anyMap(),
                eq("system-flight-quality-automation")
        );
        verify(incidentAutomationService, never()).synchronizeDrone(
                eq(1L),
                eq(FlightQualityIncidentAutomationService
                        .DEFAULT_LIMIT_PER_DRONE)
        );
    }

    private FlightQualityAssessmentResponse response() {
        return new FlightQualityAssessmentResponse(
                10L,
                1L,
                "session-1",
                FlightSessionStatus.COMPLETED,
                FlightQualityAssessmentService.CURRENT_RULE_VERSION,
                95,
                FlightQualityGrade.EXCELLENT,
                40,
                28,
                27,
                0,
                0,
                null,
                new FlightQualityMetricsResponse(
                        2,
                        2,
                        new BigDecimal("100.00"),
                        new BigDecimal("100.00"),
                        new BigDecimal("1.00"),
                        0,
                        0,
                        0,
                        80,
                        1,
                        1,
                        new BigDecimal("120.00"),
                        new BigDecimal("100.00")
                ),
                Instant.parse("2026-07-25T01:01:00Z")
        );
    }
}
