package com.visionflow.api.ai.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record AiAlertResolveRequest(
        @NotBlank
        @Size(max = 100)
        String operator,

        @Size(max = 500)
        String note
) {
}
