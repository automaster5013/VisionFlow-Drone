package com.visionflow.api.incident.service;

import com.visionflow.api.ai.domain.AiAlert;
import com.visionflow.api.ai.domain.AiInferenceEvent;
import com.visionflow.api.ai.repository.AiAlertRepository;
import com.visionflow.api.ai.repository.AiInferenceEventRepository;
import com.visionflow.api.drone.domain.DroneTelemetryHistory;
import com.visionflow.api.drone.repository.DroneTelemetryHistoryRepository;
import com.visionflow.api.geofence.domain.DroneGeofenceEvent;
import com.visionflow.api.geofence.repository.DroneGeofenceEventRepository;
import com.visionflow.api.flight.quality.domain.FlightQualityAssessment;
import com.visionflow.api.flight.quality.repository.FlightQualityAssessmentRepository;
import com.visionflow.api.incident.domain.Incident;
import com.visionflow.api.incident.domain.IncidentLocationSource;
import com.visionflow.api.incident.dto.IncidentContextResponse;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Optional;

@Service
public class IncidentContextService {

    private final AiAlertRepository alertRepository;
    private final AiInferenceEventRepository inferenceEventRepository;
    private final DroneGeofenceEventRepository geofenceEventRepository;
    private final DroneTelemetryHistoryRepository telemetryRepository;
    private final FlightQualityAssessmentRepository qualityRepository;

    public IncidentContextService(
            AiAlertRepository alertRepository,
            AiInferenceEventRepository inferenceEventRepository,
            DroneGeofenceEventRepository geofenceEventRepository,
            DroneTelemetryHistoryRepository telemetryRepository,
            FlightQualityAssessmentRepository qualityRepository
    ) {
        this.alertRepository = alertRepository;
        this.inferenceEventRepository = inferenceEventRepository;
        this.geofenceEventRepository = geofenceEventRepository;
        this.telemetryRepository = telemetryRepository;
        this.qualityRepository = qualityRepository;
    }

    @Transactional(readOnly = true)
    public IncidentContextResponse build(Incident incident) {
        return switch (incident.getSourceType()) {
            case AI_ALERT -> buildAiContext(incident);
            case GEOFENCE -> buildGeofenceContext(incident);
            case FLIGHT_QUALITY -> buildFlightQualityContext(incident);
            case FLIGHT_GATE -> emptyContext(
                    incident,
                    toInstant(incident.getOccurredAt(), ZoneOffset.UTC)
            );
        };
    }

    private IncidentContextResponse buildFlightQualityContext(
            Incident incident
    ) {
        String sessionId = normalizeSessionId(incident.getSessionId());
        Optional<FlightQualityAssessment> assessment =
                sessionId == null
                        ? Optional.empty()
                        : qualityRepository
                                .findFirstByDroneIdAndSessionIdOrderByEvaluatedAtDesc(
                                        incident.getDroneId(),
                                        sessionId
                                );
        LocalDateTime target = assessment
                .map(FlightQualityAssessment::getEvaluatedAt)
                .orElse(incident.getOccurredAt());
        Optional<DroneTelemetryHistory> nearestTelemetry =
                findNearestTelemetry(
                        incident.getDroneId(),
                        sessionId,
                        target
                );
        DroneTelemetryHistory telemetry = nearestTelemetry.orElse(null);
        boolean hasLocation = telemetry != null
                && telemetry.getLatitude() != null
                && telemetry.getLongitude() != null;
        Instant occurredAt = toInstant(target, ZoneOffset.UTC);

        return new IncidentContextResponse(
                incident.getId(),
                incident.getDroneId(),
                sessionId,
                occurredAt,
                nearestTelemetry.isPresent(),
                hasLocation
                        ? IncidentLocationSource.NEAREST_TELEMETRY
                        : IncidentLocationSource.UNAVAILABLE,
                hasLocation ? telemetry.getLatitude() : null,
                hasLocation ? telemetry.getLongitude() : null,
                hasLocation ? telemetry.getAltitude() : null,
                hasLocation
                        ? toInstant(
                                telemetry.getRecordedAt(),
                                ZoneId.systemDefault()
                        )
                        : null,
                null,
                false,
                null
        );
    }

