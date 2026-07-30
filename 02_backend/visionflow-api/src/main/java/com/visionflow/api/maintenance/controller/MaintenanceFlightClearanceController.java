package com.visionflow.api.maintenance.controller;

import com.visionflow.api.maintenance.dto.MaintenanceFleetFlightClearanceResponse;
import com.visionflow.api.maintenance.dto.MaintenanceFlightClearanceResponse;
import com.visionflow.api.maintenance.service.MaintenanceFlightGateService;
import jakarta.validation.constraints.Positive;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/maintenance/flight-clearance")
@Validated
public class MaintenanceFlightClearanceController {

    private final MaintenanceFlightGateService flightGateService;

    public MaintenanceFlightClearanceController(
            MaintenanceFlightGateService flightGateService
    ) {
        this.flightGateService = flightGateService;
    }

    @GetMapping("/{droneId}")
    public MaintenanceFlightClearanceResponse findClearance(
            @PathVariable
            @Positive(message = "드론 ID는 1 이상이어야 합니다.")
            Long droneId
    ) {
        return flightGateService.evaluate(droneId);
    }

    @GetMapping
    public MaintenanceFleetFlightClearanceResponse findFleetClearance() {
        return flightGateService.evaluateFleet();
    }
}
