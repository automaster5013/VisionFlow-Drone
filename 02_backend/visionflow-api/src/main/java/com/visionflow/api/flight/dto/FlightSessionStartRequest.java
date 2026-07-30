package com.visionflow.api.flight.dto;

import jakarta.validation.constraints.Size;

public record FlightSessionStartRequest(
        @Size(
                max = 120,
                message = "비행 세션명은 120자 이하여야 합니다."
        )
        String name,

        @Size(
                max = 500,
                message = "비행 세션 설명은 500자 이하여야 합니다."
        )
        String description,

        @Size(
                max = 100,
                message = "소스 장치 ID는 100자 이하여야 합니다."
        )
        String sourceDeviceId
) {
}
