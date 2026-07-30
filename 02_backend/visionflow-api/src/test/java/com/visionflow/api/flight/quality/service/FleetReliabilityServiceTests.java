package com.visionflow.api.flight.quality.service;

import com.visionflow.api.drone.domain.Drone;
import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.flight.domain.FlightSession;
import com.visionflow.api.flight.domain.FlightSessionStatus;
import com.visionflow.api.flight.quality.domain.FleetReliabilityStatus;
import com.visionflow.api.flight.quality.domain.FlightQualityAssessment;
import com.visionflow.api.flight.quality.domain.FlightQualityGrade;
import com.visionflow.api.flight.quality.domain.FlightQualityRisk;
import com.visionflow.api.flight.quality.domain.FlightQualitySeverity;
import com.visionflow.api.flight.quality.domain.FlightQualitySnapshot;
import com.visionflow.api.flight.quality.repository.FlightQualityAssessmentRepository;
import com.visionflow.api.flight.repository.FlightSessionRepository;
import org.junit.jupiter.api.Test;
import org.springframework.data.domain.Pageable;

import java.time.LocalDateTime;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class FleetReliabilityServiceTests {

    private final FlightQualityAssessmentRepository assessmentRepository =
            mock(FlightQualityAssessmentRepository.class);
    private final FlightSessionRepository sessionRepository =
            mock(FlightSessionRepository.class);
    private final DroneRepository droneRepository =
            mock(DroneRepository.class);
    private final FleetReliabilityService service =
            new FleetReliabilityService(
                    assessmentRepository,
                    sessionRepository,
                    droneRepository
            );

    @Test
    void summarizesPersistedAssessmentsIntoFleetAndDroneMetrics() {
        FlightSession first = terminalSession(
                "session-1",
                1L,
                60,
                false
        );
        FlightSession second = terminalSession(
                "session-2",
                1L,
                120,
                false
        );
        FlightSession risky = terminalSession(
                "session-3",
                2L,
                30,
                true
        );
        FlightQualityAssessment firstAssessment = assessment(
                first,
                80,
                1,
                0,
                LocalDateTime.of(2026, 7, 25, 1, 2)
        );
        FlightQualityAssessment secondAssessment = assessment(
                second,
                90,
                0,
                0,
                LocalDateTime.of(2026, 7, 25, 2, 3)
        );
        FlightQualityAssessment riskyAssessment = assessment(
                risky,
                50,
                0,
                1,
                LocalDateTime.of(2026, 7, 25, 3, 1)
        );
        Drone firstDrone = drone(1L, "DRONE-001", "Vision Eagle 1");
        Drone secondDrone = drone(2L, "DRONE-002", "Vision Eagle 2");

        when(assessmentRepository.findDistinctDroneIds())
                .thenReturn(List.of(1L, 2L));
        when(assessmentRepository.findByDroneIdOrderByEvaluatedAtDesc(
                eq(1L),
                any(Pageable.class)
        )).thenReturn(List.of(secondAssessment, firstAssessment));
        when(assessmentRepository.findByDroneIdOrderByEvaluatedAtDesc(
                eq(2L),
                any(Pageable.class)
        )).thenReturn(List.of(riskyAssessment));
        when(sessionRepository.findAllById(any()))
                .thenReturn(List.of(first, second, risky));
        when(droneRepository.findAllById(List.of(1L, 2L)))
                .thenReturn(List.of(firstDrone, secondDrone));
        when(sessionRepository.findDistinctDroneIdsByStatusIn(any()))
                .thenReturn(List.of(1L, 2L));

        var result = service.summarize(20);

        assertThat(result.droneCount()).isEqualTo(2);
        assertThat(result.assessmentCount()).isEqualTo(3);
        assertThat(result.attentionDroneCount()).isEqualTo(2);
        assertThat(result.fleetAverageScore())
                .isEqualByComparingTo("67.5");
        assertThat(result.backfillCandidateDroneIds())
                .containsExactly(1L, 2L);
        assertThat(result.drones())
                .extracting(item -> item.droneId())
                .containsExactly(2L, 1L);

        var firstDroneResult = result.drones().get(1);
        assertThat(firstDroneResult.status())
                .isEqualTo(FleetReliabilityStatus.WATCH);
        assertThat(firstDroneResult.averageScore())
                .isEqualByComparingTo("85.0");
        assertThat(firstDroneResult.minimumScore()).isEqualTo(80);
        assertThat(firstDroneResult.latestScore()).isEqualTo(90);
        assertThat(firstDroneResult.previousScore()).isEqualTo(80);
        assertThat(firstDroneResult.completedCount()).isEqualTo(2);
        assertThat(firstDroneResult.totalDurationSeconds()).isEqualTo(180);
        assertThat(firstDroneResult.trend())
                .extracting(point -> point.sessionId())
                .containsExactly("session-1", "session-2");
        verify(assessmentRepository)
                .findByDroneIdOrderByEvaluatedAtDesc(
                        eq(1L),
                        any(Pageable.class)
                );
    }

    @Test
    void returnsEmptySummaryWhenNoAssessmentExists() {
        when(assessmentRepository.findDistinctDroneIds())
                .thenReturn(List.of());
        when(droneRepository.findAllById(List.of()))
                .thenReturn(List.of());
        when(sessionRepository.findDistinctDroneIdsByStatusIn(any()))
                .thenReturn(List.of(3L));

        var result = service.summarize(20);

        assertThat(result.droneCount()).isZero();
        assertThat(result.assessmentCount()).isZero();
        assertThat(result.fleetAverageScore())
                .isEqualByComparingTo("0.0");
        assertThat(result.backfillCandidateDroneIds())
                .containsExactly(3L);
        assertThat(result.drones()).isEmpty();
    }

    private Drone drone(Long id, String code, String name) {
        Drone drone = mock(Drone.class);
        when(drone.getId()).thenReturn(id);
        when(drone.getDroneCode()).thenReturn(code);
        when(drone.getName()).thenReturn(name);
        when(drone.getModelName()).thenReturn("Custom Vision Drone");
        return drone;
    }

    private FlightSession terminalSession(
            String sessionId,
            Long droneId,
            int durationSeconds,
            boolean aborted
    ) {
        LocalDateTime startedAt =
                LocalDateTime.of(2026, 7, 25, droneId.intValue(), 0);
        FlightSession session = FlightSession.start(
                sessionId,
                droneId,
                "함대 신뢰도 검증 " + sessionId,
                null,
                "test-device",
                startedAt
        );

        if (aborted) {
            session.abort(startedAt.plusSeconds(durationSeconds));
        } else {
            session.complete(startedAt.plusSeconds(durationSeconds));
        }

        return session;
    }

    private FlightQualityAssessment assessment(
            FlightSession session,
            int score,
            int warningCount,
            int criticalCount,
            LocalDateTime evaluatedAt
    ) {
        FlightQualityGrade grade = score >= 90
                ? FlightQualityGrade.EXCELLENT
                : score >= 75
                ? FlightQualityGrade.GOOD
                : score >= 60
                ? FlightQualityGrade.CAUTION
                : FlightQualityGrade.RISK;
        FlightQualityRisk primaryRisk = criticalCount > 0
                ? new FlightQualityRisk(
                        FlightQualitySeverity.CRITICAL,
                        "비행 품질 위험",
                        "즉시 확인이 필요합니다."
                )
                : warningCount > 0
                ? new FlightQualityRisk(
                        FlightQualitySeverity.WARNING,
                        "비행 품질 주의",
                        "추세를 관찰하세요."
                )
                : null;
        FlightQualitySnapshot snapshot = new FlightQualitySnapshot(
                session.getStatus(),
                score,
                grade,
                score,
                score,
                score,
                5,
                5,
                100,
                100,
                1.0,
                0,
                0,
                0,
                80,
                1,
                1,
                100.0,
                100,
                warningCount,
                criticalCount,
                primaryRisk
        );

        return FlightQualityAssessment.create(
                session,
                FlightQualityAssessmentService.CURRENT_RULE_VERSION,
                snapshot,
                evaluatedAt
        );
    }
}
