package com.visionflow.api.maintenance.service;

import com.visionflow.api.incident.domain.Incident;
import com.visionflow.api.incident.domain.IncidentActionHistory;
import com.visionflow.api.incident.domain.IncidentActionType;
import com.visionflow.api.incident.domain.IncidentStatus;
import com.visionflow.api.incident.repository.IncidentActionHistoryRepository;
import com.visionflow.api.incident.repository.IncidentRepository;
import com.visionflow.api.maintenance.domain.FlightClearanceStatus;
import com.visionflow.api.maintenance.domain.MaintenanceSlaClosureStatus;
import com.visionflow.api.maintenance.domain.MaintenanceSlaResponseStatus;
import com.visionflow.api.maintenance.domain.MaintenanceSlaStatus;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrder;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrderStatus;
import com.visionflow.api.maintenance.dto.MaintenanceSlaIncidentTrackingItemResponse;
import com.visionflow.api.maintenance.dto.MaintenanceSlaIncidentTrackingResponse;
import com.visionflow.api.maintenance.repository.MaintenanceWorkOrderRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
public class MaintenanceSlaIncidentTrackingService {

    public static final int DEFAULT_WINDOW_DAYS = 30;
    public static final int MAX_WINDOW_DAYS = 90;

    private final MaintenanceWorkOrderRepository workOrderRepository;
    private final IncidentRepository incidentRepository;
    private final IncidentActionHistoryRepository historyRepository;

    public MaintenanceSlaIncidentTrackingService(
            MaintenanceWorkOrderRepository workOrderRepository,
            IncidentRepository incidentRepository,
            IncidentActionHistoryRepository historyRepository
    ) {
        this.workOrderRepository = workOrderRepository;
        this.incidentRepository = incidentRepository;
        this.historyRepository = historyRepository;
    }

    @Transactional(readOnly = true)
    public MaintenanceSlaIncidentTrackingResponse getTracking(
            int windowDays
    ) {
        validateWindowDays(windowDays);

        Instant evaluatedAt = Instant.now();
        LocalDateTime openedFrom = LocalDateTime.ofInstant(
                evaluatedAt.minus(windowDays, ChronoUnit.DAYS),
                ZoneOffset.UTC
        );
        List<MaintenanceWorkOrder> workOrders = workOrderRepository
                .findAllByOpenedAtGreaterThanEqualOrderByOpenedAtDescIdDesc(
                        openedFrom
                );
        Map<Long, Incident> incidentsById = incidentRepository
                .findAllById(
                        workOrders.stream()
                                .map(MaintenanceWorkOrder::getIncidentId)
                                .distinct()
                                .toList()
                )
                .stream()
                .collect(
                        Collectors.toMap(
                                Incident::getId,
                                Function.identity()
                        )
                );
        Map<Long, IncidentActionHistory> escalationsByIncidentId =
                new HashMap<>();

        List<MaintenanceSlaIncidentTrackingItemResponse> items = workOrders
                .stream()
                .map(workOrder -> toItem(
                        workOrder,
                        incidentsById.get(workOrder.getIncidentId()),
                        evaluatedAt,
                        escalationsByIncidentId
                ))
                .sorted(trackingOrder())
                .toList();

        return new MaintenanceSlaIncidentTrackingResponse(
                evaluatedAt,
                windowDays,
                items.size(),
                (int) items.stream()
                        .filter(item -> item.incidentStatus() != null)
                        .count(),
                (int) items.stream()
                        .filter(
                                item -> item.slaStatus()
                                        == MaintenanceSlaStatus.OVERDUE
                        )
                        .count(),
                (int) items.stream()
                        .filter(
                                MaintenanceSlaIncidentTrackingItemResponse
                                        ::escalated
                        )
                        .count(),
                countResponseStatus(
                        items,
                        MaintenanceSlaResponseStatus.MONITORING
                ),
                countResponseStatus(
                        items,
                        MaintenanceSlaResponseStatus.ESCALATION_PENDING
                ),
                countResponseStatus(
                        items,
                        MaintenanceSlaResponseStatus.ASSIGNMENT_REQUIRED
                ),
                countResponseStatus(
                        items,
                        MaintenanceSlaResponseStatus.IN_RESPONSE
                ),
                countResponseStatus(
                        items,
                        MaintenanceSlaResponseStatus.COMPLETED
                ),
                countClosureStatus(
                        items,
                        MaintenanceSlaClosureStatus.WORK_ORDER_PENDING
                ),
                countClosureStatus(
                        items,
                        MaintenanceSlaClosureStatus
                                .RETURN_TO_SERVICE_CONFIRMED
                ),
                countClosureStatus(
                        items,
                        MaintenanceSlaClosureStatus.GROUNDED_CONFIRMED
                ),
                countClosureStatus(
                        items,
                        MaintenanceSlaClosureStatus.REVIEW_REQUIRED
                ),
                items
        );
    }

