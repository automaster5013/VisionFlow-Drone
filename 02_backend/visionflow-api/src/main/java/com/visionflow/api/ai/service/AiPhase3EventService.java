package com.visionflow.api.ai.service;

import com.visionflow.api.ai.domain.AiPhase3Event;
import com.visionflow.api.ai.dto.AiPhase3DepthUpdateRequest;
import com.visionflow.api.ai.dto.AiPhase3EventCreateRequest;
import com.visionflow.api.ai.dto.AiPhase3EventResponse;
import com.visionflow.api.ai.repository.AiPhase3EventRepository;
import com.visionflow.api.common.exception.ResourceNotFoundException;
import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.flight.service.FlightSessionCorrelationGuard;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Locale;
import java.util.List;
import java.util.Set;

@Service
public class AiPhase3EventService {

    private static final Logger LOGGER =
            LoggerFactory.getLogger(AiPhase3EventService.class);

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
        String eventKey = request.eventKey().trim();
        String sessionId =
                sessionCorrelationGuard.requireOwnedSessionForUpdate(
                        request.sessionId(),
                        request.droneId()
                );

        return eventRepository.findByEventKey(eventKey)
                .map(event -> {
                    AiPhase3EventResponse response =
                            AiPhase3EventResponse.from(event);
                    logEventIngest("duplicate", response);
                    return response;
                })
                .orElseGet(() -> {
                    AiPhase3EventResponse response =
                            createNew(request, sessionId);
                    logEventIngest("created", response);
                    return response;
                });
    }

    @Transactional(readOnly = true)
    public List<AiPhase3EventResponse> findRecent(
            Long droneId,
            int limit
    ) {
        int safeLimit = Math.max(1, Math.min(limit, 200));
        PageRequest pageRequest = PageRequest.of(0, safeLimit);

        List<AiPhase3Event> events = droneId == null
                ? eventRepository.findAllByOrderByCapturedAtDesc(pageRequest)
                : eventRepository.findAllByDroneIdOrderByCapturedAtDesc(
                        droneId,
                        pageRequest
                );

        return events.stream()
                .map(AiPhase3EventResponse::from)
                .toList();
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

        AiPhase3EventResponse response =
                AiPhase3EventResponse.from(event);
        logDepthEnrichment(response);
        return response;
    }

    private static void logEventIngest(
            String outcome,
            AiPhase3EventResponse response
    ) {
        LOGGER.info(
                "VISIONFLOW_PHASE3_EVENT_INGEST "
                        + "outcome={} eventKey=\"{}\" eventId={} "
                        + "droneId={} sessionId=\"{}\" sourceId=\"{}\" "
                        + "trackId={} frameIndex={} ppeState=\"{}\"",
                outcome,
                safeLogValue(response.eventKey()),
                response.id(),
                response.droneId(),
                safeLogValue(response.sessionId()),
                safeLogValue(response.sourceId()),
                response.trackId(),
                response.frameIndex(),
                safeLogValue(response.ppeState())
        );
    }

    private static void logDepthEnrichment(
            AiPhase3EventResponse response
    ) {
        LOGGER.info(
                "VISIONFLOW_PHASE3_DEPTH_ENRICH "
                        + "outcome=updated eventKey=\"{}\" eventId={} "
                        + "droneId={} sessionId=\"{}\" depthBucket=\"{}\" "
                        + "estimatedDepthM={} enrichmentLatencyMs={}",
                safeLogValue(response.eventKey()),
                response.id(),
                response.droneId(),
                safeLogValue(response.sessionId()),
                safeLogValue(response.depthBucket()),
                response.estimatedDepthM(),
                response.enrichmentLatencyMs()
        );
    }

    private static String safeLogValue(String value) {
        if (value == null) {
            return "";
        }

        return value
                .replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\r", "\\r")
                .replace("\n", "\\n")
                .replace("\t", "\\t");
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