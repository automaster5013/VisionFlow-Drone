package com.visionflow.api.maintenance.controller;

import com.visionflow.api.maintenance.domain.MaintenanceWorkOrderStatus;
import com.visionflow.api.maintenance.dto.MaintenanceInspectionCompleteRequest;
import com.visionflow.api.maintenance.dto.MaintenanceInspectionStartRequest;
import com.visionflow.api.maintenance.dto.MaintenanceWorkOrderDetailResponse;
import com.visionflow.api.maintenance.dto.MaintenanceWorkOrderResponse;
import com.visionflow.api.maintenance.service.MaintenanceWorkOrderService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Positive;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/maintenance/work-orders")
@Validated
public class MaintenanceWorkOrderController {

    private final MaintenanceWorkOrderService workOrderService;

    public MaintenanceWorkOrderController(
            MaintenanceWorkOrderService workOrderService
    ) {
        this.workOrderService = workOrderService;
    }

    @GetMapping
    public List<MaintenanceWorkOrderResponse> findWorkOrders(
            @RequestParam(required = false)
            @Positive(message = "드론 ID는 1 이상이어야 합니다.")
            Long droneId,

            @RequestParam(required = false)
            MaintenanceWorkOrderStatus status,

            @RequestParam(defaultValue = "100")
            @Min(value = 1, message = "조회 개수는 1 이상이어야 합니다.")
            @Max(value = 500, message = "조회 개수는 500 이하여야 합니다.")
            int limit
    ) {
        return workOrderService.findWorkOrders(
                droneId,
                status,
                limit
        );
    }

    @GetMapping("/{workOrderId}")
    public MaintenanceWorkOrderDetailResponse findDetail(
            @PathVariable @Positive Long workOrderId
    ) {
        return workOrderService.findDetail(workOrderId);
    }

    @PatchMapping("/{workOrderId}/start")
    public MaintenanceWorkOrderResponse startInspection(
            @PathVariable @Positive Long workOrderId,
            @Valid @RequestBody MaintenanceInspectionStartRequest request
    ) {
        return workOrderService.startInspection(workOrderId, request);
    }

    @PatchMapping("/{workOrderId}/complete")
    public MaintenanceWorkOrderResponse completeInspection(
            @PathVariable @Positive Long workOrderId,
            @Valid @RequestBody MaintenanceInspectionCompleteRequest request
    ) {
        return workOrderService.completeInspection(workOrderId, request);
    }
}