    private MaintenanceSlaIncidentTrackingItemResponse toItem(
            MaintenanceWorkOrder workOrder,
            Incident incident,
            Instant evaluatedAt,
            Map<Long, IncidentActionHistory> escalationCache
    ) {
        MaintenanceSlaPolicy.Evaluation sla =
                MaintenanceSlaPolicy.evaluate(workOrder, evaluatedAt);
        IncidentActionHistory escalation = escalationCache.computeIfAbsent(
                workOrder.getIncidentId(),
                this::findLatestEscalation
        );
        MaintenanceSlaResponseStatus responseStatus =
                responseStatus(
                        incident,
                        sla.status(),
                        escalation != null
                );
        MaintenanceSlaClosureStatus closureStatus =
                closureStatus(workOrder, incident);

        return new MaintenanceSlaIncidentTrackingItemResponse(
                workOrder.getId(),
                workOrder.getIncidentId(),
                workOrder.getDroneId(),
                workOrder.getStatus(),
                workOrder.getClearanceStatus(),
                incident == null ? null : incident.getStatus(),
                incident == null ? null : incident.getPriority(),
                incident == null ? null : incident.getTitle(),
                incident == null ? null : incident.getAssignee(),
                sla.status(),
                sla.dueAt(),
                sla.overdueMinutes(),
                escalation != null,
                escalation == null
                        ? null
                        : escalation.getCreatedAt().toInstant(
                                ZoneOffset.UTC
                        ),
                escalation == null ? null : escalation.getActor(),
                escalation == null ? null : escalation.getNote(),
                responseStatus,
                recommendedAction(responseStatus),
                closureStatus,
                closureRecommendedAction(closureStatus)
        );
    }

    private IncidentActionHistory findLatestEscalation(Long incidentId) {
        return historyRepository
                .findAllByIncidentIdOrderByCreatedAtAscIdAsc(incidentId)
                .stream()
                .filter(
                        history -> history.getActionType()
                                == IncidentActionType.SLA_ESCALATED
                )
                .filter(
                        history -> MaintenanceSlaIncidentEscalationService
                                .SYSTEM_ACTOR
                                .equals(history.getActor())
                )
                .reduce((previous, current) -> current)
                .orElse(null);
    }

    private Comparator<MaintenanceSlaIncidentTrackingItemResponse>
    trackingOrder() {
        return Comparator
                .comparingInt(
                        (
                                MaintenanceSlaIncidentTrackingItemResponse
                                        item
                        ) -> closureOrder(item.closureStatus())
                )
                .thenComparingInt(
                        (
                                MaintenanceSlaIncidentTrackingItemResponse
                                        item
                        ) -> responseOrder(item.responseStatus())
                )
                .thenComparingInt(item -> slaOrder(item.slaStatus()))
                .thenComparing(
                        MaintenanceSlaIncidentTrackingItemResponse
                                ::escalated,
                        Comparator.reverseOrder()
                )
                .thenComparing(
                        MaintenanceSlaIncidentTrackingItemResponse
                                ::workOrderId,
                        Comparator.reverseOrder()
                );
    }

    private int countResponseStatus(
            List<MaintenanceSlaIncidentTrackingItemResponse> items,
            MaintenanceSlaResponseStatus status
    ) {
        return (int) items.stream()
                .filter(item -> item.responseStatus() == status)
                .count();
    }

    private int countClosureStatus(
            List<MaintenanceSlaIncidentTrackingItemResponse> items,
            MaintenanceSlaClosureStatus status
    ) {
        return (int) items.stream()
                .filter(item -> item.closureStatus() == status)
                .count();
    }

    private MaintenanceSlaResponseStatus responseStatus(
            Incident incident,
            MaintenanceSlaStatus slaStatus,
            boolean escalated
    ) {
        if (
                incident != null
                        && (
                        incident.getStatus() == IncidentStatus.RESOLVED
                                || incident.getStatus()
                                == IncidentStatus.CLOSED
                )
        ) {
            return MaintenanceSlaResponseStatus.COMPLETED;
        }
        if (
                incident == null
                        || (
                        slaStatus == MaintenanceSlaStatus.OVERDUE
                                && !escalated
                )
        ) {
            return MaintenanceSlaResponseStatus.ESCALATION_PENDING;
        }
        if (escalated && isBlank(incident.getAssignee())) {
            return MaintenanceSlaResponseStatus.ASSIGNMENT_REQUIRED;
        }
        if (escalated) {
            return MaintenanceSlaResponseStatus.IN_RESPONSE;
        }
        return MaintenanceSlaResponseStatus.MONITORING;
    }

    private String recommendedAction(
            MaintenanceSlaResponseStatus status
    ) {
        return switch (status) {
            case MONITORING -> "SLA 기한과 정비 진행 상태를 계속 감시하세요.";
            case ESCALATION_PENDING ->
                    "자동 상향 스케줄러와 연결 Incident 상태를 확인하세요.";
            case ASSIGNMENT_REQUIRED ->
                    "Incident 담당자를 지정하고 조치를 시작하세요.";
            case IN_RESPONSE ->
                    "담당자 조치 내용과 Incident 상태를 갱신하세요.";
            case COMPLETED ->
                    "종료된 조치 결과와 Incident 보고서를 확인하세요.";
        };
    }

