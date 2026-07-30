package com.visionflow.api.incident.controller;

import com.visionflow.api.audit.domain.AuditAction;
import com.visionflow.api.audit.domain.AuditEntityType;
import com.visionflow.api.audit.service.AuditLogService;
import com.visionflow.api.incident.domain.IncidentPriority;
import com.visionflow.api.incident.domain.IncidentSourceType;
import com.visionflow.api.incident.domain.IncidentStatus;
import com.visionflow.api.incident.dto.IncidentAssignRequest;
import com.visionflow.api.incident.dto.IncidentDetailResponse;
import com.visionflow.api.incident.dto.IncidentNoteCreateRequest;
import com.visionflow.api.incident.dto.IncidentPriorityUpdateRequest;
import com.visionflow.api.incident.dto.IncidentReportResponse;
import com.visionflow.api.incident.dto.IncidentResponse;
import com.visionflow.api.incident.dto.IncidentStatusUpdateRequest;
import com.visionflow.api.incident.service.IncidentReportService;
import com.visionflow.api.incident.service.IncidentService;
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
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.List;
import java.util.Map;

@Validated
@RestController
@RequestMapping("/api/incidents")
public class IncidentController {

    private final IncidentService incidentService;
    private final IncidentReportService incidentReportService;
    private final AuditLogService auditLogService;

    public IncidentController(
            IncidentService incidentService,
            IncidentReportService incidentReportService,
            AuditLogService auditLogService
    ) {
        this.incidentService = incidentService;
        this.incidentReportService = incidentReportService;
        this.auditLogService = auditLogService;
    }

    @GetMapping
    public List<IncidentResponse> findIncidents(
            @RequestParam(required = false)
            @Positive
            Long droneId,

            @RequestParam(required = false)
            IncidentSourceType sourceType,

            @RequestParam(required = false)
            IncidentPriority priority,

            @RequestParam(required = false)
            IncidentStatus status,

            @RequestParam(required = false)
            @Size(max = 100)
            String assignee,

            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
            Instant from,

            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
            Instant to,

            @RequestParam(defaultValue = "100")
            @Min(1)
            @Max(500)
            int limit
    ) {
        return incidentService.findIncidents(
                droneId,
                sourceType,
                priority,
                status,
                assignee,
                from,
                to,
                limit
        );
    }

    @GetMapping("/{incidentId}")
    public IncidentDetailResponse findDetail(
            @PathVariable @Positive Long incidentId
    ) {
        return incidentService.findDetail(incidentId);
    }

    @GetMapping("/{incidentId}/report")
    public IncidentReportResponse findReport(
            @PathVariable @Positive Long incidentId
    ) {
        return incidentReportService.build(incidentId);
    }

    @PatchMapping("/{incidentId}/assignee")
    public IncidentResponse assign(
            @PathVariable @Positive Long incidentId,
            @Valid @RequestBody IncidentAssignRequest request
    ) {
        IncidentResponse response = incidentService.assign(
                incidentId,
                request.assignee(),
                request.actor()
        );
        auditLogService.record(
                AuditAction.INCIDENT_ASSIGNED,
                AuditEntityType.INCIDENT,
                response.id(),
                "Incident 담당자 지정",
                Map.of(
                        "assignee", request.assignee(),
                        "status", response.status().name()
                ),
                request.actor()
        );
        return response;
    }

    @PatchMapping("/{incidentId}/priority")
    public IncidentResponse changePriority(
            @PathVariable @Positive Long incidentId,
            @Valid @RequestBody IncidentPriorityUpdateRequest request
    ) {
        IncidentResponse response = incidentService.changePriority(
                incidentId,
                request.priority(),
                request.actor(),
                request.note()
        );
        auditLogService.record(
                AuditAction.INCIDENT_PRIORITY_CHANGED,
                AuditEntityType.INCIDENT,
                response.id(),
                "Incident 우선순위 변경",
                Map.of(
                        "priority", response.priority().name(),
                        "status", response.status().name()
                ),
                request.actor()
        );
        return response;
    }

    @PatchMapping("/{incidentId}/status")
    public IncidentResponse changeStatus(
            @PathVariable @Positive Long incidentId,
            @Valid @RequestBody IncidentStatusUpdateRequest request
    ) {
        IncidentResponse response = incidentService.changeStatus(
                incidentId,
                request.status(),
                request.actor(),
                request.note()
        );
        auditLogService.record(
                AuditAction.INCIDENT_STATUS_CHANGED,
                AuditEntityType.INCIDENT,
                response.id(),
                "Incident 상태 변경",
                Map.of(
                        "status", response.status().name(),
                        "priority", response.priority().name()
                ),
                request.actor()
        );
        return response;
    }

    @PostMapping("/{incidentId}/notes")
    public IncidentDetailResponse addNote(
            @PathVariable @Positive Long incidentId,
            @Valid @RequestBody IncidentNoteCreateRequest request
    ) {
        IncidentDetailResponse response = incidentService.addNote(
                incidentId,
                request.actor(),
                request.note()
        );
        auditLogService.record(
                AuditAction.INCIDENT_NOTE_ADDED,
                AuditEntityType.INCIDENT,
                response.incident().id(),
                "Incident 조치 메모 추가",
                Map.of(
                        "status", response.incident().status().name(),
                        "noteLength", request.note().length()
                ),
                request.actor()
        );
        return response;
    }
}
