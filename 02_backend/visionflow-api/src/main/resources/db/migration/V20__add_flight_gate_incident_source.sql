-- 반복 비행 시작 차단 Incident는 source_id에 drone_id를 저장한다.
-- 기존 (source_type, source_id) 유니크 키로 기체별 중복 생성을 차단한다.
ALTER TABLE incident
    DROP CHECK chk_incident_source_type;

ALTER TABLE incident
    ADD CONSTRAINT chk_incident_source_type
        CHECK (
            source_type IN (
                'AI_ALERT',
                'GEOFENCE',
                'FLIGHT_QUALITY',
                'FLIGHT_GATE'
            )
        );
