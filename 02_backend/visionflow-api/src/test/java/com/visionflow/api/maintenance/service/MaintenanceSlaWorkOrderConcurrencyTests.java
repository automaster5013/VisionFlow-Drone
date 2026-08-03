package com.visionflow.api.maintenance.service;

import com.visionflow.api.audit.service.AuditLogService;
import com.visionflow.api.incident.domain.Incident;
import com.visionflow.api.incident.domain.IncidentPriority;
import com.visionflow.api.incident.domain.IncidentStatus;
import com.visionflow.api.incident.realtime.IncidentRealtimePublisher;
import com.visionflow.api.incident.repository.IncidentActionHistoryRepository;
import com.visionflow.api.incident.repository.IncidentRepository;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrder;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrderStatus;
import com.visionflow.api.maintenance.dto.MaintenanceSlaEscalationResultResponse;
import com.visionflow.api.maintenance.repository.MaintenanceWorkOrderRepository;
import jakarta.persistence.LockModeType;
import org.junit.jupiter.api.Test;
import org.mockito.InOrder;
import org.springframework.data.jpa.repository.Lock;

import java.lang.reflect.Method;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.Collection;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class MaintenanceSlaWorkOrderConcurrencyTests {

    private final MaintenanceWorkOrderRepository workOrderRepository =
            mock(MaintenanceWorkOrderRepository.class);
    private final IncidentRepository incidentRepository =
            mock(IncidentRepository.class);
    private final IncidentActionHistoryRepository historyRepository =
            mock(IncidentActionHistoryRepository.class);
    private final IncidentRealtimePublisher realtimePublisher =
            mock(IncidentRealtimePublisher.class);
    private final AuditLogService auditLogService =
            mock(AuditLogService.class);
    private final MaintenanceSlaIncidentEscalationService service =
            new MaintenanceSlaIncidentEscalationService(
                    workOrderRepository,
                    incidentRepository,
                    historyRepository,
                    realtimePublisher,
                    auditLogService
            );

    @Test
    void candidateScanRemainsNonLockingAndMutationReloadUsesWriteLock()
            throws NoSuchMethodException {
        Method candidateScan = MaintenanceWorkOrderRepository.class
                .getMethod(
                        "findActiveIdsForSlaEvaluation",
                        Collection.class
                );
        Method mutationReload = MaintenanceWorkOrderRepository.class
                .getMethod("findByIdForUpdate", Long.class);

        assertThat(candidateScan.getAnnotation(Lock.class)).isNull();
        Lock lock = mutationReload.getAnnotation(Lock.class);
        assertThat(lock).isNotNull();
        assertThat(lock.value()).isEqualTo(
                LockModeType.PESSIMISTIC_WRITE
        );
    }

    @Test
    void locksIncidentThenReloadsWorkOrderBeforeSlaSideEffects() {
        Instant now = Instant.parse("2026-08-04T06:00:00Z");
        MaintenanceWorkOrder order = order(
                701L,
                801L,
                MaintenanceWorkOrderStatus.OPEN,
                now.minusSeconds(3 * 60 * 60L)
        );
        Incident incident = incident(801L);
        stubCandidate(order, incident);
        when(historyRepository
                .existsByIncidentIdAndActionTypeAndActor(
                        any(),
                        any(),
                        any()
                ))
                .thenReturn(false);
        when(incidentRepository.saveAndFlush(incident))
                .thenReturn(incident);

        service.escalateOverdueAt(now);

        InOrder locking = inOrder(
                workOrderRepository,
                incidentRepository
        );
        locking.verify(workOrderRepository)
                .findActiveIdsForSlaEvaluation(any());
        locking.verify(workOrderRepository).findIncidentIdById(701L);
        locking.verify(incidentRepository).findByIdForUpdate(801L);
        locking.verify(workOrderRepository).findByIdForUpdate(701L);
        verify(historyRepository)
                .existsByIncidentIdAndActionTypeAndActor(
                        any(),
                        any(),
                        any()
                );
    }

    @Test
    void completedWorkOrderAfterCandidateScanIsNotEscalated() {
        Instant now = Instant.parse("2026-08-04T06:00:00Z");
        MaintenanceWorkOrder completed = order(
                702L,
                802L,
                MaintenanceWorkOrderStatus.COMPLETED,
                now.minusSeconds(3 * 60 * 60L)
        );
        Incident incident = incident(802L);
        stubCandidate(completed, incident);

        MaintenanceSlaEscalationResultResponse result =
                service.escalateOverdueAt(now);

        assertThat(result.scannedWorkOrders()).isEqualTo(1);
        assertThat(result.overdueWorkOrders()).isZero();
        assertThat(result.escalatedIncidents()).isZero();
        verify(incidentRepository, never()).saveAndFlush(any());
        verify(historyRepository, never()).saveAndFlush(any());
        verify(realtimePublisher, never()).publishAfterCommit(
                any(),
                any()
        );
    }

    private void stubCandidate(
            MaintenanceWorkOrder order,
            Incident incident
    ) {
        Long workOrderId = order.getId();
        Long incidentId = order.getIncidentId();
        when(workOrderRepository.findActiveIdsForSlaEvaluation(any()))
                .thenReturn(List.of(workOrderId));
        when(workOrderRepository.findIncidentIdById(workOrderId))
                .thenReturn(Optional.of(incidentId));
        when(incidentRepository.findByIdForUpdate(incidentId))
                .thenReturn(Optional.of(incident));
        when(workOrderRepository.findByIdForUpdate(workOrderId))
                .thenReturn(Optional.of(order));
    }

    private MaintenanceWorkOrder order(
            Long id,
            Long incidentId,
            MaintenanceWorkOrderStatus status,
            Instant openedAt
    ) {
        MaintenanceWorkOrder order = mock(MaintenanceWorkOrder.class);
        lenient().when(order.getId()).thenReturn(id);
        lenient().when(order.getIncidentId()).thenReturn(incidentId);
        lenient().when(order.getDroneId()).thenReturn(id);
        lenient().when(order.getStatus()).thenReturn(status);
        lenient().when(order.getOpenedAt()).thenReturn(
                LocalDateTime.ofInstant(openedAt, ZoneOffset.UTC)
        );
        return order;
    }

    private Incident incident(Long id) {
        Incident incident = mock(Incident.class);
        lenient().when(incident.getId()).thenReturn(id);
        lenient().when(incident.getDroneId()).thenReturn(id);
        lenient().when(incident.getStatus())
                .thenReturn(IncidentStatus.OPEN);
        lenient().when(incident.getPriority())
                .thenReturn(IncidentPriority.HIGH);
        return incident;
    }
}
