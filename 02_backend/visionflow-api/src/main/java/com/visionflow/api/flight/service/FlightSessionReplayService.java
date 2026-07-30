package com.visionflow.api.flight.service;

import com.visionflow.api.ai.domain.AiDetection;
import com.visionflow.api.ai.domain.AiInferenceEvent;
import com.visionflow.api.ai.dto.AiInferenceEventResponse;
import com.visionflow.api.ai.repository.AiDetectionRepository;
import com.visionflow.api.ai.repository.AiInferenceEventRepository;
import com.visionflow.api.common.exception.ResourceNotFoundException;
import com.visionflow.api.drone.domain.DroneTelemetryHistory;
import com.visionflow.api.drone.dto.DroneTelemetryHistoryResponse;
import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.drone.repository.DroneTelemetryHistoryRepository;
import com.visionflow.api.flight.domain.FlightSession;
import com.visionflow.api.flight.dto.AiFlightSessionSummaryProjection;
import com.visionflow.api.flight.dto.FlightSessionReplayResponse;
import com.visionflow.api.flight.dto.FlightSessionSummaryResponse;
import com.visionflow.api.flight.dto.TelemetryFlightSessionSummaryProjection;
import com.visionflow.api.flight.repository.FlightSessionRepository;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@Service
public class FlightSessionReplayService {

    private static final int DEFAULT_TELEMETRY_LIMIT = 5_000;
    private static final int MAX_TELEMETRY_LIMIT = 5_000;
    private static final int DEFAULT_EVENT_LIMIT = 200;
    private static final int MAX_EVENT_LIMIT = 1_000;
    private static final int DEFAULT_SESSION_LIST_LIMIT = 20;
    private static final int MAX_SESSION_LIST_LIMIT = 100;

    private final DroneRepository droneRepository;
    private final FlightSessionRepository sessionRepository;
    private final DroneTelemetryHistoryRepository telemetryRepository;
    private final AiInferenceEventRepository eventRepository;
    private final AiDetectionRepository detectionRepository;

    public FlightSessionReplayService(
            DroneRepository droneRepository,
            FlightSessionRepository sessionRepository,
            DroneTelemetryHistoryRepository telemetryRepository,
            AiInferenceEventRepository eventRepository,
            AiDetectionRepository detectionRepository
    ) {
        this.droneRepository = droneRepository;
        this.sessionRepository = sessionRepository;
        this.telemetryRepository = telemetryRepository;
        this.eventRepository = eventRepository;
        this.detectionRepository = detectionRepository;
    }

    @Transactional(readOnly = true)
    public List<FlightSessionSummaryResponse> findSessions(
            Long droneId,
            String searchTerm,
            Integer requestedLimit
    ) {
        ensureDroneExists(droneId);

        String normalizedSearchTerm = normalizeSearchTerm(searchTerm);
        int limit = normalizeLimit(
                requestedLimit,
                DEFAULT_SESSION_LIST_LIMIT,
                MAX_SESSION_LIST_LIMIT
        );
        // 두 테이블의 최신 순서가 서로 달라도 같은 세션의 집계가
        // 누락되지 않도록 병합 후보는 최대 허용 개수까지 조회합니다.
        PageRequest pageRequest = PageRequest.of(
                0,
                MAX_SESSION_LIST_LIMIT
        );

        List<FlightSession> managedSessions =
                sessionRepository.findSessionMetadata(
                        droneId,
                        normalizedSearchTerm,
                        pageRequest
                );

        List<TelemetryFlightSessionSummaryProjection> telemetrySummaries =
                telemetryRepository.findFlightSessionSummaries(
                        droneId,
                        normalizedSearchTerm,
                        pageRequest
                );

        List<AiFlightSessionSummaryProjection> aiSummaries =
                eventRepository.findFlightSessionSummaries(
                        droneId,
                        normalizedSearchTerm,
                        pageRequest
                );

        Map<String, FlightSessionAccumulator> summariesById =
                new LinkedHashMap<>();

        for (FlightSession session : managedSessions) {
            FlightSessionAccumulator accumulator =
                    summariesById.computeIfAbsent(
                            session.getSessionId(),
                            FlightSessionAccumulator::new
                    );

            Instant sessionStartedAt = toInstant(
                    session.getStartedAt(),
                    ZoneId.systemDefault()
            );
            Instant sessionEndedAt =
                    session.getStatus().isTerminal()
                            && session.getEndedAt() != null
                            ? toInstant(
                                    session.getEndedAt(),
                                    ZoneId.systemDefault()
                            )
                            : Instant.now();

            accumulator.mergeManagedSession(
                    session.getName(),
                    session.getDescription(),
                    session.getStatus().name(),
                    session.getSourceDeviceId(),
                    sessionStartedAt,
                    sessionEndedAt
            );
        }

        for (TelemetryFlightSessionSummaryProjection summary
                : telemetrySummaries) {
            FlightSessionAccumulator accumulator =
                    summariesById.computeIfAbsent(
                            summary.getSessionId(),
                            FlightSessionAccumulator::new
                    );

            accumulator.mergeTelemetry(
                    toInstant(
                            summary.getStartedAt(),
                            ZoneId.systemDefault()
                    ),
                    toInstant(
                            summary.getEndedAt(),
                            ZoneId.systemDefault()
                    ),
                    safeLong(summary.getTelemetryCount())
            );
        }

        for (AiFlightSessionSummaryProjection summary : aiSummaries) {
            FlightSessionAccumulator accumulator =
                    summariesById.computeIfAbsent(
                            summary.getSessionId(),
                            FlightSessionAccumulator::new
                    );

            accumulator.mergeAiEvents(
                    toInstant(summary.getStartedAt(), ZoneOffset.UTC),
                    toInstant(summary.getEndedAt(), ZoneOffset.UTC),
                    safeLong(summary.getAiEventCount()),
                    safeLong(summary.getDetectionCount())
            );
        }

        return summariesById.values()
                .stream()
                .map(summary -> summary.toResponse(droneId))
                .sorted(
                        Comparator.comparing(
                                FlightSessionSummaryResponse::endedAt
                        ).reversed()
                )
                .limit(limit)
                .toList();
    }

