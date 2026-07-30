package com.visionflow.api.incident.realtime;

import com.visionflow.api.incident.dto.IncidentResponse;

import java.time.LocalDateTime;
import java.time.ZoneOffset;

public record IncidentRealtimeMessage(
        IncidentRealtimeAction action,
        IncidentResponse incident,
        LocalDateTime publishedAt
) {
    public static IncidentRealtimeMessage of(
            IncidentRealtimeAction action,
            IncidentResponse incident
    ) {
        return new IncidentRealtimeMessage(
                action,
                incident,
                LocalDateTime.now(ZoneOffset.UTC)
        );
    }
}
