package com.visionflow.api.maintenance.controller;

import com.visionflow.api.maintenance.config.MaintenanceSlaAutomationProperties;
import com.visionflow.api.maintenance.dto.MaintenanceSlaAutomationStatusResponse;
import com.visionflow.api.maintenance.service.MaintenanceSlaPolicy;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/maintenance/sla")
public class MaintenanceSlaController {

    private final MaintenanceSlaAutomationProperties properties;

    public MaintenanceSlaController(
            MaintenanceSlaAutomationProperties properties
    ) {
        this.properties = properties;
    }

    @GetMapping
    public MaintenanceSlaAutomationStatusResponse status() {
        return new MaintenanceSlaAutomationStatusResponse(
                properties.isAutomationEnabled(),
                MaintenanceSlaPolicy.OPEN_SLA_MINUTES,
                MaintenanceSlaPolicy.IN_PROGRESS_SLA_MINUTES,
                MaintenanceSlaPolicy.DUE_SOON_MINUTES,
                properties.getInitialDelayMs(),
                properties.getScanDelayMs()
        );
    }

}
