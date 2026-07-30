CREATE TABLE drone_telemetry_history
(
    id            BIGINT AUTO_INCREMENT,
    drone_id      BIGINT         NOT NULL,
    latitude      DECIMAL(10, 7) NULL,
    longitude     DECIMAL(10, 7) NULL,
    altitude      DECIMAL(10, 2) NULL,
    battery_level INT            NULL,
    status        VARCHAR(32)    NOT NULL,
    recorded_at   DATETIME(6)    NOT NULL,
    created_at    DATETIME(6)    NOT NULL DEFAULT CURRENT_TIMESTAMP(6),

    CONSTRAINT pk_drone_telemetry_history
        PRIMARY KEY (id),

    CONSTRAINT fk_telemetry_history_drone
        FOREIGN KEY (drone_id)
            REFERENCES drone (id)
            ON DELETE CASCADE,

    INDEX idx_telemetry_drone_recorded_at
        (drone_id, recorded_at),

    INDEX idx_telemetry_recorded_at
        (recorded_at)
);