    private IncidentContextResponse buildAiContext(Incident incident) {
        Optional<AiAlert> alert = alertRepository.findById(
                incident.getSourceId()
        );

        if (alert.isEmpty()) {
            return emptyContext(
                    incident,
                    toInstant(incident.getOccurredAt(), ZoneOffset.UTC)
            );
        }

        Optional<AiInferenceEvent> inferenceEvent =
                inferenceEventRepository.findById(
                        alert.get().getEventId()
                );

        if (inferenceEvent.isEmpty()) {
            return emptyContext(
                    incident,
                    toInstant(alert.get().getCapturedAt(), ZoneOffset.UTC)
            );
        }

        AiInferenceEvent event = inferenceEvent.get();
        String sessionId = normalizeSessionId(event.getSessionId());
        Instant occurredAt = toInstant(
                event.getCapturedAt(),
                ZoneOffset.UTC
        );
        LocalDateTime telemetryTarget = LocalDateTime.ofInstant(
                occurredAt,
                ZoneId.systemDefault()
        );
        Optional<DroneTelemetryHistory> nearestTelemetry =
                findNearestTelemetry(
                        incident.getDroneId(),
                        sessionId,
                        telemetryTarget
                );

        DroneTelemetryHistory telemetry = nearestTelemetry.orElse(null);
        boolean hasLocation = telemetry != null
                && telemetry.getLatitude() != null
                && telemetry.getLongitude() != null;
        boolean snapshotAvailable = event.getSnapshotFileName() != null;

        return new IncidentContextResponse(
                incident.getId(),
                incident.getDroneId(),
                sessionId,
                occurredAt,
                nearestTelemetry.isPresent(),
                hasLocation
                        ? IncidentLocationSource.NEAREST_TELEMETRY
                        : IncidentLocationSource.UNAVAILABLE,
                hasLocation ? telemetry.getLatitude() : null,
                hasLocation ? telemetry.getLongitude() : null,
                hasLocation ? telemetry.getAltitude() : null,
                hasLocation
                        ? toInstant(
                                telemetry.getRecordedAt(),
                                ZoneId.systemDefault()
                        )
                        : null,
                event.getId(),
                snapshotAvailable,
                snapshotAvailable
                        ? "/api/ai/events/"
                                + event.getId()
                                + "/snapshot"
                        : null
        );
    }

    private IncidentContextResponse buildGeofenceContext(
            Incident incident
    ) {
        Optional<DroneGeofenceEvent> sourceEvent =
                geofenceEventRepository.findById(incident.getSourceId());

        if (sourceEvent.isEmpty()) {
            return emptyContext(
                    incident,
                    toInstant(
                            incident.getOccurredAt(),
                            ZoneId.systemDefault()
                    )
            );
        }

        DroneGeofenceEvent event = sourceEvent.get();
        String sessionId = normalizeSessionId(
                event.getFlightSessionId()
        );
        Instant occurredAt = toInstant(
                event.getDetectedAt(),
                ZoneId.systemDefault()
        );
        boolean hasLocation = event.getDetectedLatitude() != null
                && event.getDetectedLongitude() != null;
        boolean replayAvailable = findNearestTelemetry(
                incident.getDroneId(),
                sessionId,
                event.getDetectedAt()
        ).isPresent();

        return new IncidentContextResponse(
                incident.getId(),
                incident.getDroneId(),
                sessionId,
                occurredAt,
                replayAvailable,
                hasLocation
                        ? IncidentLocationSource.GEOFENCE_EVENT
                        : IncidentLocationSource.UNAVAILABLE,
                hasLocation ? event.getDetectedLatitude() : null,
                hasLocation ? event.getDetectedLongitude() : null,
                hasLocation ? event.getDetectedAltitude() : null,
                hasLocation ? occurredAt : null,
                null,
                false,
                null
        );
    }

    private Optional<DroneTelemetryHistory> findNearestTelemetry(
            Long droneId,
            String sessionId,
            LocalDateTime target
    ) {
        if (sessionId == null) {
            return Optional.empty();
        }

        Optional<DroneTelemetryHistory> before = telemetryRepository
                .findFirstByDroneIdAndFlightSessionIdAndRecordedAtLessThanEqualOrderByRecordedAtDesc(
                        droneId,
                        sessionId,
                        target
                );
        Optional<DroneTelemetryHistory> after = telemetryRepository
                .findFirstByDroneIdAndFlightSessionIdAndRecordedAtGreaterThanEqualOrderByRecordedAtAsc(
                        droneId,
                        sessionId,
                        target
                );

        if (before.isEmpty()) {
            return after;
        }
        if (after.isEmpty()) {
            return before;
        }

        Duration beforeDistance = Duration.between(
                before.get().getRecordedAt(),
                target
        ).abs();
        Duration afterDistance = Duration.between(
                target,
                after.get().getRecordedAt()
        ).abs();

        return beforeDistance.compareTo(afterDistance) <= 0
                ? before
                : after;
    }

    private IncidentContextResponse emptyContext(
            Incident incident,
            Instant occurredAt
    ) {
        String sessionId = normalizeSessionId(incident.getSessionId());

        return new IncidentContextResponse(
                incident.getId(),
                incident.getDroneId(),
                sessionId,
                occurredAt,
                false,
                IncidentLocationSource.UNAVAILABLE,
                null,
                null,
                null,
                null,
                null,
                false,
                null
        );
    }

    private String normalizeSessionId(String sessionId) {
        if (sessionId == null) {
            return null;
        }

        String normalized = sessionId.trim();
        return normalized.isEmpty() ? null : normalized;
    }

    private Instant toInstant(LocalDateTime value, ZoneId zoneId) {
        return value.atZone(zoneId).toInstant();
    }
}
