ALTER TABLE flight_quality_assessment
    MODIFY COLUMN score INT NOT NULL,
    MODIFY COLUMN data_score INT NOT NULL,
    MODIFY COLUMN flight_score INT NOT NULL,
    MODIFY COLUMN ai_score INT NOT NULL,
    MODIFY COLUMN telemetry_count BIGINT NOT NULL,
    MODIFY COLUMN valid_coordinate_count BIGINT NOT NULL,
    MODIFY COLUMN unrealistic_jump_count INT NOT NULL,
    MODIFY COLUMN altitude_spike_count INT NOT NULL,
    MODIFY COLUMN battery_increase_count INT NOT NULL,
    MODIFY COLUMN ai_event_count BIGINT NOT NULL,
    MODIFY COLUMN detected_event_count BIGINT NOT NULL,
    MODIFY COLUMN warning_count INT NOT NULL,
    MODIFY COLUMN critical_count INT NOT NULL;
