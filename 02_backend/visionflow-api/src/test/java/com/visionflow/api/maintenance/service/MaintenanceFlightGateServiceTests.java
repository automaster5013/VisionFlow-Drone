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
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrderStatus;
import com.visionflow.api.maintenance.exception.FlightClearanceRequiredException;
import com.visionflow.api.maintenance.repository.MaintenanceWorkOrderRepository;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.anyMap;
import static org.mockito.Mockito.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class MaintenanceFlightGateServiceTests {

    private final MaintenanceWorkOrderRepository repository =
            mock(MaintenanceWorkOrderRepository.class);
    private final DroneRepository droneRepository =
            mock(DroneRepository.class);
    private final MaintenanceFlightGateProperties properties =
            new MaintenanceFlightGateProperties();
    private final AuditLogService auditLogService =
            mock(AuditLogService.class);
    private final FlightGateIncidentAutomationService
            incidentAutomationService =
            mock(FlightGateIncidentAutomationService.class);
    private final MaintenanceFlightGateService service =
            new MaintenanceFlightGateService(
                    repository,
                    droneRepository,
                    properties,
                    auditLogService,
                    incidentAutomationService
            );

    @Test
    void enforcedModeBlocksPendingInspection() {
        properties.setMode(MaintenanceFlightGateMode.ENFORCED);
        MaintenanceWorkOrder order = workOrder(
                31L,
                MaintenanceWorkOrderStatus.OPEN,
                FlightClearanceStatus.PENDING_INSPECTION
        );
        when(repository.findFirstByDroneIdOrderByUpdatedAtDescIdDesc(3L))
                .thenReturn(Optional.of(order));
        AuditLogResponse decisionLog = blockedDecisionLog();
        when(auditLogService.record(
                eq(AuditAction.MAINTENANCE_FLIGHT_START_BLOCKED),
                eq(AuditEntityType.MAINTENANCE_FLIGHT_GATE),
                eq(3L),
                eq("정비 게이트 비행 시작 차단"),
                anyMap()
        )).thenReturn(decisionLog);

        var result = service.evaluate(3L);

        assertThat(result.enforced()).isTrue();
        assertThat(result.flightAllowed()).isFalse();
        assertThat(result.attentionRequired()).isTrue();
        assertThatThrownBy(() -> service.requireStartClearance(3L))
                .isInstanceOf(FlightClearanceRequiredException.class)
                .hasMessageContaining("재운항 승인");
        verify(auditLogService).record(
                eq(AuditAction.MAINTENANCE_FLIGHT_START_BLOCKED),
                eq(AuditEntityType.MAINTENANCE_FLIGHT_GATE),
                eq(3L),
                eq("정비 게이트 비행 시작 차단"),
                anyMap()
        );
        verify(incidentAutomationService).handleBlocked(
                result,
                decisionLog
        );
    }

    @Test
    void advisoryModeWarnsButAllowsGroundedDrone() {
        properties.setMode(MaintenanceFlightGateMode.ADVISORY);
        MaintenanceWorkOrder order = workOrder(
                31L,
                MaintenanceWorkOrderStatus.GROUNDED,
                FlightClearanceStatus.GROUNDED
        );
        when(repository.findFirstByDroneIdOrderByUpdatedAtDescIdDesc(3L))
                .thenReturn(Optional.of(order));

        var result = service.evaluate(3L);

        assertThat(result.enforced()).isFalse();
        assertThat(result.flightAllowed()).isTrue();
        assertThat(result.attentionRequired()).isTrue();
        assertThat(result.reason()).contains("안내 모드");

        service.requireStartClearance(3L);
        verify(auditLogService).record(
                eq(AuditAction.MAINTENANCE_FLIGHT_START_ADVISORY),
                eq(AuditEntityType.MAINTENANCE_FLIGHT_GATE),
                eq(3L),
                eq("정비 게이트 주의 후 비행 시작 허용"),
                anyMap()
        );
    }

    @Test
    void clearedDroneIsAllowedInEnforcedMode() {
        properties.setMode(MaintenanceFlightGateMode.ENFORCED);
        MaintenanceWorkOrder order = workOrder(
                31L,
                MaintenanceWorkOrderStatus.COMPLETED,
                FlightClearanceStatus.CLEARED
        );
        when(repository.findFirstByDroneIdOrderByUpdatedAtDescIdDesc(3L))
                .thenReturn(Optional.of(order));

        var result = service.evaluate(3L);

        assertThat(result.flightAllowed()).isTrue();
        assertThat(result.attentionRequired()).isFalse();

        service.requireStartClearance(3L);
        verify(auditLogService).record(
                eq(AuditAction.MAINTENANCE_FLIGHT_START_ALLOWED),
                eq(AuditEntityType.MAINTENANCE_FLIGHT_GATE),
                eq(3L),
                eq("정비 게이트 비행 시작 허용"),
                anyMap()
        );
    }

    @Test
    void droneWithoutWorkOrderIsAllowed() {
        properties.setMode(MaintenanceFlightGateMode.ENFORCED);
        when(repository.findFirstByDroneIdOrderByUpdatedAtDescIdDesc(3L))
                .thenReturn(Optional.empty());

        var result = service.evaluate(3L);

        assertThat(result.flightAllowed()).isTrue();
        assertThat(result.workOrderId()).isNull();
    }

    @Test
    void fleetEvaluationReturnsAllowedAttentionAndBlockedCounts() {
        properties.setMode(MaintenanceFlightGateMode.ENFORCED);
        Drone droneOne = drone(1L);
        Drone droneTwo = drone(2L);
        Drone droneThree = drone(3L);
        MaintenanceWorkOrder pending = workOrder(
                41L,
                MaintenanceWorkOrderStatus.OPEN,
                FlightClearanceStatus.PENDING_INSPECTION
        );
        when(pending.getDroneId()).thenReturn(2L);
        MaintenanceWorkOrder cleared = workOrder(
                42L,
                MaintenanceWorkOrderStatus.COMPLETED,
                FlightClearanceStatus.CLEARED
        );
        when(cleared.getDroneId()).thenReturn(3L);
        when(droneRepository.findAllByOrderByCreatedAtDesc())
                .thenReturn(List.of(droneOne, droneTwo, droneThree));
        when(repository.findLatestForAllDrones())
                .thenReturn(List.of(pending, cleared));

        var result = service.evaluateFleet();

        assertThat(result.mode())
                .isEqualTo(MaintenanceFlightGateMode.ENFORCED);
        assertThat(result.totalDrones()).isEqualTo(3);
        assertThat(result.allowedDrones()).isEqualTo(2);
        assertThat(result.attentionDrones()).isEqualTo(1);
        assertThat(result.blockedDrones()).isEqualTo(1);
        assertThat(result.clearances())
                .extracting(clearance -> clearance.droneId())
                .containsExactly(1L, 2L, 3L);
    }

    private MaintenanceWorkOrder workOrder(
            Long id,
            MaintenanceWorkOrderStatus status,
            FlightClearanceStatus clearance
    ) {
        MaintenanceWorkOrder workOrder =
                mock(MaintenanceWorkOrder.class);
        when(workOrder.getId()).thenReturn(id);
        when(workOrder.getStatus()).thenReturn(status);
        when(workOrder.getClearanceStatus()).thenReturn(clearance);
        return workOrder;
    }

    private Drone drone(Long id) {
        Drone drone = mock(Drone.class);
        when(drone.getId()).thenReturn(id);
        return drone;
    }

    private AuditLogResponse blockedDecisionLog() {
        return new AuditLogResponse(
                901L,
                Instant.parse("2026-07-26T05:00:00Z"),
                "demo-operator",
                AuditAction.MAINTENANCE_FLIGHT_START_BLOCKED,
                AuditEntityType.MAINTENANCE_FLIGHT_GATE,
                "3",
                "정비 게이트 비행 시작 차단",
                "{}",
                "POST",
                "/api/drones/3/flight-sessions",
                "test-trace"
        );
    }
}
