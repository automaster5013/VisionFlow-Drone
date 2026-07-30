package com.visionflow.api.audit.controller;

import com.visionflow.api.audit.domain.AuditAction;
import com.visionflow.api.audit.domain.AuditEntityType;
import com.visionflow.api.audit.dto.AuditLogExportResult;
import com.visionflow.api.audit.dto.AuditLogPageResponse;
import com.visionflow.api.audit.dto.AuditRetentionExecutionResponse;
import com.visionflow.api.audit.dto.AuditRetentionStatusResponse;
import com.visionflow.api.audit.service.AuditLogService;
import com.visionflow.api.audit.service.AuditRetentionService;
import com.visionflow.api.common.exception.BusinessException;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Size;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

@Validated
@RestController
@RequestMapping("/api/audit-logs")
public class AuditLogController {

    private final AuditLogService auditLogService;
    private final AuditRetentionService retentionService;

    public AuditLogController(
            AuditLogService auditLogService,
            AuditRetentionService retentionService
    ) {
        this.auditLogService = auditLogService;
        this.retentionService = retentionService;
    }

    @GetMapping
    public AuditLogPageResponse find(
            @RequestParam(required = false)
            AuditAction action,

            @RequestParam(required = false)
            AuditEntityType entityType,

            @RequestParam(required = false)
            @Size(max = 100)
            String entityId,

            @RequestParam(required = false)
            @Size(max = 100)
            String actor,

            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
            Instant from,

            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
            Instant to,

            @RequestParam(defaultValue = "0")
            @Min(0)
            int page,

            @RequestParam(defaultValue = "30")
            @Min(1)
            @Max(100)
            int size
    ) {
        return auditLogService.find(
                action,
                entityType,
                entityId,
                actor,
                from,
                to,
                page,
                size
        );
    }

    @GetMapping(value = "/export", produces = "text/csv")
    public ResponseEntity<byte[]> export(
            @RequestParam(required = false)
            AuditAction action,

            @RequestParam(required = false)
            AuditEntityType entityType,

            @RequestParam(required = false)
            @Size(max = 100)
            String entityId,

            @RequestParam(required = false)
            @Size(max = 100)
            String actor,

            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
            Instant from,

            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
            Instant to,

            @RequestParam(defaultValue = "5000")
            @Min(1)
            @Max(5000)
            int limit
    ) {
        AuditLogExportResult result = auditLogService.exportCsv(
                action,
                entityType,
                entityId,
                actor,
                from,
                to,
                limit
        );

        Map<String, Object> details = new LinkedHashMap<>();
        details.put("exportedCount", result.exportedCount());
        details.put("totalElements", result.totalElements());
        details.put("limit", limit);
        putIfPresent(details, "action", action == null ? null : action.name());
        putIfPresent(
                details,
                "entityType",
                entityType == null ? null : entityType.name()
        );
        putIfPresent(details, "entityId", entityId);
        putIfPresent(details, "actor", actor);
        putIfPresent(details, "from", from == null ? null : from.toString());
        putIfPresent(details, "to", to == null ? null : to.toString());
        auditLogService.record(
                AuditAction.AUDIT_LOG_EXPORTED,
                AuditEntityType.AUDIT_LOG,
                result.filename(),
                "감사 로그 CSV 내보내기",
                details
        );

        return ResponseEntity.ok()
                .contentType(new MediaType("text", "csv", StandardCharsets.UTF_8))
                .contentLength(result.content().length)
                .header(HttpHeaders.CACHE_CONTROL, "no-store")
                .header(
                        HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"" + result.filename() + "\""
                )
                .header(
                        "X-VisionFlow-Exported-Count",
                        String.valueOf(result.exportedCount())
                )
                .header(
                        "X-VisionFlow-Total-Count",
                        String.valueOf(result.totalElements())
                )
                .body(result.content());
    }

    @GetMapping("/retention")
    public AuditRetentionStatusResponse retentionStatus() {
        return retentionService.inspect();
    }

    @PostMapping("/retention/cleanup")
    public AuditRetentionExecutionResponse cleanupRetention(
            @RequestParam(defaultValue = "false")
            boolean confirm,

            @RequestParam(defaultValue = "false")
            boolean backupConfirmed
    ) {
        if (!confirm) {
            throw new BusinessException(
                    HttpStatus.BAD_REQUEST,
                    "AUDIT_RETENTION_CONFIRMATION_REQUIRED",
                    "감사 로그 정리를 실행하려면 confirm=true가 필요합니다."
            );
        }
        if (!backupConfirmed) {
            throw new BusinessException(
                    HttpStatus.BAD_REQUEST,
                    "AUDIT_RETENTION_BACKUP_CONFIRMATION_REQUIRED",
                    "감사 로그 CSV 백업 후 backupConfirmed=true를 입력해야 합니다."
            );
        }
        AuditRetentionExecutionResponse result =
                retentionService.cleanup("MANUAL");
        auditLogService.record(
                AuditAction.AUDIT_LOG_RETENTION_EXECUTED,
                AuditEntityType.AUDIT_LOG,
                "manual-" + result.executedAt(),
                "감사 로그 수동 보존 정리",
                Map.of(
                        "deletedCount", result.deletedCount(),
                        "remainingEligibleCount",
                        result.remainingEligibleCount(),
                        "retentionDays", result.retentionDays(),
                        "cutoff", result.cutoff().toString(),
                        "trigger", result.trigger()
                )
        );
        return result;
    }

    private void putIfPresent(
            Map<String, Object> target,
            String key,
            String value
    ) {
        if (value != null && !value.isBlank()) {
            target.put(key, value.trim());
        }
    }
}
