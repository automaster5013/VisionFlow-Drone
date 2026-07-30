package com.visionflow.api.flight.quality.service;

import com.visionflow.api.drone.domain.Drone;
import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.flight.domain.FlightSession;
import com.visionflow.api.flight.domain.FlightSessionStatus;
import com.visionflow.api.flight.quality.domain.FleetReliabilityStatus;
import com.visionflow.api.flight.quality.domain.FlightQualityAssessment;
import com.visionflow.api.flight.quality.dto.DroneReliabilityResponse;
import com.visionflow.api.flight.quality.dto.FleetReliabilityResponse;
import com.visionflow.api.flight.quality.dto.FleetReliabilityTrendPointResponse;
import com.visionflow.api.flight.quality.dto.FlightQualityAssessmentResponse;
import com.visionflow.api.flight.quality.repository.FlightQualityAssessmentRepository;
import com.visionflow.api.flight.repository.FlightSessionRepository;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.math.RoundingMode;
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
import java.util.Optional;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
@Transactional(readOnly = true)
public class FleetReliabilityService {

    private final FlightQualityAssessmentRepository assessmentRepository;
    private final FlightSessionRepository sessionRepository;
    private final DroneRepository droneRepository;

    public FleetReliabilityService(
            FlightQualityAssessmentRepository assessmentRepository,
            FlightSessionRepository sessionRepository,
            DroneRepository droneRepository
    ) {
        this.assessmentRepository = assessmentRepository;
        this.sessionRepository = sessionRepository;
        this.droneRepository = droneRepository;
    }

    public FleetReliabilityResponse summarize(int limitPerDrone) {
        List<Long> droneIds = assessmentRepository.findDistinctDroneIds();
        Map<Long, List<FlightQualityAssessment>> assessmentsByDrone =
                loadAssessments(droneIds, limitPerDrone);
        Map<String, FlightSession> sessionsById = loadSessions(
                assessmentsByDrone.values()
        );
        Map<Long, Drone> dronesById = droneRepository
                .findAllById(droneIds)
                .stream()
                .collect(Collectors.toMap(
                        Drone::getId,
                        Function.identity()
                ));
        List<DroneReliabilityResponse> drones = assessmentsByDrone
                .entrySet()
                .stream()
                .filter(entry -> !entry.getValue().isEmpty())
                .map(entry -> summarizeDrone(
                        entry.getKey(),
                        entry.getValue(),
                        sessionsById,
                        dronesById.get(entry.getKey())
                ))
                .sorted(
                        Comparator
                                .comparingInt((DroneReliabilityResponse item) ->
                                        statusOrder(item.status())
                                )
                                .thenComparing(
                                        DroneReliabilityResponse::averageScore
                                )
                                .thenComparing(
                                        DroneReliabilityResponse::droneId
                                )
                )
                .toList();
        int assessmentCount = drones.stream()
                .mapToInt(DroneReliabilityResponse::assessmentCount)
                .sum();
        int attentionDroneCount = (int) drones.stream()
                .filter(item ->
                        item.status() != FleetReliabilityStatus.STABLE
                )
                .count();
        BigDecimal fleetAverageScore = decimal(
                drones.stream()
                        .mapToDouble(item ->
                                item.averageScore().doubleValue()
                        )
                        .average()
                        .orElse(0)
        );
        List<Long> backfillCandidateDroneIds = sessionRepository
                .findDistinctDroneIdsByStatusIn(
                        Set.of(
                                FlightSessionStatus.COMPLETED,
                                FlightSessionStatus.ABORTED
                        )
                );

        return new FleetReliabilityResponse(
                Instant.now(),
                FlightQualityAssessmentService.CURRENT_RULE_VERSION,
                limitPerDrone,
                drones.size(),
                assessmentCount,
                fleetAverageScore,
                attentionDroneCount,
                backfillCandidateDroneIds,
                drones
        );
    }

    public Optional<DroneReliabilityResponse> summarizeDrone(
            Long droneId,
            int limitPerDrone
    ) {
        List<FlightQualityAssessment> assessments = assessmentRepository
                .findByDroneIdOrderByEvaluatedAtDesc(
                        droneId,
                        PageRequest.of(0, limitPerDrone)
                );
        if (assessments.isEmpty()) {
            return Optional.empty();
        }

        Map<String, FlightSession> sessionsById = loadSessions(
                List.of(assessments)
        );
        Drone drone = droneRepository.findById(droneId).orElse(null);

        return Optional.of(
                summarizeDrone(
                        droneId,
                        assessments,
                        sessionsById,
                        drone
                )
        );
    }

    private Map<Long, List<FlightQualityAssessment>> loadAssessments(
            List<Long> droneIds,
            int limitPerDrone
    ) {
        Map<Long, List<FlightQualityAssessment>> result =
                new LinkedHashMap<>();

        for (Long droneId : droneIds) {
            result.put(
                    droneId,
                    assessmentRepository
                            .findByDroneIdOrderByEvaluatedAtDesc(
                                    droneId,
                                    PageRequest.of(0, limitPerDrone)
                            )
            );
        }

        return result;
    }

    private Map<String, FlightSession> loadSessions(
            Collection<List<FlightQualityAssessment>> histories
    ) {
        List<String> sessionIds = histories.stream()
                .flatMap(Collection::stream)
                .map(FlightQualityAssessment::getSessionId)
                .distinct()
                .toList();

        return sessionRepository.findAllById(sessionIds)
                .stream()
                .collect(Collectors.toMap(
                        FlightSession::getSessionId,
                        Function.identity()
                ));
    }

