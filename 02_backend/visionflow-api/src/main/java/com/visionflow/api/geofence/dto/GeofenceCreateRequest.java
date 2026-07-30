package com.visionflow.api.geofence.dto;

import com.visionflow.api.geofence.domain.GeofenceRule;
import jakarta.validation.constraints.*;

import java.math.BigDecimal;

public record GeofenceCreateRequest(
        @NotBlank
        @Size(max = 100)
        String name,

        @NotNull
        GeofenceRule ruleType,

        @NotNull
        @DecimalMin("-90.0")
        @DecimalMax("90.0")
        BigDecimal centerLatitude,

        @NotNull
        @DecimalMin("-180.0")
        @DecimalMax("180.0")
        BigDecimal centerLongitude,

        @NotNull
        @DecimalMin("1.0")
        @DecimalMax("50000.0")
        BigDecimal radiusMeters,

        Boolean active
) {
}