package com.visionflow.api.ai.dto;

import com.visionflow.api.ai.domain.VideoSourceType;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;
import java.time.Instant;

public record AiPhase3EventCreateRequest(
        @NotBlank
        @Size(max = 200)
        String eventKey,

        @NotBlank
        @Size(max = 100)
        String sourceId,

        @NotBlank
        @Size(max = 36)
        String sessionId,

        @NotNull
        VideoSourceType sourceType,

        @NotNull
        @Positive
        Long droneId,

        @NotNull
        @Positive
        Long trackId,

        @NotNull
        @PositiveOrZero
        Long frameIndex,

        @NotNull
        Instant capturedAt,

        @NotBlank
        @Size(max = 40)
        String ppeState,

        @NotNull
        @DecimalMin("0.0")
        @DecimalMax("1.0")
        BigDecimal noHelmetRate,

        @NotNull
        @DecimalMin("0.0")
        @DecimalMax("1.0")
        BigDecimal helmetRate,

        @NotNull
        @DecimalMin("0.0")
        @DecimalMax("1.0")
        BigDecimal unknownRate,

        @NotNull
        @DecimalMin("0.0")
        BigDecimal streakSeconds
) {
}