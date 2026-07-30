package com.visionflow.api.incident.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record IncidentAssignRequest(
        @NotBlank
        @Size(max = 100)
        String assignee,

        @NotBlank
        @Size(max = 100)
        String actor
) {
}
