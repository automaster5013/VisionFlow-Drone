package com.visionflow.api.audit.service;

import com.visionflow.api.audit.config.AuditRetentionProperties;
import com.visionflow.api.audit.dto.AuditRetentionExecutionResponse;
import com.visionflow.api.audit.dto.AuditRetentionStatusResponse;
import com.visionflow.api.audit.repository.AuditLogRepository;
import com.visionflow.api.common.exception.BusinessException;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.List;

@Service
public class AuditRetentionService {

    private final AuditLogRepository auditLogRepository;
    private final AuditRetentionProperties properties;

    public AuditRetentionService(
            AuditLogRepository auditLogRepository,
            AuditRetentionProperties properties
    ) {
        this.auditLogRepository = auditLogRepository;
        this.properties = properties;
    }

    @Transactional(readOnly = true)
    public AuditRetentionStatusResponse inspect() {
        Instant checkedAt = Instant.now();
        Instant cutoff = cutoffAt(checkedAt);
        long eligibleCount = auditLogRepository.countByOccurredAtBefore(
                toUtcDateTime(cutoff)
        );
        return new AuditRetentionStatusResponse(
                properties.isEnabled(),
                properties.isArchiveConfirmed(),
                true,
                properties.getDays(),
                properties.getBatchSize(),
                properties.getCron(),
                cutoff,
                eligibleCount,
                checkedAt
        );
    }

    @Transactional
    public AuditRetentionExecutionResponse cleanup(String trigger) {
        requireEnabled();
        Instant executedAt = Instant.now();
        Instant cutoff = cutoffAt(executedAt);
        LocalDateTime cutoffDateTime = toUtcDateTime(cutoff);
        List<Long> ids = auditLogRepository.findRetentionCandidateIds(
                cutoffDateTime,
                PageRequest.of(0, properties.getBatchSize())
        );
        if (!ids.isEmpty()) {
            auditLogRepository.deleteAllByIdInBatch(ids);
            auditLogRepository.flush();
        }
        long remaining = auditLogRepository.countByOccurredAtBefore(
                cutoffDateTime
        );
        return new AuditRetentionExecutionResponse(
                true,
                normalizeTrigger(trigger),
                properties.getDays(),
                properties.getBatchSize(),
                cutoff,
                ids.size(),
                remaining,
                executedAt
        );
    }

    private void requireEnabled() {
        if (!properties.isEnabled()) {
            throw new BusinessException(
                    HttpStatus.CONFLICT,
                    "AUDIT_RETENTION_DISABLED",
                    "감사 로그 자동 보존 정책이 비활성화되어 있습니다."
            );
        }
        if (!properties.isArchiveConfirmed()) {
            throw new BusinessException(
                    HttpStatus.CONFLICT,
                    "AUDIT_RETENTION_ARCHIVE_NOT_CONFIRMED",
                    "감사 로그 CSV 백업 확인 설정이 필요합니다."
            );
        }
    }

    private String normalizeTrigger(String trigger) {
        if (trigger == null || trigger.isBlank()) {
            return "UNKNOWN";
        }
        String normalized = trigger.trim().toUpperCase();
        return normalized.length() > 20
                ? normalized.substring(0, 20)
                : normalized;
    }

    private Instant cutoffAt(Instant referenceTime) {
        return referenceTime.minus(properties.getDays(), ChronoUnit.DAYS);
    }

    private LocalDateTime toUtcDateTime(Instant value) {
        return LocalDateTime.ofInstant(value, ZoneOffset.UTC);
    }
}
