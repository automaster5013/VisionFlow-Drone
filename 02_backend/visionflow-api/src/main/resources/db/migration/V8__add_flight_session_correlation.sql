ALTER TABLE drone
    ADD COLUMN flight_session_id VARCHAR(36) NULL
        AFTER source_device_id;

ALTER TABLE drone_telemetry_history
    ADD COLUMN flight_session_id VARCHAR(36) NULL
        AFTER source_device_id;

CREATE INDEX idx_telemetry_flight_session_recorded_at
    ON drone_telemetry_history (flight_session_id, recorded_at);

CREATE INDEX idx_ai_event_session_captured_at
    ON ai_inference_event (session_id, captured_at);
