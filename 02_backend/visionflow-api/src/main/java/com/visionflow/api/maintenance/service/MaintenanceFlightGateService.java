package com.visionflow.api.maintenance.service;

import com.visionflow.api.audit.domain.AuditAction;
import com.visionflow.api.audit.domain.AuditEntityType;
import com.visionflow.api.audit.dto.AuditLogResponse;
import com.visionflow.api.audit.service.AuditLogService;
import com.visionflow.api.drone.domain.Drone;
import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.maintenance.config.MaintenanceFlightGateProperties;
import com.visionflow.api.maintenance.domain.FlightClearanceStatus;
import com.visionflow.api.maintenance.domain.MaintenanceFlightGateMode;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrder;
import com.visionflow.api.maintenance.dto.MaintenanceFleetFlightClearanceResponse;
import com.visionflow.api.maintenance.dto.MaintenanceFlightClearanceResponse;
import com.visionflow.api.maintenance.exception.FlightClearanceRequiredException;
import com.visionflow.api.maintenance.repository.MaintenanceWorkOrderRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

@Service
public class MaintenanceFlightGateService {

    private static final Logger log = LoggerFactory.getLogger(
            MaintenanceFlightGateService.class
    );

    private final MaintenanceWorkOrderRepository workOrderRepository;
    private final DroneRepository droneRepository;
    private final MaintenanceFlightGateProperties properties;
    private final AuditLogService auditLogService;
    private final FlightGateIncidentAutomationService
            incidentAutomationService;

    public MaintenanceFlightGateService(
            MaintenanceWorkOrderRepository workOrderRepository,
            DroneRepository droneRepository,
            MaintenanceFlightGateProperties properties,
            AuditLogService auditLogService,
            FlightGateIncidentAutomationService incidentAutomationService
    ) {
        this.workOrderRepository = workOrderRepository;
        this.droneRepository = droneRepository;
        this.properties = properties;
        this.auditLogService = auditLogService;
        this.incidentAutomationService = incidentAutomationService;
    }

    @Transactional(readOnly = true)
    public MaintenanceFlightClearanceResponse evaluate(Long droneId) {
        MaintenanceFlightGateMode mode = properties.getMode();
        Optional<MaintenanceWorkOrder> latest =
                workOrderRepository
                        .findFirstByDroneIdOrderByUpdatedAtDescIdDesc(
                                droneId
                        );

        return evaluate(droneId, latest.orElse(null), mode);
    }

    @Transactional(readOnly = true)
    public MaintenanceFleetFlightClearanceResponse evaluateFleet() {
        MaintenanceFlightGateMode mode = properties.getMode();
        List<Drone> drones =
                droneRepository.findAllByOrderByCreatedAtDesc();
        Map<Long, MaintenanceWorkOrder> latestByDroneId =
                new HashMap<>();
        workOrderRepository.findLatestForAllDrones().forEach(
                order -> latestByDroneId.put(
                        order.getDroneId(),
                        order
                )
        );

        List<MaintenanceFlightClearanceResponse> clearances =
                drones.stream()
                        .map(drone -> evaluate(
                                drone.getId(),
                                latestByDroneId.get(drone.getId()),
                                mode
                        ))
                        .toList();
        int allowedDrones = 0;
        int attentionDrones = 0;
        int blockedDrones = 0;
        for (MaintenanceFlightClearanceResponse clearance : clearances) {
            if (clearance.flightAllowed()) {
                allowedDrones += 1;
            } else {
                blockedDrones += 1;
            }
            if (clearance.attentionRequired()) {
                attentionDrones += 1;
            }
        }

        return new MaintenanceFleetFlightClearanceResponse(
                mode,
                mode == MaintenanceFlightGateMode.ENFORCED,
                clearances.size(),
                allowedDrones,
                attentionDrones,
                blockedDrones,
                Instant.now(),
                clearances
        );
    }

    private MaintenanceFlightClearanceResponse evaluate(
            Long droneId,
            MaintenanceWorkOrder order,
            MaintenanceFlightGateMode mode
    ) {
        if (order == null) {
            return new MaintenanceFlightClearanceResponse(
                    droneId,
                    mode,
                    mode == MaintenanceFlightGateMode.ENFORCED,
                    true,
                    false,
                    null,
                    null,
                    null,
                    "해당 기체에 미해결 점검 작업이 없습니다."
            );
        }

        boolean cleared =
                order.getClearanceStatus()
                        == FlightClearanceStatus.CLEARED;
        boolean enforced =
                mode == MaintenanceFlightGateMode.ENFORCED;
        boolean allowed =
                mode == MaintenanceFlightGateMode.OFF
                        || cleared
                        || !enforced;
        boolean attentionRequired =
                mode != MaintenanceFlightGateMode.OFF && !cleared;

        return new MaintenanceFlightClearanceResponse(
                droneId,
                mode,
                enforced,
                allowed,
                attentionRequired,
                order.getId(),
                order.getStatus(),
                order.getClearanceStatus(),
                reason(mode, order, cleared)
        );
    }

