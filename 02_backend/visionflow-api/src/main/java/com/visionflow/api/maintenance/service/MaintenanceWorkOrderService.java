package com.visionflow.api.maintenance.service;

import com.visionflow.api.audit.domain.AuditAction;
import com.visionflow.api.audit.domain.AuditEntityType;
import com.visionflow.api.audit.service.AuditLogService;
import com.visionflow.api.common.exception.ResourceNotFoundException;
import com.visionflow.api.common.security.OperatorPrincipal;
import com.visionflow.api.incident.domain.Incident;
import com.visionflow.api.maintenance.domain.MaintenanceCompletionDecision;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrder;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrderActionType;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrderHistory;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrderStatus;
import com.visionflow.api.maintenance.dto.MaintenanceInspectionCompleteRequest;
import com.visionflow.api.maintenance.dto.MaintenanceInspectionStartRequest;
import com.visionflow.api.maintenance.dto.MaintenanceWorkOrderDetailResponse;
import com.visionflow.api.maintenance.dto.MaintenanceWorkOrderHistoryResponse;
import com.visionflow.api.maintenance.dto.MaintenanceWorkOrderResponse;
import com.visionflow.api.maintenance.repository.MaintenanceWorkOrderHistoryRepository;
import com.visionflow.api.maintenance.repository.MaintenanceWorkOrderRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.PageRequest;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.Optional;

@Service
public class MaintenanceWorkOrderService {

    private static final Logger log = LoggerFactory.getLogger(
            MaintenanceWorkOrderService.class
    );
    private static final String SYSTEM_ACTOR =
            "system-flight-quality-maintenance";

    private final MaintenanceWorkOrderRepository workOrderRepository;
    private final MaintenanceWorkOrderHistoryRepository historyRepository;
    private final AuditLogService auditLogService;
    private final FlightGateIncidentAutomationService
            incidentAutomationService;

    public MaintenanceWorkOrderService(
            MaintenanceWorkOrderRepository workOrderRepository,
            MaintenanceWorkOrderHistoryRepository historyRepository,
            AuditLogService auditLogService,
            FlightGateIncidentAutomationService incidentAutomationService
    ) {
        this.workOrderRepository = workOrderRepository;
        this.historyRepository = historyRepository;
        this.auditLogService = auditLogService;
        this.incidentAutomationService = incidentAutomationService;
    }

    @Transactional
    public MaintenanceWorkOrderResponse synchronizeRequired(
            Incident incident,
            Long sourceAssessmentId
    ) {
        LocalDateTime now = nowUtc();
        Optional<MaintenanceWorkOrder> existing =
                workOrderRepository.findByIncidentIdForUpdate(
                        incident.getId()
                );

        if (existing.isEmpty()) {
            MaintenanceWorkOrder created = workOrderRepository.saveAndFlush(
                    MaintenanceWorkOrder.open(
                            incident.getId(),
                            incident.getDroneId(),
                            incident.getSessionId(),
                            sourceAssessmentId,
                            now
                    )
            );
            saveHistory(
                    created,
                    MaintenanceWorkOrderActionType.CREATED,
                    null,
                    created.getStatus(),
                    SYSTEM_ACTOR,
                    "기체 신뢰도 Incident에서 점검 작업 자동 생성"
            );
            recordAudit(
                    AuditAction.MAINTENANCE_WORK_ORDER_SYNCHRONIZED,
                    created,
                    "점검 작업 자동 생성",
                    SYSTEM_ACTOR
            );
            return MaintenanceWorkOrderResponse.from(created);
        }

        MaintenanceWorkOrder order = existing.get();
        MaintenanceWorkOrderStatus previousStatus = order.getStatus();
        boolean changed = order.synchronizeRisk(
                incident.getSessionId(),
                sourceAssessmentId,
                now
        );

        if (!changed) {
            return MaintenanceWorkOrderResponse.from(order);
        }

        order = workOrderRepository.saveAndFlush(order);
        MaintenanceWorkOrderActionType action =
                previousStatus == MaintenanceWorkOrderStatus.COMPLETED
                        ? MaintenanceWorkOrderActionType.REOPENED
                        : MaintenanceWorkOrderActionType.RISK_SYNCHRONIZED;
        saveHistory(
                order,
                action,
                previousStatus,
                order.getStatus(),
                SYSTEM_ACTOR,
                action == MaintenanceWorkOrderActionType.REOPENED
                        ? "재발한 기체 신뢰도 위험으로 점검 작업 재개"
                        : "최신 기체 신뢰도 평가와 작업 원본 동기화"
        );
        recordAudit(
                AuditAction.MAINTENANCE_WORK_ORDER_SYNCHRONIZED,
                order,
                "점검 작업 원본 동기화",
                SYSTEM_ACTOR
        );
        return MaintenanceWorkOrderResponse.from(order);
    }

