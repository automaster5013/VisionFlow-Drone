package com.visionflow.api.drone.service;

import com.visionflow.api.drone.domain.Drone;
import com.visionflow.api.drone.domain.DroneStatus;
import com.visionflow.api.drone.dto.DroneStatusUpdateRequest;
import com.visionflow.api.drone.dto.DroneUpdateRequest;
import com.visionflow.api.drone.realtime.DroneRealtimePublisher;
import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.flight.service.FlightSessionCorrelationGuard;
import com.visionflow.api.geofence.service.GeofenceService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class DroneServiceConcurrencyTests {

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
    void basicInformationUpdateUsesWriteLock() {
        Drone drone = drone();
        when(droneRepository.findByIdForUpdate(1L))
                .thenReturn(Optional.of(drone));

        var response = service.updateDrone(
                1L,
                new DroneUpdateRequest(
                        "변경 드론",
                        "VF-X2",
                        "SERIAL-2",
                        "rtsp://camera/2"
                )
        );

        assertThat(response.name()).isEqualTo("변경 드론");
        assertThat(response.modelName()).isEqualTo("VF-X2");
        verify(droneRepository).findByIdForUpdate(1L);
        verify(droneRepository, never()).findById(1L);
    }

    @Test
    void statusUpdateUsesWriteLock() {
        Drone drone = drone();
        when(droneRepository.findByIdForUpdate(1L))
                .thenReturn(Optional.of(drone));

        var response = service.updateStatus(
                1L,
                new DroneStatusUpdateRequest(DroneStatus.FLYING)
        );

        assertThat(response.status()).isEqualTo(DroneStatus.FLYING);
        verify(droneRepository).findByIdForUpdate(1L);
        verify(droneRepository, never()).findById(1L);
    }

    @Test
    void readOnlyDetailKeepsNonLockingLookup() {
        Drone drone = drone();
        when(droneRepository.findById(1L))
                .thenReturn(Optional.of(drone));

        var response = service.getDrone(1L);

        assertThat(response.droneCode()).isEqualTo("DRONE-1");
        verify(droneRepository).findById(1L);
        verify(droneRepository, never()).findByIdForUpdate(1L);
    }

    private Drone drone() {
        return new Drone(
                "DRONE-1",
                "기준 드론",
                "VF-X1",
                "SERIAL-1",
                DroneStatus.ONLINE,
                "rtsp://camera/1",
                null,
                null,
                null,
                80,
                null
        );
    }
}
