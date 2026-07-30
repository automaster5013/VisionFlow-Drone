CREATE TABLE maintenance_work_order (
    id BIGINT NOT NULL AUTO_INCREMENT,
    incident_id BIGINT NOT NULL,
    drone_id BIGINT NOT NULL,
    session_id VARCHAR(36) NULL,
    source_assessment_id BIGINT NULL,
    status VARCHAR(20) NOT NULL,
    clearance_status VARCHAR(30) NOT NULL,
    assignee VARCHAR(100) NULL,
    finding VARCHAR(1000) NULL,
    resolution_note VARCHAR(1000) NULL,
    opened_at DATETIME(6) NOT NULL,
    started_at DATETIME(6) NULL,
    completed_at DATETIME(6) NULL,
    cleared_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,

    PRIMARY KEY (id),
    UNIQUE KEY uk_maintenance_work_order_incident (incident_id),
    KEY idx_maintenance_work_order_drone_status (
        drone_id,
        status,
        updated_at
    ),
    KEY idx_maintenance_work_order_clearance (
        clearance_status,
        updated_at
    ),
    KEY idx_maintenance_work_order_session (session_id),

    CONSTRAINT fk_maintenance_work_order_incident
        FOREIGN KEY (incident_id)
        REFERENCES incident (id)
        ON DELETE CASCADE,
    CONSTRAINT fk_maintenance_work_order_drone
        FOREIGN KEY (drone_id)
        REFERENCES drone (id),
    CONSTRAINT fk_maintenance_work_order_assessment
        FOREIGN KEY (source_assessment_id)
        REFERENCES flight_quality_assessment (id)
        ON DELETE SET NULL,
    CONSTRAINT chk_maintenance_work_order_status
        CHECK (
            status IN (
                'OPEN',
                'IN_PROGRESS',
                'COMPLETED',
                'GROUNDED'
            )
        ),
    CONSTRAINT chk_maintenance_clearance_status
        CHECK (
            clearance_status IN (
                'PENDING_INSPECTION',
                'CLEARED',
                'GROUNDED'
            )
        ),
    CONSTRAINT chk_maintenance_completion
        CHECK (
            status NOT IN ('COMPLETED', 'GROUNDED')
            OR completed_at IS NOT NULL
        ),
    CONSTRAINT chk_maintenance_clearance
        CHECK (
            clearance_status <> 'CLEARED'
            OR cleared_at IS NOT NULL
        )
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;

CREATE TABLE maintenance_work_order_history (
    id BIGINT NOT NULL AUTO_INCREMENT,
    work_order_id BIGINT NOT NULL,
    action_type VARCHAR(30) NOT NULL,
    previous_status VARCHAR(20) NULL,
    new_status VARCHAR(20) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    note VARCHAR(1000) NULL,
    created_at DATETIME(6) NOT NULL,

    PRIMARY KEY (id),
    KEY idx_maintenance_history_work_order (
        work_order_id,
        created_at,
        id
    ),

    CONSTRAINT fk_maintenance_history_work_order
        FOREIGN KEY (work_order_id)
        REFERENCES maintenance_work_order (id)
        ON DELETE CASCADE,
    CONSTRAINT chk_maintenance_history_action
        CHECK (
            action_type IN (
                'CREATED',
                'RISK_SYNCHRONIZED',
                'REOPENED',
                'INSPECTION_STARTED',
                'RETURNED_TO_SERVICE',
                'GROUNDED'
            )
        ),
    CONSTRAINT chk_maintenance_history_previous_status
        CHECK (
            previous_status IS NULL
            OR previous_status IN (
                'OPEN',
                'IN_PROGRESS',
                'COMPLETED',
                'GROUNDED'
            )
        ),
    CONSTRAINT chk_maintenance_history_new_status
        CHECK (
            new_status IN (
                'OPEN',
                'IN_PROGRESS',
                'COMPLETED',
                'GROUNDED'
            )
        )
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;

-- V18에서 이미 생성된 활성 기체 신뢰도 Incident를 최초 작업지시로 이관한다.
INSERT INTO maintenance_work_order (
    incident_id,
    drone_id,
    session_id,
    source_assessment_id,
    status,
    clearance_status,
    opened_at,
    created_at,
    updated_at
)
SELECT
    incident_record.id,
    incident_record.drone_id,
    incident_record.session_id,
    (
        SELECT MAX(assessment.id)
        FROM flight_quality_assessment assessment
        WHERE assessment.session_id = incident_record.session_id
    ),
    'OPEN',
    'PENDING_INSPECTION',
    UTC_TIMESTAMP(6),
    UTC_TIMESTAMP(6),
    UTC_TIMESTAMP(6)
FROM incident incident_record
WHERE incident_record.source_type = 'FLIGHT_QUALITY'
  AND incident_record.status IN ('OPEN', 'IN_PROGRESS');

INSERT INTO maintenance_work_order_history (
    work_order_id,
    action_type,
    previous_status,
    new_status,
    actor,
    note,
    created_at
)
SELECT
    work_order.id,
    'CREATED',
    NULL,
    work_order.status,
    'V19_MIGRATION',
    '기존 활성 기체 신뢰도 Incident에서 점검 작업 자동 이관',
    work_order.created_at
FROM maintenance_work_order work_order;
