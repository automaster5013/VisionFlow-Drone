CREATE TABLE audit_log (
    id BIGINT NOT NULL AUTO_INCREMENT,
    occurred_at DATETIME(6) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    action VARCHAR(80) NOT NULL,
    entity_type VARCHAR(60) NOT NULL,
    entity_id VARCHAR(100) NOT NULL,
    summary VARCHAR(255) NOT NULL,
    details_json LONGTEXT NULL,
    request_method VARCHAR(10) NULL,
    request_path VARCHAR(500) NULL,
    trace_id VARCHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    INDEX idx_audit_log_occurred_at (occurred_at DESC),
    INDEX idx_audit_log_entity (entity_type, entity_id, occurred_at DESC),
    INDEX idx_audit_log_action (action, occurred_at DESC),
    INDEX idx_audit_log_actor (actor, occurred_at DESC),
    INDEX idx_audit_log_trace_id (trace_id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;
