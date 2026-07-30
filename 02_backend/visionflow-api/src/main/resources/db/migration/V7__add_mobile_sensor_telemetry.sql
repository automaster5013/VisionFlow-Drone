ALTER TABLE drone
    ADD COLUMN heading DECIMAL(6, 2) NULL AFTER battery_level,
    ADD COLUMN pitch DECIMAL(6, 2) NULL AFTER heading,
    ADD COLUMN roll DECIMAL(6, 2) NULL AFTER pitch,
    ADD COLUMN ground_speed DECIMAL(10, 2) NULL AFTER roll,
    ADD COLUMN horizontal_accuracy DECIMAL(10, 2) NULL AFTER ground_speed,
    ADD COLUMN vertical_accuracy DECIMAL(10, 2) NULL AFTER horizontal_accuracy,
    ADD COLUMN telemetry_source VARCHAR(30) NOT NULL DEFAULT 'API'
        AFTER vertical_accuracy,
    ADD COLUMN source_device_id VARCHAR(100) NULL AFTER telemetry_source;

ALTER TABLE drone
    ADD CONSTRAINT chk_drone_heading
        CHECK (heading IS NULL OR heading BETWEEN 0 AND 360),
    ADD CONSTRAINT chk_drone_pitch
        CHECK (pitch IS NULL OR pitch BETWEEN -180 AND 180),
    ADD CONSTRAINT chk_drone_roll
        CHECK (roll IS NULL OR roll BETWEEN -90 AND 90),
    ADD CONSTRAINT chk_drone_ground_speed
        CHECK (ground_speed IS NULL OR ground_speed >= 0),
    ADD CONSTRAINT chk_drone_horizontal_accuracy
        CHECK (horizontal_accuracy IS NULL OR horizontal_accuracy >= 0),
    ADD CONSTRAINT chk_drone_vertical_accuracy
        CHECK (vertical_accuracy IS NULL OR vertical_accuracy >= 0),
    ADD CONSTRAINT chk_drone_telemetry_source
        CHECK (
            telemetry_source IN (
                'API',
                'SIMULATOR',
                'MOBILE_SENSOR',
                'DJI_DEVICE'
            )
        );

ALTER TABLE drone_telemetry_history
    ADD COLUMN heading DECIMAL(6, 2) NULL AFTER battery_level,
    ADD COLUMN pitch DECIMAL(6, 2) NULL AFTER heading,
    ADD COLUMN roll DECIMAL(6, 2) NULL AFTER pitch,
    ADD COLUMN ground_speed DECIMAL(10, 2) NULL AFTER roll,
    ADD COLUMN horizontal_accuracy DECIMAL(10, 2) NULL AFTER ground_speed,
    ADD COLUMN vertical_accuracy DECIMAL(10, 2) NULL AFTER horizontal_accuracy,
    ADD COLUMN telemetry_source VARCHAR(30) NOT NULL DEFAULT 'API'
        AFTER vertical_accuracy,
    ADD COLUMN source_device_id VARCHAR(100) NULL AFTER telemetry_source;

ALTER TABLE drone_telemetry_history
    ADD CONSTRAINT chk_history_heading
        CHECK (heading IS NULL OR heading BETWEEN 0 AND 360),
    ADD CONSTRAINT chk_history_pitch
        CHECK (pitch IS NULL OR pitch BETWEEN -180 AND 180),
    ADD CONSTRAINT chk_history_roll
        CHECK (roll IS NULL OR roll BETWEEN -90 AND 90),
    ADD CONSTRAINT chk_history_ground_speed
        CHECK (ground_speed IS NULL OR ground_speed >= 0),
    ADD CONSTRAINT chk_history_horizontal_accuracy
        CHECK (horizontal_accuracy IS NULL OR horizontal_accuracy >= 0),
    ADD CONSTRAINT chk_history_vertical_accuracy
        CHECK (vertical_accuracy IS NULL OR vertical_accuracy >= 0),
    ADD CONSTRAINT chk_history_telemetry_source
        CHECK (
            telemetry_source IN (
                'API',
                'SIMULATOR',
                'MOBILE_SENSOR',
                'DJI_DEVICE'
            )
        );

CREATE INDEX idx_history_source_recorded
    ON drone_telemetry_history (
        telemetry_source,
        recorded_at
    );
