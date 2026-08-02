package com.visionflow.api.demo.repository;

import com.visionflow.api.demo.domain.DemoScenario;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;

public interface DemoScenarioRepository
        extends JpaRepository<DemoScenario, String> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            SELECT scenario
            FROM DemoScenario scenario
            WHERE scenario.scenarioId = :scenarioId
            """)
    Optional<DemoScenario> findByIdForUpdate(
            @Param("scenarioId") String scenarioId
    );
}
