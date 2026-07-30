package com.visionflow.api.ai.controller;

import com.visionflow.api.ai.domain.AiAlertSeverity;
import com.visionflow.api.ai.domain.AiAlertStatus;
import com.visionflow.api.ai.dto.AiAlertAcknowledgeRequest;
import com.visionflow.api.ai.dto.AiAlertDetailResponse;
import com.visionflow.api.ai.dto.AiAlertResolveRequest;
import com.visionflow.api.ai.dto.AiAlertResponse;
import com.visionflow.api.ai.service.AiAlertService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.List;

@Validated
@RestController
@RequestMapping("/api/ai/alerts")
public class AiAlertController {

    private final AiAlertService alertService;

    public AiAlertController(AiAlertService alertService) {
        this.alertService = alertService;
    }

    @GetMapping
    public List<AiAlertResponse> findAlerts(
            @RequestParam(required = false)
            @Positive
            Long droneId,

            @RequestParam(required = false)
            @Size(max = 36)
            String sessionId,

            @RequestParam(required = false)
            AiAlertSeverity severity,

            @RequestParam(required = false)
            AiAlertStatus status,

            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
            Instant from,

            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
            Instant to,

            @RequestParam(defaultValue = "100")
            @Min(1)
            @Max(200)
            int limit
    ) {
        return alertService.findAlerts(
                droneId,
                sessionId,
                severity,
                status,
                from,
                to,
                limit
        );
    }

    @GetMapping("/{alertId}")
    public AiAlertDetailResponse findDetail(
            @PathVariable @Positive Long alertId
    ) {
        return alertService.findDetail(alertId);
    }

    @PatchMapping("/{alertId}/acknowledge")
    public AiAlertResponse acknowledge(
            @PathVariable @Positive Long alertId,
            @Valid @RequestBody AiAlertAcknowledgeRequest request
    ) {
        return alertService.acknowledge(alertId, request.operator());
    }

    @PatchMapping("/{alertId}/resolve")
    public AiAlertResponse resolve(
            @PathVariable @Positive Long alertId,
            @Valid @RequestBody AiAlertResolveRequest request
    ) {
        return alertService.resolve(
                alertId,
                request.operator(),
                request.note()
        );
    }
}
