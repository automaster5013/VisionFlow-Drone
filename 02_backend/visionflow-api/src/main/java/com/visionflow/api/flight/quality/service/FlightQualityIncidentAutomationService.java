package com.visionflow.api.flight.quality.service;

import com.visionflow.api.audit.domain.AuditAction;
import com.visionflow.api.audit.domain.AuditEntityType;
import com.visionflow.api.audit.service.AuditLogService;
import com.visionflow.api.common.exception.ResourceNotFoundException;
import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.flight.quality.domain.FleetReliabilityStatus;
import com.visionflow.api.flight.quality.domain.FlightQualityIncidentSyncAction;
import com.visionflow.api.flight.quality.domain.FlightQualitySeverity;
import com.visionflow.api.flight.quality.dto.DroneReliabilityResponse;
import com.visionflow.api.flight.quality.dto.FleetReliabilityResponse;
import com.visionflow.api.flight.quality.dto.FlightQualityIncidentSyncItemResponse;
import com.visionflow.api.flight.quality.dto.FlightQualityIncidentSyncResponse;
import com.visionflow.api.flight.quality.dto.FlightQualityRiskResponse;
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
import com.visionflow.api.maintenance.service.MaintenanceWorkOrderService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;

@Service
public class FlightQualityIncidentAutomationService {

    public static final int DEFAULT_LIMIT_PER_DRONE = 20;

    private static final Logger log = LoggerFactory.getLogger(
            FlightQualityIncidentAutomationService.class
    );
    private static final String SYSTEM_ACTOR =
            "system-flight-quality-incident";

    private final FleetReliabilityService reliabilityService;
    private final DroneRepository droneRepository;
    private final IncidentRepository incidentRepository;
    private final IncidentActionHistoryRepository historyRepository;
    private final IncidentRealtimePublisher realtimePublisher;
    private final AuditLogService auditLogService;
    private final MaintenanceWorkOrderService maintenanceWorkOrderService;

    public FlightQualityIncidentAutomationService(
            FleetReliabilityService reliabilityService,
            DroneRepository droneRepository,
            IncidentRepository incidentRepository,
            IncidentActionHistoryRepository historyRepository,
            IncidentRealtimePublisher realtimePublisher,
            AuditLogService auditLogService,
            MaintenanceWorkOrderService maintenanceWorkOrderService
    ) {
        this.reliabilityService = reliabilityService;
        this.droneRepository = droneRepository;
        this.incidentRepository = incidentRepository;
        this.historyRepository = historyRepository;
        this.realtimePublisher = realtimePublisher;
        this.auditLogService = auditLogService;
        this.maintenanceWorkOrderService = maintenanceWorkOrderService;
    }

    @Transactional
    public FlightQualityIncidentSyncResponse synchronizeFleet(
            int limitPerDrone
    ) {
        FleetReliabilityResponse fleet =
                reliabilityService.summarize(limitPerDrone);
        List<FlightQualityIncidentSyncItemResponse> items =
                new ArrayList<>(fleet.drones().size());

        for (DroneReliabilityResponse reliability : fleet.drones()) {
            items.add(synchronizeReliability(reliability));
        }

        return FlightQualityIncidentSyncResponse.from(
                limitPerDrone,
                items
        );
    }

