package com.visionflow.api.maintenance.service;

import com.visionflow.api.audit.domain.AuditAction;
import com.visionflow.api.audit.domain.AuditEntityType;
import com.visionflow.api.audit.dto.AuditLogResponse;
import com.visionflow.api.audit.repository.AuditLogRepository;
import com.visionflow.api.audit.service.AuditLogService;
import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.incident.domain.Incident;
import com.visionflow.api.incident.domain.IncidentActionHistory;
import com.visionflow.api.incident.domain.IncidentActionType;
import com.visionflow.api.incident.domain.IncidentPriority;
import com.visionflow.api.incident.domain.IncidentSourceType;
import com.visionflow.api.incident.domain.IncidentStatus;
import com.visionflow.api.incident.dto.IncidentResponse;
import com.visionflow.api.incident.realtime.IncidentRealtimeAction;
import com.visionflow.api.incident.realtime.IncidentRealtimePublisher;
import com.visionflow.api.incident.repository.IncidentActionHistoryRepository;
import com.visionflow.api.incident.repository.IncidentRepository;
import com.visionflow.api.maintenance.config.MaintenanceFlightGateProperties;
import com.visionflow.api.maintenance.dto.MaintenanceFlightClearanceResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.Map;
import java.util.Optional;

@Service
public class FlightGateIncidentAutomationService {

    private static final Logger log = LoggerFactory.getLogger(
            FlightGateIncidentAutomationService.class
    );
    private static final String SYSTEM_ACTOR =
            "system-maintenance-flight-gate";

    private final MaintenanceFlightGateProperties properties;
    private final AuditLogRepository auditLogRepository;
    private final DroneRepository droneRepository;
    private final IncidentRepository incidentRepository;
    private final IncidentActionHistoryRepository historyRepository;
    private final IncidentRealtimePublisher realtimePublisher;
    private final AuditLogService auditLogService;

    public FlightGateIncidentAutomationService(
            MaintenanceFlightGateProperties properties,
            AuditLogRepository auditLogRepository,
            DroneRepository droneRepository,
            IncidentRepository incidentRepository,
            IncidentActionHistoryRepository historyRepository,
            IncidentRealtimePublisher realtimePublisher,
            AuditLogService auditLogService
    ) {
        this.properties = properties;
        this.auditLogRepository = auditLogRepository;
        this.droneRepository = droneRepository;
        this.incidentRepository = incidentRepository;
        this.historyRepository = historyRepository;
        this.realtimePublisher = realtimePublisher;
        this.auditLogService = auditLogService;
    }

    @Transactional(
            propagation = Propagation.REQUIRES_NEW
    )
    public Optional<IncidentResponse> handleBlocked(
            MaintenanceFlightClearanceResponse clearance,
            AuditLogResponse decisionLog
    ) {
        MaintenanceFlightGateProperties.IncidentEscalation settings =
                properties.getIncident();
        if (!settings.isEnabled()) {
            return Optional.empty();
        }

        LocalDateTime occurredAt = LocalDateTime.ofInstant(
                decisionLog.occurredAt(),
                ZoneOffset.UTC
        );
        long recentBlockCount = countRecentBlocks(
                clearance.droneId(),
                occurredAt,
                settings.getWindowMinutes()
        );
        if (recentBlockCount < settings.getThreshold()) {
            return Optional.empty();
        }
        if (
                droneRepository.findByIdForUpdate(clearance.droneId())
                        .isEmpty()
        ) {
            log.warn(
                    "반복 비행 차단 Incident 동기화 대상 드론 없음: "
                            + "droneId={}",
                    clearance.droneId()
            );
            return Optional.empty();
        }

        Optional<Incident> existing = incidentRepository
                .findBySourceTypeAndSourceIdForUpdate(
                        IncidentSourceType.FLIGHT_GATE,
                        clearance.droneId()
                );
        if (existing.isEmpty()) {
            return Optional.of(create(
                    clearance,
                    occurredAt,
                    recentBlockCount,
                    settings
            ));
        }

        Incident incident = existing.get();
        if (isActive(incident.getStatus())) {
            return Optional.of(IncidentResponse.from(incident));
        }

        IncidentStatus previousStatus = incident.getStatus();
        incident.reopenFromFlightGate(
                settings.getPriority(),
                title(clearance.droneId()),
                summary(
                        clearance,
                        recentBlockCount,
                        settings.getWindowMinutes()
                ),
                occurredAt,
                occurredAt
        );
        incident = incidentRepository.saveAndFlush(incident);
        saveHistory(
                incident,
                IncidentActionType.SOURCE_SYNCHRONIZED,
                previousStatus,
                IncidentStatus.OPEN,
                "반복 비행 시작 차단으로 Incident 재개"
        );
        return Optional.of(
                publishAndAudit(
                        incident,
                        IncidentRealtimeAction.SOURCE_SYNCHRONIZED,
                        "REOPENED",
                        recentBlockCount,
                        settings.getWindowMinutes()
                )
        );
    }

