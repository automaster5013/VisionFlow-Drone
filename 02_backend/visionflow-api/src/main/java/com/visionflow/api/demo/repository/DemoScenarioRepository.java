package com.visionflow.api.demo.repository;

import com.visionflow.api.demo.domain.DemoScenario;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DemoScenarioRepository
        extends JpaRepository<DemoScenario, String> {
}
