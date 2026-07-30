package com.visionflow.api.maintenance.service;

import com.visionflow.api.audit.domain.AuditAction;
import com.visionflow.api.audit.domain.AuditEntityType;
import com.visionflow.api.audit.service.AuditLogService;
import com.visionflow.api.incident.domain.Incident;
import com.visionflow.api.incident.domain.IncidentActionHistory;
import com.visionflow.api.incident.domain.IncidentActionType;
import com.visionflow.api.incident.domain.IncidentPriority;
import com.visionflow.api.incident.domain.IncidentStatus;
import com.visionflow.api.incident.dto.IncidentResponse;
import com.visionflow.api.incident.realtime.IncidentRealtimeAction;
import com.visionflow.api.incident.realtime.IncidentRealtimePublisher;
import com.visionflow.api.incident.repository.IncidentActionHistoryRepository;
import com.visionflow.api.incident.repository.IncidentRepository;
import com.visionflow.api.maintenance.domain.MaintenanceSlaStatus;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrder;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrderStatus;
import com.visionflow.api.maintenance.dto.MaintenanceSlaEscalationResultResponse;
import com.visionflow.api.maintenance.repository.MaintenanceWorkOrderRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;

@Service
public class MaintenanceSlaIncidentEscalationService {

    private static final Logger log = LoggerFactory.getLogger(
            MaintenanceSlaIncidentEscalationService.class
    );
    static final String SYSTEM_ACTOR = "SYSTEM_MAINTENANCE_SLA";

    private final MaintenanceWorkOrderRepository workOrderRepository;
    private final IncidentRepository incidentRepository;
    private final IncidentActionHistoryRepository historyRepository;
    private final IncidentRealtimePublisher realtimePublisher;
    private final AuditLogService auditLogService;

    public MaintenanceSlaIncidentEscalationService(
            MaintenanceWorkOrderRepository workOrderRepository,
            IncidentRepository incidentRepository,
            IncidentActionHistoryRepository historyRepository,
            IncidentRealtimePublisher realtimePublisher,
            AuditLogService auditLogService
    ) {
        this.workOrderRepository = workOrderRepository;
        this.incidentRepository = incidentRepository;
        this.historyRepository = historyRepository;
        this.realtimePublisher = realtimePublisher;
        this.auditLogService = auditLogService;
    }

    @Transactional
    public MaintenanceSlaEscalationResultResponse escalateOverdue() {
        return escalateOverdueAt(Instant.now());
    }

    MaintenanceSlaEscalationResultResponse escalateOverdueAt(
            Instant evaluatedAt
    ) {
        List<MaintenanceWorkOrder> candidates =
                workOrderRepository.findActiveForSlaEvaluation(
                        List.of(
                                MaintenanceWorkOrderStatus.OPEN,
                                MaintenanceWorkOrderStatus.IN_PROGRESS
                        )
                );
        int overdue = 0;
        int escalated = 0;
        int alreadyEscalated = 0;
        int skipped = 0;

        for (MaintenanceWorkOrder order : candidates) {
            MaintenanceSlaPolicy.Evaluation sla =
                    MaintenanceSlaPolicy.evaluate(order, evaluatedAt);
            if (sla.status() != MaintenanceSlaStatus.OVERDUE) {
                continue;
            }
            overdue += 1;

            if (
                    historyRepository
                            .existsByIncidentIdAndActionTypeAndActor(
                                    order.getIncidentId(),
                                    IncidentActionType.SLA_ESCALATED,
                                    SYSTEM_ACTOR
                            )
            ) {
                alreadyEscalated += 1;
                continue;
            }

            Incident incident = incidentRepository
                    .findById(order.getIncidentId())
                    .orElse(null);
            if (
                    incident == null
                            || incident.getStatus()
                            == IncidentStatus.CLOSED
            ) {
                skipped += 1;
                log.warn(
                        "정비 SLA Incident 에스컬레이션 생략: "
                                + "workOrderId={}, incidentId={}",
                        order.getId(),
                        order.getIncidentId()
                );
                continue;
            }

            escalate(order, incident, sla, evaluatedAt);
            escalated += 1;
        }

        return new MaintenanceSlaEscalationResultResponse(
                evaluatedAt,
                candidates.size(),
                overdue,
                escalated,
                alreadyEscalated,
                skipped
        );
    }

    private void escalate(
            MaintenanceWorkOrder order,
            Incident incident,
            MaintenanceSlaPolicy.Evaluation sla,
            Instant evaluatedAt
    ) {
        LocalDateTime changedAt = LocalDateTime.ofInstant(
                evaluatedAt,
                ZoneOffset.UTC
        );
        IncidentStatus previousStatus = incident.getStatus();
        IncidentPriority previousPriority = incident.getPriority();

        if (previousStatus == IncidentStatus.RESOLVED) {
            incident.changeStatus(
                    IncidentStatus.IN_PROGRESS,
                    changedAt
            );
        }
        incident.changePriority(IncidentPriority.CRITICAL, changedAt);
        incident = incidentRepository.saveAndFlush(incident);

        String note = "정비 작업 SLA 초과: workOrderId="
                + order.getId()
                + ", overdueMinutes="
                + sla.overdueMinutes()
                + ", priority="
                + previousPriority
                + " -> "
                + incident.getPriority();
        historyRepository.saveAndFlush(
                IncidentActionHistory.create(
                        incident.getId(),
                        IncidentActionType.SLA_ESCALATED,
                        previousStatus,
                        incident.getStatus(),
                        SYSTEM_ACTOR,
                        note
                )
        );

        IncidentResponse response = IncidentResponse.from(incident);
        realtimePublisher.publishAfterCommit(
                IncidentRealtimeAction.SLA_ESCALATED,
                response
        );
        recordAudit(order, response, sla);
    }

    private void recordAudit(
            MaintenanceWorkOrder order,
            IncidentResponse incident,
            MaintenanceSlaPolicy.Evaluation sla
    ) {
        try {
            auditLogService.record(
                    AuditAction.INCIDENT_PRIORITY_CHANGED,
                    AuditEntityType.INCIDENT,
                    incident.id(),
                    "정비 SLA 초과 Incident 자동 에스컬레이션",
                    Map.of(
                            "workOrderId", order.getId(),
                            "droneId", order.getDroneId(),
                            "incidentId", incident.id(),
                            "priority", incident.priority().name(),
                            "status", incident.status().name(),
                            "slaDueAt", sla.dueAt().toString(),
                            "slaOverdueMinutes",
                            sla.overdueMinutes()
                    ),
                    SYSTEM_ACTOR
            );
        } catch (RuntimeException exception) {
            log.error(
                    "정비 SLA Incident 감사 로그 저장 실패: "
                            + "workOrderId={}, incidentId={}",
                    order.getId(),
                    incident.id(),
                    exception
            );
        }
    }
}
