CREATE TABLE incident (
    id BIGINT NOT NULL AUTO_INCREMENT,
    source_type VARCHAR(30) NOT NULL,
    source_id BIGINT NOT NULL,
    drone_id BIGINT NOT NULL,
    session_id VARCHAR(36) NULL,
    priority VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    title VARCHAR(200) NOT NULL,
    summary VARCHAR(1000) NOT NULL,
    assignee VARCHAR(100) NULL,
    assigned_by VARCHAR(100) NULL,
    assigned_at DATETIME(6) NULL,
    occurred_at DATETIME(6) NOT NULL,
    resolved_at DATETIME(6) NULL,
    closed_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,

    PRIMARY KEY (id),
    UNIQUE KEY uk_incident_source (source_type, source_id),
    KEY idx_incident_status_priority (
        status,
        priority,
        occurred_at
    ),
    KEY idx_incident_drone_status (
        drone_id,
        status,
        occurred_at
    ),
    KEY idx_incident_assignee_status (assignee, status),
    KEY idx_incident_session (session_id),

    CONSTRAINT chk_incident_source_type
        CHECK (source_type IN ('AI_ALERT', 'GEOFENCE')),
    CONSTRAINT chk_incident_priority
        CHECK (priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    CONSTRAINT chk_incident_status
        CHECK (status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED')),
    CONSTRAINT chk_incident_assignment
        CHECK (
            assignee IS NULL
            OR (assigned_by IS NOT NULL AND assigned_at IS NOT NULL)
        ),
    CONSTRAINT chk_incident_resolution
        CHECK (
            status NOT IN ('RESOLVED', 'CLOSED')
            OR resolved_at IS NOT NULL
        ),
    CONSTRAINT chk_incident_closure
        CHECK (status <> 'CLOSED' OR closed_at IS NOT NULL)
);

CREATE TABLE incident_action_history (
    id BIGINT NOT NULL AUTO_INCREMENT,
    incident_id BIGINT NOT NULL,
    action_type VARCHAR(30) NOT NULL,
    previous_status VARCHAR(20) NULL,
    new_status VARCHAR(20) NULL,
    actor VARCHAR(100) NOT NULL,
    note VARCHAR(1000) NULL,
    created_at DATETIME(6) NOT NULL,

    PRIMARY KEY (id),
    KEY idx_incident_history_incident (
        incident_id,
        created_at,
        id
    ),

    CONSTRAINT fk_incident_history_incident
        FOREIGN KEY (incident_id)
        REFERENCES incident (id)
        ON DELETE CASCADE,
    CONSTRAINT chk_incident_history_action
        CHECK (
            action_type IN (
                'CREATED',
                'ASSIGNED',
                'PRIORITY_CHANGED',
                'STATUS_CHANGED',
                'NOTE_ADDED',
                'SOURCE_SYNCHRONIZED'
            )
        ),
    CONSTRAINT chk_incident_history_previous_status
        CHECK (
            previous_status IS NULL
            OR previous_status IN (
                'OPEN',
                'IN_PROGRESS',
                'RESOLVED',
                'CLOSED'
            )
        ),
    CONSTRAINT chk_incident_history_new_status
        CHECK (
            new_status IS NULL
            OR new_status IN (
                'OPEN',
                'IN_PROGRESS',
                'RESOLVED',
                'CLOSED'
            )
        )
);

-- V11 이전 AI 경보를 Incident로 이관한다.
INSERT INTO incident (
    source_type,
    source_id,
    drone_id,
    session_id,
    priority,
    status,
    title,
    summary,
    assignee,
    assigned_by,
    assigned_at,
    occurred_at,
    resolved_at,
    closed_at,
    created_at,
    updated_at
)
SELECT
    'AI_ALERT',
    alert.id,
    alert.drone_id,
    alert.session_id,
    CASE alert.severity
        WHEN 'CRITICAL' THEN 'CRITICAL'
        WHEN 'WARNING' THEN 'HIGH'
        ELSE 'LOW'
    END,
    CASE alert.status
        WHEN 'ACKNOWLEDGED' THEN 'IN_PROGRESS'
        WHEN 'RESOLVED' THEN 'RESOLVED'
        ELSE 'OPEN'
    END,
    alert.title,
    alert.summary,
    CASE
        WHEN alert.status = 'RESOLVED' THEN alert.resolved_by
        WHEN alert.status = 'ACKNOWLEDGED' THEN alert.acknowledged_by
        ELSE NULL
    END,
    CASE
        WHEN alert.status = 'RESOLVED' THEN alert.resolved_by
        WHEN alert.status = 'ACKNOWLEDGED' THEN alert.acknowledged_by
        ELSE NULL
    END,
    CASE
        WHEN alert.status = 'RESOLVED' THEN alert.resolved_at
        WHEN alert.status = 'ACKNOWLEDGED' THEN alert.acknowledged_at
        ELSE NULL
    END,
    alert.captured_at,
    alert.resolved_at,
    NULL,
    alert.created_at,
    alert.updated_at
FROM ai_alert alert;

-- V11 이전 지오펜스 위반 이력을 Incident로 이관한다.
INSERT INTO incident (
    source_type,
    source_id,
    drone_id,
    session_id,
    priority,
    status,
    title,
    summary,
    assignee,
    assigned_by,
    assigned_at,
    occurred_at,
    resolved_at,
    closed_at,
    created_at,
    updated_at
)
SELECT
    'GEOFENCE',
    geofence_event.id,
    geofence_event.drone_id,
    NULL,
    CASE geofence_event.rule_type
        WHEN 'KEEP_OUT' THEN 'CRITICAL'
        ELSE 'HIGH'
    END,
    CASE
        WHEN geofence_event.resolved_at IS NULL THEN 'OPEN'
        ELSE 'RESOLVED'
    END,
    CONCAT('지오펜스 위반: ', geofence_event.geofence_name),
    CONCAT(
        geofence_event.drone_code,
        ' / ',
        geofence_event.rule_type,
        ' / 경계 중심 거리 ',
        CAST(geofence_event.distance_meters AS CHAR),
        'm'
    ),
    NULL,
    NULL,
    NULL,
    geofence_event.detected_at,
    geofence_event.resolved_at,
    NULL,
    geofence_event.created_at,
    geofence_event.updated_at
FROM drone_geofence_event geofence_event;

-- 이관된 모든 Incident에 최초 생성 이력을 남긴다.
INSERT INTO incident_action_history (
    incident_id,
    action_type,
    previous_status,
    new_status,
    actor,
    note,
    created_at
)
SELECT
    incident.id,
    'CREATED',
    NULL,
    incident.status,
    'V11_MIGRATION',
    '기존 이벤트 이력에서 자동 이관',
    incident.created_at
FROM incident;
