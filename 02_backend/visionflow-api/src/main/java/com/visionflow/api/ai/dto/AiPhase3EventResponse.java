package com.visionflow.api.ai.dto;

import com.visionflow.api.ai.domain.AiPhase3Event;
import com.visionflow.api.ai.domain.VideoSourceType;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;

public record AiPhase3EventResponse(
        Long id,
        String eventKey,
        String sourceId,
        String sessionId,
        VideoSourceType sourceType,
        Long droneId,
        Long trackId,
        Long frameIndex,
        Instant capturedAt,
        String ppeState,
        BigDecimal noHelmetRate,
        BigDecimal helmetRate,
        BigDecimal unknownRate,
        BigDecimal streakSeconds,
        BigDecimal estimatedDepthM,
        BigDecimal sceneQ33M,
        BigDecimal sceneQ66M,
        String depthBucket,
        BigDecimal enrichmentLatencyMs,
        Instant createdAt,
        Instant updatedAt
) {
    public static AiPhase3EventResponse from(AiPhase3Event event) {
        return new AiPhase3EventResponse(
                event.getId(),
                event.getEventKey(),
                event.getSourceId(),
                event.getSessionId(),
                event.getSourceType(),
                event.getDroneId(),
                event.getTrackId(),
                event.getFrameIndex(),
                toInstant(event.getCapturedAt()),
                event.getPpeState(),
                event.getNoHelmetRate(),
                event.getHelmetRate(),
                event.getUnknownRate(),
                event.getStreakSeconds(),
                event.getEstimatedDepthM(),
                event.getSceneQ33M(),
                event.getSceneQ66M(),
                event.getDepthBucket(),
                event.getEnrichmentLatencyMs(),
                toInstant(event.getCreatedAt()),
                toInstant(event.getUpdatedAt())
        );
    }

    private static Instant toInstant(LocalDateTime value) {
        return value == null
                ? null
                : value.toInstant(ZoneOffset.UTC);
    }
}