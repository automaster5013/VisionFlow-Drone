package com.visionflow.api.drone.service;

import com.visionflow.api.drone.domain.Drone;
import com.visionflow.api.drone.exception.DroneHistoryDeleteDeniedException;
import com.visionflow.api.drone.realtime.DroneRealtimePublisher;
import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.geofence.service.GeofenceService;
import com.visionflow.api.flight.service.FlightSessionCorrelationGuard;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class DroneServiceDeletionTests {

    private final DroneRepository droneRepository =
            mock(DroneRepository.class);
    private final DroneRealtimePublisher realtimePublisher =
            mock(DroneRealtimePublisher.class);
    private final DroneTelemetryHistoryService telemetryHistoryService =
            mock(DroneTelemetryHistoryService.class);
    private final GeofenceService geofenceService =
            mock(GeofenceService.class);
    private final FlightSessionCorrelationGuard sessionCorrelationGuard =
            mock(FlightSessionCorrelationGuard.class);

    private DroneService service;

    @BeforeEach
    void setUp() {
        service = new DroneService(
                droneRepository,
                realtimePublisher,
                telemetryHistoryService,
                geofenceService,
                sessionCorrelationGuard
        );
    }

    @Test
    void deniesDeleteWhenOperationalHistoryExists() {
        Drone drone = mock(Drone.class);
        when(droneRepository.findByIdForUpdate(1L))
                .thenReturn(Optional.of(drone));
        when(droneRepository.countDeletionDependencies(1L))
                .thenReturn(3L);

        assertThatThrownBy(() -> service.deleteDrone(1L))
                .isInstanceOfSatisfying(
                        DroneHistoryDeleteDeniedException.class,
                        exception -> {
                            assertThat(exception.getStatus())
                                    .isEqualTo(HttpStatus.CONFLICT);
                            assertThat(exception.getCode())
                                    .isEqualTo("DRONE_HISTORY_DELETE_DENIED");
                        }
                );

        verify(droneRepository, never()).delete(drone);
    }

    @Test
    void deletesUnusedDroneWithoutOperationalHistory() {
        Drone drone = mock(Drone.class);
        when(droneRepository.findByIdForUpdate(2L))
                .thenReturn(Optional.of(drone));
        when(droneRepository.countDeletionDependencies(2L))
                .thenReturn(0L);

        service.deleteDrone(2L);

        verify(droneRepository).delete(drone);
    }
}
