package com.visionflow.api.ai.realtime;

import com.visionflow.api.ai.dto.AiAlertResponse;

import java.time.Instant;

public record AiAlertRealtimeMessage(
        AiAlertRealtimeAction action,
        Instant occurredAt,
        AiAlertResponse alert
) {
    public static AiAlertRealtimeMessage of(
            AiAlertRealtimeAction action,
            AiAlertResponse alert
    ) {
        return new AiAlertRealtimeMessage(
                action,
                Instant.now(),
                alert
        );
    }
}