    private DroneReliabilityResponse summarizeDrone(
            Long droneId,
            List<FlightQualityAssessment> recentAssessments,
            Map<String, FlightSession> sessionsById,
            Drone drone
    ) {
        List<FlightQualityAssessment> newestFirst =
                new ArrayList<>(recentAssessments);
        newestFirst.sort(
                Comparator.comparing(
                                FlightQualityAssessment::getEvaluatedAt
                        )
                        .reversed()
        );
        FlightQualityAssessment latest = newestFirst.get(0);
        Integer previousScore = newestFirst.size() > 1
                ? newestFirst.get(1).getScore()
                : null;
        BigDecimal averageScore = decimal(
                newestFirst.stream()
                        .mapToInt(FlightQualityAssessment::getScore)
                        .average()
                        .orElse(0)
        );
        int minimumScore = newestFirst.stream()
                .mapToInt(FlightQualityAssessment::getScore)
                .min()
                .orElse(0);
        int criticalCount = newestFirst.stream()
                .mapToInt(FlightQualityAssessment::getCriticalCount)
                .sum();
        int warningCount = newestFirst.stream()
                .mapToInt(FlightQualityAssessment::getWarningCount)
                .sum();
        int completedCount = (int) newestFirst.stream()
                .filter(item ->
                        item.getSessionStatus()
                                == FlightSessionStatus.COMPLETED
                )
                .count();
        int abortedCount = (int) newestFirst.stream()
                .filter(item ->
                        item.getSessionStatus()
                                == FlightSessionStatus.ABORTED
                )
                .count();
        long totalDurationSeconds = newestFirst.stream()
                .map(item -> sessionsById.get(item.getSessionId()))
                .filter(session -> session != null)
                .mapToLong(this::durationSeconds)
                .sum();
        List<FleetReliabilityTrendPointResponse> trend = newestFirst
                .stream()
                .sorted(Comparator.comparing(
                        FlightQualityAssessment::getEvaluatedAt
                ))
                .map(item -> toTrendPoint(
                        item,
                        sessionsById.get(item.getSessionId())
                ))
                .toList();
        FleetReliabilityStatus status = reliabilityStatus(
                averageScore,
                criticalCount,
                warningCount
        );

        return new DroneReliabilityResponse(
                droneId,
                drone == null ? null : drone.getDroneCode(),
                drone == null ? null : drone.getName(),
                drone == null ? null : drone.getModelName(),
                status,
                newestFirst.size(),
                averageScore,
                minimumScore,
                latest.getScore(),
                previousScore,
                completedCount,
                abortedCount,
                totalDurationSeconds,
                criticalCount,
                warningCount,
                FlightQualityAssessmentResponse.from(latest),
                trend
        );
    }

    private FleetReliabilityTrendPointResponse toTrendPoint(
            FlightQualityAssessment assessment,
            FlightSession session
    ) {
        if (session == null) {
            Instant evaluatedAt = assessment.getEvaluatedAt()
                    .toInstant(ZoneOffset.UTC);

            return new FleetReliabilityTrendPointResponse(
                    assessment.getSessionId(),
                    assessment.getSessionId(),
                    assessment.getSessionStatus(),
                    evaluatedAt,
                    evaluatedAt,
                    0,
                    FlightQualityAssessmentResponse.from(assessment)
            );
        }

        ZoneId zoneId = ZoneId.systemDefault();

        return new FleetReliabilityTrendPointResponse(
                session.getSessionId(),
                session.getName(),
                session.getStatus(),
                toInstant(session.getStartedAt(), zoneId),
                toInstant(
                        session.getEndedAt() == null
                                ? session.getStartedAt()
                                : session.getEndedAt(),
                        zoneId
                ),
                durationSeconds(session),
                FlightQualityAssessmentResponse.from(assessment)
        );
    }

    private long durationSeconds(FlightSession session) {
        LocalDateTime endedAt = session.getEndedAt() == null
                ? session.getStartedAt()
                : session.getEndedAt();

        return Math.max(
                0,
                Duration.between(
                        session.getStartedAt(),
                        endedAt
                ).getSeconds()
        );
    }

    private Instant toInstant(LocalDateTime value, ZoneId zoneId) {
        return value.atZone(zoneId).toInstant();
    }

    private FleetReliabilityStatus reliabilityStatus(
            BigDecimal averageScore,
            int criticalCount,
            int warningCount
    ) {
        if (
                criticalCount > 0
                        || averageScore.compareTo(BigDecimal.valueOf(60)) < 0
        ) {
            return FleetReliabilityStatus.CHECK;
        }
        if (
                warningCount > 0
                        || averageScore.compareTo(BigDecimal.valueOf(75)) < 0
        ) {
            return FleetReliabilityStatus.WATCH;
        }
        return FleetReliabilityStatus.STABLE;
    }

    private int statusOrder(FleetReliabilityStatus status) {
        return switch (status) {
            case CHECK -> 0;
            case WATCH -> 1;
            case STABLE -> 2;
        };
    }

    private BigDecimal decimal(double value) {
        return BigDecimal.valueOf(value)
                .setScale(1, RoundingMode.HALF_UP);
    }
}