    private MaintenanceSlaClosureStatus closureStatus(
            MaintenanceWorkOrder workOrder,
            Incident incident
    ) {
        if (incident == null) {
            return MaintenanceSlaClosureStatus.REVIEW_REQUIRED;
        }

        boolean incidentCompleted =
                incident.getStatus() == IncidentStatus.RESOLVED
                        || incident.getStatus() == IncidentStatus.CLOSED;
        MaintenanceWorkOrderStatus workOrderStatus =
                workOrder.getStatus();
        FlightClearanceStatus clearanceStatus =
                workOrder.getClearanceStatus();

        if (!incidentCompleted) {
            if (
                    (
                            workOrderStatus
                                    == MaintenanceWorkOrderStatus.OPEN
                                    || workOrderStatus
                                    == MaintenanceWorkOrderStatus.IN_PROGRESS
                    )
                            && clearanceStatus
                            == FlightClearanceStatus.PENDING_INSPECTION
            ) {
                return MaintenanceSlaClosureStatus.RESPONSE_ACTIVE;
            }
            if (
                    workOrderStatus
                            == MaintenanceWorkOrderStatus.GROUNDED
                            && clearanceStatus
                            == FlightClearanceStatus.GROUNDED
            ) {
                return MaintenanceSlaClosureStatus.RESPONSE_ACTIVE;
            }
            return MaintenanceSlaClosureStatus.REVIEW_REQUIRED;
        }

        if (
                (
                        workOrderStatus == MaintenanceWorkOrderStatus.OPEN
                                || workOrderStatus
                                == MaintenanceWorkOrderStatus.IN_PROGRESS
                )
                        && clearanceStatus
                        == FlightClearanceStatus.PENDING_INSPECTION
        ) {
            return MaintenanceSlaClosureStatus.WORK_ORDER_PENDING;
        }
        if (
                workOrderStatus == MaintenanceWorkOrderStatus.COMPLETED
                        && clearanceStatus
                        == FlightClearanceStatus.CLEARED
        ) {
            return MaintenanceSlaClosureStatus
                    .RETURN_TO_SERVICE_CONFIRMED;
        }
        if (
                workOrderStatus == MaintenanceWorkOrderStatus.GROUNDED
                        && clearanceStatus
                        == FlightClearanceStatus.GROUNDED
        ) {
            return MaintenanceSlaClosureStatus.GROUNDED_CONFIRMED;
        }
        return MaintenanceSlaClosureStatus.REVIEW_REQUIRED;
    }

    private String closureRecommendedAction(
            MaintenanceSlaClosureStatus status
    ) {
        return switch (status) {
            case RESPONSE_ACTIVE ->
                    "Incident 대응과 정비 진행 상태를 계속 확인하세요.";
            case WORK_ORDER_PENDING ->
                    "Incident는 해결되었습니다. 진행 중인 정비 작업을 마감하세요.";
            case RETURN_TO_SERVICE_CONFIRMED ->
                    "재운항 승인과 비행 허가 CLEARED 상태를 확인했습니다.";
            case GROUNDED_CONFIRMED ->
                    "운항 중지를 유지하고 수리 후 재점검을 준비하세요.";
            case REVIEW_REQUIRED ->
                    "Incident·정비 작업·비행 허가 상태 조합을 수동 점검하세요.";
        };
    }

    private int closureOrder(MaintenanceSlaClosureStatus status) {
        return switch (status) {
            case REVIEW_REQUIRED -> 0;
            case WORK_ORDER_PENDING -> 1;
            case RESPONSE_ACTIVE -> 2;
            case GROUNDED_CONFIRMED -> 3;
            case RETURN_TO_SERVICE_CONFIRMED -> 4;
        };
    }

    private int responseOrder(MaintenanceSlaResponseStatus status) {
        return switch (status) {
            case ESCALATION_PENDING -> 0;
            case ASSIGNMENT_REQUIRED -> 1;
            case IN_RESPONSE -> 2;
            case MONITORING -> 3;
            case COMPLETED -> 4;
        };
    }

    private boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private int slaOrder(MaintenanceSlaStatus status) {
        return switch (status) {
            case OVERDUE -> 0;
            case DUE_SOON -> 1;
            case ON_TRACK -> 2;
            case NOT_APPLICABLE -> 3;
        };
    }

    private void validateWindowDays(int windowDays) {
        if (windowDays < 1 || windowDays > MAX_WINDOW_DAYS) {
            throw new IllegalArgumentException(
                    "정비 SLA Incident 조회 기간은 1~"
                            + MAX_WINDOW_DAYS
                            + "일이어야 합니다."
            );
        }
    }
}
