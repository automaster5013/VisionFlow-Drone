package com.visionflow.api.maintenance.controller;

import com.visionflow.api.maintenance.dto.MaintenanceSlaIncidentTrackingResponse;
import com.visionflow.api.maintenance.service.MaintenanceSlaIncidentTrackingService;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/maintenance/sla/incidents")
@Validated
public class MaintenanceSlaIncidentTrackingController {

    private final MaintenanceSlaIncidentTrackingService trackingService;

    public MaintenanceSlaIncidentTrackingController(
            MaintenanceSlaIncidentTrackingService trackingService
    ) {
        this.trackingService = trackingService;
    }

    @GetMapping
    public MaintenanceSlaIncidentTrackingResponse getTracking(
            @RequestParam(defaultValue = "30")
            @Min(
                    value = 1,
                    message = "조회 기간은 1일 이상이어야 합니다."
            )
            @Max(
                    value = MaintenanceSlaIncidentTrackingService
                            .MAX_WINDOW_DAYS,
                    message = "조회 기간은 90일 이하여야 합니다."
            )
            int windowDays
    ) {
        return trackingService.getTracking(windowDays);
    }
}
