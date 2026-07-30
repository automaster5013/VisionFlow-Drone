package com.visionflow.api.ai.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record AiAlertAcknowledgeRequest(
        @NotBlank
        @Size(max = 100)
        String operator
) {
}
