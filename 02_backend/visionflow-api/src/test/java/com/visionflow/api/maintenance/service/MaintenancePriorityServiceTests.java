package com.visionflow.api.maintenance.service;

import com.visionflow.api.maintenance.domain.FlightClearanceStatus;
import com.visionflow.api.maintenance.domain.MaintenanceCompletionDecision;
import com.visionflow.api.maintenance.domain.MaintenanceFlightGateMode;
import com.visionflow.api.maintenance.domain.MaintenancePriorityLevel;
import com.visionflow.api.maintenance.domain.MaintenanceSlaStatus;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrder;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrderStatus;
import com.visionflow.api.maintenance.dto.MaintenanceFleetFlightClearanceResponse;
import com.visionflow.api.maintenance.dto.MaintenanceFlightClearanceResponse;
import com.visionflow.api.maintenance.dto.MaintenancePriorityQueueResponse;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class MaintenancePriorityServiceTests {

    @Test
    void prioritizesBlockedThenPendingThenNormalDrones() {
        Instant evaluatedAt = Instant.parse("2026-07-26T09:00:00Z");
        MaintenanceWorkOrder open = MaintenanceWorkOrder.open(
                11L,
                1L,
                null,
                101L,
                LocalDateTime.ofInstant(
                        evaluatedAt.minusSeconds(5 * 24 * 60 * 60L),
                        ZoneOffset.UTC
                )
        );
        MaintenanceWorkOrder grounded = MaintenanceWorkOrder.open(
                12L,
                2L,
                null,
                102L,
                LocalDateTime.ofInstant(
                        evaluatedAt.minusSeconds(60 * 60L),
                        ZoneOffset.UTC
                )
        );
        grounded.startInspection(
                "tester",
                LocalDateTime.ofInstant(
                        evaluatedAt.minusSeconds(30 * 60L),
                        ZoneOffset.UTC
                )
        );
        grounded.complete(
                MaintenanceCompletionDecision.KEEP_GROUNDED,
                "모터 점검 필요",
                "운항 중지",
                LocalDateTime.ofInstant(
                        evaluatedAt.minusSeconds(10 * 60L),
                        ZoneOffset.UTC
                )
        );
        MaintenanceFleetFlightClearanceResponse fleet =
                new MaintenanceFleetFlightClearanceResponse(
                        MaintenanceFlightGateMode.ENFORCED,
                        true,
                        3,
                        2,
                        2,
                        1,
                        evaluatedAt,
                        List.of(
                                clearance(
                                        1L,
                                        true,
                                        true,
                                        101L,
                                        MaintenanceWorkOrderStatus.OPEN,
                                        FlightClearanceStatus.PENDING_INSPECTION
                                ),
                                clearance(
                                        2L,
                                        false,
                                        true,
                                        102L,
                                        MaintenanceWorkOrderStatus.GROUNDED,
                                        FlightClearanceStatus.GROUNDED
                                ),
                                clearance(
                                        3L,
                                        true,
                                        false,
                                        null,
                                        null,
                                        null
                                )
                        )
                );

        MaintenancePriorityQueueResponse response =
                MaintenancePriorityService.prioritize(
                        fleet,
                        List.of(open, grounded),
                        evaluatedAt
                );

        assertThat(response.totalDrones()).isEqualTo(3);
        assertThat(response.urgentDrones()).isEqualTo(2);
        assertThat(response.attentionDrones()).isZero();
        assertThat(response.normalDrones()).isEqualTo(1);
        assertThat(response.overdueDrones()).isEqualTo(1);
        assertThat(response.dueSoonDrones()).isZero();
        assertThat(response.priorities())
                .extracting(item -> item.droneId())
                .containsExactly(2L, 1L, 3L);
        assertThat(response.priorities().get(0).priority())
                .isEqualTo(MaintenancePriorityLevel.CRITICAL);
        assertThat(response.priorities().get(0).riskScore())
                .isEqualTo(100);
        assertThat(response.priorities().get(1).priority())
                .isEqualTo(MaintenancePriorityLevel.CRITICAL);
        assertThat(response.priorities().get(1).riskScore())
                .isEqualTo(100);
        assertThat(response.priorities().get(1).waitingMinutes())
                .isEqualTo(5 * 24 * 60L);
        assertThat(response.priorities().get(1).slaStatus())
                .isEqualTo(MaintenanceSlaStatus.OVERDUE);
        assertThat(response.priorities().get(2).priority())
                .isEqualTo(MaintenancePriorityLevel.LOW);
    }

    @Test
    void marksOpenInspectionDueWithinThirtyMinutesAsDueSoon() {
        Instant evaluatedAt = Instant.parse("2026-07-26T09:00:00Z");
        MaintenanceWorkOrder open = MaintenanceWorkOrder.open(
                21L,
                1L,
                null,
                201L,
                LocalDateTime.ofInstant(
                        evaluatedAt.minusSeconds(90 * 60L),
                        ZoneOffset.UTC
                )
        );
        MaintenanceFleetFlightClearanceResponse fleet =
                new MaintenanceFleetFlightClearanceResponse(
                        MaintenanceFlightGateMode.ADVISORY,
                        false,
                        1,
                        1,
                        1,
                        0,
                        evaluatedAt,
                        List.of(
                                new MaintenanceFlightClearanceResponse(
                                        1L,
                                        MaintenanceFlightGateMode.ADVISORY,
                                        false,
                                        true,
                                        true,
                                        201L,
                                        MaintenanceWorkOrderStatus.OPEN,
                                        FlightClearanceStatus.PENDING_INSPECTION,
                                        "점검 대기"
                                )
                        )
                );

        MaintenancePriorityQueueResponse response =
                MaintenancePriorityService.prioritize(
                        fleet,
                        List.of(open),
                        evaluatedAt
                );

        assertThat(response.dueSoonDrones()).isEqualTo(1);
        assertThat(response.overdueDrones()).isZero();
        assertThat(response.priorities().get(0).slaStatus())
                .isEqualTo(MaintenanceSlaStatus.DUE_SOON);
        assertThat(response.priorities().get(0).slaRemainingMinutes())
                .isEqualTo(30L);
        assertThat(response.priorities().get(0).riskScore())
                .isEqualTo(75);
    }

    private MaintenanceFlightClearanceResponse clearance(
            Long droneId,
            boolean flightAllowed,
            boolean attentionRequired,
            Long workOrderId,
            MaintenanceWorkOrderStatus workOrderStatus,
            FlightClearanceStatus clearanceStatus
    ) {
        return new MaintenanceFlightClearanceResponse(
                droneId,
                MaintenanceFlightGateMode.ENFORCED,
                true,
                flightAllowed,
                attentionRequired,
                workOrderId,
                workOrderStatus,
                clearanceStatus,
                flightAllowed
                        ? "정비 상태를 확인하세요."
                        : "점검 완료 전까지 비행할 수 없습니다."
        );
    }
}