    @Transactional(
            propagation = Propagation.REQUIRES_NEW
    )
    public Optional<IncidentResponse> resolveForDrone(
            Long droneId,
            String actor,
            String note
    ) {
        Optional<Incident> existing = incidentRepository
                .findBySourceTypeAndSourceIdForUpdate(
                        IncidentSourceType.FLIGHT_GATE,
                        droneId
                );
        if (existing.isEmpty() || !isActive(existing.get().getStatus())) {
            return Optional.empty();
        }

        Incident incident = existing.get();
        IncidentStatus previousStatus = incident.getStatus();
        LocalDateTime now = nowUtc();
        incident.changeStatus(IncidentStatus.RESOLVED, now);
        incident = incidentRepository.saveAndFlush(incident);
        saveHistory(
                incident,
                IncidentActionType.SOURCE_SYNCHRONIZED,
                previousStatus,
                IncidentStatus.RESOLVED,
                note,
                actor
        );
        return Optional.of(
                publishAndAudit(
                        incident,
                        IncidentRealtimeAction.SOURCE_SYNCHRONIZED,
                        "RESOLVED",
                        null,
                        properties.getIncident().getWindowMinutes()
                )
        );
    }

    private IncidentResponse create(
            MaintenanceFlightClearanceResponse clearance,
            LocalDateTime occurredAt,
            long recentBlockCount,
            MaintenanceFlightGateProperties.IncidentEscalation settings
    ) {
        Incident incident = Incident.create(
                IncidentSourceType.FLIGHT_GATE,
                clearance.droneId(),
                clearance.droneId(),
                null,
                settings.getPriority(),
                IncidentStatus.OPEN,
                title(clearance.droneId()),
                summary(
                        clearance,
                        recentBlockCount,
                        settings.getWindowMinutes()
                ),
                occurredAt,
                null
        );
        incident = incidentRepository.saveAndFlush(incident);
        saveHistory(
                incident,
                IncidentActionType.CREATED,
                null,
                IncidentStatus.OPEN,
                "반복 비행 시작 차단 임계값 도달"
        );
        return publishAndAudit(
                incident,
                IncidentRealtimeAction.CREATED,
                "CREATED",
                recentBlockCount,
                settings.getWindowMinutes()
        );
    }

    private long countRecentBlocks(
            Long droneId,
            LocalDateTime occurredAt,
            int windowMinutes
    ) {
        return auditLogRepository.search(
                        AuditAction.MAINTENANCE_FLIGHT_START_BLOCKED,
                        AuditEntityType.MAINTENANCE_FLIGHT_GATE,
                        String.valueOf(droneId),
                        null,
                        occurredAt.minusMinutes(windowMinutes),
                        occurredAt,
                        PageRequest.of(0, 1)
                )
                .getTotalElements();
    }

    private IncidentResponse publishAndAudit(
            Incident incident,
            IncidentRealtimeAction realtimeAction,
            String synchronizationAction,
            Long recentBlockCount,
            int windowMinutes
    ) {
        IncidentResponse response = IncidentResponse.from(incident);
        realtimePublisher.publishAfterCommit(realtimeAction, response);
        recordAudit(
                response,
                synchronizationAction,
                recentBlockCount,
                windowMinutes
        );
        return response;
    }

    private void saveHistory(
            Incident incident,
            IncidentActionType actionType,
            IncidentStatus previousStatus,
            IncidentStatus newStatus,
            String note
    ) {
        saveHistory(
                incident,
                actionType,
                previousStatus,
                newStatus,
                note,
                SYSTEM_ACTOR
        );
    }

    private void saveHistory(
            Incident incident,
            IncidentActionType actionType,
            IncidentStatus previousStatus,
            IncidentStatus newStatus,
            String note,
            String actor
    ) {
        historyRepository.saveAndFlush(
                IncidentActionHistory.create(
                        incident.getId(),
                        actionType,
                        previousStatus,
                        newStatus,
                        actor,
                        note
                )
        );
    }

    private void recordAudit(
            IncidentResponse incident,
            String synchronizationAction,
            Long recentBlockCount,
            int windowMinutes
    ) {
        try {
            auditLogService.record(
                    AuditAction
                            .MAINTENANCE_FLIGHT_GATE_INCIDENT_SYNCHRONIZED,
                    AuditEntityType.INCIDENT,
                    incident.id(),
                    "비행 게이트 Incident 자동 동기화",
                    Map.of(
                            "droneId", incident.droneId(),
                            "incidentSourceId", incident.sourceId(),
                            "status", incident.status().name(),
                            "action", synchronizationAction,
                            "recentBlockCount",
                            recentBlockCount == null
                                    ? 0L
                                    : recentBlockCount,
                            "windowMinutes", windowMinutes
                    ),
                    SYSTEM_ACTOR
            );
        } catch (RuntimeException exception) {
            log.error(
                    "비행 게이트 Incident 감사 로그 저장 실패: "
                            + "droneId={}, incidentId={}",
                    incident.droneId(),
                    incident.id(),
                    exception
            );
        }
    }

    private String title(Long droneId) {
        return "반복 비행 시작 차단: Drone #" + droneId;
    }

    private String summary(
            MaintenanceFlightClearanceResponse clearance,
            long recentBlockCount,
            int windowMinutes
    ) {
        return windowMinutes
                + "분 내 "
                + recentBlockCount
                + "회 차단 / "
                + clearance.reason();
    }

    private boolean isActive(IncidentStatus status) {
        return status == IncidentStatus.OPEN
                || status == IncidentStatus.IN_PROGRESS;
    }

    private LocalDateTime nowUtc() {
        return LocalDateTime.now(ZoneOffset.UTC);
    }
}
