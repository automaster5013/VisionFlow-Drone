package com.visionflow.api.incident.service;

import com.visionflow.api.ai.domain.AiAlert;
import com.visionflow.api.ai.domain.AiAlertSeverity;
import com.visionflow.api.ai.domain.AiAlertStatus;
import com.visionflow.api.common.exception.BusinessException;
import com.visionflow.api.common.exception.ResourceNotFoundException;
import com.visionflow.api.geofence.domain.DroneGeofenceEvent;
import com.visionflow.api.geofence.domain.GeofenceRule;
import com.visionflow.api.incident.domain.Incident;
import com.visionflow.api.incident.domain.IncidentActionHistory;
import com.visionflow.api.incident.domain.IncidentActionType;
import com.visionflow.api.incident.domain.IncidentPriority;
import com.visionflow.api.incident.domain.IncidentSourceType;
import com.visionflow.api.incident.domain.IncidentStatus;
import com.visionflow.api.incident.dto.IncidentActionHistoryResponse;
import com.visionflow.api.incident.dto.IncidentDetailResponse;
import com.visionflow.api.incident.dto.IncidentResponse;
import com.visionflow.api.incident.realtime.IncidentRealtimeAction;
import com.visionflow.api.incident.realtime.IncidentRealtimePublisher;
import com.visionflow.api.incident.repository.IncidentActionHistoryRepository;
import com.visionflow.api.incident.repository.IncidentRepository;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;

@Service
public class IncidentService {

    private static final String SYSTEM_AI = "AI_ALERT_SYNC";
    private static final String SYSTEM_GEOFENCE = "GEOFENCE_SYNC";

    private final IncidentRepository incidentRepository;
    private final IncidentActionHistoryRepository historyRepository;
    private final IncidentRealtimePublisher realtimePublisher;
    private final IncidentContextService contextService;

    public IncidentService(
            IncidentRepository incidentRepository,
            IncidentActionHistoryRepository historyRepository,
            IncidentRealtimePublisher realtimePublisher,
            IncidentContextService contextService
    ) {
        this.incidentRepository = incidentRepository;
        this.historyRepository = historyRepository;
        this.realtimePublisher = realtimePublisher;
        this.contextService = contextService;
    }

    @Transactional
    public IncidentResponse createFromAiAlert(AiAlert alert) {
        return incidentRepository.findBySourceTypeAndSourceId(
                        IncidentSourceType.AI_ALERT,
                        alert.getId()
                )
                .map(IncidentResponse::from)
                .orElseGet(() -> createIncident(
                        IncidentSourceType.AI_ALERT,
                        alert.getId(),
                        alert.getDroneId(),
                        alert.getSessionId(),
                        mapPriority(alert.getSeverity()),
                        mapStatus(alert.getStatus()),
                        alert.getTitle(),
                        alert.getSummary(),
                        alert.getCapturedAt(),
                        alert.getResolvedAt(),
                        SYSTEM_AI,
                        "AI 경보에서 자동 생성"
                ));
    }

    @Transactional
    public IncidentResponse synchronizeAiAlert(
            AiAlert alert,
            String actor,
            String note
    ) {
        createFromAiAlert(alert);
        return synchronizeSourceStatus(
                IncidentSourceType.AI_ALERT,
                alert.getId(),
                mapStatus(alert.getStatus()),
                normalizeActor(actor, SYSTEM_AI),
                normalizeOptional(note)
        );
    }

    @Transactional
    public IncidentResponse createFromGeofenceEvent(
            DroneGeofenceEvent event
    ) {
        return incidentRepository.findBySourceTypeAndSourceId(
                        IncidentSourceType.GEOFENCE,
                        event.getId()
                )
                .map(IncidentResponse::from)
                .orElseGet(() -> createIncident(
                        IncidentSourceType.GEOFENCE,
                        event.getId(),
                        event.getDroneId(),
                        event.getFlightSessionId(),
                        event.getRuleType() == GeofenceRule.KEEP_OUT
                                ? IncidentPriority.CRITICAL
                                : IncidentPriority.HIGH,
                        event.getResolvedAt() == null
                                ? IncidentStatus.OPEN
                                : IncidentStatus.RESOLVED,
                        "지오펜스 위반: " + event.getGeofenceName(),
                        buildGeofenceSummary(event),
                        event.getDetectedAt(),
                        event.getResolvedAt(),
                        SYSTEM_GEOFENCE,
                        "지오펜스 위반 이벤트에서 자동 생성"
                ));
    }

    @Transactional
    public IncidentResponse synchronizeGeofenceResolved(
            DroneGeofenceEvent event,
            String note
    ) {
        createFromGeofenceEvent(event);
        return synchronizeSourceStatus(
                IncidentSourceType.GEOFENCE,
                event.getId(),
                IncidentStatus.RESOLVED,
                SYSTEM_GEOFENCE,
                normalizeOptional(note)
        );
    }

