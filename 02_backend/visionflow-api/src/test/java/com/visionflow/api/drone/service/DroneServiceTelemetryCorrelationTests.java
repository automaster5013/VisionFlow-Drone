package com.visionflow.api.drone.service;

import com.visionflow.api.drone.domain.Drone;
import com.visionflow.api.drone.dto.DroneTelemetryUpdateRequest;
import com.visionflow.api.drone.realtime.DroneRealtimePublisher;
import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.flight.exception.FlightSessionDroneMismatchException;
import com.visionflow.api.flight.service.FlightSessionCorrelationGuard;
import com.visionflow.api.geofence.service.GeofenceService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class DroneServiceTelemetryCorrelationTests {

    private final DroneRepository droneRepository =
            mock(DroneRepository.class);
    private final DroneRealtimePublisher realtimePublisher =
            mock(DroneRealtimePublisher.class);
    private final DroneTelemetryHistoryService telemetryHistoryService =
            mock(DroneTelemetryHistoryService.class);
    private final GeofenceService geofenceService =
            mock(GeofenceService.class);
    private final FlightSessionCorrelationGuard correlationGuard =
            mock(FlightSessionCorrelationGuard.class);

    private DroneService service;

    @BeforeEach
    void setUp() {
        service = new DroneService(
                droneRepository,
                realtimePublisher,
                telemetryHistoryService,
                geofenceService,
                correlationGuard
        );
    }

    @Test
    void rejectsMismatchedSessionBeforeTelemetryMutation() {
        Drone drone = mock(Drone.class);
        when(droneRepository.findByIdForUpdate(7L))
                .thenReturn(Optional.of(drone));
        when(correlationGuard.requireOptionalOwnedSession(
                "session-2",
                7L
        )).thenThrow(new FlightSessionDroneMismatchException("mismatch"));

        assertThatThrownBy(() -> service.updateTelemetry(7L, request()))
                .isInstanceOf(FlightSessionDroneMismatchException.class);

        verify(droneRepository).findByIdForUpdate(7L);
        verify(droneRepository, never()).findById(7L);
        verify(droneRepository, never()).flush();
        verify(telemetryHistoryService, never()).record(
                org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.any()
        );
    }

    private DroneTelemetryUpdateRequest request() {
        return new DroneTelemetryUpdateRequest(
                new BigDecimal("37.5000000"),
                new BigDecimal("127.0000000"),
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                "session-2",
                null
        );
    }
}
