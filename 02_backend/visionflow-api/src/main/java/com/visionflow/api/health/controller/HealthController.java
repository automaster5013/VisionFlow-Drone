package com.visionflow.api.health.controller;

import com.visionflow.api.common.response.ApiResponse;
import com.visionflow.api.health.dto.HealthResponse;
import com.visionflow.api.health.service.HealthService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/health")
public class HealthController {

    private final HealthService healthService;

    public HealthController(HealthService healthService) {
        this.healthService = healthService;
    }

    @GetMapping
    public ResponseEntity<ApiResponse<HealthResponse>> health() {
        HealthResponse response = healthService.checkHealth();

        return ResponseEntity.ok(
                ApiResponse.success(response)
        );
    }
}