    @Transactional(readOnly = true)
    public List<IncidentResponse> findIncidents(
            Long droneId,
            IncidentSourceType sourceType,
            IncidentPriority priority,
            IncidentStatus status,
            String assignee,
            Instant from,
            Instant to,
            int limit
    ) {
        validatePeriod(from, to);
        int safeLimit = Math.max(1, Math.min(limit, 500));

        return incidentRepository.findIncidents(
                        droneId,
                        sourceType,
                        priority,
                        status,
                        normalizeOptional(assignee),
                        toUtcDateTime(from),
                        toUtcDateTime(to),
                        PageRequest.of(0, safeLimit)
                )
                .stream()
                .map(IncidentResponse::from)
                .toList();
    }

    @Transactional(readOnly = true)
    public IncidentDetailResponse findDetail(Long incidentId) {
        Incident incident = findIncident(incidentId);
        List<IncidentActionHistoryResponse> history = historyRepository
                .findAllByIncidentIdOrderByCreatedAtAscIdAsc(incidentId)
                .stream()
                .map(IncidentActionHistoryResponse::from)
                .toList();

        return new IncidentDetailResponse(
                IncidentResponse.from(incident),
                history,
                contextService.build(incident)
        );
    }

    @Transactional
    public IncidentResponse assign(
            Long incidentId,
            String assignee,
            String actor
    ) {
        Incident incident = findIncident(incidentId);
        String safeAssignee = normalizeRequired(assignee, "담당자");
        String safeActor = normalizeRequired(actor, "처리자");

        if (!incident.assign(
                safeAssignee,
                safeActor,
                nowUtc()
        )) {
            return IncidentResponse.from(incident);
        }

        incident = incidentRepository.saveAndFlush(incident);
        saveHistory(
                incident,
                IncidentActionType.ASSIGNED,
                null,
                null,
                safeActor,
                "담당자 지정: " + safeAssignee
        );

        IncidentResponse response = IncidentResponse.from(incident);
        realtimePublisher.publishAfterCommit(
                IncidentRealtimeAction.ASSIGNED,
                response
        );
        return response;
    }

    @Transactional
    public IncidentResponse changePriority(
            Long incidentId,
            IncidentPriority priority,
            String actor,
            String note
    ) {
        Incident incident = findIncident(incidentId);
        String safeActor = normalizeRequired(actor, "처리자");
        IncidentPriority previousPriority = incident.getPriority();

        if (!incident.changePriority(priority, nowUtc())) {
            return IncidentResponse.from(incident);
        }

        incident = incidentRepository.saveAndFlush(incident);
        String changeNote = "우선순위 변경: "
                + previousPriority
                + " -> "
                + priority;
        String safeNote = normalizeOptional(note);
        if (safeNote != null) {
            changeNote += " / " + safeNote;
        }

        saveHistory(
                incident,
                IncidentActionType.PRIORITY_CHANGED,
                null,
                null,
                safeActor,
                changeNote
        );

        IncidentResponse response = IncidentResponse.from(incident);
        realtimePublisher.publishAfterCommit(
                IncidentRealtimeAction.PRIORITY_CHANGED,
                response
        );
        return response;
    }

    @Transactional
    public IncidentResponse changeStatus(
            Long incidentId,
            IncidentStatus nextStatus,
            String actor,
            String note
    ) {
        Incident incident = findIncident(incidentId);
        String safeActor = normalizeRequired(actor, "처리자");
        IncidentStatus previousStatus = incident.getStatus();

        validateTransition(previousStatus, nextStatus);
        if (!incident.changeStatus(nextStatus, nowUtc())) {
            return IncidentResponse.from(incident);
        }

        incident = incidentRepository.saveAndFlush(incident);
        saveHistory(
                incident,
                IncidentActionType.STATUS_CHANGED,
                previousStatus,
                nextStatus,
                safeActor,
                normalizeOptional(note)
        );

        IncidentResponse response = IncidentResponse.from(incident);
        realtimePublisher.publishAfterCommit(
                IncidentRealtimeAction.STATUS_CHANGED,
                response
        );
        return response;
    }

    @Transactional
    public IncidentDetailResponse addNote(
            Long incidentId,
            String actor,
            String note
    ) {
        Incident incident = findIncident(incidentId);
        String safeActor = normalizeRequired(actor, "작성자");
        String safeNote = normalizeRequired(note, "조치 메모");
        incident.touch(nowUtc());
        incident = incidentRepository.saveAndFlush(incident);
        saveHistory(
                incident,
                IncidentActionType.NOTE_ADDED,
                null,
                null,
                safeActor,
                safeNote
        );

        realtimePublisher.publishAfterCommit(
                IncidentRealtimeAction.NOTE_ADDED,
                IncidentResponse.from(incident)
        );
        return findDetail(incidentId);
    }

