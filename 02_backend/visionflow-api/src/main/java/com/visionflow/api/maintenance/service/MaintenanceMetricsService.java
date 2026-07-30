package com.visionflow.api.maintenance.service;

import com.visionflow.api.maintenance.domain.MaintenanceWorkOrder;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrderStatus;
import com.visionflow.api.maintenance.dto.MaintenanceFleetFlightClearanceResponse;
import com.visionflow.api.maintenance.dto.MaintenanceMetricsResponse;
import com.visionflow.api.maintenance.repository.MaintenanceWorkOrderRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;

@Service
public class MaintenanceMetricsService {

    private final MaintenanceWorkOrderRepository workOrderRepository;
    private final MaintenanceFlightGateService flightGateService;

    public MaintenanceMetricsService(
            MaintenanceWorkOrderRepository workOrderRepository,
            MaintenanceFlightGateService flightGateService
    ) {
        this.workOrderRepository = workOrderRepository;
        this.flightGateService = flightGateService;
    }

    @Transactional(readOnly = true)
    public MaintenanceMetricsResponse getMetrics(int windowDays) {
        LocalDateTime generatedAt = LocalDateTime.now(ZoneOffset.UTC);
        LocalDateTime windowStartedAt =
                generatedAt.minusDays(windowDays);
        List<MaintenanceWorkOrder> workOrders =
                workOrderRepository
                        .findAllByOpenedAtGreaterThanEqualOrderByOpenedAtDescIdDesc(
                                windowStartedAt
                        );
        MaintenanceFleetFlightClearanceResponse fleet =
                flightGateService.evaluateFleet();

        return summarize(
                windowDays,
                windowStartedAt,
                generatedAt,
                workOrders,
                fleet
        );
    }

    static MaintenanceMetricsResponse summarize(
            int windowDays,
            LocalDateTime windowStartedAt,
            LocalDateTime generatedAt,
            List<MaintenanceWorkOrder> workOrders,
            MaintenanceFleetFlightClearanceResponse fleet
    ) {
        long open = count(
                workOrders,
                MaintenanceWorkOrderStatus.OPEN
        );
        long inProgress = count(
                workOrders,
                MaintenanceWorkOrderStatus.IN_PROGRESS
        );
        long completed = count(
                workOrders,
                MaintenanceWorkOrderStatus.COMPLETED
        );
        long grounded = count(
                workOrders,
                MaintenanceWorkOrderStatus.GROUNDED
        );
        long resolved = completed + grounded;
        double resolutionRate = workOrders.isEmpty()
                ? 0.0
                : roundOneDecimal(
                        (double) resolved
                                / (double) workOrders.size()
                                * 100.0
                );

        return new MaintenanceMetricsResponse(
                windowDays,
                windowStartedAt.toInstant(ZoneOffset.UTC),
                generatedAt.toInstant(ZoneOffset.UTC),
                workOrders.size(),
                open,
                inProgress,
                completed,
                grounded,
                resolved,
                resolutionRate,
                averageMinutes(
                        workOrders,
                        DurationType.START_DELAY
                ),
                averageMinutes(
                        workOrders,
                        DurationType.RESOLUTION
                ),
                fleet.mode(),
                fleet.enforced(),
                fleet.totalDrones(),
                fleet.allowedDrones(),
                fleet.attentionDrones(),
                fleet.blockedDrones()
        );
    }

    private static long count(
            List<MaintenanceWorkOrder> workOrders,
            MaintenanceWorkOrderStatus status
    ) {
        return workOrders.stream()
                .filter(order -> order.getStatus() == status)
                .count();
    }

    private static Long averageMinutes(
            List<MaintenanceWorkOrder> workOrders,
            DurationType type
    ) {
        double average = workOrders.stream()
                .map(order -> durationMinutes(order, type))
                .filter(value -> value != null && value >= 0)
                .mapToLong(Long::longValue)
                .average()
                .orElse(Double.NaN);
        return Double.isNaN(average)
                ? null
                : Math.round(average);
    }

    private static Long durationMinutes(
            MaintenanceWorkOrder order,
            DurationType type
    ) {
        LocalDateTime end = type == DurationType.START_DELAY
                ? order.getStartedAt()
                : order.getCompletedAt();
        if (end == null || end.isBefore(order.getOpenedAt())) {
            return null;
        }
        return Duration.between(
                order.getOpenedAt(),
                end
        ).toMinutes();
    }

    private static double roundOneDecimal(double value) {
        return Math.round(value * 10.0) / 10.0;
    }

    private enum DurationType {
        START_DELAY,
        RESOLUTION
    }
}
