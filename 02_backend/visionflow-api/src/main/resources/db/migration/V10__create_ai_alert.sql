CREATE TABLE ai_alert (
    id BIGINT NOT NULL AUTO_INCREMENT,
    event_id BIGINT NOT NULL,
    drone_id BIGINT NOT NULL,
    session_id VARCHAR(36) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    title VARCHAR(200) NOT NULL,
    summary VARCHAR(500) NOT NULL,
    primary_class_name VARCHAR(100) NOT NULL,
    max_confidence DECIMAL(8, 6) NOT NULL,
    detection_count INT NOT NULL,
    captured_at DATETIME(6) NOT NULL,
    acknowledged_at DATETIME(6) NULL,
    acknowledged_by VARCHAR(100) NULL,
    resolved_at DATETIME(6) NULL,
    resolved_by VARCHAR(100) NULL,
    resolution_note VARCHAR(500) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,

    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_alert_event (event_id),
    KEY idx_ai_alert_severity_status (
        severity,
        status,
        captured_at
    ),
    KEY idx_ai_alert_drone_status_captured (
        drone_id,
        status,
        captured_at
    ),
    KEY idx_ai_alert_session (session_id),

    CONSTRAINT fk_ai_alert_event
        FOREIGN KEY (event_id)
        REFERENCES ai_inference_event (id)
        ON DELETE CASCADE,
    CONSTRAINT chk_ai_alert_severity
        CHECK (severity IN ('INFO', 'WARNING', 'CRITICAL')),
    CONSTRAINT chk_ai_alert_status
        CHECK (status IN ('OPEN', 'ACKNOWLEDGED', 'RESOLVED')),
    CONSTRAINT chk_ai_alert_confidence
        CHECK (max_confidence >= 0 AND max_confidence <= 1),
    CONSTRAINT chk_ai_alert_detection_count
        CHECK (detection_count > 0),
    CONSTRAINT chk_ai_alert_acknowledgement
        CHECK (
            status = 'OPEN'
            OR status = 'RESOLVED'
            OR (
                acknowledged_at IS NOT NULL
                AND acknowledged_by IS NOT NULL
            )
        ),
    CONSTRAINT chk_ai_alert_resolution
        CHECK (
            status <> 'RESOLVED'
            OR (
                resolved_at IS NOT NULL
                AND resolved_by IS NOT NULL
            )
        )
);

-- V10 적용 전에 이미 저장된 탐지 이벤트도 경보 목록에서 조회되도록 보정한다.
INSERT INTO ai_alert (
    event_id,
    drone_id,
    session_id,
    severity,
    status,
    title,
    summary,
    primary_class_name,
    max_confidence,
    detection_count,
    captured_at,
    created_at,
    updated_at
)
SELECT
    inference_event.id,
    inference_event.drone_id,
    inference_event.session_id,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM ai_detection critical_detection
            WHERE critical_detection.event_id = inference_event.id
              AND LOWER(TRIM(critical_detection.class_name)) IN (
                    'fire',
                    'smoke',
                    'gun',
                    'knife',
                    'weapon',
                    'accident',
                    'fight'
              )
              AND critical_detection.confidence >= 0.600000
        ) THEN 'CRITICAL'
        WHEN (
            SELECT MAX(warning_detection.confidence)
            FROM ai_detection warning_detection
            WHERE warning_detection.event_id = inference_event.id
        ) >= 0.700000
            OR inference_event.detection_count >= 3
        THEN 'WARNING'
        ELSE 'INFO'
    END,
    'OPEN',
    CONCAT('기존 AI 탐지 이벤트 #', inference_event.id),
    CONCAT(inference_event.detection_count, '개 객체 탐지'),
    (
        SELECT primary_detection.class_name
        FROM ai_detection primary_detection
        WHERE primary_detection.event_id = inference_event.id
        ORDER BY primary_detection.confidence DESC,
                 primary_detection.id ASC
        LIMIT 1
    ),
    (
        SELECT MAX(max_detection.confidence)
        FROM ai_detection max_detection
        WHERE max_detection.event_id = inference_event.id
    ),
    inference_event.detection_count,
    inference_event.captured_at,
    inference_event.created_at,
    inference_event.created_at
FROM ai_inference_event inference_event
WHERE inference_event.detection_count > 0
  AND EXISTS (
        SELECT 1
        FROM ai_detection detection
        WHERE detection.event_id = inference_event.id
  );
