package com.visionflow.api.flight.quality.dto;

import com.visionflow.api.flight.quality.domain.FlightQualityIncidentSyncAction;

import java.time.Instant;
import java.util.List;

public record FlightQualityIncidentSyncResponse(
        Instant synchronizedAt,
        int limitPerDrone,
        int evaluatedDroneCount,
        int createdCount,
        int updatedCount,
        int deduplicatedCount,
        int reopenedCount,
        int resolvedCount,
        int skippedCount,
        List<FlightQualityIncidentSyncItemResponse> items
) {

    public static FlightQualityIncidentSyncResponse from(
            int limitPerDrone,
            List<FlightQualityIncidentSyncItemResponse> items
    ) {
        return new FlightQualityIncidentSyncResponse(
                Instant.now(),
                limitPerDrone,
                items.size(),
                count(items, FlightQualityIncidentSyncAction.CREATED),
                count(items, FlightQualityIncidentSyncAction.UPDATED),
                count(items, FlightQualityIncidentSyncAction.DEDUPLICATED),
                count(items, FlightQualityIncidentSyncAction.REOPENED),
                count(items, FlightQualityIncidentSyncAction.RESOLVED),
                count(items, FlightQualityIncidentSyncAction.SKIPPED_STABLE),
                List.copyOf(items)
        );
    }

    private static int count(
            List<FlightQualityIncidentSyncItemResponse> items,
            FlightQualityIncidentSyncAction action
    ) {
        return (int) items.stream()
                .filter(item -> item.action() == action)
                .count();
    }
}
