package com.visionflow.api.ai.dto;

import com.visionflow.api.ai.domain.AiDetection;
import com.visionflow.api.ai.domain.AiInferenceEvent;
import com.visionflow.api.ai.domain.VideoSourceType;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;

public record AiInferenceEventResponse(
        Long id,
        String sourceId,
        String sessionId,
        VideoSourceType sourceType,
        Long droneId,
        Long frameIndex,
        Instant capturedAt,
        Instant receivedAt,
        BigDecimal inferenceMs,
        Integer detectionCount,
        Boolean snapshotAvailable,
        String snapshotUrl,
        Long snapshotSizeBytes,
        Instant snapshotCreatedAt,
        List<AiDetectionResponse> detections
) {
    public static AiInferenceEventResponse from(
            AiInferenceEvent event,
            List<AiDetection> detections
    ) {
        return new AiInferenceEventResponse(
                event.getId(),
                event.getSourceId(),
                event.getSessionId(),
                event.getSourceType(),
                event.getDroneId(),
                event.getFrameIndex(),
                event.getCapturedAt().toInstant(ZoneOffset.UTC),
                event.getReceivedAt().toInstant(ZoneOffset.UTC),
                event.getInferenceMs(),
                event.getDetectionCount(),
                event.getSnapshotFileName() != null,
                event.getSnapshotFileName() == null
                        ? null
                        : "/api/ai/events/" + event.getId() + "/snapshot",
                event.getSnapshotSizeBytes(),
                event.getSnapshotCreatedAt() == null
                        ? null
                        : event.getSnapshotCreatedAt().toInstant(ZoneOffset.UTC),
                detections.stream()
                        .map(AiDetectionResponse::from)
                        .toList()
        );
    }
}