    @Transactional(readOnly = true)
    public List<MaintenanceWorkOrderResponse> findWorkOrders(
            Long droneId,
            MaintenanceWorkOrderStatus status,
            int limit
    ) {
        return workOrderRepository.findWorkOrders(
                        droneId,
                        status,
                        PageRequest.of(0, limit)
                )
                .stream()
                .map(MaintenanceWorkOrderResponse::from)
                .toList();
    }

    @Transactional(readOnly = true)
    public MaintenanceWorkOrderDetailResponse findDetail(Long workOrderId) {
        MaintenanceWorkOrder order = requireWorkOrder(workOrderId);
        List<MaintenanceWorkOrderHistoryResponse> history =
                historyRepository
                        .findAllByWorkOrderIdOrderByCreatedAtAscIdAsc(
                                workOrderId
                        )
                        .stream()
                        .map(MaintenanceWorkOrderHistoryResponse::from)
                        .toList();
        return new MaintenanceWorkOrderDetailResponse(
                MaintenanceWorkOrderResponse.from(order),
                history
        );
    }

    @Transactional
    public MaintenanceWorkOrderResponse startInspection(
            Long workOrderId,
            MaintenanceInspectionStartRequest request
    ) {
        MaintenanceWorkOrder order =
                requireWorkOrderForUpdate(workOrderId);
        MaintenanceWorkOrderStatus previousStatus = order.getStatus();
        String actor = actor(request.actor());
        order.startInspection(
                normalizeRequired(
                        request.assignee(),
                        100,
                        "점검 담당자"
                ),
                nowUtc()
        );
        order = workOrderRepository.saveAndFlush(order);
        saveHistory(
                order,
                MaintenanceWorkOrderActionType.INSPECTION_STARTED,
                previousStatus,
                order.getStatus(),
                actor,
                normalizeOptional(
                        request.note(),
                        1000,
                        "점검 시작 메모"
                )
        );
        recordAudit(
                AuditAction.MAINTENANCE_INSPECTION_STARTED,
                order,
                "기체 점검 시작",
                actor
        );
        return MaintenanceWorkOrderResponse.from(order);
    }

    @Transactional
    public MaintenanceWorkOrderResponse completeInspection(
            Long workOrderId,
            MaintenanceInspectionCompleteRequest request
    ) {
        MaintenanceWorkOrder order =
                requireWorkOrderForUpdate(workOrderId);
        MaintenanceWorkOrderStatus previousStatus = order.getStatus();
        String actor = actor(request.actor());
        String finding = normalizeRequired(
                request.finding(),
                1000,
                "점검 결과"
        );
        String resolutionNote = normalizeRequired(
                request.resolutionNote(),
                1000,
                "조치 메모"
        );
        order.complete(
                request.decision(),
                finding,
                resolutionNote,
                nowUtc()
        );
        order = workOrderRepository.saveAndFlush(order);
        MaintenanceWorkOrderActionType action =
                request.decision()
                        == MaintenanceCompletionDecision.RETURN_TO_SERVICE
                        ? MaintenanceWorkOrderActionType.RETURNED_TO_SERVICE
                        : MaintenanceWorkOrderActionType.GROUNDED;
        saveHistory(
                order,
                action,
                previousStatus,
                order.getStatus(),
                actor,
                finding + " / " + resolutionNote
        );
        recordAudit(
                request.decision()
                        == MaintenanceCompletionDecision.RETURN_TO_SERVICE
                        ? AuditAction.MAINTENANCE_RETURN_TO_SERVICE_APPROVED
                        : AuditAction.MAINTENANCE_DRONE_GROUNDED,
                order,
                request.decision()
                        == MaintenanceCompletionDecision.RETURN_TO_SERVICE
                        ? "기체 재운항 승인"
                        : "기체 운항 중지 유지",
                actor
        );
        if (
                request.decision()
                        == MaintenanceCompletionDecision.RETURN_TO_SERVICE
        ) {
            resolveFlightGateIncident(order, actor);
        }
        return MaintenanceWorkOrderResponse.from(order);
    }

