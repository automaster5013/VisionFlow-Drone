package com.visionflow.api.maintenance.controller;

import com.visionflow.api.maintenance.dto.MaintenancePriorityQueueResponse;
import com.visionflow.api.maintenance.service.MaintenancePriorityService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/maintenance/priorities")
public class MaintenancePriorityController {

    private final MaintenancePriorityService priorityService;

    public MaintenancePriorityController(
            MaintenancePriorityService priorityService
    ) {
        this.priorityService = priorityService;
    }

    @GetMapping
    public MaintenancePriorityQueueResponse getPriorities() {
        return priorityService.getPriorities();
    }
}
