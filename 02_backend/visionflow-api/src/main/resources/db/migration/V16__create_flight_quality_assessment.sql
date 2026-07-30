CREATE TABLE flight_quality_assessment
(
    id                          BIGINT       NOT NULL AUTO_INCREMENT,
    session_id                  VARCHAR(36)  NOT NULL,
    drone_id                    BIGINT       NOT NULL,
    rule_version                VARCHAR(30)  NOT NULL,
    session_status              VARCHAR(20)  NOT NULL,
    score                       TINYINT UNSIGNED NOT NULL,
    grade                       VARCHAR(20)  NOT NULL,
    data_score                  TINYINT UNSIGNED NOT NULL,
    flight_score                TINYINT UNSIGNED NOT NULL,
    ai_score                    TINYINT UNSIGNED NOT NULL,
    telemetry_count             BIGINT UNSIGNED NOT NULL,
    valid_coordinate_count      BIGINT UNSIGNED NOT NULL,
    coordinate_coverage_percent DECIMAL(6, 2) NOT NULL,
    battery_coverage_percent    DECIMAL(6, 2) NOT NULL,
    max_telemetry_gap_seconds   DECIMAL(12, 3) NULL,
    unrealistic_jump_count      INT UNSIGNED NOT NULL,
    altitude_spike_count        INT UNSIGNED NOT NULL,
    battery_increase_count      INT UNSIGNED NOT NULL,
    minimum_battery_level       INT NULL,
    ai_event_count              BIGINT UNSIGNED NOT NULL,
    detected_event_count        BIGINT UNSIGNED NOT NULL,
    average_inference_ms        DECIMAL(12, 3) NULL,
    snapshot_coverage_percent   DECIMAL(6, 2) NOT NULL,
    warning_count               INT UNSIGNED NOT NULL,
    critical_count              INT UNSIGNED NOT NULL,
    primary_risk_severity       VARCHAR(20) NULL,
    primary_risk_title          VARCHAR(120) NULL,
    primary_risk_detail         VARCHAR(500) NULL,
    evaluated_at                DATETIME(6) NOT NULL,
    created_at                  DATETIME(6) NOT NULL,
    updated_at                  DATETIME(6) NOT NULL,

    CONSTRAINT pk_flight_quality_assessment
        PRIMARY KEY (id),

    CONSTRAINT uk_flight_quality_session_rule
        UNIQUE (session_id, rule_version),

    CONSTRAINT fk_flight_quality_session
        FOREIGN KEY (session_id)
            REFERENCES flight_session (session_id)
            ON DELETE CASCADE,

    CONSTRAINT fk_flight_quality_drone
        FOREIGN KEY (drone_id)
            REFERENCES drone (id)
            ON DELETE CASCADE,

    CONSTRAINT chk_flight_quality_session_status
        CHECK (session_status IN ('READY', 'ACTIVE', 'COMPLETED', 'ABORTED')),

    CONSTRAINT chk_flight_quality_grade
        CHECK (grade IN ('EXCELLENT', 'GOOD', 'CAUTION', 'RISK')),

    CONSTRAINT chk_flight_quality_severity
        CHECK (
            primary_risk_severity IS NULL
            OR primary_risk_severity IN ('WARNING', 'CRITICAL')
        ),

    CONSTRAINT chk_flight_quality_total_score
        CHECK (score BETWEEN 0 AND 100),

    CONSTRAINT chk_flight_quality_component_scores
        CHECK (
            data_score BETWEEN 0 AND 40
            AND flight_score BETWEEN 0 AND 30
            AND ai_score BETWEEN 0 AND 30
        ),

    CONSTRAINT chk_flight_quality_coverage
        CHECK (
            coordinate_coverage_percent BETWEEN 0 AND 100
            AND battery_coverage_percent BETWEEN 0 AND 100
            AND snapshot_coverage_percent BETWEEN 0 AND 100
        ),

    INDEX idx_flight_quality_drone_evaluated
        (drone_id, evaluated_at DESC),

    INDEX idx_flight_quality_drone_grade
        (drone_id, grade, evaluated_at DESC)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;