    private IncidentResponse createIncident(
            IncidentSourceType sourceType,
            Long sourceId,
            Long droneId,
            String sessionId,
            IncidentPriority priority,
            IncidentStatus status,
            String title,
            String summary,
            LocalDateTime occurredAt,
            LocalDateTime sourceResolvedAt,
            String actor,
            String note
    ) {
        Incident incident = Incident.create(
                sourceType,
                sourceId,
                droneId,
                sessionId,
                priority,
                status,
                title,
                summary,
                occurredAt,
                sourceResolvedAt
        );

        incident = incidentRepository.saveAndFlush(incident);
        saveHistory(
                incident,
                IncidentActionType.CREATED,
                null,
                status,
                actor,
                note
        );

        IncidentResponse response = IncidentResponse.from(incident);
        realtimePublisher.publishAfterCommit(
                IncidentRealtimeAction.CREATED,
                response
        );
        return response;
    }

    private IncidentResponse synchronizeSourceStatus(
            IncidentSourceType sourceType,
            Long sourceId,
            IncidentStatus nextStatus,
            String actor,
            String note
    ) {
        Incident incident = incidentRepository
                .findBySourceTypeAndSourceId(sourceType, sourceId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "원본 이벤트에 연결된 Incident를 찾을 수 없습니다: "
                                + sourceType
                                + "/"
                                + sourceId
                ));
        IncidentStatus previousStatus = incident.getStatus();

        if (!incident.synchronizeStatus(nextStatus, nowUtc())) {
            return IncidentResponse.from(incident);
        }

        incident = incidentRepository.saveAndFlush(incident);
        saveHistory(
                incident,
                IncidentActionType.SOURCE_SYNCHRONIZED,
                previousStatus,
                nextStatus,
                actor,
                note
        );

        IncidentResponse response = IncidentResponse.from(incident);
        realtimePublisher.publishAfterCommit(
                IncidentRealtimeAction.SOURCE_SYNCHRONIZED,
                response
        );
        return response;
    }

    private void saveHistory(
            Incident incident,
            IncidentActionType actionType,
            IncidentStatus previousStatus,
            IncidentStatus newStatus,
            String actor,
            String note
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

    private Incident findIncident(Long incidentId) {
        return incidentRepository.findById(incidentId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Incident를 찾을 수 없습니다: " + incidentId
                ));
    }

    private void validateTransition(
            IncidentStatus current,
            IncidentStatus next
    ) {
        if (current == next) {
            return;
        }

        boolean allowed = switch (current) {
            case OPEN -> next == IncidentStatus.IN_PROGRESS
                    || next == IncidentStatus.RESOLVED;
            case IN_PROGRESS -> next == IncidentStatus.OPEN
                    || next == IncidentStatus.RESOLVED;
            case RESOLVED -> next == IncidentStatus.IN_PROGRESS
                    || next == IncidentStatus.CLOSED;
            case CLOSED -> false;
        };

        if (!allowed) {
            throw new BusinessException(
                    HttpStatus.CONFLICT,
                    "INVALID_INCIDENT_STATUS_TRANSITION",
                    "허용되지 않는 Incident 상태 변경입니다: "
                            + current
                            + " -> "
                            + next
            );
        }
    }

    private IncidentPriority mapPriority(AiAlertSeverity severity) {
        return switch (severity) {
            case INFO -> IncidentPriority.LOW;
            case WARNING -> IncidentPriority.HIGH;
            case CRITICAL -> IncidentPriority.CRITICAL;
        };
    }

    private IncidentStatus mapStatus(AiAlertStatus status) {
        return switch (status) {
            case OPEN -> IncidentStatus.OPEN;
            case ACKNOWLEDGED -> IncidentStatus.IN_PROGRESS;
            case RESOLVED -> IncidentStatus.RESOLVED;
        };
    }

    private String buildGeofenceSummary(DroneGeofenceEvent event) {
        return event.getDroneCode()
                + " / "
                + event.getRuleType()
                + " / 경계 중심 거리 "
                + event.getDistanceMeters()
                + "m";
    }

    private void validatePeriod(Instant from, Instant to) {
        if (from != null && to != null && from.isAfter(to)) {
            throw new BusinessException(
                    HttpStatus.BAD_REQUEST,
                    "INVALID_INCIDENT_PERIOD",
                    "조회 시작 시각은 종료 시각보다 늦을 수 없습니다."
            );
        }
    }

    private LocalDateTime toUtcDateTime(Instant value) {
        return value == null
                ? null
                : LocalDateTime.ofInstant(value, ZoneOffset.UTC);
    }

    private LocalDateTime nowUtc() {
        return LocalDateTime.now(ZoneOffset.UTC);
    }

    private String normalizeActor(String actor, String fallback) {
        String normalized = normalizeOptional(actor);
        return normalized == null ? fallback : normalized;
    }

    private String normalizeRequired(String value, String fieldName) {
        String normalized = normalizeOptional(value);
        if (normalized == null) {
            throw new BusinessException(
                    HttpStatus.BAD_REQUEST,
                    "INVALID_INCIDENT_REQUEST",
                    fieldName + "는 비어 있을 수 없습니다."
            );
        }
        return normalized;
    }

    private String normalizeOptional(String value) {
        if (value == null) {
            return null;
        }

        String normalized = value.trim();
        return normalized.isEmpty() ? null : normalized;
    }
}
