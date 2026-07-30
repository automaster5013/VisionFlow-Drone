package com.visionflow.api.audit.dto;

import org.springframework.data.domain.Page;

import java.util.List;

public record AuditLogPageResponse(
        List<AuditLogResponse> content,
        int page,
        int size,
        long totalElements,
        int totalPages,
        boolean first,
        boolean last
) {

    public static AuditLogPageResponse from(Page<AuditLogResponse> result) {
        return new AuditLogPageResponse(
                result.getContent(),
                result.getNumber(),
                result.getSize(),
                result.getTotalElements(),
                result.getTotalPages(),
                result.isFirst(),
                result.isLast()
        );
    }
}
