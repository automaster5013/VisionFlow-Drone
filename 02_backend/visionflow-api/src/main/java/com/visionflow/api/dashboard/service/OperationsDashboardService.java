package com.visionflow.api.dashboard.service;

import com.visionflow.api.ai.domain.AiInferenceEvent;
import com.visionflow.api.ai.repository.AiInferenceEventRepository;
import com.visionflow.api.audit.domain.AuditAction;
import com.visionflow.api.audit.domain.AuditEntityType;
import com.visionflow.api.audit.domain.AuditLog;
import com.visionflow.api.audit.repository.AuditLogRepository;
import com.visionflow.api.dashboard.dto.OperationsDashboardResponse;
import com.visionflow.api.dashboard.dto.OperationsDashboardResponse.AiAlertItem;
import com.visionflow.api.dashboard.dto.OperationsDashboardResponse.AiInferenceStatistics;
import com.visionflow.api.dashboard.dto.OperationsDashboardResponse.DashboardFilters;
import com.visionflow.api.dashboard.dto.OperationsDashboardResponse.FlightGateDecisionItem;
import com.visionflow.api.dashboard.dto.OperationsDashboardResponse.FlightGateStatistics;
import com.visionflow.api.dashboard.dto.OperationsDashboardResponse.FlightSessionItem;
import com.visionflow.api.dashboard.dto.OperationsDashboardResponse.FlightSessionStatistics;
import com.visionflow.api.flight.domain.FlightSession;
import com.visionflow.api.flight.domain.FlightSessionStatus;
import com.visionflow.api.flight.repository.FlightSessionRepository;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;

@Service
public class OperationsDashboardService {

    private static final int MIN_LIMIT = 1;
    private static final int MAX_LIMIT = 20;

    private final FlightSessionRepository flightSessionRepository;
    private final AiInferenceEventRepository aiInferenceEventRepository;
    private final AuditLogRepository auditLogRepository;

    public OperationsDashboardService(
            FlightSessionRepository flightSessionRepository,
            AiInferenceEventRepository aiInferenceEventRepository,
            AuditLogRepository auditLogRepository
    ) {
        this.flightSessionRepository = flightSessionRepository;
        this.aiInferenceEventRepository = aiInferenceEventRepository;
        this.auditLogRepository = auditLogRepository;
    }

    @Transactional(readOnly = true)
    public OperationsDashboardResponse findOperations(int requestedLimit) {
        return findOperations(
                null,
                null,
                null,
                null,
                requestedLimit
        );
    }

