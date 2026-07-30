package com.visionflow.api.incident.service;

import com.visionflow.api.common.exception.ResourceNotFoundException;
import com.visionflow.api.incident.domain.Incident;
import com.visionflow.api.incident.domain.IncidentActionHistory;
import com.visionflow.api.incident.domain.IncidentActionType;
import com.visionflow.api.incident.domain.IncidentSourceType;
import com.visionflow.api.incident.domain.IncidentStatus;
import com.visionflow.api.incident.dto.IncidentActionHistoryResponse;
import com.visionflow.api.incident.dto.IncidentContextResponse;
import com.visionflow.api.incident.dto.IncidentReportMetricsResponse;
import com.visionflow.api.incident.dto.IncidentReportResponse;
import com.visionflow.api.incident.dto.IncidentResponse;
import com.visionflow.api.incident.repository.IncidentActionHistoryRepository;
import com.visionflow.api.incident.repository.IncidentRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;

@Service
public class IncidentReportService {

    private final IncidentRepository incidentRepository;
    private final IncidentActionHistoryRepository historyRepository;
    private final IncidentContextService contextService;

    public IncidentReportService(
            IncidentRepository incidentRepository,
            IncidentActionHistoryRepository historyRepository,
            IncidentContextService contextService
    ) {
        this.incidentRepository = incidentRepository;
        this.historyRepository = historyRepository;
        this.contextService = contextService;
    }

    @Transactional(readOnly = true)
    public IncidentReportResponse build(Long incidentId) {
        Incident incident = incidentRepository.findById(incidentId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Incident를 찾을 수 없습니다: " + incidentId
                ));
        List<IncidentActionHistory> history = historyRepository
                .findAllByIncidentIdOrderByCreatedAtAscIdAsc(incidentId);
        IncidentContextResponse context = contextService.build(incident);
        IncidentReportMetricsResponse metrics = buildMetrics(
                incident,
                context,
                history
        );

        return new IncidentReportResponse(
                Instant.now(),
                IncidentResponse.from(incident),
                context,
                metrics,
                history.stream()
                        .map(IncidentActionHistoryResponse::from)
                        .toList()
        );
    }

    private IncidentReportMetricsResponse buildMetrics(
            Incident incident,
            IncidentContextResponse context,
            List<IncidentActionHistory> history
    ) {
        Instant responseStartedAt = history.stream()
                .filter(this::isOperatorResponse)
                .map(IncidentActionHistory::getCreatedAt)
                .map(this::toAuditInstant)
                .findFirst()
                .orElse(null);
        Instant resolvedAt = findStatusChangedAt(
                history,
                IncidentStatus.RESOLVED,
                IncidentStatus.CLOSED
        );
        Instant closedAt = findStatusChangedAt(
                history,
                IncidentStatus.CLOSED
        );

        if (resolvedAt == null && incident.getResolvedAt() != null) {
            resolvedAt = toSourceInstant(
                    incident.getResolvedAt(),
                    incident.getSourceType()
            );
        }
        if (closedAt == null && incident.getClosedAt() != null) {
            closedAt = toAuditInstant(incident.getClosedAt());
        }

        long noteCount = history.stream()
                .filter(item -> item.getActionType()
                        == IncidentActionType.NOTE_ADDED)
                .count();
        boolean evidenceAvailable = context.snapshotAvailable()
                || context.replayAvailable()
                || context.latitude() != null;

        return new IncidentReportMetricsResponse(
                responseStartedAt,
                resolvedAt,
                closedAt,
                elapsedSeconds(context.occurredAt(), responseStartedAt),
                elapsedSeconds(context.occurredAt(), resolvedAt),
                history.size(),
                Math.toIntExact(noteCount),
                evidenceAvailable
        );
    }

    private boolean isOperatorResponse(IncidentActionHistory history) {
        return history.getActionType() == IncidentActionType.ASSIGNED
                || history.getActionType()
                        == IncidentActionType.PRIORITY_CHANGED
                || history.getActionType()
                        == IncidentActionType.STATUS_CHANGED
                || history.getActionType() == IncidentActionType.NOTE_ADDED;
    }

    private Instant findStatusChangedAt(
            List<IncidentActionHistory> history,
            IncidentStatus... statuses
    ) {
        return history.stream()
                .filter(item -> matchesStatus(item.getNewStatus(), statuses))
                .map(IncidentActionHistory::getCreatedAt)
                .map(this::toAuditInstant)
                .findFirst()
                .orElse(null);
    }

    private boolean matchesStatus(
            IncidentStatus candidate,
            IncidentStatus[] statuses
    ) {
        if (candidate == null) {
            return false;
        }

        for (IncidentStatus status : statuses) {
            if (candidate == status) {
                return true;
            }
        }

        return false;
    }

    private Long elapsedSeconds(Instant start, Instant end) {
        if (start == null || end == null) {
            return null;
        }

        return Math.max(0, Duration.between(start, end).getSeconds());
    }

    private Instant toAuditInstant(LocalDateTime value) {
        return value.toInstant(ZoneOffset.UTC);
    }

    private Instant toSourceInstant(
            LocalDateTime value,
            IncidentSourceType sourceType
    ) {
        if (
                sourceType == IncidentSourceType.AI_ALERT
                        || sourceType == IncidentSourceType.FLIGHT_QUALITY
                        || sourceType == IncidentSourceType.FLIGHT_GATE
        ) {
            return value.toInstant(ZoneOffset.UTC);
        }

        return value.atZone(ZoneId.systemDefault()).toInstant();
    }
}
