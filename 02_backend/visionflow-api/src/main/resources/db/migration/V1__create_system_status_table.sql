CREATE TABLE system_status (
                               id BIGINT NOT NULL AUTO_INCREMENT,
                               service_name VARCHAR(100) NOT NULL,
                               status VARCHAR(30) NOT NULL,
                               message VARCHAR(255),
                               checked_at DATETIME(6) NOT NULL,

                               PRIMARY KEY (id),

                               CONSTRAINT uk_system_status_service_name
                                   UNIQUE (service_name)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;