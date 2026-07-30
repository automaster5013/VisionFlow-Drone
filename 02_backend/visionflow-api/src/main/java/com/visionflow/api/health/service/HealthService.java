package com.visionflow.api.health.service;

import com.visionflow.api.health.dto.HealthResponse;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;

@Service
public class HealthService {

    private final JdbcTemplate jdbcTemplate;

    public HealthService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public HealthResponse checkHealth() {
        String databaseStatus = checkDatabase();

        return new HealthResponse(
                "visionflow-api",
                "UP",
                databaseStatus,
                LocalDateTime.now()
        );
    }

    private String checkDatabase() {
        try {
            Integer result = jdbcTemplate.queryForObject(
                    "SELECT 1",
                    Integer.class
            );

            return Integer.valueOf(1).equals(result)
                    ? "UP"
                    : "DOWN";

        } catch (Exception exception) {
            return "DOWN";
        }
    }
}