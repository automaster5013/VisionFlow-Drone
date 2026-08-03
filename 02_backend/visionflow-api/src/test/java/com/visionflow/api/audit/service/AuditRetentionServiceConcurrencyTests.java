package com.visionflow.api.audit.service;

import com.visionflow.api.audit.config.AuditRetentionProperties;
import com.visionflow.api.audit.domain.AuditAction;
import com.visionflow.api.audit.domain.AuditEntityType;
import com.visionflow.api.audit.domain.AuditLog;
import com.visionflow.api.audit.dto.AuditRetentionExecutionResponse;
import com.visionflow.api.audit.repository.AuditLogRepository;
import jakarta.persistence.LockModeType;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.InOrder;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.test.util.ReflectionTestUtils;

import java.lang.reflect.Method;
import java.time.LocalDateTime;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AuditRetentionServiceConcurrencyTests {

    private final AuditLogRepository auditLogRepository =
            mock(AuditLogRepository.class);
    private final AuditRetentionProperties properties =
            new AuditRetentionProperties();

    private AuditRetentionService service;

    @BeforeEach
    void setUp() {
        properties.setEnabled(true);
        properties.setArchiveConfirmed(true);
        properties.setDays(90);
        properties.setBatchSize(2);
        service = new AuditRetentionService(
                auditLogRepository,
                properties
        );
    }

    @Test
    void retentionCandidateQueryUsesPessimisticWriteLock()
            throws NoSuchMethodException {
        Method method = AuditLogRepository.class.getMethod(
                "findRetentionCandidatesForUpdate",
                LocalDateTime.class,
                Pageable.class
        );

        Lock lock = method.getAnnotation(Lock.class);

        assertThat(lock).isNotNull();
        assertThat(lock.value()).isEqualTo(
                LockModeType.PESSIMISTIC_WRITE
        );
    }

    @Test
    void cleanupLocksCandidateRowsBeforeBatchDelete() {
        AuditLog first = auditLog(101L);
        AuditLog second = auditLog(102L);
        when(auditLogRepository.findRetentionCandidatesForUpdate(
                any(LocalDateTime.class),
                eq(PageRequest.of(0, 2))
        )).thenReturn(List.of(first, second));
        when(auditLogRepository.countByOccurredAtBefore(
                any(LocalDateTime.class)
        )).thenReturn(3L);

        AuditRetentionExecutionResponse response = service.cleanup(
                "manual"
        );

        InOrder order = inOrder(auditLogRepository);
        order.verify(auditLogRepository)
                .findRetentionCandidatesForUpdate(
                        any(LocalDateTime.class),
                        eq(PageRequest.of(0, 2))
                );
        order.verify(auditLogRepository)
                .deleteAllByIdInBatch(List.of(101L, 102L));
        order.verify(auditLogRepository).flush();
        order.verify(auditLogRepository)
                .countByOccurredAtBefore(any(LocalDateTime.class));
        assertThat(response.trigger()).isEqualTo("MANUAL");
        assertThat(response.deletedCount()).isEqualTo(2);
        assertThat(response.remainingEligibleCount()).isEqualTo(3L);
    }

    @Test
    void retentionInspectionKeepsNonLockingCountQuery() {
        when(auditLogRepository.countByOccurredAtBefore(
                any(LocalDateTime.class)
        )).thenReturn(4L);

        var response = service.inspect();

        assertThat(response.eligibleCount()).isEqualTo(4L);
        verify(auditLogRepository).countByOccurredAtBefore(
                any(LocalDateTime.class)
        );
        verify(auditLogRepository, never())
                .findRetentionCandidatesForUpdate(
                        any(LocalDateTime.class),
                        any(Pageable.class)
                );
    }

    private AuditLog auditLog(Long id) {
        AuditLog auditLog = AuditLog.create(
                LocalDateTime.of(2026, 1, 1, 0, 0),
                "system",
                AuditAction.AUDIT_LOG_EXPORTED,
                AuditEntityType.AUDIT_LOG,
                "audit-" + id,
                "retention candidate",
                null,
                null,
                null,
                "trace-" + id
        );
        ReflectionTestUtils.setField(auditLog, "id", id);
        return auditLog;
    }
}
