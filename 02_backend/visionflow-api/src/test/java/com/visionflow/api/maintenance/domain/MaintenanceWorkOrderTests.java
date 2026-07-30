package com.visionflow.api.maintenance.domain;

import org.junit.jupiter.api.Test;

import java.time.LocalDateTime;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class MaintenanceWorkOrderTests {

    @Test
    void inspectionCanReturnDroneToService() {
        LocalDateTime openedAt = LocalDateTime.of(
                2026,
                7,
                25,
                10,
                0
        );
        MaintenanceWorkOrder order = MaintenanceWorkOrder.open(
                11L,
                3L,
                "session-1",
                21L,
                openedAt
        );

        order.startInspection("demo-operator", openedAt.plusMinutes(5));
        order.complete(
                MaintenanceCompletionDecision.RETURN_TO_SERVICE,
                "기체 및 통신 상태 정상",
                "재운항 승인",
                openedAt.plusMinutes(10)
        );

        assertThat(order.getStatus())
                .isEqualTo(MaintenanceWorkOrderStatus.COMPLETED);
        assertThat(order.getClearanceStatus())
                .isEqualTo(FlightClearanceStatus.CLEARED);
        assertThat(order.getClearedAt())
                .isEqualTo(openedAt.plusMinutes(10));
    }

    @Test
    void newRiskReopensPreviouslyClearedOrder() {
        LocalDateTime openedAt = LocalDateTime.of(
                2026,
                7,
                25,
                10,
                0
        );
        MaintenanceWorkOrder order = MaintenanceWorkOrder.open(
                11L,
                3L,
                "session-1",
                21L,
                openedAt
        );
        order.startInspection("demo-operator", openedAt.plusMinutes(5));
        order.complete(
                MaintenanceCompletionDecision.RETURN_TO_SERVICE,
                "정상",
                "승인",
                openedAt.plusMinutes(10)
        );

        boolean changed = order.synchronizeRisk(
                "session-2",
                22L,
                openedAt.plusDays(1)
        );

        assertThat(changed).isTrue();
        assertThat(order.getStatus())
                .isEqualTo(MaintenanceWorkOrderStatus.OPEN);
        assertThat(order.getClearanceStatus())
                .isEqualTo(FlightClearanceStatus.PENDING_INSPECTION);
        assertThat(order.getClearedAt()).isNull();
        assertThat(order.getSessionId()).isEqualTo("session-2");
    }

    @Test
    void orderMustBeInProgressBeforeCompletion() {
        MaintenanceWorkOrder order = MaintenanceWorkOrder.open(
                11L,
                3L,
                "session-1",
                21L,
                LocalDateTime.now()
        );

        assertThatThrownBy(() -> order.complete(
                MaintenanceCompletionDecision.KEEP_GROUNDED,
                "이상",
                "운항 중지",
                LocalDateTime.now()
        ))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("진행 중인 점검");
    }
}
