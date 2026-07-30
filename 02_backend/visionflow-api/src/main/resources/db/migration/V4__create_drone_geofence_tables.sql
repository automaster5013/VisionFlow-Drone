CREATE TABLE drone_geofence (
                                id BIGINT NOT NULL AUTO_INCREMENT,
                                name VARCHAR(100) NOT NULL,
                                rule_type VARCHAR(20) NOT NULL,
                                center_latitude DECIMAL(10, 7) NOT NULL,
                                center_longitude DECIMAL(10, 7) NOT NULL,
                                radius_meters DECIMAL(10, 2) NOT NULL,
                                active BOOLEAN NOT NULL DEFAULT TRUE,
                                created_at DATETIME(6) NOT NULL,
                                updated_at DATETIME(6) NOT NULL,

                                PRIMARY KEY (id),
                                UNIQUE KEY uk_drone_geofence_name (name),
                                KEY idx_drone_geofence_active (active),

                                CONSTRAINT chk_drone_geofence_rule
                                    CHECK (rule_type IN ('KEEP_IN', 'KEEP_OUT')),
                                CONSTRAINT chk_drone_geofence_radius
                                    CHECK (radius_meters > 0)
);

CREATE TABLE drone_geofence_event (
                                      id BIGINT NOT NULL AUTO_INCREMENT,
                                      drone_id BIGINT NOT NULL,
                                      drone_code VARCHAR(100) NOT NULL,
                                      geofence_id BIGINT NOT NULL,
                                      geofence_name VARCHAR(100) NOT NULL,
                                      rule_type VARCHAR(20) NOT NULL,

                                      last_latitude DECIMAL(10, 7) NOT NULL,
                                      last_longitude DECIMAL(10, 7) NOT NULL,
                                      last_altitude DECIMAL(10, 2) NULL,
                                      distance_meters DECIMAL(12, 2) NOT NULL,

                                      detected_at DATETIME(6) NOT NULL,
                                      resolved_at DATETIME(6) NULL,
                                      created_at DATETIME(6) NOT NULL,
                                      updated_at DATETIME(6) NOT NULL,

                                      PRIMARY KEY (id),
                                      KEY idx_geofence_event_drone (drone_id, detected_at),
                                      KEY idx_geofence_event_zone (geofence_id, detected_at),
                                      KEY idx_geofence_event_active (resolved_at, detected_at),

                                      CONSTRAINT fk_geofence_event_geofence
                                          FOREIGN KEY (geofence_id)
                                              REFERENCES drone_geofence (id)
);