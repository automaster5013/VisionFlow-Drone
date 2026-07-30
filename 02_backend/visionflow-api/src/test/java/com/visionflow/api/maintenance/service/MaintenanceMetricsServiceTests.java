package com.visionflow.api.maintenance.service;

import com.visionflow.api.maintenance.domain.MaintenanceCompletionDecision;
import com.visionflow.api.maintenance.domain.MaintenanceFlightGateMode;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrder;
import com.visionflow.api.maintenance.dto.MaintenanceFleetFlightClearanceResponse;
import com.visionflow.api.maintenance.dto.MaintenanceMetricsResponse;
import com.visionflow.api.maintenance.repository.MaintenanceWorkOrderRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Instant;
import java.time.LocalDateTime;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class MaintenanceMetricsServiceTests {

    @Mock
    private MaintenanceWorkOrderRepository workOrderRepository;

    @Mock
    private MaintenanceFlightGateService flightGateService;

    @Test
    void summarizesWorkOrdersAndCurrentFleetClearance() {
        LocalDateTime now = LocalDateTime.of(
                2026,
                7,
                26,
                12,
                0
        );
        List<MaintenanceWorkOrder> workOrders = List.of(
                MaintenanceWorkOrder.open(1L, 1L, null, 11L,
                        now.minusHours(4)),
                inProgress(2L, 2L, now.minusHours(3),
                        now.minusHours(2)),
                completed(3L, 3L, now.minusHours(5),
                        now.minusHours(4), now.minusHours(1),
                        MaintenanceCompletionDecision.RETURN_TO_SERVICE),
                completed(4L, 4L, now.minusHours(6),
                        now.minusHours(5), now.minusHours(2),
                        MaintenanceCompletionDecision.KEEP_GROUNDED)
        );
        MaintenanceFleetFlightClearanceResponse fleet =
                new MaintenanceFleetFlightClearanceResponse(
                        MaintenanceFlightGateMode.ENFORCED,
                        true,
                        3,
                        1,
                        2,
                        2,
                        Instant.parse("2026-07-26T03:00:00Z"),
                        List.of()
                );
        when(
                workOrderRepository
                        .findAllByOpenedAtGreaterThanEqualOrderByOpenedAtDescIdDesc(
                                any()
                        )
        ).thenReturn(workOrders);
        when(flightGateService.evaluateFleet()).thenReturn(fleet);
        MaintenanceMetricsService service =
                new MaintenanceMetricsService(
                        workOrderRepository,
                        flightGateService
                );

        MaintenanceMetricsResponse response = service.getMetrics(30);

        assertThat(response.totalWorkOrders()).isEqualTo(4);
        assertThat(response.openWorkOrders()).isEqualTo(1);
        assertThat(response.inProgressWorkOrders()).isEqualTo(1);
        assertThat(response.completedWorkOrders()).isEqualTo(1);
        assertThat(response.groundedWorkOrders()).isEqualTo(1);
        assertThat(response.resolvedWorkOrders()).isEqualTo(2);
        assertThat(response.resolutionRatePercent()).isEqualTo(50.0);
        assertThat(response.averageStartDelayMinutes()).isEqualTo(60L);
        assertThat(response.averageResolutionMinutes()).isEqualTo(240L);
        assertThat(response.gateMode())
                .isEqualTo(MaintenanceFlightGateMode.ENFORCED);
        assertThat(response.allowedDrones()).isEqualTo(1);
        assertThat(response.attentionDrones()).isEqualTo(2);
        assertThat(response.blockedDrones()).isEqualTo(2);
    }

    @Test
    void emptyWindowReturnsZeroRatesAndNullDurations() {
        MaintenanceFleetFlightClearanceResponse fleet =
                new MaintenanceFleetFlightClearanceResponse(
                        MaintenanceFlightGateMode.ADVISORY,
                        false,
                        0,
                        0,
                        0,
                        0,
                        Instant.parse("2026-07-26T03:00:00Z"),
                        List.of()
                );
        when(
                workOrderRepository
                        .findAllByOpenedAtGreaterThanEqualOrderByOpenedAtDescIdDesc(
                                any()
                        )
        ).thenReturn(List.of());
        when(flightGateService.evaluateFleet()).thenReturn(fleet);
        MaintenanceMetricsService service =
                new MaintenanceMetricsService(
                        workOrderRepository,
                        flightGateService
                );

        MaintenanceMetricsResponse response = service.getMetrics(7);

        assertThat(response.totalWorkOrders()).isZero();
        assertThat(response.resolutionRatePercent()).isZero();
        assertThat(response.averageStartDelayMinutes()).isNull();
        assertThat(response.averageResolutionMinutes()).isNull();
    }

    private MaintenanceWorkOrder inProgress(
            Long incidentId,
            Long droneId,
            LocalDateTime openedAt,
            LocalDateTime startedAt
    ) {
        MaintenanceWorkOrder order = MaintenanceWorkOrder.open(
                incidentId,
                droneId,
                null,
                null,
                openedAt
        );
        order.startInspection("tester", startedAt);
        return order;
    }

    private MaintenanceWorkOrder completed(
            Long incidentId,
            Long droneId,
            LocalDateTime openedAt,
            LocalDateTime startedAt,
            LocalDateTime completedAt,
            MaintenanceCompletionDecision decision
    ) {
        MaintenanceWorkOrder order = inProgress(
                incidentId,
                droneId,
                openedAt,
                startedAt
        );
        order.complete(
                decision,
                "점검 완료",
                "검증 조치",
                completedAt
        );
        return order;
    }
}
