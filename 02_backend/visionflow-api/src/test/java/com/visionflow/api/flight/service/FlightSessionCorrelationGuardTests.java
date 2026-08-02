package com.visionflow.api.flight.service;

import com.visionflow.api.common.exception.ResourceNotFoundException;
import com.visionflow.api.flight.domain.FlightSession;
import com.visionflow.api.flight.exception.FlightSessionDroneMismatchException;
import com.visionflow.api.flight.repository.FlightSessionRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;

import java.time.LocalDateTime;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class FlightSessionCorrelationGuardTests {

    private final FlightSessionRepository sessionRepository =
            mock(FlightSessionRepository.class);

    private FlightSessionCorrelationGuard guard;

    @BeforeEach
    void setUp() {
        guard = new FlightSessionCorrelationGuard(sessionRepository);
    }

    @Test
    void acceptsSessionOwnedByRequestedDroneAndNormalizesId() {
        FlightSession session = session("session-1", 7L);
        when(sessionRepository.findById("session-1"))
                .thenReturn(Optional.of(session));

        String result = guard.requireOwnedSession("  session-1  ", 7L);

        assertThat(result).isEqualTo("session-1");
    }

    @Test
    void rejectsUnknownSessionWithoutCreatingSoftCorrelation() {
        when(sessionRepository.findById("missing-session"))
                .thenReturn(Optional.empty());

        assertThatThrownBy(() -> guard.requireOwnedSession(
                "missing-session",
                7L
        )).isInstanceOfSatisfying(
                ResourceNotFoundException.class,
                exception -> {
                    assertThat(exception.getStatus())
                            .isEqualTo(HttpStatus.NOT_FOUND);
                    assertThat(exception.getCode())
                            .isEqualTo("RESOURCE_NOT_FOUND");
                }
        );
    }

    @Test
    void rejectsSessionOwnedByAnotherDrone() {
        when(sessionRepository.findById("session-2"))
                .thenReturn(Optional.of(session("session-2", 8L)));

        assertThatThrownBy(() -> guard.requireOwnedSession(
                "session-2",
                7L
        )).isInstanceOfSatisfying(
                FlightSessionDroneMismatchException.class,
                exception -> {
                    assertThat(exception.getStatus())
                            .isEqualTo(HttpStatus.CONFLICT);
                    assertThat(exception.getCode())
                            .isEqualTo("FLIGHT_SESSION_DRONE_MISMATCH");
                }
        );
    }

    @Test
    void allowsTelemetryWithoutSessionReference() {
        assertThat(guard.requireOptionalOwnedSession("  ", 7L))
                .isNull();
        verify(sessionRepository, never()).findById("  ");
    }

    private FlightSession session(String sessionId, Long droneId) {
        return FlightSession.start(
                sessionId,
                droneId,
                "test session",
                null,
                "test-device",
                LocalDateTime.of(2026, 8, 2, 12, 0)
        );
    }
}