    @Transactional
    public FlightQualityIncidentSyncItemResponse synchronizeDrone(
            Long droneId,
            int limitPerDrone
    ) {
        DroneReliabilityResponse reliability = reliabilityService
                .summarizeDrone(droneId, limitPerDrone)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "기체 품질 평가를 찾을 수 없습니다: " + droneId
                ));
        return synchronizeReliability(reliability);
    }

    private FlightQualityIncidentSyncItemResponse synchronizeReliability(
            DroneReliabilityResponse reliability
    ) {
        droneRepository.findByIdForUpdate(reliability.droneId())
                .orElseThrow(() -> new ResourceNotFoundException(
                        "드론을 찾을 수 없습니다: " + reliability.droneId()
                ));

        Optional<Incident> existing = incidentRepository
                .findBySourceTypeAndSourceIdForUpdate(
                        IncidentSourceType.FLIGHT_QUALITY,
                        reliability.droneId()
                );

        if (
                reliability.status() == FleetReliabilityStatus.STABLE
                        && existing.isEmpty()
        ) {
            return result(
                    reliability,
                    FlightQualityIncidentSyncAction.SKIPPED_STABLE,
                    null
            );
        }

        if (existing.isEmpty()) {
            return create(reliability);
        }

        return update(existing.get(), reliability);
    }

    private FlightQualityIncidentSyncItemResponse create(
            DroneReliabilityResponse reliability
    ) {
        Incident incident = Incident.create(
                IncidentSourceType.FLIGHT_QUALITY,
                reliability.droneId(),
                reliability.droneId(),
                reliability.latestAssessment().sessionId(),
                priority(reliability),
                IncidentStatus.OPEN,
                title(reliability),
                summary(reliability),
                occurredAt(reliability),
                null
        );
        incident = incidentRepository.saveAndFlush(incident);
        saveHistory(
                incident,
                null,
                IncidentStatus.OPEN,
                "기체 신뢰도 "
                        + reliability.status()
                        + " 상태에서 자동 생성"
        );
        maintenanceWorkOrderService.synchronizeRequired(
                incident,
                reliability.latestAssessment().id()
        );
        IncidentResponse response = IncidentResponse.from(incident);
        realtimePublisher.publishAfterCommit(
                IncidentRealtimeAction.CREATED,
                response
        );
        recordAudit(
                response,
                reliability,
                FlightQualityIncidentSyncAction.CREATED
        );
        return result(
                reliability,
                FlightQualityIncidentSyncAction.CREATED,
                response
        );
    }

    private FlightQualityIncidentSyncItemResponse update(
            Incident incident,
            DroneReliabilityResponse reliability
    ) {
        IncidentStatus previousStatus = incident.getStatus();
        IncidentStatus nextStatus = nextStatus(
                previousStatus,
                reliability.status()
        );

        if (
                reliability.status() == FleetReliabilityStatus.STABLE
                        && previousStatus != IncidentStatus.OPEN
                        && previousStatus != IncidentStatus.IN_PROGRESS
        ) {
            return result(
                    reliability,
                    FlightQualityIncidentSyncAction.SKIPPED_STABLE,
                    IncidentResponse.from(incident)
            );
        }

        IncidentPriority nextPriority =
                reliability.status() == FleetReliabilityStatus.STABLE
                        ? incident.getPriority()
                        : preserveRaisedPriority(
                                incident.getPriority(),
                                priority(reliability),
                                previousStatus
                        );
        boolean changed = incident.synchronizeFlightQuality(
                reliability.latestAssessment().sessionId(),
                nextPriority,
                nextStatus,
                title(reliability),
                summary(reliability),
                occurredAt(reliability),
                nowUtc()
        );
        FlightQualityIncidentSyncAction action = action(
                previousStatus,
                nextStatus,
                reliability.status()
        );

        if (!changed) {
            if (reliability.status() != FleetReliabilityStatus.STABLE) {
                maintenanceWorkOrderService.synchronizeRequired(
                        incident,
                        reliability.latestAssessment().id()
                );
            }
            return result(
                    reliability,
                    reliability.status() == FleetReliabilityStatus.STABLE
                            ? FlightQualityIncidentSyncAction.SKIPPED_STABLE
                            : FlightQualityIncidentSyncAction.DEDUPLICATED,
                    IncidentResponse.from(incident)
            );
        }

        incident = incidentRepository.saveAndFlush(incident);
        if (reliability.status() != FleetReliabilityStatus.STABLE) {
            maintenanceWorkOrderService.synchronizeRequired(
                    incident,
                    reliability.latestAssessment().id()
            );
        }
        saveHistory(
                incident,
                previousStatus,
                nextStatus,
                historyNote(reliability, action)
        );
        IncidentResponse response = IncidentResponse.from(incident);
        realtimePublisher.publishAfterCommit(
                IncidentRealtimeAction.SOURCE_SYNCHRONIZED,
                response
        );
        recordAudit(response, reliability, action);
        return result(reliability, action, response);
    }

    private void saveHistory(
            Incident incident,
            IncidentStatus previousStatus,
            IncidentStatus nextStatus,
            String note
    ) {
        historyRepository.saveAndFlush(
                IncidentActionHistory.create(
                        incident.getId(),
                        previousStatus == null
                                ? IncidentActionType.CREATED
                                : IncidentActionType.SOURCE_SYNCHRONIZED,
                        previousStatus,
                        nextStatus,
                        SYSTEM_ACTOR,
                        note
                )
        );
    }

    private void recordAudit(
            IncidentResponse incident,
            DroneReliabilityResponse reliability,
            FlightQualityIncidentSyncAction action
    ) {
        try {
            auditLogService.record(
                    AuditAction.FLIGHT_QUALITY_INCIDENT_SYNCHRONIZED,
                    AuditEntityType.INCIDENT,
                    incident.id(),
                    "기체 신뢰도 Incident 자동 동기화",
                    Map.of(
                            "droneId", reliability.droneId(),
                            "status", reliability.status().name(),
                            "action", action.name(),
                            "latestScore", reliability.latestScore(),
                            "averageScore", reliability.averageScore(),
                            "sourceAssessmentId",
                            reliability.latestAssessment().id()
                    ),
                    SYSTEM_ACTOR
            );
        } catch (RuntimeException exception) {
            log.error(
                    "기체 신뢰도 Incident 감사 로그 저장 실패: "
                            + "droneId={}, incidentId={}",
                    reliability.droneId(),
                    incident.id(),
                    exception
            );
        }
    }

    private IncidentStatus nextStatus(
            IncidentStatus current,
            FleetReliabilityStatus reliability
    ) {
        if (reliability == FleetReliabilityStatus.STABLE) {
            return IncidentStatus.RESOLVED;
        }
        if (
                current == IncidentStatus.OPEN
                        || current == IncidentStatus.IN_PROGRESS
        ) {
            return current;
        }
        return IncidentStatus.OPEN;
    }

    private FlightQualityIncidentSyncAction action(
            IncidentStatus previousStatus,
            IncidentStatus nextStatus,
            FleetReliabilityStatus reliability
    ) {
        if (reliability == FleetReliabilityStatus.STABLE) {
            return FlightQualityIncidentSyncAction.RESOLVED;
        }
        if (
                previousStatus == IncidentStatus.RESOLVED
                        || previousStatus == IncidentStatus.CLOSED
        ) {
            return FlightQualityIncidentSyncAction.REOPENED;
        }
        return FlightQualityIncidentSyncAction.UPDATED;
    }

    private IncidentPriority priority(
            DroneReliabilityResponse reliability
    ) {
        if (reliability.status() == FleetReliabilityStatus.WATCH) {
            return IncidentPriority.MEDIUM;
        }
        FlightQualityRiskResponse risk =
                reliability.latestAssessment().primaryRisk();
        if (
                reliability.criticalCount() > 0
                        || (
                                risk != null
                                        && risk.severity()
                                        == FlightQualitySeverity.CRITICAL
                        )
        ) {
            return IncidentPriority.CRITICAL;
        }
        return IncidentPriority.HIGH;
    }

    private IncidentPriority preserveRaisedPriority(
            IncidentPriority current,
            IncidentPriority calculated,
            IncidentStatus currentStatus
    ) {
        if (
                currentStatus != IncidentStatus.OPEN
                        && currentStatus != IncidentStatus.IN_PROGRESS
        ) {
            return calculated;
        }
        return priorityRank(current) >= priorityRank(calculated)
                ? current
                : calculated;
    }

    private int priorityRank(IncidentPriority priority) {
        return switch (priority) {
            case LOW -> 0;
            case MEDIUM -> 1;
            case HIGH -> 2;
            case CRITICAL -> 3;
        };
    }

    private String title(DroneReliabilityResponse reliability) {
        String identity = reliability.droneName() != null
                ? reliability.droneName()
                : reliability.droneCode() != null
                ? reliability.droneCode()
                : "Drone #" + reliability.droneId();
        return "기체 신뢰도 점검: " + identity;
    }

    private String summary(DroneReliabilityResponse reliability) {
        FlightQualityRiskResponse risk =
                reliability.latestAssessment().primaryRisk();
        String riskSummary = risk == null
                ? "주요 위험 없음"
                : risk.title() + " - " + risk.detail();
        return "상태 "
                + reliability.status()
                + " / 최근 "
                + reliability.latestScore()
                + "점 / 평균 "
                + reliability.averageScore()
                + "점 / "
                + riskSummary;
    }

    private String historyNote(
            DroneReliabilityResponse reliability,
            FlightQualityIncidentSyncAction action
    ) {
        return "신뢰도 자동 동기화: action="
                + action
                + ", status="
                + reliability.status()
                + ", latestScore="
                + reliability.latestScore()
                + ", averageScore="
                + reliability.averageScore()
                + ", sessionId="
                + reliability.latestAssessment().sessionId();
    }

    private LocalDateTime occurredAt(
            DroneReliabilityResponse reliability
    ) {
        return LocalDateTime.ofInstant(
                reliability.latestAssessment().evaluatedAt(),
                ZoneOffset.UTC
        );
    }

    private LocalDateTime nowUtc() {
        return LocalDateTime.now(ZoneOffset.UTC);
    }

    private FlightQualityIncidentSyncItemResponse result(
            DroneReliabilityResponse reliability,
            FlightQualityIncidentSyncAction action,
            IncidentResponse incident
    ) {
        return new FlightQualityIncidentSyncItemResponse(
                reliability.droneId(),
                reliability.status(),
                action,
                incident
        );
    }
}
