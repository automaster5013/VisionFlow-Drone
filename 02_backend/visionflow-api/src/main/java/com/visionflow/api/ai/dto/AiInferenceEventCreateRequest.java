package com.visionflow.api.ai.dto;

import com.visionflow.api.ai.domain.VideoSourceType;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record AiInferenceEventCreateRequest(
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
        @PositiveOrZero
        Long frameIndex,

        @NotNull
        Instant capturedAt,

        @NotNull
        @PositiveOrZero
        BigDecimal inferenceMs,

        @NotNull
        @PositiveOrZero
        Integer detectionCount,

        @NotNull
        @Size(max = 500)
        List<@Valid AiDetectionRequest> detections
) {
    @AssertTrue(
            message = "detectionCount는 detections 배열 크기와 일치해야 합니다."
    )
    public boolean isDetectionCountConsistent() {
        return detectionCount == null
                || detections == null
                || detectionCount == detections.size();
    }
}
