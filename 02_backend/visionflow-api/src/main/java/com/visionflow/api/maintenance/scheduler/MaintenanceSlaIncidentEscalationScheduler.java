package com.visionflow.api.maintenance.scheduler;

import com.visionflow.api.maintenance.dto.MaintenanceSlaEscalationResultResponse;
import com.visionflow.api.maintenance.service.MaintenanceSlaIncidentEscalationService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
        name = "visionflow.maintenance.sla.automation-enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class MaintenanceSlaIncidentEscalationScheduler {

    private static final Logger log = LoggerFactory.getLogger(
            MaintenanceSlaIncidentEscalationScheduler.class
    );

    private final MaintenanceSlaIncidentEscalationService service;

    public MaintenanceSlaIncidentEscalationScheduler(
            MaintenanceSlaIncidentEscalationService service
    ) {
        this.service = service;
    }

    @Scheduled(
            initialDelayString =
                    "${visionflow.maintenance.sla.initial-delay-ms:15000}",
            fixedDelayString =
                    "${visionflow.maintenance.sla.scan-delay-ms:30000}"
    )
    public void scan() {
        try {
            MaintenanceSlaEscalationResultResponse result =
                    service.escalateOverdue();
            if (result.escalatedIncidents() > 0) {
                log.warn(
                        "정비 SLA 초과 Incident 자동 에스컬레이션: {}건",
                        result.escalatedIncidents()
                );
            }
        } catch (RuntimeException exception) {
            log.error(
                    "정비 SLA 초과 Incident 검색 실패",
                    exception
            );
        }
    }
}
