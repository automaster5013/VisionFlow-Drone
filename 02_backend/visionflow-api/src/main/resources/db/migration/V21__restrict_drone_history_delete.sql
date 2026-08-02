-- A Drone can be removed only while it has no operational history.
-- Application checks cover physical and soft correlations; these constraints
-- are the final database boundary for Drone-owned physical history.
ALTER TABLE drone_telemetry_history
    DROP FOREIGN KEY fk_telemetry_history_drone;

ALTER TABLE drone_telemetry_history
    ADD CONSTRAINT fk_telemetry_history_drone
        FOREIGN KEY (drone_id)
            REFERENCES drone (id)
            ON DELETE RESTRICT;

ALTER TABLE flight_session
    DROP FOREIGN KEY fk_flight_session_drone;

ALTER TABLE flight_session
    ADD CONSTRAINT fk_flight_session_drone
        FOREIGN KEY (drone_id)
            REFERENCES drone (id)
            ON DELETE RESTRICT;

ALTER TABLE flight_quality_assessment
    DROP FOREIGN KEY fk_flight_quality_drone;

ALTER TABLE flight_quality_assessment
    ADD CONSTRAINT fk_flight_quality_drone
        FOREIGN KEY (drone_id)
            REFERENCES drone (id)
            ON DELETE RESTRICT;
