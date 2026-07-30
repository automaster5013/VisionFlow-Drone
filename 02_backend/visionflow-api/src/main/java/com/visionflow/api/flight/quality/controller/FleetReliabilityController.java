package com.visionflow.api.flight.quality.controller;

import com.visionflow.api.flight.quality.dto.FleetReliabilityResponse;
import com.visionflow.api.flight.quality.dto.FlightQualityIncidentSyncResponse;
import com.visionflow.api.flight.quality.service.FlightQualityIncidentAutomationService;
import com.visionflow.api.flight.quality.service.FleetReliabilityService;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/flight-quality")
@Validated
public class FleetReliabilityController {

    private final FleetReliabilityService reliabilityService;
    private final FlightQualityIncidentAutomationService incidentAutomationService;

    public FleetReliabilityController(
            FleetReliabilityService reliabilityService,
            FlightQualityIncidentAutomationService incidentAutomationService
    ) {
        this.reliabilityService = reliabilityService;
        this.incidentAutomationService = incidentAutomationService;
    }

    @GetMapping("/fleet-reliability")
    public FleetReliabilityResponse findFleetReliability(
            @RequestParam(defaultValue = "20")
            @Min(
                    value = 1,
                    message = "기체별 품질 평가 제한값은 1 이상이어야 합니다."
            )
            @Max(
                    value = 100,
                    message = "기체별 품질 평가 제한값은 100 이하여야 합니다."
            )
            Integer limitPerDrone
    ) {
        return reliabilityService.summarize(limitPerDrone);
    }

    @PostMapping("/fleet-reliability/incidents/synchronize")
    public FlightQualityIncidentSyncResponse synchronizeIncidents(
            @RequestParam(defaultValue = "20")
            @Min(
                    value = 1,
                    message = "기체별 품질 평가 제한값은 1 이상이어야 합니다."
            )
            @Max(
                    value = 100,
                    message = "기체별 품질 평가 제한값은 100 이하여야 합니다."
            )
            Integer limitPerDrone
    ) {
        return incidentAutomationService.synchronizeFleet(limitPerDrone);
    }
}
