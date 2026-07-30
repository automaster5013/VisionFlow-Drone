package com.visionflow.api.flight.dto;

import jakarta.validation.constraints.Size;

public record FlightSessionUpdateRequest(
        @Size(
                max = 120,
                message = "비행 세션명은 120자 이하여야 합니다."
        )
        String name,

        @Size(
                max = 500,
                message = "비행 세션 설명은 500자 이하여야 합니다."
        )
        String description
) {
}
