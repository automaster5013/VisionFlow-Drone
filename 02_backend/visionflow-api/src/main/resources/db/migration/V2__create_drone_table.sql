CREATE TABLE drone (
                       id BIGINT NOT NULL AUTO_INCREMENT,

                       drone_code VARCHAR(50) NOT NULL,
                       name VARCHAR(100) NOT NULL,
                       model_name VARCHAR(100),
                       serial_number VARCHAR(100),

                       status VARCHAR(30) NOT NULL DEFAULT 'OFFLINE',

                       rtsp_url VARCHAR(500),

                       latitude DECIMAL(10, 7),
                       longitude DECIMAL(10, 7),
                       altitude DECIMAL(10, 2),

                       battery_level INT,

                       last_connected_at DATETIME(6),

                       created_at DATETIME(6) NOT NULL,
                       updated_at DATETIME(6) NOT NULL,

                       PRIMARY KEY (id),

                       CONSTRAINT uk_drone_code
                           UNIQUE (drone_code),

                       CONSTRAINT uk_drone_serial_number
                           UNIQUE (serial_number),

                       CONSTRAINT chk_drone_battery_level
                           CHECK (
                               battery_level IS NULL
                                   OR battery_level BETWEEN 0 AND 100
                               ),

                       CONSTRAINT chk_drone_latitude
                           CHECK (
                               latitude IS NULL
                                   OR latitude BETWEEN -90 AND 90
                               ),

                       CONSTRAINT chk_drone_longitude
                           CHECK (
                               longitude IS NULL
                                   OR longitude BETWEEN -180 AND 180
                               )

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;