package com.visionflow.api.flight.quality.domain;

public enum FlightQualityIncidentSyncAction {
    CREATED,
    UPDATED,
    DEDUPLICATED,
    REOPENED,
    RESOLVED,
    SKIPPED_STABLE
}
