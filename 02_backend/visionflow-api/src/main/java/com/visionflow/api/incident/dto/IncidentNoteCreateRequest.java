package com.visionflow.api.incident.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record IncidentNoteCreateRequest(
        @NotBlank
        @Size(max = 100)
        String actor,

        @NotBlank
        @Size(max = 1000)
        String note
) {
}