    @Transactional(readOnly = true)
    public MaintenanceFlightClearanceResponse requireStartClearance(
            Long droneId
    ) {
        MaintenanceFlightClearanceResponse clearance = evaluate(droneId);
        AuditAction action = decisionAction(clearance);
        AuditLogResponse decisionLog = recordDecision(action, clearance);
        if (
                action == AuditAction.MAINTENANCE_FLIGHT_START_BLOCKED
                        && decisionLog != null
        ) {
            synchronizeBlockedIncident(clearance, decisionLog);
        }

        if (!clearance.flightAllowed()) {
            throw new FlightClearanceRequiredException(
                    clearance.reason()
                            + " 점검 작업 #"
                            + clearance.workOrderId()
                            + "에서 재운항 승인을 완료하세요."
            );
        }

        return clearance;
    }

    private AuditAction decisionAction(
            MaintenanceFlightClearanceResponse clearance
    ) {
        if (!clearance.flightAllowed()) {
            return AuditAction.MAINTENANCE_FLIGHT_START_BLOCKED;
        }
        return clearance.attentionRequired()
                ? AuditAction.MAINTENANCE_FLIGHT_START_ADVISORY
                : AuditAction.MAINTENANCE_FLIGHT_START_ALLOWED;
    }

    private AuditLogResponse recordDecision(
            AuditAction action,
            MaintenanceFlightClearanceResponse clearance
    ) {
        Map<String, Object> details = new LinkedHashMap<>();
        details.put("droneId", clearance.droneId());
        details.put("mode", clearance.mode().name());
        details.put("flightAllowed", clearance.flightAllowed());
        details.put(
                "attentionRequired",
                clearance.attentionRequired()
        );
        details.put("workOrderId", clearance.workOrderId());
        details.put(
                "workOrderStatus",
                clearance.workOrderStatus() == null
                        ? null
                        : clearance.workOrderStatus().name()
        );
        details.put(
                "clearanceStatus",
                clearance.clearanceStatus() == null
                        ? null
                        : clearance.clearanceStatus().name()
        );
        details.put("reason", clearance.reason());

        try {
            return auditLogService.record(
                    action,
                    AuditEntityType.MAINTENANCE_FLIGHT_GATE,
                    clearance.droneId(),
                    decisionSummary(action),
                    details
            );
        } catch (RuntimeException exception) {
            log.error(
                    "비행 허가 판단 감사 로그 저장 실패: droneId={}, action={}",
                    clearance.droneId(),
                    action,
                    exception
            );
            return null;
        }
    }

    private void synchronizeBlockedIncident(
            MaintenanceFlightClearanceResponse clearance,
            AuditLogResponse decisionLog
    ) {
        try {
            incidentAutomationService.handleBlocked(
                    clearance,
                    decisionLog
            );
        } catch (RuntimeException exception) {
            log.error(
                    "반복 비행 차단 Incident 동기화 실패: droneId={}",
                    clearance.droneId(),
                    exception
            );
        }
    }

    private String decisionSummary(AuditAction action) {
        return switch (action) {
            case MAINTENANCE_FLIGHT_START_ALLOWED ->
                    "정비 게이트 비행 시작 허용";
            case MAINTENANCE_FLIGHT_START_ADVISORY ->
                    "정비 게이트 주의 후 비행 시작 허용";
            case MAINTENANCE_FLIGHT_START_BLOCKED ->
                    "정비 게이트 비행 시작 차단";
            default -> throw new IllegalArgumentException(
                    "지원하지 않는 비행 허가 감사 작업입니다: " + action
            );
        };
    }

    private String reason(
            MaintenanceFlightGateMode mode,
            MaintenanceWorkOrder order,
            boolean cleared
    ) {
        if (cleared) {
            return "작업 #" + order.getId()
                    + "에서 재운항 승인이 확인되었습니다.";
        }
        String state = order.getClearanceStatus()
                == FlightClearanceStatus.GROUNDED
                ? "운항 중지"
                : "점검 또는 승인 대기";

        return switch (mode) {
            case OFF -> state
                    + " 상태이지만 비행 허가 게이트가 꺼져 있습니다.";
            case ADVISORY -> state
                    + " 상태입니다. 현재는 안내 모드이므로 시작은 허용됩니다.";
            case ENFORCED -> state
                    + " 상태이므로 새 비행 세션을 시작할 수 없습니다.";
        };
    }
}
