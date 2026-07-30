package com.visionflow.api.geofence.service;

import com.visionflow.api.common.exception.ResourceNotFoundException;
import com.visionflow.api.common.exception.DuplicateResourceException;
import com.visionflow.api.drone.domain.Drone;
import com.visionflow.api.geofence.domain.*;
import com.visionflow.api.geofence.dto.*;
import com.visionflow.api.geofence.realtime.GeofenceRealtimePublisher;
import com.visionflow.api.geofence.repository.*;
import com.visionflow.api.incident.service.IncidentService;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.visionflow.api.geofence.dto.GeofenceActiveUpdateRequest;
import com.visionflow.api.geofence.dto.GeofenceUpdateRequest;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

@Service
public class GeofenceService {

    private static final double EARTH_RADIUS_METERS = 6_371_008.8;

    private final DroneGeofenceRepository geofenceRepository;
    private final DroneGeofenceEventRepository eventRepository;
    private final GeofenceRealtimePublisher realtimePublisher;
    private final IncidentService incidentService;

    public GeofenceService(
            DroneGeofenceRepository geofenceRepository,
            DroneGeofenceEventRepository eventRepository,
            GeofenceRealtimePublisher realtimePublisher,
            IncidentService incidentService
    ) {
        this.geofenceRepository = geofenceRepository;
        this.eventRepository = eventRepository;
        this.realtimePublisher = realtimePublisher;
        this.incidentService = incidentService;
    }

    @Transactional
    public GeofenceResponse create(GeofenceCreateRequest request) {
        String normalizedName = request.name().trim();

        if (geofenceRepository.existsByNameIgnoreCase(normalizedName)) {
            throw new DuplicateResourceException(
                    "이미 존재하는 지오펜스 이름입니다: " + normalizedName
            );
        }

        boolean active = request.active() == null || request.active();

        DroneGeofence geofence = DroneGeofence.create(
                normalizedName,
                request.ruleType(),
                request.centerLatitude(),
                request.centerLongitude(),
                request.radiusMeters(),
                active
        );

        return GeofenceResponse.from(
                geofenceRepository.saveAndFlush(geofence)
        );
    }

    @Transactional(readOnly = true)
    public List<GeofenceResponse> findAll() {
        return geofenceRepository
                .findAllByOrderByCreatedAtDesc()
                .stream()
                .map(GeofenceResponse::from)
                .toList();
    }

    @Transactional(readOnly = true)
    public List<GeofenceEventResponse> findEvents(
            boolean activeOnly,
            int limit
    ) {
        int safeLimit = Math.max(1, Math.min(limit, 500));
        PageRequest pageable = PageRequest.of(0, safeLimit);

        List<DroneGeofenceEvent> events = activeOnly
                ? eventRepository
                .findByResolvedAtIsNullOrderByDetectedAtDesc(pageable)
                : eventRepository
                .findAllByOrderByDetectedAtDesc(pageable);

        return events.stream()
                .map(GeofenceEventResponse::from)
                .toList();
    }

    @Transactional(readOnly = true)
    public GeofenceResponse findById(Long id) {
        return GeofenceResponse.from(
                findGeofence(id)
        );
    }

    @Transactional
    public GeofenceResponse update(
            Long id,
            GeofenceUpdateRequest request
    ) {
        DroneGeofence geofence = findGeofence(id);
        String normalizedName = request.name().trim();

        if (geofenceRepository
                .existsByNameIgnoreCaseAndIdNot(
                        normalizedName,
                        id
                )) {
            throw new DuplicateResourceException(
                    "이미 존재하는 지오펜스 이름입니다: "
                            + normalizedName
            );
        }

        geofence.update(
                normalizedName,
                request.ruleType(),
                request.centerLatitude(),
                request.centerLongitude(),
                request.radiusMeters()
        );

        return GeofenceResponse.from(
                geofenceRepository.saveAndFlush(geofence)
        );
    }

