CREATE TABLE ai_inference_event (
    id BIGINT NOT NULL AUTO_INCREMENT,
    source_id VARCHAR(100) NOT NULL,
    session_id VARCHAR(36) NOT NULL,
    source_type VARCHAR(30) NOT NULL,
    drone_id BIGINT NOT NULL,
    frame_index BIGINT NOT NULL,
    captured_at DATETIME(6) NOT NULL,
    received_at DATETIME(6) NOT NULL,
    inference_ms DECIMAL(12, 3) NOT NULL,
    detection_count INT NOT NULL,
    created_at DATETIME(6) NOT NULL,

    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_event_frame (
        source_id,
        session_id,
        frame_index
    ),
    KEY idx_ai_event_drone_captured (
        drone_id,
        captured_at
    ),
    KEY idx_ai_event_source_captured (
        source_id,
        captured_at
    ),

    CONSTRAINT chk_ai_event_source_type
        CHECK (
            source_type IN (
                'SMARTPHONE_LIVE',
                'DUMMY_VIDEO',
                'DJI_LIVE'
            )
        ),
    CONSTRAINT chk_ai_event_frame_index
        CHECK (frame_index >= 0),
    CONSTRAINT chk_ai_event_detection_count
        CHECK (detection_count >= 0)
);

CREATE TABLE ai_detection (
    id BIGINT NOT NULL AUTO_INCREMENT,
    event_id BIGINT NOT NULL,
    class_id INT NOT NULL,
    class_name VARCHAR(100) NOT NULL,
    confidence DECIMAL(8, 6) NOT NULL,
    bbox_x1 DECIMAL(12, 3) NOT NULL,
    bbox_y1 DECIMAL(12, 3) NOT NULL,
    bbox_x2 DECIMAL(12, 3) NOT NULL,
    bbox_y2 DECIMAL(12, 3) NOT NULL,
    created_at DATETIME(6) NOT NULL,

    PRIMARY KEY (id),
    KEY idx_ai_detection_event (event_id),
    KEY idx_ai_detection_class (class_name, created_at),

    CONSTRAINT fk_ai_detection_event
        FOREIGN KEY (event_id)
        REFERENCES ai_inference_event (id)
        ON DELETE CASCADE,
    CONSTRAINT chk_ai_detection_class_id
        CHECK (class_id >= 0),
    CONSTRAINT chk_ai_detection_confidence
        CHECK (confidence >= 0 AND confidence <= 1),
    CONSTRAINT chk_ai_detection_bbox
        CHECK (bbox_x2 >= bbox_x1 AND bbox_y2 >= bbox_y1)
);
