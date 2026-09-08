CREATE TABLE flight_session_pause (
    session_id VARCHAR(36) NOT NULL,
    pause_index INT NOT NULL,
    paused_at DATETIME(6) NOT NULL,
    resumed_at DATETIME(6) NULL,
    PRIMARY KEY (session_id, pause_index),
    CONSTRAINT fk_flight_session_pause FOREIGN KEY (session_id) REFERENCES flight_session(session_id) ON DELETE CASCADE,
    CONSTRAINT ck_flight_session_pause_time CHECK (resumed_at IS NULL OR resumed_at >= paused_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
