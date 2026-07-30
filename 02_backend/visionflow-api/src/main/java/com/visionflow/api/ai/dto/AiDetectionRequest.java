package com.visionflow.api.ai.dto;

import jakarta.validation.constraints.*;

import java.math.BigDecimal;

public record AiDetectionRequest(
        @NotNull
        @PositiveOrZero
        Integer classId,

        @NotBlank
        @Size(max = 100)
        String className,

        @NotNull
        @DecimalMin("0.0")
        @DecimalMax("1.0")
        BigDecimal confidence,

        @NotNull
        @PositiveOrZero
        BigDecimal x1,

        @NotNull
        @PositiveOrZero
        BigDecimal y1,

        @NotNull
        @PositiveOrZero
        BigDecimal x2,

        @NotNull
        @PositiveOrZero
        BigDecimal y2
) {
    @AssertTrue(message = "바운딩 박스는 x2 >= x1, y2 >= y1이어야 합니다.")
    public boolean isBoundingBoxValid() {
        return x1 == null
                || y1 == null
                || x2 == null
                || y2 == null
                || (x2.compareTo(x1) >= 0 && y2.compareTo(y1) >= 0);
    }
}
