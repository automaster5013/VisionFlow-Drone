package com.visionflow.api.ai.dto;

public record AiAlertDetailResponse(
        AiAlertResponse alert,
        AiInferenceEventResponse event
) {
}
