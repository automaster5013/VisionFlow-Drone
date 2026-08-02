package com.visionflow.api.geofence.service;

import com.visionflow.api.drone.domain.Drone;
import com.visionflow.api.drone.domain.DroneStatus;
import com.visionflow.api.geofence.domain.DroneGeofence;
import com.visionflow.api.geofence.domain.DroneGeofenceEvent;
import com.visionflow.api.geofence.domain.GeofenceRule;
import com.visionflow.api.geofence.dto.GeofenceActiveUpdateRequest;
import com.visionflow.api.geofence.dto.GeofenceUpdateRequest;
import com.visionflow.api.geofence.realtime.GeofenceRealtimePublisher;
import com.visionflow.api.geofence.repository.DroneGeofenceEventRepository;
import com.visionflow.api.geofence.repository.DroneGeofenceRepository;
import com.visionflow.api.incident.service.IncidentService;
import org.junit.jupiter.api.Test;
import org.mockito.InOrder;
import org.springframework.test.util.ReflectionTestUtils;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class GeofenceServiceConcurrencyTests {

    private final DroneGeofenceRepository geofenceRepository =
            mock(DroneGeofenceRepository.class);
    private final DroneGeofenceEventRepository eventRepository =
            mock(DroneGeofenceEventRepository.class);
    private final GeofenceRealtimePublisher realtimePublisher =
            mock(GeofenceRealtimePublisher.class);
    private final IncidentService incidentService =
            mock(IncidentService.class);
    private final GeofenceService service = new GeofenceService(
            geofenceRepository,
            eventRepository,
            realtimePublisher,
            incidentService
    );

    @Test
    void updateLocksGeofenceBeforeMutation() {
        DroneGeofence geofence = geofence(41L, true);
        when(geofenceRepository.findByIdForUpdate(41L))
                .thenReturn(Optional.of(geofence));
        when(geofenceRepository
                .existsByNameIgnoreCaseAndIdNot("Updated zone", 41L))
                .thenReturn(false);
        when(geofenceRepository.saveAndFlush(geofence))
                .thenReturn(geofence);

        service.update(
                41L,
                new GeofenceUpdateRequest(
                        "Updated zone",
                        GeofenceRule.KEEP_OUT,
                        BigDecimal.valueOf(37.5),
                        BigDecimal.valueOf(127.0),
                        BigDecimal.valueOf(250)
                )
        );

        verify(geofenceRepository).findByIdForUpdate(41L);
        verify(geofenceRepository, never()).findById(41L);
    }

    @Test
    void changeActiveLocksGeofenceBeforeMutation() {
        DroneGeofence geofence = geofence(42L, false);
        when(geofenceRepository.findByIdForUpdate(42L))
                .thenReturn(Optional.of(geofence));
        when(geofenceRepository.saveAndFlush(geofence))
                .thenReturn(geofence);

        service.changeActive(
                42L,
                new GeofenceActiveUpdateRequest(true)
        );

        verify(geofenceRepository).findByIdForUpdate(42L);
        verify(geofenceRepository, never()).findById(42L);
    }

    @Test
    void readOnlyDetailKeepsNonLockingLookup() {
        DroneGeofence geofence = geofence(43L, true);
        when(geofenceRepository.findById(43L))
                .thenReturn(Optional.of(geofence));

        service.findById(43L);

        verify(geofenceRepository).findById(43L);
        verify(geofenceRepository, never())
                .findByIdForUpdate(43L);
    }

    @Test
    void evaluationLocksGeofenceBeforeActiveEventLookup() {
        Drone drone = drone(7L);
        DroneGeofence candidate = geofence(44L, true);
        when(geofenceRepository
                .findAllByActiveTrueOrderByCreatedAtDesc())
                .thenReturn(List.of(candidate));
        when(geofenceRepository.findByIdForUpdate(44L))
                .thenReturn(Optional.of(candidate));
        when(eventRepository
                .findFirstByDroneIdAndGeofenceIdAndResolvedAtIsNullOrderByDetectedAtDesc(
                        7L,
                        44L
                ))
                .thenReturn(Optional.empty());
        when(eventRepository.saveAndFlush(any(DroneGeofenceEvent.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));

        service.evaluate(
                drone,
                LocalDateTime.of(2026, 8, 2, 14, 0)
        );

        InOrder order = inOrder(
                geofenceRepository,
                eventRepository
        );
        order.verify(geofenceRepository).findByIdForUpdate(44L);
        order.verify(eventRepository)
                .findFirstByDroneIdAndGeofenceIdAndResolvedAtIsNullOrderByDetectedAtDesc(
                        7L,
                        44L
                );
        verify(eventRepository).saveAndFlush(
                any(DroneGeofenceEvent.class)
        );
    }

    private DroneGeofence geofence(Long id, boolean active) {
        DroneGeofence geofence = DroneGeofence.create(
                "Zone " + id,
                GeofenceRule.KEEP_OUT,
                BigDecimal.valueOf(37.5),
                BigDecimal.valueOf(127.0),
                BigDecimal.valueOf(250),
                active
        );
        ReflectionTestUtils.setField(geofence, "id", id);
        return geofence;
    }

    private Drone drone(Long id) {
        Drone drone = new Drone(
                "DRONE-" + id,
                "Concurrency test drone",
                "VisionFlow",
                "SERIAL-" + id,
                DroneStatus.FLYING,
                null,
                BigDecimal.valueOf(37.5),
                BigDecimal.valueOf(127.0),
                BigDecimal.valueOf(30),
                90,
                LocalDateTime.of(2026, 8, 2, 14, 0)
        );
        ReflectionTestUtils.setField(drone, "id", id);
        return drone;
    }
}
