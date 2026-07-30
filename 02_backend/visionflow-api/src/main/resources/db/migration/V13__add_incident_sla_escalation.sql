ALTER TABLE incident
    ADD COLUMN sla_due_at DATETIME(6) NULL
        AFTER closed_at,
    ADD COLUMN sla_breached_at DATETIME(6) NULL
        AFTER sla_due_at,
    ADD COLUMN escalation_level INT NOT NULL DEFAULT 0
        AFTER sla_breached_at;

CREATE INDEX idx_incident_sla_scan
    ON incident (sla_breached_at, sla_due_at, status);

-- 기존 진행 중 Incident는 배포 직후 일괄 초과 처리되지 않도록
-- V13 적용 시각부터 우선순위별 전체 대응시간을 새로 부여한다.
UPDATE incident
SET sla_due_at = CASE priority
        WHEN 'CRITICAL' THEN UTC_TIMESTAMP(6) + INTERVAL 5 MINUTE
        WHEN 'HIGH' THEN UTC_TIMESTAMP(6) + INTERVAL 15 MINUTE
        WHEN 'MEDIUM' THEN UTC_TIMESTAMP(6) + INTERVAL 30 MINUTE
        ELSE UTC_TIMESTAMP(6) + INTERVAL 60 MINUTE
    END
WHERE status IN ('OPEN', 'IN_PROGRESS')
  AND sla_due_at IS NULL;

ALTER TABLE incident_action_history
    DROP CHECK chk_incident_history_action;

ALTER TABLE incident_action_history
    ADD CONSTRAINT chk_incident_history_action
        CHECK (
            action_type IN (
                'CREATED',
                'ASSIGNED',
                'PRIORITY_CHANGED',
                'STATUS_CHANGED',
                'NOTE_ADDED',
                'SOURCE_SYNCHRONIZED',
                'SLA_ESCALATED'
            )
        );
