package com.visionflow.api.maintenance.service;

import com.visionflow.api.maintenance.domain.FlightClearanceStatus;
import com.visionflow.api.maintenance.domain.MaintenancePriorityLevel;
import com.visionflow.api.maintenance.domain.MaintenanceSlaStatus;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrder;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrderStatus;
import com.visionflow.api.maintenance.dto.MaintenanceFleetFlightClearanceResponse;
import com.visionflow.api.maintenance.dto.MaintenanceFlightClearanceResponse;
import com.visionflow.api.maintenance.dto.MaintenancePriorityItemResponse;
import com.visionflow.api.maintenance.dto.MaintenancePriorityQueueResponse;
import com.visionflow.api.maintenance.repository.MaintenanceWorkOrderRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
public class MaintenancePriorityService {

    private final MaintenanceWorkOrderRepository workOrderRepository;
    private final MaintenanceFlightGateService flightGateService;

    public MaintenancePriorityService(
            MaintenanceWorkOrderRepository workOrderRepository,
            MaintenanceFlightGateService flightGateService
    ) {
        this.workOrderRepository = workOrderRepository;
        this.flightGateService = flightGateService;
    }

    @Transactional(readOnly = true)
    public MaintenancePriorityQueueResponse getPriorities() {
        Instant evaluatedAt = Instant.now();
        MaintenanceFleetFlightClearanceResponse fleet =
                flightGateService.evaluateFleet();
        List<MaintenanceWorkOrder> latestWorkOrders =
                workOrderRepository.findLatestForAllDrones();

        return prioritize(fleet, latestWorkOrders, evaluatedAt);
    }

    static MaintenancePriorityQueueResponse prioritize(
            MaintenanceFleetFlightClearanceResponse fleet,
            List<MaintenanceWorkOrder> latestWorkOrders,
            Instant evaluatedAt
    ) {
        Map<Long, MaintenanceWorkOrder> workOrderByDrone =
                latestWorkOrders.stream()
                        .collect(
                                HashMap::new,
                                (items, order) ->
                                        items.putIfAbsent(
                                                order.getDroneId(),
                                                order
                                        ),
                                HashMap::putAll
                        );

        List<MaintenancePriorityItemResponse> priorities =
                fleet.clearances().stream()
                        .map(clearance -> toPriority(
                                clearance,
                                workOrderByDrone.get(clearance.droneId()),
                                evaluatedAt
                        ))
                        .sorted(
                                Comparator
                                        .comparingInt(
                                                MaintenancePriorityItemResponse
                                                        ::riskScore
                                        )
                                        .reversed()
                                        .thenComparing(
                                                MaintenancePriorityItemResponse
                                                        ::flightAllowed
                                        )
                                        .thenComparing(
                                                MaintenancePriorityItemResponse
                                                        ::droneId
                                        )
                        )
                        .toList();

        int urgent = (int) priorities.stream()
                .filter(item ->
                        item.priority()
                                == MaintenancePriorityLevel.CRITICAL
                                || item.priority()
                                == MaintenancePriorityLevel.HIGH
                )
                .count();
        int attention = (int) priorities.stream()
                .filter(item ->
                        item.priority()
                                == MaintenancePriorityLevel.MEDIUM
                )
                .count();
        int overdue = (int) priorities.stream()
                .filter(item ->
                        item.slaStatus()
                                == MaintenanceSlaStatus.OVERDUE
                )
                .count();
        int dueSoon = (int) priorities.stream()
                .filter(item ->
                        item.slaStatus()
                                == MaintenanceSlaStatus.DUE_SOON
                )
                .count();

        return new MaintenancePriorityQueueResponse(
                fleet.mode(),
                fleet.enforced(),
                evaluatedAt,
                priorities.size(),
                urgent,
                attention,
                priorities.size() - urgent - attention,
                overdue,
                dueSoon,
                priorities
        );
    }

    private static MaintenancePriorityItemResponse toPriority(
            MaintenanceFlightClearanceResponse clearance,
            MaintenanceWorkOrder workOrder,
            Instant evaluatedAt
    ) {
        MaintenanceWorkOrderStatus status = workOrder == null
                ? clearance.workOrderStatus()
                : workOrder.getStatus();
        FlightClearanceStatus clearanceStatus = workOrder == null
                ? clearance.clearanceStatus()
                : workOrder.getClearanceStatus();
        Instant openedAt = workOrder == null
                || workOrder.getOpenedAt() == null
                ? null
                : workOrder.getOpenedAt().toInstant(ZoneOffset.UTC);
        Long waitingMinutes = waitingMinutes(
                workOrder,
                evaluatedAt
        );
        MaintenanceSlaPolicy.Evaluation sla =
                MaintenanceSlaPolicy.evaluate(workOrder, evaluatedAt);
        int riskScore = riskScore(
                clearance,
                status,
                clearanceStatus,
                waitingMinutes,
                sla.status()
        );
        MaintenancePriorityLevel priority = priority(riskScore);

        return new MaintenancePriorityItemResponse(
                clearance.droneId(),
                priority,
                riskScore,
                clearance.flightAllowed(),
                clearance.attentionRequired(),
                workOrder == null || workOrder.getId() == null
                        ? clearance.workOrderId()
                        : workOrder.getId(),
                status,
                clearanceStatus,
                openedAt,
                waitingMinutes,
                sla.status(),
                sla.dueAt(),
                sla.remainingMinutes(),
                sla.overdueMinutes(),
                recommendedAction(
                        clearance,
                        status,
                        clearanceStatus,
                        sla.status()
                ),
                clearance.reason()
        );
    }

