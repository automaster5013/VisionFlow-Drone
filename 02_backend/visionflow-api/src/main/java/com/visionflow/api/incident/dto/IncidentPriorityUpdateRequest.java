package com.visionflow.api.incident.dto;

import com.visionflow.api.incident.domain.IncidentPriority;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record IncidentPriorityUpdateRequest(
        @NotNull
        IncidentPriority priority,

        @NotBlank
        @Size(max = 100)
        String actor,

        @Size(max = 1000)
        String note
) {
}
