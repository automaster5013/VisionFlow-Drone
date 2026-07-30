package com.visionflow.api.dashboard.dto;

import java.time.Instant;
import java.util.List;

public record OperationsDashboardResponse(
        Instant generatedAt,
        DashboardFilters filters,
        FlightSessionStatistics flightSessions,
        AiInferenceStatistics aiInference,
        FlightGateStatistics flightGate,
        List<FlightSessionItem> recentSessions,
        List<FlightSessionItem> recentAbortedSessions,
        List<AiAlertItem> recentAiAlerts,
        List<FlightGateDecisionItem> recentFlightGateDecisions
) {

    public record DashboardFilters(
            Long droneId,
            String status,
            Instant from,
            Instant to,
            int limit
    ) {
    }

    public record FlightSessionStatistics(
            long total,
            long ready,
            long active,
            long completed,
            long aborted
    ) {
    }

    public record AiInferenceStatistics(
            long totalEvents,
            long detectedEvents,
            long totalDetections
    ) {
    }

    public record FlightGateStatistics(
            long total,
            long allowed,
            long advisory,
            long blocked
    ) {
    }

    public record FlightSessionItem(
            String sessionId,
            Long droneId,
            String name,
            String description,
            String status,
            String sourceDeviceId,
            Instant startedAt,
            Instant endedAt,
            long durationSeconds
    ) {
    }

    public record AiAlertItem(
            Long eventId,
            Long droneId,
            String sessionId,
            String sourceId,
            String sourceType,
            Long frameIndex,
            Instant capturedAt,
            int detectionCount,
            boolean snapshotAvailable
    ) {
    }

    public record FlightGateDecisionItem(
            Long auditId,
            Long droneId,
            String action,
            String summary,
            Instant occurredAt
    ) {
    }
}
