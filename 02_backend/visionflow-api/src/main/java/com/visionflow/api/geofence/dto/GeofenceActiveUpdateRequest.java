package com.visionflow.api.geofence.dto;

import jakarta.validation.constraints.NotNull;

public record GeofenceActiveUpdateRequest(
        @NotNull Boolean active
) {
}