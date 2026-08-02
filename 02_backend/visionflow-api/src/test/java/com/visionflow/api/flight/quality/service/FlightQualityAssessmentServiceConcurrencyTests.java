package com.visionflow.api.flight.quality.service;

import com.visionflow.api.ai.repository.AiInferenceEventRepository;
import com.visionflow.api.common.exception.ResourceNotFoundException;
import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.drone.repository.DroneTelemetryHistoryRepository;
import com.visionflow.api.flight.domain.FlightSession;
import com.visionflow.api.flight.quality.repository.FlightQualityAssessmentRepository;
import com.visionflow.api.flight.repository.FlightSessionRepository;
import org.junit.jupiter.api.Test;

import java.time.LocalDateTime;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class FlightQualityAssessmentServiceConcurrencyTests {

    private final DroneRepository droneRepository =
            mock(DroneRepository.class);
    private final FlightSessionRepository sessionRepository =
            mock(FlightSessionRepository.class);
    private final DroneTelemetryHistoryRepository telemetryRepository =
            mock(DroneTelemetryHistoryRepository.class);
    private final AiInferenceEventRepository eventRepository =
            mock(AiInferenceEventRepository.class);
    private final FlightQualityAssessmentRepository assessmentRepository =
            mock(FlightQualityAssessmentRepository.class);
    private final FlightQualityCalculator calculator =
            mock(FlightQualityCalculator.class);
    private final FlightQualityAssessmentService service =
            new FlightQualityAssessmentService(
                    droneRepository,
                    sessionRepository,
                    telemetryRepository,
                    eventRepository,
                    assessmentRepository,
                    calculator
            );

    @Test
    void recalculationLocksSessionBeforeReadingSamples() {
        FlightSession session = session("session-lock");
        IllegalStateException failure =
                new IllegalStateException("표본 조회 중단");
        when(droneRepository.existsById(1L)).thenReturn(true);
        when(sessionRepository.findBySessionIdAndDroneIdForUpdate(
                "session-lock",
                1L
        )).thenReturn(Optional.of(session));
        when(telemetryRepository.countByDroneIdAndFlightSessionId(
                1L,
                "session-lock"
        )).thenThrow(failure);

        assertThatThrownBy(() ->
                service.recalculate(1L, "session-lock")
        ).isSameAs(failure);

        var ordered = inOrder(sessionRepository, telemetryRepository);
        ordered.verify(sessionRepository)
                .findBySessionIdAndDroneIdForUpdate(
                        "session-lock",
                        1L
                );
        ordered.verify(telemetryRepository)
                .countByDroneIdAndFlightSessionId(
                        1L,
                        "session-lock"
                );
        verify(sessionRepository, never())
                .findBySessionIdAndDroneId("session-lock", 1L);
    }

    @Test
    void readOnlyDetailKeepsNonLockingSessionLookup() {
        FlightSession session = session("session-read");
        when(droneRepository.existsById(1L)).thenReturn(true);
        when(sessionRepository.findBySessionIdAndDroneId(
                "session-read",
                1L
        )).thenReturn(Optional.of(session));
        when(
                assessmentRepository
                        .findFirstByDroneIdAndSessionIdOrderByEvaluatedAtDesc(
                                1L,
                                "session-read"
                        )
        ).thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.find(1L, "session-read"))
                .isInstanceOf(ResourceNotFoundException.class)
                .hasMessageContaining("저장된 비행 품질 평가");

        verify(sessionRepository)
                .findBySessionIdAndDroneId("session-read", 1L);
        verify(sessionRepository, never())
                .findBySessionIdAndDroneIdForUpdate(
                        "session-read",
                        1L
                );
    }

    private FlightSession session(String sessionId) {
        return FlightSession.start(
                sessionId,
                1L,
                "동시성 검증",
                null,
                "test-device",
                LocalDateTime.of(2026, 8, 3, 3, 0)
        );
    }
}
