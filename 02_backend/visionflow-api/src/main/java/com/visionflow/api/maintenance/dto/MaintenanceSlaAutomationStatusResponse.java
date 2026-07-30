package com.visionflow.api.maintenance.dto;

public record MaintenanceSlaAutomationStatusResponse(
        boolean automationEnabled,
        long openSlaMinutes,
        long inProgressSlaMinutes,
        long dueSoonMinutes,
        long initialDelayMs,
        long scanDelayMs
) {
}
