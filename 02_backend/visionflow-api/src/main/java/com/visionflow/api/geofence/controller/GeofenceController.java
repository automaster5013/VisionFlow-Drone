package com.visionflow.api.geofence.controller;

import com.visionflow.api.audit.domain.AuditAction;
import com.visionflow.api.audit.domain.AuditEntityType;
import com.visionflow.api.audit.service.AuditLogService;
import com.visionflow.api.geofence.dto.*;
import com.visionflow.api.geofence.service.GeofenceService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/geofences")
public class GeofenceController {

    private final GeofenceService geofenceService;
    private final AuditLogService auditLogService;

    public GeofenceController(
            GeofenceService geofenceService,
            AuditLogService auditLogService
    ) {
        this.geofenceService = geofenceService;
        this.auditLogService = auditLogService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public GeofenceResponse create(
            @Valid @RequestBody GeofenceCreateRequest request
    ) {
        GeofenceResponse response = geofenceService.create(request);
        auditLogService.record(
                AuditAction.GEOFENCE_CREATED,
                AuditEntityType.GEOFENCE,
                response.id(),
                "지오펜스 생성",
                Map.of(
                        "name", response.name(),
                        "ruleType", response.ruleType().name(),
                        "active", response.active()
                )
        );
        return response;
    }

    @GetMapping
    public List<GeofenceResponse> findAll() {
        return geofenceService.findAll();
    }

    @GetMapping("/events")
    public List<GeofenceEventResponse> findEvents(
            @RequestParam(defaultValue = "false")
            boolean activeOnly,

            @RequestParam(defaultValue = "100")
            int limit
    ) {
        return geofenceService.findEvents(activeOnly, limit);
    }

    @GetMapping("/{id}")
    public GeofenceResponse findById(
            @PathVariable Long id
    ) {
        return geofenceService.findById(id);
    }

    @PutMapping("/{id}")
    public GeofenceResponse update(
            @PathVariable Long id,
            @Valid @RequestBody
            GeofenceUpdateRequest request
    ) {
        GeofenceResponse response = geofenceService.update(id, request);
        auditLogService.record(
                AuditAction.GEOFENCE_UPDATED,
                AuditEntityType.GEOFENCE,
                response.id(),
                "지오펜스 정보 수정",
                Map.of(
                        "name", response.name(),
                        "ruleType", response.ruleType().name(),
                        "active", response.active()
                )
        );
        return response;
    }

    @PatchMapping("/{id}/active")
    public GeofenceResponse changeActive(
            @PathVariable Long id,
            @Valid @RequestBody
            GeofenceActiveUpdateRequest request
    ) {
        GeofenceResponse response = geofenceService.changeActive(id, request);
        auditLogService.record(
                response.active()
                        ? AuditAction.GEOFENCE_ACTIVATED
                        : AuditAction.GEOFENCE_DEACTIVATED,
                AuditEntityType.GEOFENCE,
                response.id(),
                response.active() ? "지오펜스 활성화" : "지오펜스 비활성화",
                Map.of(
                        "name", response.name(),
                        "active", response.active()
                )
        );
        return response;
    }
}
