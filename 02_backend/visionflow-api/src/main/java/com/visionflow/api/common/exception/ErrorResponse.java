package com.visionflow.api.common.exception;

import java.time.LocalDateTime;
import java.util.Map;

public record ErrorResponse(
        boolean success,
        String code,
        String message,
        Map<String, String> errors,
        LocalDateTime timestamp
) {

    public static ErrorResponse of(
            String code,
            String message
    ) {
        return new ErrorResponse(
                false,
                code,
                message,
                Map.of(),
                LocalDateTime.now()
        );
    }

    public static ErrorResponse validation(
            Map<String, String> errors
    ) {
        return new ErrorResponse(
                false,
                "VALIDATION_ERROR",
                "입력값이 올바르지 않습니다.",
                errors,
                LocalDateTime.now()
        );
    }
}