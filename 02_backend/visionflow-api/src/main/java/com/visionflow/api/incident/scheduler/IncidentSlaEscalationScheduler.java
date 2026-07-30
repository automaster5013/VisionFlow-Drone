package com.visionflow.api.incident.scheduler;

import com.visionflow.api.incident.service.IncidentSlaEscalationService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
        name = "visionflow.incident.sla.enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class IncidentSlaEscalationScheduler {

    private static final Logger log = LoggerFactory.getLogger(
            IncidentSlaEscalationScheduler.class
    );

    private final IncidentSlaEscalationService escalationService;

    public IncidentSlaEscalationScheduler(
            IncidentSlaEscalationService escalationService
    ) {
        this.escalationService = escalationService;
    }

    @Scheduled(
            initialDelayString = "${visionflow.incident.sla.initial-delay-ms:10000}",
            fixedDelayString = "${visionflow.incident.sla.scan-delay-ms:15000}"
    )
    public void scan() {
        try {
            int count = escalationService.escalateOverdueIncidents();

            if (count > 0) {
                log.warn("SLA 초과 Incident 자동 에스컬레이션: {}건", count);
            }
        } catch (RuntimeException error) {
            log.error("SLA 초과 Incident 검색 실패", error);
        }
    }
}
