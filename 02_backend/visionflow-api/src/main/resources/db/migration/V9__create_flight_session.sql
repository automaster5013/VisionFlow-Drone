CREATE TABLE flight_session
(
    session_id       VARCHAR(36)  NOT NULL,
    drone_id         BIGINT       NOT NULL,
    name             VARCHAR(120) NOT NULL,
    description      VARCHAR(500) NULL,
    status           VARCHAR(20)  NOT NULL,
    source_device_id VARCHAR(100) NULL,
    started_at       DATETIME(6)  NOT NULL,
    ended_at         DATETIME(6)  NULL,
    created_at       DATETIME(6)  NOT NULL,
    updated_at       DATETIME(6)  NOT NULL,

    CONSTRAINT pk_flight_session
        PRIMARY KEY (session_id),

    CONSTRAINT fk_flight_session_drone
        FOREIGN KEY (drone_id)
            REFERENCES drone (id)
            ON DELETE CASCADE,

    CONSTRAINT chk_flight_session_status
        CHECK (status IN ('READY', 'ACTIVE', 'COMPLETED', 'ABORTED')),

    CONSTRAINT chk_flight_session_time_range
        CHECK (ended_at IS NULL OR ended_at >= started_at),

    INDEX idx_flight_session_drone_started
        (drone_id, started_at),

    INDEX idx_flight_session_drone_status
        (drone_id, status)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;

-- V8 이전부터 UUID로 저장된 텔레메트리·AI 이벤트도 관리 목록에서
-- 사라지지 않도록 완료된 세션으로 한 번만 이관합니다.
INSERT INTO flight_session (
    session_id,
    drone_id,
    name,
    description,
    status,
    source_device_id,
    started_at,
    ended_at,
    created_at,
    updated_at
)
SELECT legacy.session_id,
       MIN(legacy.drone_id),
       CONCAT(
           '이전 비행 ',
           DATE_FORMAT(MIN(legacy.observed_at), '%Y-%m-%d %H:%i')
       ),
       NULL,
       'COMPLETED',
       NULL,
       MIN(legacy.observed_at),
       MAX(legacy.observed_at),
       MIN(legacy.observed_at),
       MAX(legacy.observed_at)
FROM (
    SELECT history.flight_session_id AS session_id,
           history.drone_id AS drone_id,
           history.recorded_at AS observed_at
    FROM drone_telemetry_history history
    WHERE history.flight_session_id IS NOT NULL
      AND history.flight_session_id <> ''

    UNION ALL

    SELECT inference_event.session_id AS session_id,
           inference_event.drone_id AS drone_id,
           inference_event.captured_at AS observed_at
    FROM ai_inference_event inference_event
    WHERE inference_event.session_id IS NOT NULL
      AND inference_event.session_id <> ''
) legacy
INNER JOIN drone existing_drone
        ON existing_drone.id = legacy.drone_id
GROUP BY legacy.session_id;
