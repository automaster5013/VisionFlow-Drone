CREATE TABLE demo_scenario (
    scenario_id VARCHAR(36) NOT NULL,
    drone_id BIGINT NOT NULL,
    flight_session_id VARCHAR(36) NOT NULL,
    ai_event_id BIGINT NULL,
    ai_alert_id BIGINT NULL,
    incident_id BIGINT NULL,
    stage VARCHAR(20) NOT NULL,
    last_message VARCHAR(500) NOT NULL,
    started_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    completed_at DATETIME(6) NULL,
    PRIMARY KEY (scenario_id),
    CONSTRAINT chk_demo_scenario_stage
        CHECK (stage IN (
            'READY',
            'DETECTED',
            'ESCALATED',
            'RESOLVED',
            'COMPLETED'
        ))
);

CREATE INDEX idx_demo_scenario_drone_started
    ON demo_scenario (drone_id, started_at);

CREATE INDEX idx_demo_scenario_incident
    ON demo_scenario (incident_id);