    @Transactional
    public GeofenceResponse changeActive(
            Long id,
            GeofenceActiveUpdateRequest request
    ) {
        DroneGeofence geofence = findGeofence(id);
        boolean nextActive = request.active();

        if (geofence.isActive() && !nextActive) {
            LocalDateTime resolvedAt = LocalDateTime.now();

            List<DroneGeofenceEvent> activeEvents =
                    eventRepository
                            .findAllByGeofenceIdAndResolvedAtIsNull(
                                    id
                            );

            for (DroneGeofenceEvent event : activeEvents) {
                event.resolve(resolvedAt);
            }

            eventRepository.flush();

            for (DroneGeofenceEvent event : activeEvents) {
                incidentService.synchronizeGeofenceResolved(
                        event,
                        "지오펜스 비활성화로 위반 이벤트 자동 해결"
                );
                realtimePublisher.publish(
                        GeofenceEventResponse.from(event)
                );
            }
        }

        geofence.changeActive(nextActive);

        return GeofenceResponse.from(
                geofenceRepository.saveAndFlush(geofence)
        );
    }

    private DroneGeofence findGeofence(Long id) {
        return geofenceRepository.findById(id)
                .orElseThrow(() ->
                        new ResourceNotFoundException(
                                "지오펜스를 찾을 수 없습니다: " + id
                        )
                );
    }

    @Transactional
    public void evaluate(Drone drone, LocalDateTime detectedAt) {
        if (drone.getLatitude() == null ||
                drone.getLongitude() == null) {
            return;
        }

        for (DroneGeofence geofence :
                geofenceRepository
                        .findAllByActiveTrueOrderByCreatedAtDesc()) {

            BigDecimal distanceMeters =
                    calculateDistanceMeters(drone, geofence);

            boolean violation = isViolation(
                    geofence,
                    distanceMeters
            );

            Optional<DroneGeofenceEvent> activeEvent =
                    eventRepository
                            .findFirstByDroneIdAndGeofenceIdAndResolvedAtIsNullOrderByDetectedAtDesc(
                                    drone.getId(),
                                    geofence.getId()
                            );

            if (violation && activeEvent.isEmpty()) {
                DroneGeofenceEvent event =
                        DroneGeofenceEvent.start(
                                drone,
                                geofence,
                                distanceMeters,
                                detectedAt
                        );

                event = eventRepository.saveAndFlush(event);
                incidentService.createFromGeofenceEvent(event);
                realtimePublisher.publish(
                        GeofenceEventResponse.from(event)
                );
                continue;
            }

            if (violation) {
                activeEvent.ifPresent(event ->
                        event.applyTelemetry(
                                drone,
                                distanceMeters
                        )
                );
                continue;
            }

            if (activeEvent.isPresent()) {
                DroneGeofenceEvent event = activeEvent.get();

                event.resolve(
                        drone,
                        distanceMeters,
                        detectedAt
                );

                eventRepository.flush();
                incidentService.synchronizeGeofenceResolved(
                        event,
                        "드론이 지오펜스 정상 영역으로 복귀"
                );
                realtimePublisher.publish(
                        GeofenceEventResponse.from(event)
                );
            }
        }
    }

    private boolean isViolation(
            DroneGeofence geofence,
            BigDecimal distanceMeters
    ) {
        int compared = distanceMeters.compareTo(
                geofence.getRadiusMeters()
        );

        return switch (geofence.getRuleType()) {
            case KEEP_OUT -> compared <= 0;
            case KEEP_IN -> compared > 0;
        };
    }

    private BigDecimal calculateDistanceMeters(
            Drone drone,
            DroneGeofence geofence
    ) {
        double latitude1 =
                Math.toRadians(drone.getLatitude().doubleValue());
        double latitude2 =
                Math.toRadians(
                        geofence.getCenterLatitude().doubleValue()
                );

        double latitudeDelta =
                latitude2 - latitude1;

        double longitudeDelta = Math.toRadians(
                geofence.getCenterLongitude().doubleValue()
                        - drone.getLongitude().doubleValue()
        );

        double haversine =
                Math.pow(Math.sin(latitudeDelta / 2.0), 2.0)
                        + Math.cos(latitude1)
                        * Math.cos(latitude2)
                        * Math.pow(
                        Math.sin(longitudeDelta / 2.0),
                        2.0
                );

        double angularDistance = 2.0 * Math.atan2(
                Math.sqrt(haversine),
                Math.sqrt(1.0 - haversine)
        );

        return BigDecimal
                .valueOf(EARTH_RADIUS_METERS * angularDistance)
                .setScale(2, RoundingMode.HALF_UP);
    }
}
