package com.visionflow.api.ai.service;

import com.visionflow.api.ai.domain.AiAlert;
import com.visionflow.api.ai.domain.AiAlertSeverity;
import com.visionflow.api.ai.domain.AiAlertStatus;
import com.visionflow.api.ai.domain.AiDetection;
import com.visionflow.api.ai.domain.AiInferenceEvent;
import com.visionflow.api.ai.dto.AiAlertDetailResponse;
import com.visionflow.api.ai.dto.AiAlertResponse;
import com.visionflow.api.ai.dto.AiInferenceEventResponse;
import com.visionflow.api.ai.realtime.AiAlertRealtimeAction;
import com.visionflow.api.ai.realtime.AiAlertRealtimePublisher;
import com.visionflow.api.ai.repository.AiAlertRepository;
import com.visionflow.api.ai.repository.AiDetectionRepository;
import com.visionflow.api.ai.repository.AiInferenceEventRepository;
import com.visionflow.api.common.exception.ResourceNotFoundException;
import com.visionflow.api.incident.service.IncidentService;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
public class AiAlertService {

    private final AiAlertRepository alertRepository;
    private final AiInferenceEventRepository eventRepository;
    private final AiDetectionRepository detectionRepository;
    private final AiAlertRiskEvaluator riskEvaluator;
    private final AiAlertRealtimePublisher realtimePublisher;
    private final IncidentService incidentService;

    public AiAlertService(
            AiAlertRepository alertRepository,
            AiInferenceEventRepository eventRepository,
            AiDetectionRepository detectionRepository,
            AiAlertRiskEvaluator riskEvaluator,
            AiAlertRealtimePublisher realtimePublisher,
            IncidentService incidentService
    ) {
        this.alertRepository = alertRepository;
        this.eventRepository = eventRepository;
        this.detectionRepository = detectionRepository;
        this.riskEvaluator = riskEvaluator;
        this.realtimePublisher = realtimePublisher;
        this.incidentService = incidentService;
    }

    @Transactional
    public void createForEvent(
            AiInferenceEvent event,
            List<AiDetection> detections
    ) {
        if (detections == null || detections.isEmpty()) {
            return;
        }

        if (alertRepository.findByEventId(event.getId()).isPresent()) {
            return;
        }

        AiAlertRiskEvaluator.RiskAssessment assessment =
                riskEvaluator.evaluate(detections);

        AiAlert alert = AiAlert.create(
                event,
                assessment.severity(),
                assessment.title(),
                assessment.summary(),
                assessment.primaryClassName(),
                assessment.maxConfidence()
        );

        alert = alertRepository.saveAndFlush(alert);
        incidentService.createFromAiAlert(alert);

        realtimePublisher.publishAfterCommit(
                AiAlertRealtimeAction.CREATED,
                AiAlertResponse.from(alert, event)
        );
    }

    @Transactional(readOnly = true)
    public List<AiAlertResponse> findAlerts(
            Long droneId,
            String sessionId,
            AiAlertSeverity severity,
            AiAlertStatus status,
            Instant from,
            Instant to,
            int limit
    ) {
        validatePeriod(from, to);

        String safeSessionId = normalizeOptional(sessionId);
        int safeLimit = Math.max(1, Math.min(limit, 200));

        List<AiAlert> alerts = alertRepository.findAlerts(
                droneId,
                safeSessionId,
                severity,
                status,
                toUtcDateTime(from),
                toUtcDateTime(to),
                PageRequest.of(0, safeLimit)
        );

        if (alerts.isEmpty()) {
            return List.of();
        }

        Map<Long, AiInferenceEvent> eventsById = eventRepository
                .findAllById(
                        alerts.stream()
                                .map(AiAlert::getEventId)
                                .distinct()
                                .toList()
                )
                .stream()
                .collect(Collectors.toMap(
                        AiInferenceEvent::getId,
                        Function.identity()
                ));

        return alerts.stream()
                .map(alert -> AiAlertResponse.from(
                        alert,
                        requireEvent(eventsById, alert.getEventId())
                ))
                .toList();
    }

    @Transactional(readOnly = true)
    public AiAlertDetailResponse findDetail(Long alertId) {
        AiAlert alert = findAlert(alertId);
        AiInferenceEvent event = findEvent(alert.getEventId());
        List<AiDetection> detections =
                detectionRepository.findAllByEventIdOrderByIdAsc(
                        event.getId()
                );

        return new AiAlertDetailResponse(
                AiAlertResponse.from(alert, event),
                AiInferenceEventResponse.from(event, detections)
        );
    }

    @Transactional
    public AiAlertResponse acknowledge(
            Long alertId,
            String operator
    ) {
        AiAlert alert = findAlert(alertId);
        alert.acknowledge(
                normalizeRequired(operator, "확인 처리자"),
                LocalDateTime.now(ZoneOffset.UTC)
        );

        alert = alertRepository.saveAndFlush(alert);
        incidentService.synchronizeAiAlert(
                alert,
                alert.getAcknowledgedBy(),
                "AI 경보 확인 처리와 동기화"
        );
        AiAlertResponse response = AiAlertResponse.from(
                alert,
                findEvent(alert.getEventId())
        );

        realtimePublisher.publishAfterCommit(
                AiAlertRealtimeAction.ACKNOWLEDGED,
                response
        );

        return response;
    }

    @Transactional
    public AiAlertResponse resolve(
            Long alertId,
            String operator,
            String note
    ) {
        AiAlert alert = findAlert(alertId);
        alert.resolve(
                normalizeRequired(operator, "해결 처리자"),
                normalizeOptional(note),
                LocalDateTime.now(ZoneOffset.UTC)
        );

        alert = alertRepository.saveAndFlush(alert);
        incidentService.synchronizeAiAlert(
                alert,
                alert.getResolvedBy(),
                alert.getResolutionNote()
        );
        AiAlertResponse response = AiAlertResponse.from(
                alert,
                findEvent(alert.getEventId())
        );

        realtimePublisher.publishAfterCommit(
                AiAlertRealtimeAction.RESOLVED,
                response
        );

        return response;
    }

    private AiAlert findAlert(Long alertId) {
        return alertRepository.findById(alertId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "AI 경보를 찾을 수 없습니다: " + alertId
                ));
    }

    private AiInferenceEvent findEvent(Long eventId) {
        return eventRepository.findById(eventId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "AI 추론 이벤트를 찾을 수 없습니다: " + eventId
                ));
    }

    private AiInferenceEvent requireEvent(
            Map<Long, AiInferenceEvent> eventsById,
            Long eventId
    ) {
        AiInferenceEvent event = eventsById.get(eventId);
        if (event == null) {
            throw new ResourceNotFoundException(
                    "AI 경보에 연결된 추론 이벤트를 찾을 수 없습니다: "
                            + eventId
            );
        }
        return event;
    }

    private void validatePeriod(Instant from, Instant to) {
        if (from != null && to != null && from.isAfter(to)) {
            throw new IllegalArgumentException(
                    "조회 시작 시각은 종료 시각보다 늦을 수 없습니다."
            );
        }
    }

    private LocalDateTime toUtcDateTime(Instant value) {
        return value == null
                ? null
                : LocalDateTime.ofInstant(value, ZoneOffset.UTC);
    }

    private String normalizeRequired(String value, String fieldName) {
        String normalized = normalizeOptional(value);
        if (normalized == null) {
            throw new IllegalArgumentException(
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
