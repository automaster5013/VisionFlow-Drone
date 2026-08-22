package com.visionflow.api.ai.controller;

import com.visionflow.api.ai.dto.AiInferenceEventCreateRequest;
import com.visionflow.api.ai.dto.AiInferenceEventResponse;
import com.visionflow.api.ai.service.AiInferenceEventService;
import com.visionflow.api.audit.domain.AuditAction;
import com.visionflow.api.audit.domain.AuditEntityType;
import com.visionflow.api.audit.service.AuditLogService;
import jakarta.validation.Valid;
import org.springframework.core.io.Resource;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/ai/events")
public class AiInferenceEventController {

    private final AiInferenceEventService eventService;
    private final AuditLogService auditLogService;

    public AiInferenceEventController(
            AiInferenceEventService eventService,
            AuditLogService auditLogService
    ) {
        this.eventService = eventService;
        this.auditLogService = auditLogService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public AiInferenceEventResponse create(
            @Valid @RequestBody
            AiInferenceEventCreateRequest request
    ) {
        return eventService.create(request);
    }

    @GetMapping
    public List<AiInferenceEventResponse> findRecent(
            @RequestParam(required = false)
            Long droneId,

            @RequestParam(defaultValue = "100")
            int limit
    ) {
        return eventService.findRecent(droneId, limit);
    }

    @PutMapping(
            path = "/{eventId}/snapshot",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    public AiInferenceEventResponse uploadSnapshot(
            @PathVariable Long eventId,
            @RequestPart("file") MultipartFile file,
            Authentication authentication
    ) {
        AiInferenceEventResponse stored =
                eventService.attachSnapshot(eventId, file);
        boolean manualOperator =
                hasManualSnapshotAuthority(authentication);

        auditLogService.record(
                AuditAction.PRIVACY_SNAPSHOT_STORED,
                AuditEntityType.AI_INFERENCE_EVENT,
                eventId,
                "AI 이벤트 개인정보 스냅샷 저장",
                Map.of(
                        "droneId", stored.droneId(),
                        "frameIndex", stored.frameIndex(),
                        "sourceId", stored.sourceId(),
                        "sourceType", stored.sourceType().name(),
                        "snapshotSizeBytes",
                        stored.snapshotSizeBytes(),
                        "storageMode",
                        manualOperator
                                ? "MANUAL_OPERATOR"
                                : "AI_INTERNAL"
                )
        );

        return stored;
    }

    private boolean hasManualSnapshotAuthority(
            Authentication authentication
    ) {
        if (
                authentication == null
                        || !authentication.isAuthenticated()
        ) {
            return false;
        }

        return authentication.getAuthorities()
                .stream()
                .map(authority -> authority.getAuthority())
                .anyMatch(authority ->
                        "ROLE_OPERATOR".equals(authority)
                                || "ROLE_ADMIN".equals(authority)
                );
    }

    @GetMapping("/{eventId}/snapshot")
    public ResponseEntity<Resource> findSnapshot(
            @PathVariable Long eventId
    ) {
        var snapshot = eventService.findSnapshot(eventId);

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noCache())
                .header(
                        HttpHeaders.CONTENT_DISPOSITION,
                        "inline; filename=\"" + snapshot.fileName() + "\""
                )
                .contentType(MediaType.parseMediaType(snapshot.contentType()))
                .contentLength(snapshot.sizeBytes())
                .body(snapshot.resource());
    }

    @DeleteMapping("/{eventId}/snapshot")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deleteSnapshot(@PathVariable Long eventId) {
        var deletion = eventService.deleteSnapshot(eventId);

        if (!deletion.snapshotExisted()) {
            return;
        }

        auditLogService.record(
                AuditAction.PRIVACY_SNAPSHOT_DELETED,
                AuditEntityType.AI_INFERENCE_EVENT,
                eventId,
                "AI 이벤트 개인정보 스냅샷 삭제",
                Map.of(
                        "droneId", deletion.droneId(),
                        "frameIndex", deletion.frameIndex(),
                        "sourceType", deletion.sourceType().name(),
                        "snapshotSizeBytes", deletion.snapshotSizeBytes(),
                        "physicalFileDeleted", deletion.physicalFileDeleted()
                )
        );
    }
}