    private MaintenanceWorkOrder requireWorkOrder(Long workOrderId) {
        return workOrderRepository.findById(workOrderId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "점검 작업지시를 찾을 수 없습니다: "
                                + workOrderId
                ));
    }

    private MaintenanceWorkOrder requireWorkOrderForUpdate(
            Long workOrderId
    ) {
        return workOrderRepository.findByIdForUpdate(workOrderId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "점검 작업지시를 찾을 수 없습니다: "
                                + workOrderId
                ));
    }

    private void saveHistory(
            MaintenanceWorkOrder order,
            MaintenanceWorkOrderActionType action,
            MaintenanceWorkOrderStatus previousStatus,
            MaintenanceWorkOrderStatus newStatus,
            String actor,
            String note
    ) {
        historyRepository.saveAndFlush(
                MaintenanceWorkOrderHistory.create(
                        order.getId(),
                        action,
                        previousStatus,
                        newStatus,
                        actor,
                        note
                )
        );
    }

    private void recordAudit(
            AuditAction action,
            MaintenanceWorkOrder order,
            String summary,
            String actor
    ) {
        try {
            auditLogService.record(
                    action,
                    AuditEntityType.MAINTENANCE_WORK_ORDER,
                    order.getId(),
                    summary,
                    Map.of(
                            "droneId", order.getDroneId(),
                            "incidentId", order.getIncidentId(),
                            "status", order.getStatus().name(),
                            "clearanceStatus",
                            order.getClearanceStatus().name()
                    ),
                    actor
            );
        } catch (RuntimeException exception) {
            log.error(
                    "점검 작업 감사 로그 저장 실패: workOrderId={}",
                    order.getId(),
                    exception
            );
        }
    }

    private void resolveFlightGateIncident(
            MaintenanceWorkOrder order,
            String actor
    ) {
        try {
            incidentAutomationService.resolveForDrone(
                    order.getDroneId(),
                    actor,
                    "점검 완료 및 재운항 승인"
            );
        } catch (RuntimeException exception) {
            log.error(
                    "재운항 승인 후 비행 게이트 Incident 해제 실패: "
                            + "workOrderId={}, droneId={}",
                    order.getId(),
                    order.getDroneId(),
                    exception
            );
        }
    }

    private String actor(String requestedActor) {
        Authentication authentication = SecurityContextHolder
                .getContext()
                .getAuthentication();
        if (
                authentication != null
                        && authentication.isAuthenticated()
                        && authentication.getPrincipal()
                        instanceof OperatorPrincipal principal
        ) {
            return principal.username();
        }
        return normalizeRequired(requestedActor, 100, "처리자");
    }

    private String normalizeRequired(
            String value,
            int maximumLength,
            String fieldName
    ) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(fieldName + "는 필수입니다.");
        }
        String normalized = value.trim();
        if (normalized.length() > maximumLength) {
            throw new IllegalArgumentException(
                    fieldName + "는 " + maximumLength + "자 이하여야 합니다."
            );
        }
        return normalized;
    }

    private String normalizeOptional(
            String value,
            int maximumLength,
            String fieldName
    ) {
        return value == null || value.isBlank()
                ? null
                : normalizeRequired(value, maximumLength, fieldName);
    }

    private LocalDateTime nowUtc() {
        return LocalDateTime.now(ZoneOffset.UTC);
    }
}