    @Transactional(readOnly = true)
    public FlightSessionReplayResponse findReplay(
            Long droneId,
            String sessionId,
            Integer requestedTelemetryLimit,
            Integer requestedEventLimit
    ) {
        ensureDroneExists(droneId);

        String normalizedSessionId = normalizeSessionId(sessionId);
        int telemetryLimit = normalizeLimit(
                requestedTelemetryLimit,
                DEFAULT_TELEMETRY_LIMIT,
                MAX_TELEMETRY_LIMIT
        );
        int eventLimit = normalizeLimit(
                requestedEventLimit,
                DEFAULT_EVENT_LIMIT,
                MAX_EVENT_LIMIT
        );

        List<DroneTelemetryHistory> telemetry =
                telemetryRepository
                        .findByDroneIdAndFlightSessionIdOrderByRecordedAtAsc(
                                droneId,
                                normalizedSessionId,
                                PageRequest.of(0, telemetryLimit)
                        );

        List<AiInferenceEvent> events =
                eventRepository
                        .findAllByDroneIdAndSessionIdOrderByCapturedAtAsc(
                                droneId,
                                normalizedSessionId,
                                PageRequest.of(0, eventLimit)
                        );

        if (telemetry.isEmpty() && events.isEmpty()) {
            throw new ResourceNotFoundException(
                    "비행 세션을 찾을 수 없습니다: "
                            + normalizedSessionId
            );
        }

        Map<Long, List<AiDetection>> detectionsByEventId =
                findDetectionsByEventId(events);

        List<DroneTelemetryHistoryResponse> telemetryResponses =
                telemetry.stream()
                        .map(DroneTelemetryHistoryResponse::from)
                        .toList();

        List<AiInferenceEventResponse> eventResponses =
                events.stream()
                        .map(event -> AiInferenceEventResponse.from(
                                event,
                                detectionsByEventId.getOrDefault(
                                        event.getId(),
                                        List.of()
                                )
                        ))
                        .toList();

        List<Instant> timelineTimestamps = new ArrayList<>(
                telemetry.size() + events.size()
        );

        telemetry.stream()
                .map(this::toInstant)
                .forEach(timelineTimestamps::add);

        events.stream()
                .map(this::toInstant)
                .forEach(timelineTimestamps::add);

        Instant startedAt = timelineTimestamps.stream()
                .min(Instant::compareTo)
                .orElseThrow();
        Instant endedAt = timelineTimestamps.stream()
                .max(Instant::compareTo)
                .orElseThrow();

        int detectionCount = events.stream()
                .map(AiInferenceEvent::getDetectionCount)
                .filter(value -> value != null)
                .mapToInt(Integer::intValue)
                .sum();

        long durationSeconds = Math.max(
                0,
                Duration.between(startedAt, endedAt).getSeconds()
        );

        return new FlightSessionReplayResponse(
                normalizedSessionId,
                droneId,
                startedAt,
                endedAt,
                durationSeconds,
                telemetryResponses.size(),
                eventResponses.size(),
                detectionCount,
                telemetryResponses,
                eventResponses
        );
    }

    private Map<Long, List<AiDetection>> findDetectionsByEventId(
            List<AiInferenceEvent> events
    ) {
        if (events.isEmpty()) {
            return Map.of();
        }

        Collection<Long> eventIds = events.stream()
                .map(AiInferenceEvent::getId)
                .toList();

        return detectionRepository
                .findAllByEventIdInOrderByEventIdAscIdAsc(eventIds)
                .stream()
                .collect(Collectors.groupingBy(
                        AiDetection::getEventId,
                        LinkedHashMap::new,
                        Collectors.toList()
                ));
    }

