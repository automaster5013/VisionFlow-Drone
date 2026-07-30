-- VisionFlow AI cleanup target verification
-- READ ONLY: SELECT statements only.

SET @source_id = 'browser-camera-001';

SELECT
    session_id,
    COUNT(*) AS events,
    SUM(detection_count) AS detection_count_recorded,
    SUM(snapshot_file_name IS NOT NULL) AS snapshots,
    SUM(snapshot_file_name IS NULL) AS events_without_snapshot,
    ROUND(SUM(COALESCE(snapshot_size_bytes, 0)) / 1024 / 1024 / 1024, 3) AS snapshot_gb,
    MIN(id) AS min_event_id,
    MAX(id) AS max_event_id,
    MIN(captured_at) AS first_captured_at,
    MAX(captured_at) AS last_captured_at
FROM ai_inference_event
WHERE source_id = @source_id
  AND session_id IN (
      '720f652c-8498-4686-a20d-fb573b7ef562',
      '890614dc-71ff-45ea-bf9a-62177cde072f',
      'a8edd33f-7e44-4e01-93b7-2bdaafff5587'
  )
  AND id BETWEEN 6943 AND 140249
GROUP BY session_id
ORDER BY min_event_id;

SELECT
    COUNT(*) AS target_events,
    SUM(detection_count) AS target_detection_count_recorded,
    SUM(snapshot_file_name IS NOT NULL) AS target_snapshots,
    SUM(snapshot_file_name IS NULL) AS target_events_without_snapshot,
    SUM(COALESCE(snapshot_size_bytes, 0)) AS target_snapshot_bytes,
    ROUND(SUM(COALESCE(snapshot_size_bytes, 0)) / 1024 / 1024 / 1024, 3) AS target_snapshot_gb,
    MIN(id) AS target_min_event_id,
    MAX(id) AS target_max_event_id
FROM ai_inference_event
WHERE source_id = @source_id
  AND session_id IN (
      '720f652c-8498-4686-a20d-fb573b7ef562',
      '890614dc-71ff-45ea-bf9a-62177cde072f',
      'a8edd33f-7e44-4e01-93b7-2bdaafff5587'
  )
  AND id BETWEEN 6943 AND 140249;

SELECT COUNT(*) AS target_detections
FROM ai_detection d
JOIN ai_inference_event e ON e.id = d.event_id
WHERE e.source_id = @source_id
  AND e.session_id IN (
      '720f652c-8498-4686-a20d-fb573b7ef562',
      '890614dc-71ff-45ea-bf9a-62177cde072f',
      'a8edd33f-7e44-4e01-93b7-2bdaafff5587'
  )
  AND e.id BETWEEN 6943 AND 140249;

SELECT COUNT(*) AS target_alerts
FROM ai_alert a
JOIN ai_inference_event e ON e.id = a.event_id
WHERE e.source_id = @source_id
  AND e.session_id IN (
      '720f652c-8498-4686-a20d-fb573b7ef562',
      '890614dc-71ff-45ea-bf9a-62177cde072f',
      'a8edd33f-7e44-4e01-93b7-2bdaafff5587'
  )
  AND e.id BETWEEN 6943 AND 140249;

SELECT
    COUNT(*) AS remaining_events,
    SUM(detection_count) AS remaining_detection_count_recorded,
    SUM(snapshot_file_name IS NOT NULL) AS remaining_snapshots,
    ROUND(SUM(COALESCE(snapshot_size_bytes, 0)) / 1024 / 1024 / 1024, 3) AS remaining_snapshot_gb
FROM ai_inference_event
WHERE NOT (
    source_id = @source_id
    AND session_id IN (
        '720f652c-8498-4686-a20d-fb573b7ef562',
        '890614dc-71ff-45ea-bf9a-62177cde072f',
        'a8edd33f-7e44-4e01-93b7-2bdaafff5587'
    )
    AND id BETWEEN 6943 AND 140249
);

SELECT
    COUNT(*) AS unexpected_events_inside_id_range
FROM ai_inference_event
WHERE id BETWEEN 6943 AND 140249
  AND NOT (
      source_id = @source_id
      AND session_id IN (
          '720f652c-8498-4686-a20d-fb573b7ef562',
          '890614dc-71ff-45ea-bf9a-62177cde072f',
          'a8edd33f-7e44-4e01-93b7-2bdaafff5587'
      )
  );

SELECT
    COUNT(*) AS target_events_outside_id_range
FROM ai_inference_event
WHERE source_id = @source_id
  AND session_id IN (
      '720f652c-8498-4686-a20d-fb573b7ef562',
      '890614dc-71ff-45ea-bf9a-62177cde072f',
      'a8edd33f-7e44-4e01-93b7-2bdaafff5587'
  )
  AND (id < 6943 OR id > 140249);
