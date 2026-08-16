package com.visionflow.api.ai.service;

import com.visionflow.api.ai.domain.AiPhase3Event;
import com.visionflow.api.ai.dto.AiPhase3DepthUpdateRequest;
import com.visionflow.api.ai.dto.AiPhase3EventCreateRequest;
import com.visionflow.api.ai.dto.AiPhase3EventResponse;
import com.visionflow.api.ai.repository.AiPhase3EventRepository;
import com.visionflow.api.common.exception.ResourceNotFoundException;
import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.flight.service.FlightSessionCorrelationGuard;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Locale;
import java.util.Set;

@Service
public class AiPhase3EventService {

    private static final Set<String> DEPTH_BUCKETS = Set.of(
            "NEAR",
            "MID",
            "FAR",
            "UNKNOWN"
    );

    private final AiPhase3EventRepository eventRepository;
    private final DroneRepository droneRepository;
    private final FlightSessionCorrelationGuard sessionCorrelationGuard;

    public AiPhase3EventService(
            AiPhase3EventRepository eventRepository,
            DroneRepository droneRepository,
            FlightSessionCorrelationGuard sessionCorrelationGuard
    ) {
        this.eventRepository = eventRepository;
        this.droneRepository = droneRepository;
        this.sessionCorrelationGuard = sessionCorrelationGuard;
    }

    @Transactional
    public AiPhase3EventResponse create(
            AiPhase3EventCreateRequest request
    ) {
        String sessionId =
                sessionCorrelationGuard.requireOwnedSessionForUpdate(
                        request.sessionId(),
                        request.droneId()
                );

        return eventRepository.findByEventKey(request.eventKey().trim())
                .map(AiPhase3EventResponse::from)
                .orElseGet(() -> createNew(request, sessionId));
    }

    @Transactional
    public AiPhase3EventResponse enrichDepth(
            String eventKey,
            AiPhase3DepthUpdateRequest request
    ) {
        String safeEventKey = eventKey.trim();

        AiPhase3Event event = eventRepository
                .findByEventKeyForUpdate(safeEventKey)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Phase 3 AI event not found: " + safeEventKey
                ));

        String depthBucket = request.depthBucket()
                .trim()
                .toUpperCase(Locale.ROOT);

        if (!DEPTH_BUCKETS.contains(depthBucket)) {
            throw new IllegalArgumentException(
                    "Unsupported Phase 3 depth bucket: " + depthBucket
            );
        }

        event.enrichDepth(
                request.estimatedDepthM(),
                request.sceneQ33M(),
                request.sceneQ66M(),
                depthBucket,
                request.enrichmentLatencyMs()
        );

        event = eventRepository.saveAndFlush(event);
        return AiPhase3EventResponse.from(event);
    }

    private AiPhase3EventResponse createNew(
            AiPhase3EventCreateRequest request,
            String sessionId
    ) {
        if (!droneRepository.existsById(request.droneId())) {
            throw new ResourceNotFoundException(
                    "Drone not found: " + request.droneId()
            );
        }

        AiPhase3Event event = AiPhase3Event.create(
                request.eventKey().trim(),
                request.sourceId().trim(),
                sessionId,
                request.sourceType(),
                request.droneId(),
                request.trackId(),
                request.frameIndex(),
                request.capturedAt(),
                request.ppeState().trim(),
                request.noHelmetRate(),
                request.helmetRate(),
                request.unknownRate(),
                request.streakSeconds()
        );

        event = eventRepository.saveAndFlush(event);
        return AiPhase3EventResponse.from(event);
    }
}