    private Instant toInstant(DroneTelemetryHistory history) {
        return history.getRecordedAt()
                .atZone(ZoneId.systemDefault())
                .toInstant();
    }

    private Instant toInstant(AiInferenceEvent event) {
        return event.getCapturedAt()
                .toInstant(ZoneOffset.UTC);
    }

    private Instant toInstant(
            LocalDateTime value,
            ZoneId zoneId
    ) {
        return value.atZone(zoneId).toInstant();
    }

    private void ensureDroneExists(Long droneId) {
        if (!droneRepository.existsById(droneId)) {
            throw new ResourceNotFoundException(
                    "드론을 찾을 수 없습니다: " + droneId
            );
        }
    }

    private String normalizeSearchTerm(String searchTerm) {
        if (searchTerm == null) {
            return null;
        }

        String normalized = searchTerm.trim();

        if (normalized.isEmpty()) {
            return null;
        }

        if (normalized.length() > 36) {
            throw new IllegalArgumentException(
                    "비행 세션 검색어는 36자 이하여야 합니다."
            );
        }

        return normalized;
    }

    private long safeLong(Long value) {
        return value == null ? 0L : value;
    }

    private String normalizeSessionId(String sessionId) {
        if (sessionId == null) {
            throw new IllegalArgumentException(
                    "비행 세션 ID는 필수입니다."
            );
        }

        String normalized = sessionId.trim();

        if (normalized.isEmpty() || normalized.length() > 36) {
            throw new IllegalArgumentException(
                    "비행 세션 ID는 1~36자여야 합니다."
            );
        }

        return normalized;
    }

    private int normalizeLimit(
            Integer requestedLimit,
            int defaultLimit,
            int maxLimit
    ) {
        if (requestedLimit == null) {
            return defaultLimit;
        }

        return Math.max(1, Math.min(requestedLimit, maxLimit));
    }

    private static final class FlightSessionAccumulator {

        private final String sessionId;
        private Instant startedAt;
        private Instant endedAt;
        private long telemetryCount;
        private long aiEventCount;
        private long detectionCount;
        private String name;
        private String description;
        private String status;
        private String sourceDeviceId;
        private boolean managed;

        private FlightSessionAccumulator(String sessionId) {
            this.sessionId = sessionId;
        }

        private void mergeManagedSession(
                String sessionName,
                String sessionDescription,
                String sessionStatus,
                String sessionSourceDeviceId,
                Instant sessionStartedAt,
                Instant sessionEndedAt
        ) {
            this.name = sessionName;
            this.description = sessionDescription;
            this.status = sessionStatus;
            this.sourceDeviceId = sessionSourceDeviceId;
            this.managed = true;
            mergeRange(sessionStartedAt, sessionEndedAt);
        }

        private void mergeTelemetry(
                Instant telemetryStartedAt,
                Instant telemetryEndedAt,
                long count
        ) {
            mergeRange(telemetryStartedAt, telemetryEndedAt);
            telemetryCount += count;
        }

        private void mergeAiEvents(
                Instant aiStartedAt,
                Instant aiEndedAt,
                long eventCount,
                long totalDetectionCount
        ) {
            mergeRange(aiStartedAt, aiEndedAt);
            aiEventCount += eventCount;
            detectionCount += totalDetectionCount;
        }

        private void mergeRange(
                Instant candidateStartedAt,
                Instant candidateEndedAt
        ) {
            if (
                    startedAt == null
                            || candidateStartedAt.isBefore(startedAt)
            ) {
                startedAt = candidateStartedAt;
            }

            if (
                    endedAt == null
                            || candidateEndedAt.isAfter(endedAt)
            ) {
                endedAt = candidateEndedAt;
            }
        }

        private FlightSessionSummaryResponse toResponse(Long droneId) {
            long durationSeconds = Math.max(
                    0,
                    Duration.between(startedAt, endedAt).getSeconds()
            );
            String resolvedName = name != null
                    ? name
                    : "기존 비행 " + shortSessionId();
            String resolvedStatus = status != null
                    ? status
                    : "LEGACY";

            return new FlightSessionSummaryResponse(
                    sessionId,
                    droneId,
                    resolvedName,
                    description,
                    resolvedStatus,
                    sourceDeviceId,
                    startedAt,
                    endedAt,
                    durationSeconds,
                    telemetryCount,
                    aiEventCount,
                    detectionCount,
                    telemetryCount > 0,
                    aiEventCount > 0,
                    managed
            );
        }

        private String shortSessionId() {
            return sessionId.length() <= 8
                    ? sessionId
                    : sessionId.substring(0, 8);
        }
    }
}
