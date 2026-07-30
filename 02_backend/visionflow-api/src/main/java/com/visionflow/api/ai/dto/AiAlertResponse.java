package com.visionflow.api.ai.dto;

import com.visionflow.api.ai.domain.AiAlert;
import com.visionflow.api.ai.domain.AiAlertSeverity;
import com.visionflow.api.ai.domain.AiAlertStatus;
import com.visionflow.api.ai.domain.AiInferenceEvent;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;

public record AiAlertResponse(
        Long id,
        Long eventId,
        Long droneId,
        String sessionId,
        AiAlertSeverity severity,
        AiAlertStatus status,
        String title,
        String summary,
        String primaryClassName,
        BigDecimal maxConfidence,
        Integer detectionCount,
        Instant capturedAt,
        Boolean snapshotAvailable,
        String snapshotUrl,
        Instant acknowledgedAt,
        String acknowledgedBy,
        Instant resolvedAt,
        String resolvedBy,
        String resolutionNote,
        Instant createdAt,
        Instant updatedAt
) {
    public static AiAlertResponse from(
            AiAlert alert,
            AiInferenceEvent event
    ) {
        boolean snapshotAvailable = event.getSnapshotFileName() != null;

        return new AiAlertResponse(
                alert.getId(),
                alert.getEventId(),
                alert.getDroneId(),
                alert.getSessionId(),
                alert.getSeverity(),
                alert.getStatus(),
                alert.getTitle(),
                alert.getSummary(),
                alert.getPrimaryClassName(),
                alert.getMaxConfidence(),
                alert.getDetectionCount(),
                toInstant(alert.getCapturedAt()),
                snapshotAvailable,
                snapshotAvailable
                        ? "/api/ai/events/" + alert.getEventId() + "/snapshot"
                        : null,
                toInstant(alert.getAcknowledgedAt()),
                alert.getAcknowledgedBy(),
                toInstant(alert.getResolvedAt()),
                alert.getResolvedBy(),
                alert.getResolutionNote(),
                toInstant(alert.getCreatedAt()),
                toInstant(alert.getUpdatedAt())
        );
    }

    private static Instant toInstant(LocalDateTime value) {
        return value == null
                ? null
                : value.toInstant(ZoneOffset.UTC);
    }
}
