package com.visionflow.api.flight.quality.service;

import com.visionflow.api.common.exception.BusinessException;
import com.visionflow.api.common.exception.ResourceNotFoundException;
import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.flight.domain.FlightSession;
import com.visionflow.api.flight.domain.FlightSessionStatus;
import com.visionflow.api.flight.quality.dto.FlightQualityBackfillResponse;
import com.visionflow.api.flight.quality.repository.FlightQualityAssessmentRepository;
import com.visionflow.api.flight.repository.FlightSessionRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

@Service
public class FlightQualityBackfillService {

    private static final Logger log = LoggerFactory.getLogger(
            FlightQualityBackfillService.class
    );
    private static final int MAX_FAILURE_MESSAGE_LENGTH = 300;
    private static final List<FlightSessionStatus> TERMINAL_STATUSES =
            List.of(
                    FlightSessionStatus.COMPLETED,
                    FlightSessionStatus.ABORTED
            );

    private final DroneRepository droneRepository;
    private final FlightSessionRepository sessionRepository;
    private final FlightQualityAssessmentRepository assessmentRepository;
    private final FlightQualityAssessmentService assessmentService;

    public FlightQualityBackfillService(
            DroneRepository droneRepository,
            FlightSessionRepository sessionRepository,
            FlightQualityAssessmentRepository assessmentRepository,
            FlightQualityAssessmentService assessmentService
    ) {
        this.droneRepository = droneRepository;
        this.sessionRepository = sessionRepository;
        this.assessmentRepository = assessmentRepository;
        this.assessmentService = assessmentService;
    }

    public FlightQualityBackfillResponse backfill(
            Long droneId,
            int limit,
            boolean force
    ) {
        if (!droneRepository.existsById(droneId)) {
            throw new ResourceNotFoundException(
                    "드론을 찾을 수 없습니다: " + droneId
            );
        }

        List<FlightSession> candidates =
                sessionRepository
                        .findByDroneIdAndStatusInOrderByEndedAtDesc(
                                droneId,
                                TERMINAL_STATUSES,
                                PageRequest.of(0, limit)
                        );
        int evaluatedCount = 0;
        int skippedCount = 0;
        List<FlightQualityBackfillResponse.Failure> failures =
                new ArrayList<>();

        for (FlightSession session : candidates) {
            String sessionId = session.getSessionId();
            boolean alreadyEvaluated =
                    assessmentRepository
                            .existsBySessionIdAndRuleVersion(
                                    sessionId,
                                    FlightQualityAssessmentService
                                            .CURRENT_RULE_VERSION
                            );

            if (!force && alreadyEvaluated) {
                skippedCount += 1;
                continue;
            }

            try {
                assessmentService.recalculate(droneId, sessionId);
                evaluatedCount += 1;
            } catch (RuntimeException exception) {
                log.error(
                        "비행 품질 평가 백필 실패: "
                                + "droneId={}, sessionId={}",
                        droneId,
                        sessionId,
                        exception
                );
                failures.add(new FlightQualityBackfillResponse.Failure(
                        sessionId,
                        failureMessage(exception)
                ));
            }
        }

        return new FlightQualityBackfillResponse(
                droneId,
                FlightQualityAssessmentService.CURRENT_RULE_VERSION,
                force,
                candidates.size(),
                evaluatedCount,
                skippedCount,
                failures.size(),
                List.copyOf(failures)
        );
    }

    private String failureMessage(RuntimeException exception) {
        if (!(exception instanceof BusinessException)
                && !(exception instanceof IllegalArgumentException)) {
            return "평가 처리 중 내부 오류가 발생했습니다.";
        }

        String message = exception.getMessage();

        if (message == null || message.isBlank()) {
            message = exception.getClass().getSimpleName();
        }

        return message.length() <= MAX_FAILURE_MESSAGE_LENGTH
                ? message
                : message.substring(0, MAX_FAILURE_MESSAGE_LENGTH);
    }
}
