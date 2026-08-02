-- MySQL UNIQUE 인덱스는 NULL을 여러 건 허용한다. ACTIVE 세션만 Drone ID를
-- 생성 열에 투영해 기체별 진행 중 세션을 DB에서도 정확히 한 건으로 제한한다.
ALTER TABLE flight_session
    ADD COLUMN active_drone_id BIGINT
        GENERATED ALWAYS AS (
            CASE
                WHEN status = 'ACTIVE' THEN drone_id
                ELSE NULL
            END
        ) STORED,
    ADD CONSTRAINT uq_flight_session_one_active_per_drone
        UNIQUE (active_drone_id);
