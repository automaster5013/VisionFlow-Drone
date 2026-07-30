package com.visionflow.api.flight.dto;

import com.visionflow.api.ai.dto.AiInferenceEventResponse;
import com.visionflow.api.drone.dto.DroneTelemetryHistoryResponse;

import java.time.Instant;
import java.util.List;

public record FlightSessionReplayResponse(
        String sessionId,
        Long droneId,
        Instant startedAt,
        Instant endedAt,
        long durationSeconds,
        int telemetryCount,
        int aiEventCount,
        int detectionCount,
        List<DroneTelemetryHistoryResponse> telemetry,
        List<AiInferenceEventResponse> aiEvents
) {
}
