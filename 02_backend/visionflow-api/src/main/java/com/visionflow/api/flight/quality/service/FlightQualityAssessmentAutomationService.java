package com.visionflow.api.flight.quality.service;

import com.visionflow.api.audit.domain.AuditAction;
import com.visionflow.api.audit.domain.AuditEntityType;
import com.visionflow.api.audit.service.AuditLogService;
import com.visionflow.api.flight.event.FlightSessionClosedEvent;
import com.visionflow.api.flight.quality.dto.FlightQualityAssessmentResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

import java.util.Map;

@Service
public class FlightQualityAssessmentAutomationService {

    private static final Logger log = LoggerFactory.getLogger(
            FlightQualityAssessmentAutomationService.class
    );
    private static final String SYSTEM_ACTOR =
            "system-flight-quality-automation";

    private final FlightQualityAssessmentService assessmentService;
    private final AuditLogService auditLogService;
    private final FlightQualityIncidentAutomationService incidentAutomationService;

    public FlightQualityAssessmentAutomationService(
            FlightQualityAssessmentService assessmentService,
            AuditLogService auditLogService,
            FlightQualityIncidentAutomationService incidentAutomationService
    ) {
        this.assessmentService = assessmentService;
        this.auditLogService = auditLogService;
        this.incidentAutomationService = incidentAutomationService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void assessClosedSession(FlightSessionClosedEvent event) {
        FlightQualityAssessmentResponse response;

        try {
            response = assessmentService.recalculate(
                    event.droneId(),
                    event.sessionId()
            );
        } catch (RuntimeException exception) {
            log.error(
                    "비행 종료 후 품질 평가 자동 저장 실패: "
                            + "droneId={}, sessionId={}, status={}",
                    event.droneId(),
                    event.sessionId(),
                    event.status(),
                    exception
            );
            return;
        }

        try {
            incidentAutomationService.synchronizeDrone(
                    response.droneId(),
                    FlightQualityIncidentAutomationService
                            .DEFAULT_LIMIT_PER_DRONE
            );
        } catch (RuntimeException exception) {
            log.error(
                    "자동 품질 Incident 동기화 실패: "
                            + "droneId={}, sessionId={}",
                    response.droneId(),
                    response.sessionId(),
                    exception
            );
        }

        try {
            auditLogService.record(
                    AuditAction.FLIGHT_QUALITY_ASSESSED,
                    AuditEntityType.FLIGHT_QUALITY_ASSESSMENT,
                    response.sessionId(),
                    "비행 종료 후 품질 평가 자동 저장",
                    Map.of(
                            "droneId", response.droneId(),
                            "sessionStatus",
                            response.sessionStatus().name(),
                            "ruleVersion", response.ruleVersion(),
                            "score", response.score(),
                            "grade", response.grade().name(),
                            "trigger", "FLIGHT_SESSION_CLOSED"
                    ),
                    SYSTEM_ACTOR
            );
        } catch (RuntimeException exception) {
            log.error(
                    "자동 품질 평가 감사 로그 저장 실패: "
                            + "droneId={}, sessionId={}",
                    response.droneId(),
                    response.sessionId(),
                    exception
            );
        }
    }
}
