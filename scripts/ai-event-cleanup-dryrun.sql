-- VisionFlow AI event cleanup dry-run
-- Read-only: SELECT statements only.

SELECT
    @@global.time_zone AS global_time_zone,
    @@session.time_zone AS session_time_zone,
    NOW() AS database_now,
    UTC_TIMESTAMP() AS utc_now;

SELECT
    (SELECT COUNT(*) FROM ai_inference_event) AS exact_events,
    (SELECT COUNT(*) FROM ai_detection) AS exact_detections,
    (SELECT COUNT(*) FROM ai_alert) AS exact_alerts,
    (SELECT COUNT(*) FROM ai_inference_event WHERE snapshot_file_name IS NOT NULL) AS snapshot_references,
    (SELECT COUNT(*) FROM ai_inference_event WHERE snapshot_file_name IS NULL) AS events_without_snapshot,
    ROUND(
        (
            SELECT COALESCE(SUM(snapshot_size_bytes), 0)
            FROM ai_inference_event
            WHERE snapshot_file_name IS NOT NULL
        ) / 1024 / 1024 / 1024,
        3
    ) AS snapshot_gb,
    MIN(captured_at) AS first_captured_at,
    MAX(captured_at) AS last_captured_at,
    MIN(received_at) AS first_received_at,
    MAX(received_at) AS last_received_at
FROM ai_inference_event;

SELECT
    DATE_FORMAT(captured_at, '%Y-%m-%d %H:00:00') AS captured_hour_utc,
    COUNT(*) AS events,
    SUM(detection_count) AS detections,
    SUM(snapshot_file_name IS NOT NULL) AS snapshots,
    ROUND(SUM(COALESCE(snapshot_size_bytes, 0)) / 1024 / 1024, 2) AS snapshot_mb,
    ROUND(AVG(inference_ms), 2) AS avg_inference_ms
FROM ai_inference_event
WHERE captured_at BETWEEN
    '2026-07-28 00:00:00'
    AND '2026-07-30 23:59:59.999999'
GROUP BY DATE_FORMAT(captured_at, '%Y-%m-%d %H:00:00')
ORDER BY captured_hour_utc;

SELECT
    source_id,
    session_id,
    source_type,
    drone_id,
    MIN(captured_at) AS first_captured_at_utc,
    MAX(captured_at) AS last_captured_at_utc,
    COUNT(*) AS events,
    SUM(detection_count) AS detections,
    SUM(snapshot_file_name IS NOT NULL) AS snapshots,
    ROUND(SUM(COALESCE(snapshot_size_bytes, 0)) / 1024 / 1024 / 1024, 3) AS snapshot_gb,
    MIN(frame_index) AS min_frame_index,
    MAX(frame_index) AS max_frame_index
FROM ai_inference_event
WHERE captured_at BETWEEN
    '2026-07-28 00:00:00'
    AND '2026-07-30 23:59:59.999999'
GROUP BY source_id, session_id, source_type, drone_id
ORDER BY events DESC
LIMIT 50;

SELECT
    source_id,
    COUNT(*) AS events,
    COUNT(DISTINCT session_id) AS sessions,
    SUM(detection_count) AS detections,
    SUM(snapshot_file_name IS NOT NULL) AS snapshots,
    ROUND(SUM(COALESCE(snapshot_size_bytes, 0)) / 1024 / 1024 / 1024, 3) AS snapshot_gb,
    MIN(captured_at) AS first_captured_at_utc,
    MAX(captured_at) AS last_captured_at_utc
FROM ai_inference_event
GROUP BY source_id
ORDER BY events DESC;

SELECT
    id,
    source_id,
    session_id,
    frame_index,
    captured_at,
    snapshot_file_name,
    snapshot_size_bytes
FROM ai_inference_event
WHERE snapshot_file_name IS NULL
ORDER BY id;

SELECT
    session_id,
    COUNT(*) AS events,
    SUM(snapshot_file_name IS NOT NULL) AS snapshots,
    ROUND(SUM(COALESCE(snapshot_size_bytes, 0)) / 1024 / 1024 / 1024, 3) AS snapshot_gb,
    MIN(id) AS min_event_id,
    MAX(id) AS max_event_id,
    MIN(captured_at) AS first_captured_at_utc,
    MAX(captured_at) AS last_captured_at_utc
FROM ai_inference_event
WHERE source_id = 'browser-camera-001'
GROUP BY session_id
ORDER BY events DESC;