    private static Long waitingMinutes(
            MaintenanceWorkOrder workOrder,
            Instant evaluatedAt
    ) {
        if (
                workOrder == null
                        || workOrder.getOpenedAt() == null
                        || workOrder.getStatus()
                        == MaintenanceWorkOrderStatus.COMPLETED
                        || workOrder.getStatus()
                        == MaintenanceWorkOrderStatus.GROUNDED
        ) {
            return null;
        }
        Instant openedAt = workOrder.getOpenedAt()
                .toInstant(ZoneOffset.UTC);
        if (evaluatedAt.isBefore(openedAt)) {
            return 0L;
        }
        return Duration.between(openedAt, evaluatedAt).toMinutes();
    }

    private static int riskScore(
            MaintenanceFlightClearanceResponse clearance,
            MaintenanceWorkOrderStatus status,
            FlightClearanceStatus clearanceStatus,
            Long waitingMinutes,
            MaintenanceSlaStatus slaStatus
    ) {
        if (!clearance.flightAllowed()) {
            return 100;
        }

        int score = 0;
        if (clearance.attentionRequired()) {
            score += 20;
        }
        if (clearanceStatus == FlightClearanceStatus.GROUNDED) {
            score = Math.max(score, 95);
        } else if (
                clearanceStatus
                        == FlightClearanceStatus.PENDING_INSPECTION
        ) {
            score = Math.max(score, 55);
        }

        if (status == MaintenanceWorkOrderStatus.GROUNDED) {
            score = Math.max(score, 95);
        } else if (status == MaintenanceWorkOrderStatus.OPEN) {
            score = Math.max(score, 65);
        } else if (
                status == MaintenanceWorkOrderStatus.IN_PROGRESS
        ) {
            score = Math.max(score, 50);
        } else if (
                status == MaintenanceWorkOrderStatus.COMPLETED
        ) {
            score = Math.max(score, 5);
        }

        if (waitingMinutes != null) {
            long waitingDays = waitingMinutes / (24L * 60L);
            score += (int) Math.min(20L, waitingDays * 5L);
        }
        if (slaStatus == MaintenanceSlaStatus.OVERDUE) {
            score += 20;
        } else if (slaStatus == MaintenanceSlaStatus.DUE_SOON) {
            score += 10;
        }
        return Math.min(100, score);
    }

    private static MaintenancePriorityLevel priority(int riskScore) {
        if (riskScore >= 90) {
            return MaintenancePriorityLevel.CRITICAL;
        }
        if (riskScore >= 65) {
            return MaintenancePriorityLevel.HIGH;
        }
        if (riskScore >= 30) {
            return MaintenancePriorityLevel.MEDIUM;
        }
        return MaintenancePriorityLevel.LOW;
    }

    private static String recommendedAction(
            MaintenanceFlightClearanceResponse clearance,
            MaintenanceWorkOrderStatus status,
            FlightClearanceStatus clearanceStatus,
            MaintenanceSlaStatus slaStatus
    ) {
        if (slaStatus == MaintenanceSlaStatus.OVERDUE) {
            return "SLA 초과: 즉시 담당자와 조치 계획을 확인하세요.";
        }
        if (slaStatus == MaintenanceSlaStatus.DUE_SOON) {
            return "SLA 임박: 제한시간 전에 다음 점검 단계를 완료하세요.";
        }
        if (
                !clearance.flightAllowed()
                        || clearanceStatus
                        == FlightClearanceStatus.GROUNDED
        ) {
            return "비행을 중지하고 점검 책임자와 조치 계획을 확인하세요.";
        }
        if (status == MaintenanceWorkOrderStatus.OPEN) {
            return "점검 담당자를 지정하고 작업을 시작하세요.";
        }
        if (status == MaintenanceWorkOrderStatus.IN_PROGRESS) {
            return "점검 결과와 재운항 판정을 완료하세요.";
        }
        if (clearance.attentionRequired()) {
            return "최근 위험 평가와 추가 점검 필요성을 확인하세요.";
        }
        return "정상 운용을 유지하고 정기 점검 주기를 확인하세요.";
    }

}
