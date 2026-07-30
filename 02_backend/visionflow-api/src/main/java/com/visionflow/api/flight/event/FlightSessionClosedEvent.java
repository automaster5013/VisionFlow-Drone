package com.visionflow.api.flight.event;

import com.visionflow.api.flight.domain.FlightSessionStatus;

public record FlightSessionClosedEvent(
        Long droneId,
        String sessionId,
        FlightSessionStatus status
) {
}