    @Transactional(readOnly = true)
    public OperationsDashboardResponse findOperations(
            Long droneId,
            FlightSessionStatus status,
            Instant from,
            Instant to,
            int requestedLimit
    ) {
        ensureValidRange(from, to);

        int limit = Math.max(
                MIN_LIMIT,
                Math.min(requestedLimit, MAX_LIMIT)
        );
        PageRequest pageRequest = PageRequest.of(0, limit);
        Instant generatedAt = Instant.now();

        LocalDateTime sessionFrom = toLocalDateTime(
                from,
                ZoneId.systemDefault()
        );
        LocalDateTime sessionTo = toLocalDateTime(
                to,
                ZoneId.systemDefault()
        );
        LocalDateTime aiFrom = toLocalDateTime(from, ZoneOffset.UTC);
        LocalDateTime aiTo = toLocalDateTime(to, ZoneOffset.UTC);
        String gateEntityId =
                droneId == null ? null : String.valueOf(droneId);

        FlightSessionStatistics flightSessionStatistics =
                new FlightSessionStatistics(
                        countSessions(
                                droneId,
                                status,
                                sessionFrom,
                                sessionTo
                        ),
                        countSessionsForStatus(
                                droneId,
                                status,
                                FlightSessionStatus.READY,
                                sessionFrom,
                                sessionTo
                        ),
                        countSessionsForStatus(
                                droneId,
                                status,
                                FlightSessionStatus.ACTIVE,
                                sessionFrom,
                                sessionTo
                        ),
                        countSessionsForStatus(
                                droneId,
                                status,
                                FlightSessionStatus.COMPLETED,
                                sessionFrom,
                                sessionTo
                        ),
                        countSessionsForStatus(
                                droneId,
                                status,
                                FlightSessionStatus.ABORTED,
                                sessionFrom,
                                sessionTo
                        )
                );

        Long summedDetections =
                aiInferenceEventRepository.sumDashboardDetections(
                        droneId,
                        aiFrom,
                        aiTo
                );
        AiInferenceStatistics aiInferenceStatistics =
                new AiInferenceStatistics(
                        aiInferenceEventRepository.countDashboardEvents(
                                droneId,
                                aiFrom,
                                aiTo
                        ),
                        aiInferenceEventRepository
                                .countDashboardDetectedEvents(
                                        droneId,
                                        aiFrom,
                                        aiTo
                                ),
                        summedDetections == null ? 0L : summedDetections
                );

        FlightGateStatistics flightGateStatistics =
                new FlightGateStatistics(
                        countFlightGateDecisions(
                                null,
                                gateEntityId,
                                aiFrom,
                                aiTo
                        ),
                        countFlightGateDecisions(
                                AuditAction.MAINTENANCE_FLIGHT_START_ALLOWED,
                                gateEntityId,
                                aiFrom,
                                aiTo
                        ),
                        countFlightGateDecisions(
                                AuditAction.MAINTENANCE_FLIGHT_START_ADVISORY,
                                gateEntityId,
                                aiFrom,
                                aiTo
                        ),
                        countFlightGateDecisions(
                                AuditAction.MAINTENANCE_FLIGHT_START_BLOCKED,
                                gateEntityId,
                                aiFrom,
                                aiTo
                        )
                );

        List<FlightSessionItem> recentSessions =
                flightSessionRepository.findDashboardSessions(
                                droneId,
                                status,
                                sessionFrom,
                                sessionTo,
                                pageRequest
                        )
                        .stream()
                        .map(session -> toFlightSessionItem(
                                session,
                                generatedAt
                        ))
                        .toList();

        List<FlightSessionItem> recentAbortedSessions =
                findRecentAbortedSessions(
                        droneId,
                        status,
                        sessionFrom,
                        sessionTo,
                        pageRequest,
                        generatedAt
                );

        List<AiAlertItem> recentAiAlerts =
                aiInferenceEventRepository.findDashboardAlerts(
                                droneId,
                                aiFrom,
                                aiTo,
                                pageRequest
                        )
                        .stream()
                        .map(this::toAiAlertItem)
                        .toList();

        PageRequest auditPageRequest = PageRequest.of(
                0,
                limit,
                Sort.by(Sort.Direction.DESC, "occurredAt")
                        .and(Sort.by(Sort.Direction.DESC, "id"))
        );
        List<FlightGateDecisionItem> recentFlightGateDecisions =
                auditLogRepository.search(
                                null,
                                AuditEntityType.MAINTENANCE_FLIGHT_GATE,
                                gateEntityId,
                                null,
                                aiFrom,
                                aiTo,
                                auditPageRequest
                        )
                        .getContent()
                        .stream()
                        .map(this::toFlightGateDecisionItem)
                        .toList();

        return new OperationsDashboardResponse(
                generatedAt,
                new DashboardFilters(
                        droneId,
                        status == null ? null : status.name(),
                        from,
                        to,
                        limit
                ),
                flightSessionStatistics,
                aiInferenceStatistics,
                flightGateStatistics,
                recentSessions,
                recentAbortedSessions,
                recentAiAlerts,
                recentFlightGateDecisions
        );
    }

    private long countFlightGateDecisions(
            AuditAction action,
            String entityId,
            LocalDateTime from,
            LocalDateTime to
    ) {
        return auditLogRepository.search(
                        action,
                        AuditEntityType.MAINTENANCE_FLIGHT_GATE,
                        entityId,
                        null,
                        from,
                        to,
                        PageRequest.of(0, 1)
                )
                .getTotalElements();
    }

