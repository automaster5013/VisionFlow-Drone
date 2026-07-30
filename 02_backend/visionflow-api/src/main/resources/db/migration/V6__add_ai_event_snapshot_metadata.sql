ALTER TABLE ai_inference_event
    ADD COLUMN snapshot_file_name VARCHAR(255) NULL AFTER detection_count,
    ADD COLUMN snapshot_content_type VARCHAR(100) NULL AFTER snapshot_file_name,
    ADD COLUMN snapshot_size_bytes BIGINT NULL AFTER snapshot_content_type,
    ADD COLUMN snapshot_created_at DATETIME(6) NULL AFTER snapshot_size_bytes;

ALTER TABLE ai_inference_event
    ADD CONSTRAINT chk_ai_event_snapshot_size
        CHECK (
            snapshot_size_bytes IS NULL
            OR snapshot_size_bytes > 0
        );
