package com.visionflow.api.maintenance.service;

import com.visionflow.api.audit.service.AuditLogService;
import com.visionflow.api.incident.domain.Incident;
import com.visionflow.api.incident.domain.IncidentActionHistory;
import com.visionflow.api.incident.domain.IncidentActionType;
import com.visionflow.api.incident.domain.IncidentPriority;
import com.visionflow.api.incident.domain.IncidentStatus;
import com.visionflow.api.incident.realtime.IncidentRealtimeAction;
import com.visionflow.api.incident.realtime.IncidentRealtimePublisher;
import com.visionflow.api.incident.repository.IncidentActionHistoryRepository;
import com.visionflow.api.incident.repository.IncidentRepository;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrder;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrderStatus;
import com.visionflow.api.maintenance.dto.MaintenanceSlaEscalationResultResponse;
import com.visionflow.api.maintenance.repository.MaintenanceWorkOrderRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class MaintenanceSlaIncidentEscalationServiceTests {

    @Mock
    private MaintenanceWorkOrderRepository workOrderRepository;

    @Mock
    private IncidentRepository incidentRepository;

    @Mock
    private IncidentActionHistoryRepository historyRepository;

    @Mock
    private IncidentRealtimePublisher realtimePublisher;

    @Mock
    private AuditLogService auditLogService;

    @InjectMocks
    private MaintenanceSlaIncidentEscalationService service;

    @Test
    void escalatesOverdueWorkOrderIncidentOnlyOnce() {
        Instant now = Instant.parse("2026-07-26T12:00:00Z");
        MaintenanceWorkOrder order = order(
                51L,
                501L,
                now.minusSeconds(3 * 60 * 60L)
        );
        Incident incident = incident(
                501L,
                IncidentStatus.OPEN,
                IncidentPriority.HIGH
        );
        when(workOrderRepository.findActiveForSlaEvaluation(any()))
                .thenReturn(List.of(order));
        when(historyRepository
                .existsByIncidentIdAndActionTypeAndActor(
                        501L,
                        IncidentActionType.SLA_ESCALATED,
                        MaintenanceSlaIncidentEscalationService.SYSTEM_ACTOR
                ))
                .thenReturn(false);
        when(incidentRepository.findByIdForUpdate(501L))
                .thenReturn(Optional.of(incident));
        when(incidentRepository.saveAndFlush(incident))
                .thenReturn(incident);

        MaintenanceSlaEscalationResultResponse result =
                service.escalateOverdueAt(now);

        assertThat(result.scannedWorkOrders()).isEqualTo(1);
        assertThat(result.overdueWorkOrders()).isEqualTo(1);
        assertThat(result.escalatedIncidents()).isEqualTo(1);
        assertThat(result.alreadyEscalatedIncidents()).isZero();
        assertThat(result.skippedIncidents()).isZero();
        verify(incident).changePriority(
                IncidentPriority.CRITICAL,
                LocalDateTime.ofInstant(now, ZoneOffset.UTC)
        );
        verify(realtimePublisher).publishAfterCommit(
                eq(IncidentRealtimeAction.SLA_ESCALATED),
                any()
        );

        ArgumentCaptor<IncidentActionHistory> historyCaptor =
                ArgumentCaptor.forClass(IncidentActionHistory.class);
        verify(historyRepository).saveAndFlush(
                historyCaptor.capture()
        );
        assertThat(historyCaptor.getValue().getActionType())
                .isEqualTo(IncidentActionType.SLA_ESCALATED);
        assertThat(historyCaptor.getValue().getActor())
                .isEqualTo(
                        MaintenanceSlaIncidentEscalationService.SYSTEM_ACTOR
                );
    }

    @Test
    void reopensResolvedIncidentWhenMaintenanceSlaIsOverdue() {
        Instant now = Instant.parse("2026-07-26T12:00:00Z");
        MaintenanceWorkOrder order = order(
                52L,
                502L,
                now.minusSeconds(3 * 60 * 60L)
        );
        Incident incident = incident(
                502L,
                IncidentStatus.RESOLVED,
                IncidentPriority.MEDIUM
        );
        when(workOrderRepository.findActiveForSlaEvaluation(any()))
                .thenReturn(List.of(order));
        when(historyRepository
                .existsByIncidentIdAndActionTypeAndActor(
                        502L,
                        IncidentActionType.SLA_ESCALATED,
                        MaintenanceSlaIncidentEscalationService.SYSTEM_ACTOR
                ))
                .thenReturn(false);
        when(incidentRepository.findByIdForUpdate(502L))
                .thenReturn(Optional.of(incident));
        when(incidentRepository.saveAndFlush(incident))
                .thenReturn(incident);

        MaintenanceSlaEscalationResultResponse result =
                service.escalateOverdueAt(now);

        assertThat(result.escalatedIncidents()).isEqualTo(1);
        verify(incident).changeStatus(
                IncidentStatus.IN_PROGRESS,
                LocalDateTime.ofInstant(now, ZoneOffset.UTC)
        );
        verify(incident).changePriority(
                IncidentPriority.CRITICAL,
                LocalDateTime.ofInstant(now, ZoneOffset.UTC)
        );
    }

    @Test
    void skipsIncidentAlreadyEscalatedByMaintenanceSla() {
        Instant now = Instant.parse("2026-07-26T12:00:00Z");
        MaintenanceWorkOrder order = order(
                53L,
                503L,
                now.minusSeconds(3 * 60 * 60L)
        );
        Incident incident = incident(
                503L,
                IncidentStatus.OPEN,
                IncidentPriority.CRITICAL
        );
        when(workOrderRepository.findActiveForSlaEvaluation(any()))
                .thenReturn(List.of(order));
        when(incidentRepository.findByIdForUpdate(503L))
                .thenReturn(Optional.of(incident));
        when(historyRepository
                .existsByIncidentIdAndActionTypeAndActor(
                        503L,
                        IncidentActionType.SLA_ESCALATED,
                        MaintenanceSlaIncidentEscalationService.SYSTEM_ACTOR
                ))
                .thenReturn(true);

        MaintenanceSlaEscalationResultResponse result =
                service.escalateOverdueAt(now);

        assertThat(result.escalatedIncidents()).isZero();
        assertThat(result.alreadyEscalatedIncidents()).isEqualTo(1);
        verify(incidentRepository).findByIdForUpdate(503L);
        verify(realtimePublisher, never()).publishAfterCommit(
                any(),
                any()
        );
    }

    @Test
    void ignoresWorkOrderStillWithinSla() {
        Instant now = Instant.parse("2026-07-26T12:00:00Z");
        MaintenanceWorkOrder order = order(
                54L,
                504L,
                now.minusSeconds(60 * 60L)
        );
        when(workOrderRepository.findActiveForSlaEvaluation(any()))
                .thenReturn(List.of(order));

        MaintenanceSlaEscalationResultResponse result =
                service.escalateOverdueAt(now);

        assertThat(result.overdueWorkOrders()).isZero();
        assertThat(result.escalatedIncidents()).isZero();
        verify(historyRepository, never())
                .existsByIncidentIdAndActionTypeAndActor(
                        any(),
                        any(),
                        any()
                );
    }

    private MaintenanceWorkOrder order(
            Long id,
            Long incidentId,
            Instant openedAt
    ) {
        MaintenanceWorkOrder order =
                org.mockito.Mockito.mock(MaintenanceWorkOrder.class);
        lenient().when(order.getId()).thenReturn(id);
        lenient().when(order.getIncidentId()).thenReturn(incidentId);
        lenient().when(order.getDroneId()).thenReturn(id);
        lenient().when(order.getStatus())
                .thenReturn(MaintenanceWorkOrderStatus.OPEN);
        lenient().when(order.getOpenedAt()).thenReturn(
                LocalDateTime.ofInstant(openedAt, ZoneOffset.UTC)
        );
        return order;
    }

    private Incident incident(
            Long id,
            IncidentStatus initialStatus,
            IncidentPriority initialPriority
    ) {
        Incident incident =
                org.mockito.Mockito.mock(Incident.class);
        AtomicReference<IncidentStatus> status =
                new AtomicReference<>(initialStatus);
        AtomicReference<IncidentPriority> priority =
                new AtomicReference<>(initialPriority);

        lenient().when(incident.getId()).thenReturn(id);
        lenient().when(incident.getDroneId()).thenReturn(id);
        lenient().when(incident.getStatus()).thenAnswer(
                ignored -> status.get()
        );
        lenient().when(incident.getPriority()).thenAnswer(
                ignored -> priority.get()
        );
        lenient().when(incident.changeStatus(any(), any()))
                .thenAnswer(call -> {
                    status.set(call.getArgument(0));
                    return true;
                });
        lenient().when(incident.changePriority(any(), any()))
                .thenAnswer(call -> {
                    priority.set(call.getArgument(0));
                    return true;
                });
        return incident;
    }
}
