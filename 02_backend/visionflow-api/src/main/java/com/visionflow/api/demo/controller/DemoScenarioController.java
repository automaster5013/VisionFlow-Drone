package com.visionflow.api.demo.controller;

import com.visionflow.api.audit.domain.AuditAction;
import com.visionflow.api.audit.domain.AuditEntityType;
import com.visionflow.api.audit.service.AuditLogService;
import com.visionflow.api.demo.dto.DemoScenarioResponse;
import com.visionflow.api.demo.dto.DemoScenarioStartRequest;
import com.visionflow.api.demo.service.DemoScenarioService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Size;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@Validated
@RestController
@RequestMapping("/api/demo/scenarios")
@ConditionalOnProperty(
        name = "visionflow.demo.enabled",
        havingValue = "true"
)
public class DemoScenarioController {

    private final DemoScenarioService scenarioService;
    private final AuditLogService auditLogService;

    public DemoScenarioController(
            DemoScenarioService scenarioService,
            AuditLogService auditLogService
    ) {
        this.scenarioService = scenarioService;
        this.auditLogService = auditLogService;
    }

    @PostMapping
    public DemoScenarioResponse start(
            @Valid @RequestBody DemoScenarioStartRequest request
    ) {
        DemoScenarioResponse response = scenarioService.start(request);
        auditLogService.record(
                AuditAction.DEMO_SCENARIO_STARTED,
                AuditEntityType.DEMO_SCENARIO,
                response.scenarioId(),
                "발표 시연 시나리오 시작",
                Map.of(
                        "droneId", response.droneId(),
                        "flightSessionId", response.flightSessionId(),
                        "stage", response.stage().name()
                )
        );
        return response;
    }

    @GetMapping("/{scenarioId}")
    public DemoScenarioResponse find(
            @PathVariable @Size(max = 36) String scenarioId
    ) {
        return scenarioService.find(scenarioId);
    }

    @PostMapping("/{scenarioId}/detect")
    public DemoScenarioResponse detect(
            @PathVariable @Size(max = 36) String scenarioId
    ) {
        return recordStage(
                scenarioService.detect(scenarioId),
                AuditAction.DEMO_SCENARIO_DETECTED,
                "발표 시연 AI 탐지"
        );
    }

    @PostMapping("/{scenarioId}/escalate")
    public DemoScenarioResponse escalate(
            @PathVariable @Size(max = 36) String scenarioId
    ) {
        return recordStage(
                scenarioService.escalate(scenarioId),
                AuditAction.DEMO_SCENARIO_ESCALATED,
                "발표 시연 SLA 승격"
        );
    }

    @PostMapping("/{scenarioId}/resolve")
    public DemoScenarioResponse resolve(
            @PathVariable @Size(max = 36) String scenarioId
    ) {
        return recordStage(
                scenarioService.resolve(scenarioId),
                AuditAction.DEMO_SCENARIO_RESOLVED,
                "발표 시연 Incident 해결"
        );
    }

    @PostMapping("/{scenarioId}/complete")
    public DemoScenarioResponse complete(
            @PathVariable @Size(max = 36) String scenarioId
    ) {
        return recordStage(
                scenarioService.complete(scenarioId),
                AuditAction.DEMO_SCENARIO_COMPLETED,
                "발표 시연 시나리오 완료"
        );
    }

    private DemoScenarioResponse recordStage(
            DemoScenarioResponse response,
            AuditAction action,
            String summary
    ) {
        auditLogService.record(
                action,
                AuditEntityType.DEMO_SCENARIO,
                response.scenarioId(),
                summary,
                Map.of(
                        "droneId", response.droneId(),
                        "flightSessionId", response.flightSessionId(),
                        "stage", response.stage().name()
                )
        );
        return response;
    }
}
