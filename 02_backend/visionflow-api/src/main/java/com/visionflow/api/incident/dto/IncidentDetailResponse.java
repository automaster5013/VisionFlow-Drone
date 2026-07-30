package com.visionflow.api.incident.dto;

import java.util.List;

public record IncidentDetailResponse(
        IncidentResponse incident,
        List<IncidentActionHistoryResponse> history,
        IncidentContextResponse context
) {
}
