package com.visionflow.api.maintenance.controller;

import com.visionflow.api.maintenance.dto.MaintenanceMetricsResponse;
import com.visionflow.api.maintenance.service.MaintenanceMetricsService;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/maintenance/metrics")
@Validated
public class MaintenanceMetricsController {

    private final MaintenanceMetricsService metricsService;

    public MaintenanceMetricsController(
            MaintenanceMetricsService metricsService
    ) {
        this.metricsService = metricsService;
    }

    @GetMapping
    public MaintenanceMetricsResponse getMetrics(
            @RequestParam(defaultValue = "30")
            @Min(value = 1, message = "조회 기간은 1일 이상이어야 합니다.")
            @Max(value = 365, message = "조회 기간은 365일 이하여야 합니다.")
            int windowDays
    ) {
        return metricsService.getMetrics(windowDays);
    }
}
