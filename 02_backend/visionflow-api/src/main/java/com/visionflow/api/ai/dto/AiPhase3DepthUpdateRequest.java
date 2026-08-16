package com.visionflow.api.ai.dto;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;

public record AiPhase3DepthUpdateRequest(
        @NotNull
        @DecimalMin("0.0")
        BigDecimal estimatedDepthM,

        @NotNull
        @DecimalMin("0.0")
        BigDecimal sceneQ33M,

        @NotNull
        @DecimalMin("0.0")
        BigDecimal sceneQ66M,

        @NotBlank
        @Size(max = 20)
        String depthBucket,

        @NotNull
        @DecimalMin("0.0")
        BigDecimal enrichmentLatencyMs
) {
}