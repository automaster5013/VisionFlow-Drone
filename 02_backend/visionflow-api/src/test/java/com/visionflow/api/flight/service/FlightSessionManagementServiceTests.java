package com.visionflow.api.flight.service;

import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.drone.domain.Drone;
import com.visionflow.api.flight.domain.FlightSession;
import com.visionflow.api.flight.domain.FlightSessionStatus;
import com.visionflow.api.flight.dto.FlightSessionStartRequest;
import com.visionflow.api.flight.event.FlightSessionClosedEvent;
import com.visionflow.api.flight.repository.FlightSessionRepository;
import com.visionflow.api.maintenance.service.MaintenanceFlightGateService;
import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationEventPublisher;

import java.time.LocalDateTime;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.clearInvocations;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class FlightSessionManagementServiceTests {

    private final DroneRepository droneRepository =
            mock(DroneRepository.class);
    private final FlightSessionRepository sessionRepository =
            mock(FlightSessionRepository.class);
    private final ApplicationEventPublisher eventPublisher =
            mock(ApplicationEventPublisher.class);
    private final MaintenanceFlightGateService flightGateService =
            mock(MaintenanceFlightGateService.class);
    private final FlightSessionManagementService service =
            new FlightSessionManagementService(
                    droneRepository,
                    sessionRepository,
                    eventPublisher,
                    flightGateService
            );

    @Test
    void startingSessionChecksMaintenanceClearance() {
        when(droneRepository.findById(1L))
                .thenReturn(Optional.of(mock(Drone.class)));
        when(sessionRepository
                .findFirstByDroneIdAndStatusOrderByStartedAtDesc(
                        1L,
                        FlightSessionStatus.ACTIVE
                ))
                .thenReturn(Optional.empty());
        when(sessionRepository.save(any(FlightSession.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));

        service.start(
                1L,
                new FlightSessionStartRequest(
                        "게이트 검증 비행",
                        null,
                        "test-device"
                )
        );

        verify(flightGateService).requireStartClearance(1L);
    }

    @Test
    void completingSessionPublishesClosedEventOnce() {
        FlightSession session = activeSession("session-1");
        when(sessionRepository.findBySessionIdAndDroneId(
                "session-1",
                1L
        )).thenReturn(Optional.of(session));

        var response = service.complete(1L, "session-1");

        assertThat(response.status())
                .isEqualTo(FlightSessionStatus.COMPLETED);
        verify(eventPublisher).publishEvent(
                new FlightSessionClosedEvent(
                        1L,
                        "session-1",
                        FlightSessionStatus.COMPLETED
                )
        );

        clearInvocations(eventPublisher);
        service.complete(1L, "session-1");

        verify(eventPublisher, never()).publishEvent(
                any(FlightSessionClosedEvent.class)
        );
    }

    @Test
    void abortingSessionPublishesClosedEvent() {
        FlightSession session = activeSession("session-2");
        when(sessionRepository.findBySessionIdAndDroneId(
                "session-2",
                1L
        )).thenReturn(Optional.of(session));

        var response = service.abort(1L, "session-2");

        assertThat(response.status())
                .isEqualTo(FlightSessionStatus.ABORTED);
        verify(eventPublisher).publishEvent(
                new FlightSessionClosedEvent(
                        1L,
                        "session-2",
                        FlightSessionStatus.ABORTED
                )
        );
    }

    private FlightSession activeSession(String sessionId) {
        return FlightSession.start(
                sessionId,
                1L,
                "자동 평가 검증",
                null,
                "test-device",
                LocalDateTime.of(2026, 7, 25, 1, 0)
        );
    }
}
