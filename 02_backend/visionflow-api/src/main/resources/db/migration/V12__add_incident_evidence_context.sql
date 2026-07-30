ALTER TABLE drone_geofence_event
    ADD COLUMN flight_session_id VARCHAR(36) NULL
        AFTER drone_code,
    ADD COLUMN detected_latitude DECIMAL(10, 7) NULL
        AFTER rule_type,
    ADD COLUMN detected_longitude DECIMAL(10, 7) NULL
        AFTER detected_latitude,
    ADD COLUMN detected_altitude DECIMAL(10, 2) NULL
        AFTER detected_longitude;

-- 과거 이벤트에는 당시 별도 좌표 스냅샷이 없으므로 보유 중인
-- 마지막 이벤트 좌표를 최선의 복원값으로 사용한다.
UPDATE drone_geofence_event
SET detected_latitude = last_latitude,
    detected_longitude = last_longitude,
    detected_altitude = last_altitude
WHERE detected_latitude IS NULL
   OR detected_longitude IS NULL;

ALTER TABLE drone_geofence_event
    MODIFY COLUMN detected_latitude DECIMAL(10, 7) NOT NULL,
    MODIFY COLUMN detected_longitude DECIMAL(10, 7) NOT NULL;

CREATE INDEX idx_geofence_event_session_detected
    ON drone_geofence_event (flight_session_id, detected_at);

-- 과거 지오펜스 이벤트 발생 시각 전후 30초 이내의 가장 가까운
-- 텔레메트리에서 비행 세션을 복원한다.
UPDATE drone_geofence_event geofence_event
SET geofence_event.flight_session_id = (
    SELECT history.flight_session_id
    FROM drone_telemetry_history history
    WHERE history.drone_id = geofence_event.drone_id
      AND history.flight_session_id IS NOT NULL
      AND history.flight_session_id <> ''
      AND history.recorded_at BETWEEN
            geofence_event.detected_at - INTERVAL 30 SECOND
            AND geofence_event.detected_at + INTERVAL 30 SECOND
    ORDER BY ABS(
        TIMESTAMPDIFF(
            MICROSECOND,
            geofence_event.detected_at,
            history.recorded_at
        )
    ) ASC,
    history.id ASC
    LIMIT 1
)
WHERE geofence_event.flight_session_id IS NULL;

-- V11에서 생성된 지오펜스 Incident에도 복원된 세션을 연결한다.
UPDATE incident incident_record
JOIN drone_geofence_event geofence_event
  ON incident_record.source_type = 'GEOFENCE'
 AND incident_record.source_id = geofence_event.id
SET incident_record.session_id = geofence_event.flight_session_id,
    incident_record.updated_at = CURRENT_TIMESTAMP(6)
WHERE incident_record.session_id IS NULL
  AND geofence_event.flight_session_id IS NOT NULL;
