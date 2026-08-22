package com.visionflow.api.ai.service;

import com.visionflow.api.ai.domain.AiDetection;
import com.visionflow.api.ai.domain.AiInferenceEvent;
import com.visionflow.api.ai.domain.VideoSourceType;
import com.visionflow.api.ai.dto.AiDetectionRequest;
import com.visionflow.api.ai.dto.AiInferenceEventCreateRequest;
import com.visionflow.api.ai.dto.AiInferenceEventResponse;
import com.visionflow.api.ai.realtime.AiRealtimePublisher;
import com.visionflow.api.ai.repository.AiDetectionRepository;
import com.visionflow.api.ai.repository.AiInferenceEventRepository;
import com.visionflow.api.common.exception.ResourceNotFoundException;
import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.flight.service.FlightSessionCorrelationGuard;
import org.springframework.core.io.Resource;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;

@Service
public class AiInferenceEventService {

    private final AiInferenceEventRepository eventRepository;
    private final AiDetectionRepository detectionRepository;
    private final DroneRepository droneRepository;
    private final FlightSessionCorrelationGuard sessionCorrelationGuard;
    private final AiRealtimePublisher realtimePublisher;
    private final AiSnapshotStorageService snapshotStorageService;
    private final AiAlertService alertService;

    public AiInferenceEventService(
            AiInferenceEventRepository eventRepository,
            AiDetectionRepository detectionRepository,
            DroneRepository droneRepository,
            FlightSessionCorrelationGuard sessionCorrelationGuard,
            AiRealtimePublisher realtimePublisher,
            AiSnapshotStorageService snapshotStorageService,
            AiAlertService alertService
    ) {
        this.eventRepository = eventRepository;
        this.detectionRepository = detectionRepository;
        this.droneRepository = droneRepository;
        this.sessionCorrelationGuard = sessionCorrelationGuard;
        this.realtimePublisher = realtimePublisher;
        this.snapshotStorageService = snapshotStorageService;
        this.alertService = alertService;
    }

    @Transactional
    public AiInferenceEventResponse create(
            AiInferenceEventCreateRequest request
    ) {
        String sessionId =
                sessionCorrelationGuard.requireOwnedSessionForUpdate(
                        request.sessionId(),
                        request.droneId()
                );

        return eventRepository
                .findBySourceIdAndSessionIdAndFrameIndex(
                        request.sourceId(),
                        sessionId,
                        request.frameIndex()
                )
                .map(this::toResponse)
                .orElseGet(() -> createNew(request, sessionId));
    }

    @Transactional(readOnly = true)
    public List<AiInferenceEventResponse> findRecent(
            Long droneId,
            int limit
    ) {
        int safeLimit = Math.max(1, Math.min(limit, 200));
        PageRequest pageRequest = PageRequest.of(0, safeLimit);

        List<AiInferenceEvent> events = droneId == null
                ? eventRepository.findAllByOrderByCapturedAtDesc(
                        pageRequest
                )
                : eventRepository.findAllByDroneIdOrderByCapturedAtDesc(
                        droneId,
                        pageRequest
                );

        return events.stream()
                .map(this::toResponse)
                .toList();
    }

    @Transactional
    public AiInferenceEventResponse attachSnapshot(
            Long eventId,
            MultipartFile file
    ) {
        AiInferenceEvent event = findEventForUpdate(eventId);
        AiSnapshotStorageService.StoredSnapshot stored =
                snapshotStorageService.store(eventId, file);

        event.attachSnapshot(
                stored.fileName(),
                stored.contentType(),
                stored.sizeBytes()
        );

        event = eventRepository.saveAndFlush(event);

        AiInferenceEventResponse response = toResponse(event);
        realtimePublisher.publish(response);
        return response;
    }

