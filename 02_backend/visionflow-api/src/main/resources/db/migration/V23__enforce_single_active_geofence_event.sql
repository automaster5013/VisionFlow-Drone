ALTER TABLE drone_geofence_event
    ADD COLUMN active_drone_id BIGINT
        GENERATED ALWAYS AS (
            CASE WHEN resolved_at IS NULL THEN drone_id ELSE NULL END
        ) STORED,
    ADD COLUMN active_geofence_id BIGINT
        GENERATED ALWAYS AS (
            CASE WHEN resolved_at IS NULL THEN geofence_id ELSE NULL END
        ) STORED,
    ADD CONSTRAINT uq_geofence_event_one_active_per_drone_zone
        UNIQUE (active_drone_id, active_geofence_id);
