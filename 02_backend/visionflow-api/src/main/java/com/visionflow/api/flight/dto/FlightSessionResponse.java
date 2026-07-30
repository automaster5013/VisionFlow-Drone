package com.visionflow.api.flight.dto;

import com.visionflow.api.flight.domain.FlightSession;
import com.visionflow.api.flight.domain.FlightSessionStatus;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

public record FlightSessionResponse(
        String sessionId,
        Long droneId,
        String name,
        String description,
        FlightSessionStatus status,
        String sourceDeviceId,
        Instant startedAt,
        Instant endedAt,
        long durationSeconds,
        Instant createdAt,
        Instant updatedAt
) {

    public static FlightSessionResponse from(FlightSession session) {
        ZoneId zoneId = ZoneId.systemDefault();
        LocalDateTime effectiveEnd = session.getEndedAt() != null
                ? session.getEndedAt()
                : LocalDateTime.now();
        long durationSeconds = Math.max(
                0,
                Duration.between(
                        session.getStartedAt(),
                        effectiveEnd
                ).getSeconds()
        );

        return new FlightSessionResponse(
                session.getSessionId(),
                session.getDroneId(),
                session.getName(),
                session.getDescription(),
                session.getStatus(),
                session.getSourceDeviceId(),
                toInstant(session.getStartedAt(), zoneId),
                toInstant(session.getEndedAt(), zoneId),
                durationSeconds,
                toInstant(session.getCreatedAt(), zoneId),
                toInstant(session.getUpdatedAt(), zoneId)
        );
    }

    private static Instant toInstant(
            LocalDateTime value,
            ZoneId zoneId
    ) {
        return value == null
                ? null
                : value.atZone(zoneId).toInstant();
    }
}