    @Transactional(readOnly = true)
    public AiSnapshotDownload findSnapshot(Long eventId) {
        AiInferenceEvent event = findEvent(eventId);

        if (event.getSnapshotFileName() == null) {
            throw new ResourceNotFoundException(
                    "AI 이벤트 스냅샷을 찾을 수 없습니다: " + eventId
            );
        }

        Resource resource = snapshotStorageService.load(
                event.getSnapshotFileName()
        );

        return new AiSnapshotDownload(
                event.getSnapshotFileName(),
                event.getSnapshotContentType(),
                event.getSnapshotSizeBytes(),
                resource
        );
    }

    @Transactional
    public SnapshotDeletionResult deleteSnapshot(Long eventId) {
        AiInferenceEvent event = findEventForUpdate(eventId);
        String fileName = event.getSnapshotFileName();

        if (fileName == null) {
            return new SnapshotDeletionResult(
                    event.getId(),
                    event.getDroneId(),
                    event.getFrameIndex(),
                    event.getSourceType(),
                    false,
                    false,
                    0L
            );
        }

        long snapshotSizeBytes = event.getSnapshotSizeBytes() == null
                ? 0L
                : event.getSnapshotSizeBytes();
        boolean physicalFileDeleted = snapshotStorageService.delete(fileName);

        event.clearSnapshot();
        event = eventRepository.saveAndFlush(event);

        AiInferenceEventResponse response = toResponse(event);
        realtimePublisher.publish(response);

        return new SnapshotDeletionResult(
                event.getId(),
                event.getDroneId(),
                event.getFrameIndex(),
                event.getSourceType(),
                true,
                physicalFileDeleted,
                snapshotSizeBytes
        );
    }

    private AiInferenceEvent findEvent(Long eventId) {
        return eventRepository.findById(eventId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "AI 추론 이벤트를 찾을 수 없습니다: " + eventId
                ));
    }

    private AiInferenceEvent findEventForUpdate(Long eventId) {
        return eventRepository.findByIdForUpdate(eventId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "AI 추론 이벤트를 찾을 수 없습니다: " + eventId
                ));
    }

    private AiInferenceEventResponse createNew(
            AiInferenceEventCreateRequest request,
            String sessionId
    ) {
        if (!droneRepository.existsById(request.droneId())) {
            throw new ResourceNotFoundException(
                    "드론을 찾을 수 없습니다: " + request.droneId()
            );
        }

        AiInferenceEvent event = AiInferenceEvent.create(
                request.sourceId().trim(),
                sessionId,
                request.sourceType(),
                request.droneId(),
                request.frameIndex(),
                request.capturedAt(),
                request.inferenceMs(),
                request.detections().size()
        );

        event = eventRepository.saveAndFlush(event);

        Long eventId = event.getId();

        List<AiDetection> detections = request.detections()
                .stream()
                .map(detection -> toEntity(eventId, detection))
                .toList();

        if (!detections.isEmpty()) {
            detections = detectionRepository.saveAllAndFlush(
                    detections
            );

            alertService.createForEvent(event, detections);
        }

        AiInferenceEventResponse response =
                AiInferenceEventResponse.from(event, detections);

        realtimePublisher.publish(response);
        return response;
    }

    private AiDetection toEntity(
            Long eventId,
            AiDetectionRequest request
    ) {
        return AiDetection.create(
                eventId,
                request.classId(),
                request.className().trim(),
                request.confidence(),
                request.x1(),
                request.y1(),
                request.x2(),
                request.y2()
        );
    }

    private AiInferenceEventResponse toResponse(
            AiInferenceEvent event
    ) {
        List<AiDetection> detections =
                detectionRepository.findAllByEventIdOrderByIdAsc(
                        event.getId()
                );

        return AiInferenceEventResponse.from(event, detections);
    }

    public record AiSnapshotDownload(
            String fileName,
            String contentType,
            long sizeBytes,
            Resource resource
    ) {
    }

    public record SnapshotDeletionResult(
            Long eventId,
            Long droneId,
            Long frameIndex,
            VideoSourceType sourceType,
            boolean snapshotExisted,
            boolean physicalFileDeleted,
            long snapshotSizeBytes
    ) {
    }
}
