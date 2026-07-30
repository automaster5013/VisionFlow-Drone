package com.visionflow.api.audit.scheduler;

import com.visionflow.api.audit.domain.AuditAction;
import com.visionflow.api.audit.domain.AuditEntityType;
import com.visionflow.api.audit.dto.AuditRetentionExecutionResponse;
import com.visionflow.api.audit.service.AuditLogService;
import com.visionflow.api.audit.service.AuditRetentionService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.util.Map;

@Component
@ConditionalOnProperty(
        name = {
                "visionflow.audit.retention.enabled",
                "visionflow.audit.retention.archive-confirmed"
        },
        havingValue = "true"
)
public class AuditRetentionScheduler {

    private static final Logger log = LoggerFactory.getLogger(
            AuditRetentionScheduler.class
    );

    private final AuditRetentionService retentionService;
    private final AuditLogService auditLogService;

    public AuditRetentionScheduler(
            AuditRetentionService retentionService,
            AuditLogService auditLogService
    ) {
        this.retentionService = retentionService;
        this.auditLogService = auditLogService;
    }

    @Scheduled(
            cron = "${visionflow.audit.retention.cron:0 30 3 * * *}",
            zone = "UTC"
    )
    public void cleanup() {
        try {
            AuditRetentionExecutionResponse result =
                    retentionService.cleanup("SCHEDULED");
            if (result.deletedCount() > 0) {
                auditLogService.record(
                        AuditAction.AUDIT_LOG_RETENTION_EXECUTED,
                        AuditEntityType.AUDIT_LOG,
                        "scheduled-" + result.executedAt(),
                        "감사 로그 자동 보존 정리",
                        Map.of(
                                "deletedCount", result.deletedCount(),
                                "remainingEligibleCount",
                                result.remainingEligibleCount(),
                                "retentionDays", result.retentionDays(),
                                "cutoff", result.cutoff().toString(),
                                "trigger", result.trigger()
                        )
                );
                log.info(
                        "감사 로그 자동 보존 정리: 삭제 {}건, 잔여 대상 {}건",
                        result.deletedCount(),
                        result.remainingEligibleCount()
                );
            }
        } catch (RuntimeException error) {
            log.error("감사 로그 자동 보존 정리 실패", error);
        }
    }
}