    private long countSessions(
            Long droneId,
            FlightSessionStatus status,
            LocalDateTime from,
            LocalDateTime to
    ) {
        return flightSessionRepository.countDashboardSessions(
                droneId,
                status,
                from,
                to
        );
    }

    private long countSessionsForStatus(
            Long droneId,
            FlightSessionStatus requestedStatus,
            FlightSessionStatus countedStatus,
            LocalDateTime from,
            LocalDateTime to
    ) {
        if (
                requestedStatus != null
                        && requestedStatus != countedStatus
        ) {
            return 0L;
        }

        return countSessions(
                droneId,
                countedStatus,
                from,
                to
        );
    }

    private List<FlightSessionItem> findRecentAbortedSessions(
            Long droneId,
            FlightSessionStatus requestedStatus,
            LocalDateTime from,
            LocalDateTime to,
            PageRequest pageRequest,
            Instant generatedAt
    ) {
        if (
                requestedStatus != null
                        && requestedStatus != FlightSessionStatus.ABORTED
        ) {
            return List.of();
        }

        return flightSessionRepository.findDashboardSessions(
                        droneId,
                        FlightSessionStatus.ABORTED,
                        from,
                        to,
                        pageRequest
                )
                .stream()
                .map(session -> toFlightSessionItem(
                        session,
                        generatedAt
                ))
                .toList();
    }

    private FlightSessionItem toFlightSessionItem(
            FlightSession session,
            Instant generatedAt
    ) {
        Instant startedAt = toSystemInstant(session.getStartedAt());
        Instant endedAt = session.getEndedAt() == null
                ? null
                : toSystemInstant(session.getEndedAt());

        Instant durationEnd = resolveDurationEnd(
                session.getStatus(),
                startedAt,
                endedAt,
                generatedAt
        );
        long durationSeconds = Math.max(
                0,
                Duration.between(startedAt, durationEnd).getSeconds()
        );

        return new FlightSessionItem(
                session.getSessionId(),
                session.getDroneId(),
                session.getName(),
                session.getDescription(),
                session.getStatus().name(),
                session.getSourceDeviceId(),
                startedAt,
                endedAt,
                durationSeconds
        );
    }

    private Instant resolveDurationEnd(
            FlightSessionStatus status,
            Instant startedAt,
            Instant endedAt,
            Instant generatedAt
    ) {
        if (status == FlightSessionStatus.READY) {
            return startedAt;
        }

        return endedAt == null ? generatedAt : endedAt;
    }

    private AiAlertItem toAiAlertItem(AiInferenceEvent event) {
        String snapshotFileName = event.getSnapshotFileName();

        return new AiAlertItem(
                event.getId(),
                event.getDroneId(),
                event.getSessionId(),
                event.getSourceId(),
                event.getSourceType().name(),
                event.getFrameIndex(),
                event.getCapturedAt().toInstant(ZoneOffset.UTC),
                event.getDetectionCount(),
                snapshotFileName != null && !snapshotFileName.isBlank()
        );
    }

    private FlightGateDecisionItem toFlightGateDecisionItem(
            AuditLog auditLog
    ) {
        return new FlightGateDecisionItem(
                auditLog.getId(),
                Long.valueOf(auditLog.getEntityId()),
                auditLog.getAction().name(),
                auditLog.getSummary(),
                auditLog.getOccurredAt().toInstant(ZoneOffset.UTC)
        );
    }

    private void ensureValidRange(Instant from, Instant to) {
        if (from != null && to != null && from.isAfter(to)) {
            throw new IllegalArgumentException(
                    "대시보드 조회 시작 시각은 종료 시각보다 늦을 수 없습니다."
            );
        }
    }

    private LocalDateTime toLocalDateTime(
            Instant value,
            ZoneId zoneId
    ) {
        return value == null
                ? null
                : LocalDateTime.ofInstant(value, zoneId);
    }

    private Instant toSystemInstant(LocalDateTime value) {
        return value.atZone(ZoneId.systemDefault()).toInstant();
    }
}
