package com.visionflow.api.audit.dto;

public record AuditLogExportResult(
        byte[] content,
        String filename,
        int exportedCount,
        long totalElements
) {
}
