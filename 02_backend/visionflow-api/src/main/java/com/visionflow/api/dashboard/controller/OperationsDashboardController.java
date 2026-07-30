package com.visionflow.api.dashboard.controller;

import com.visionflow.api.dashboard.dto.OperationsDashboardResponse;
import com.visionflow.api.dashboard.service.OperationsDashboardService;
import com.visionflow.api.flight.domain.FlightSessionStatus;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Positive;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;

@RestController
@RequestMapping("/api/dashboard")
@Validated
public class OperationsDashboardController {

    private final OperationsDashboardService dashboardService;

    public OperationsDashboardController(
            OperationsDashboardService dashboardService
    ) {
        this.dashboardService = dashboardService;
    }

    @GetMapping("/operations")
    public OperationsDashboardResponse findOperations(
            @RequestParam(required = false)
            @Positive(message = "드론 ID는 1 이상이어야 합니다.")
            Long droneId,

            @RequestParam(required = false)
            FlightSessionStatus status,

            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
            Instant from,

            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
            Instant to,

            @RequestParam(defaultValue = "5")
            @Min(
                    value = 1,
                    message = "대시보드 최근 항목 제한값은 1 이상이어야 합니다."
            )
            @Max(
                    value = 20,
                    message = "대시보드 최근 항목 제한값은 20 이하여야 합니다."
            )
            Integer limit
    ) {
        return dashboardService.findOperations(
                droneId,
                status,
                from,
                to,
                limit
        );
    }
}
