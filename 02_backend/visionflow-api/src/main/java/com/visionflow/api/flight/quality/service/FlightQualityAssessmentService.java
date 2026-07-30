package com.visionflow.api.flight.quality.service;

import com.visionflow.api.ai.domain.AiInferenceEvent;
import com.visionflow.api.ai.repository.AiInferenceEventRepository;
import com.visionflow.api.common.exception.BusinessException;
import com.visionflow.api.common.exception.ResourceNotFoundException;
import com.visionflow.api.drone.domain.DroneTelemetryHistory;
import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.drone.repository.DroneTelemetryHistoryRepository;
import com.visionflow.api.flight.domain.FlightSession;
import com.visionflow.api.flight.quality.domain.FlightQualityAssessment;
import com.visionflow.api.flight.quality.domain.FlightQualityGrade;
import com.visionflow.api.flight.quality.domain.FlightQualitySnapshot;
import com.visionflow.api.flight.quality.dto.FlightQualityAssessmentResponse;
import com.visionflow.api.flight.quality.repository.FlightQualityAssessmentRepository;
import com.visionflow.api.flight.repository.FlightSessionRepository;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;

@Service
public class FlightQualityAssessmentService {

    public static final String CURRENT_RULE_VERSION = "VFQ-1.0.0";
    private static final int MAX_TELEMETRY_SAMPLES = 50_000;
    private static final int MAX_AI_EVENTS = 20_000;

    private final DroneRepository droneRepository;
    private final FlightSessionRepository sessionRepository;
    private final DroneTelemetryHistoryRepository telemetryRepository;
    private final AiInferenceEventRepository eventRepository;
    private final FlightQualityAssessmentRepository assessmentRepository;
    private final FlightQualityCalculator calculator;

    public FlightQualityAssessmentService(
            DroneRepository droneRepository,
            FlightSessionRepository sessionRepository,
            DroneTelemetryHistoryRepository telemetryRepository,
            AiInferenceEventRepository eventRepository,
            FlightQualityAssessmentRepository assessmentRepository,
            FlightQualityCalculator calculator
    ) {
        this.droneRepository = droneRepository;
        this.sessionRepository = sessionRepository;
        this.telemetryRepository = telemetryRepository;
        this.eventRepository = eventRepository;
        this.assessmentRepository = assessmentRepository;
        this.calculator = calculator;
    }

    @Transactional
    public FlightQualityAssessmentResponse recalculate(
            Long droneId,
            String sessionId
    ) {
        FlightSession session = requireSession(droneId, sessionId);
        long telemetryCount =
                telemetryRepository.countByDroneIdAndFlightSessionId(
                        droneId,
                        sessionId
                );
        long aiEventCount =
                eventRepository.countByDroneIdAndSessionId(
                        droneId,
                        sessionId
                );
        ensureSampleLimits(telemetryCount, aiEventCount);

        List<DroneTelemetryHistory> telemetry =
                telemetryRepository
                        .findByDroneIdAndFlightSessionIdOrderByRecordedAtAsc(
                                droneId,
                                sessionId,
                                PageRequest.of(
                                        0,
                                        MAX_TELEMETRY_SAMPLES
                                )
                        );
        List<AiInferenceEvent> aiEvents =
                eventRepository
                        .findAllByDroneIdAndSessionIdOrderByCapturedAtAsc(
                                droneId,
                                sessionId,
                                PageRequest.of(0, MAX_AI_EVENTS)
                        );
        FlightQualitySnapshot snapshot = calculator.calculate(
                session.getStatus(),
                telemetry,
                aiEvents
        );
        LocalDateTime evaluatedAt =
                LocalDateTime.now(ZoneOffset.UTC);
        FlightQualityAssessment assessment =
                assessmentRepository
                        .findBySessionIdAndRuleVersion(
                                sessionId,
                                CURRENT_RULE_VERSION
                        )
                        .orElse(null);

        if (assessment == null) {
            assessment = FlightQualityAssessment.create(
                    session,
                    CURRENT_RULE_VERSION,
                    snapshot,
                    evaluatedAt
            );
        } else {
            assessment.apply(snapshot, evaluatedAt);
        }
        return FlightQualityAssessmentResponse.from(
                assessmentRepository.saveAndFlush(assessment)
        );
    }

    @Transactional(readOnly = true)
    public FlightQualityAssessmentResponse find(
            Long droneId,
            String sessionId
    ) {
        requireSession(droneId, sessionId);
        return assessmentRepository
                .findFirstByDroneIdAndSessionIdOrderByEvaluatedAtDesc(
                        droneId,
                        sessionId
                )
                .map(FlightQualityAssessmentResponse::from)
                .orElseThrow(() ->
                        new ResourceNotFoundException(
                                "저장된 비행 품질 평가를 찾을 수 없습니다: "
                                        + sessionId
                        )
                );
    }

    @Transactional(readOnly = true)
    public List<FlightQualityAssessmentResponse> findHistory(
            Long droneId,
            FlightQualityGrade grade,
            int limit
    ) {
        ensureDroneExists(droneId);
        PageRequest pageRequest = PageRequest.of(0, limit);
        List<FlightQualityAssessment> assessments =
                grade == null
                        ? assessmentRepository
                        .findByDroneIdOrderByEvaluatedAtDesc(
                                droneId,
                                pageRequest
                        )
                        : assessmentRepository
                        .findByDroneIdAndGradeOrderByEvaluatedAtDesc(
                                droneId,
                                grade,
                                pageRequest
                        );

        return assessments.stream()
                .map(FlightQualityAssessmentResponse::from)
                .toList();
    }

    private FlightSession requireSession(
            Long droneId,
            String sessionId
    ) {
        ensureDroneExists(droneId);
        return sessionRepository
                .findBySessionIdAndDroneId(sessionId, droneId)
                .orElseThrow(() ->
                        new ResourceNotFoundException(
                                "관리 비행 세션을 찾을 수 없습니다: "
                                        + sessionId
                        )
                );
    }

    private void ensureDroneExists(Long droneId) {
        if (!droneRepository.existsById(droneId)) {
            throw new ResourceNotFoundException(
                    "드론을 찾을 수 없습니다: " + droneId
            );
        }
    }

    private void ensureSampleLimits(
            long telemetryCount,
            long aiEventCount
    ) {
        if (
                telemetryCount <= MAX_TELEMETRY_SAMPLES
                        && aiEventCount <= MAX_AI_EVENTS
        ) {
            return;
        }

        throw new BusinessException(
                HttpStatus.UNPROCESSABLE_CONTENT,
                "FLIGHT_QUALITY_SAMPLE_LIMIT_EXCEEDED",
                "품질 평가 표본 제한을 초과했습니다. "
                        + "텔레메트리="
                        + telemetryCount
                        + "/"
                        + MAX_TELEMETRY_SAMPLES
                        + ", AI 이벤트="
                        + aiEventCount
                        + "/"
                        + MAX_AI_EVENTS
        );
    }
}
