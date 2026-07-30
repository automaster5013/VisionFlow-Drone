package com.visionflow.api.flight.quality.repository;

import com.visionflow.api.flight.quality.domain.FlightQualityAssessment;
import com.visionflow.api.flight.quality.domain.FlightQualityGrade;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;
import java.util.Optional;

public interface FlightQualityAssessmentRepository
        extends JpaRepository<FlightQualityAssessment, Long> {

    @Query("""
            SELECT DISTINCT assessment.droneId
            FROM FlightQualityAssessment assessment
            ORDER BY assessment.droneId
            """)
    List<Long> findDistinctDroneIds();

    Optional<FlightQualityAssessment> findBySessionIdAndRuleVersion(
            String sessionId,
            String ruleVersion
    );

    boolean existsBySessionIdAndRuleVersion(
            String sessionId,
            String ruleVersion
    );

    Optional<FlightQualityAssessment>
    findFirstByDroneIdAndSessionIdOrderByEvaluatedAtDesc(
            Long droneId,
            String sessionId
    );

    List<FlightQualityAssessment>
    findByDroneIdOrderByEvaluatedAtDesc(
            Long droneId,
            Pageable pageable
    );

    List<FlightQualityAssessment>
    findByDroneIdAndGradeOrderByEvaluatedAtDesc(
            Long droneId,
            FlightQualityGrade grade,
            Pageable pageable
    );
}
