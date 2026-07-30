package com.visionflow.api.flight.quality.service;

import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.flight.domain.FlightSession;
import com.visionflow.api.flight.quality.repository.FlightQualityAssessmentRepository;
import com.visionflow.api.flight.repository.FlightSessionRepository;
import org.junit.jupiter.api.Test;
import org.springframework.data.domain.Pageable;

import java.time.LocalDateTime;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class FlightQualityBackfillServiceTests {

    private final DroneRepository droneRepository =
            mock(DroneRepository.class);
    private final FlightSessionRepository sessionRepository =
            mock(FlightSessionRepository.class);
    private final FlightQualityAssessmentRepository assessmentRepository =
            mock(FlightQualityAssessmentRepository.class);
    private final FlightQualityAssessmentService assessmentService =
            mock(FlightQualityAssessmentService.class);
    private final FlightQualityBackfillService service =
            new FlightQualityBackfillService(
                    droneRepository,
                    sessionRepository,
                    assessmentRepository,
                    assessmentService
            );

    @Test
    void backfillSkipsCurrentRuleAndEvaluatesMissingSession() {
        FlightSession alreadyEvaluated = terminalSession(
                "session-existing",
                false
        );
        FlightSession missing = terminalSession("session-missing", true);
        when(droneRepository.existsById(1L)).thenReturn(true);
        when(
                sessionRepository
                        .findByDroneIdAndStatusInOrderByEndedAtDesc(
                                eq(1L),
                                any(),
                                any(Pageable.class)
                        )
        ).thenReturn(List.of(alreadyEvaluated, missing));
        when(assessmentRepository.existsBySessionIdAndRuleVersion(
                "session-existing",
                FlightQualityAssessmentService.CURRENT_RULE_VERSION
        )).thenReturn(true);
        when(assessmentRepository.existsBySessionIdAndRuleVersion(
                "session-missing",
                FlightQualityAssessmentService.CURRENT_RULE_VERSION
        )).thenReturn(false);

        var result = service.backfill(1L, 100, false);

        assertThat(result.candidateCount()).isEqualTo(2);
        assertThat(result.evaluatedCount()).isEqualTo(1);
        assertThat(result.skippedCount()).isEqualTo(1);
        assertThat(result.failedCount()).isZero();
        verify(assessmentService).recalculate(1L, "session-missing");
    }

    @Test
    void failedSessionDoesNotStopRemainingBackfill() {
        FlightSession failed = terminalSession("session-failed", false);
        FlightSession healthy = terminalSession("session-healthy", false);
        when(droneRepository.existsById(1L)).thenReturn(true);
        when(
                sessionRepository
                        .findByDroneIdAndStatusInOrderByEndedAtDesc(
                                eq(1L),
                                any(),
                                any(Pageable.class)
                        )
        ).thenReturn(List.of(failed, healthy));
        when(assessmentService.recalculate(1L, "session-failed"))
                .thenThrow(new IllegalStateException("평가 실패"));

        var result = service.backfill(1L, 100, false);

        assertThat(result.evaluatedCount()).isEqualTo(1);
        assertThat(result.failedCount()).isEqualTo(1);
        assertThat(result.failures())
                .singleElement()
                .extracting(failure -> failure.sessionId())
                .isEqualTo("session-failed");
        verify(assessmentService).recalculate(1L, "session-healthy");
    }

    private FlightSession terminalSession(
            String sessionId,
            boolean aborted
    ) {
        LocalDateTime startedAt =
                LocalDateTime.of(2026, 7, 25, 1, 0);
        FlightSession session = FlightSession.start(
                sessionId,
                1L,
                "백필 검증",
                null,
                "test-device",
                startedAt
        );

        if (aborted) {
            session.abort(startedAt.plusMinutes(1));
        } else {
            session.complete(startedAt.plusMinutes(1));
        }

        return session;
    }
}
