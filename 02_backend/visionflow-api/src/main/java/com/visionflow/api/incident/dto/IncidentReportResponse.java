package com.visionflow.api.incident.dto;

import java.time.Instant;
import java.util.List;

public record IncidentReportResponse(
        Instant generatedAt,
        IncidentResponse incident,
        IncidentContextResponse context,
        IncidentReportMetricsResponse metrics,
        List<IncidentActionHistoryResponse> history
) {
}
