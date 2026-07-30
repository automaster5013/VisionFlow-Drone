package com.visionflow.api.maintenance.dto;

import java.util.List;

public record MaintenanceWorkOrderDetailResponse(
        MaintenanceWorkOrderResponse workOrder,
        List<MaintenanceWorkOrderHistoryResponse> history
) {
}
