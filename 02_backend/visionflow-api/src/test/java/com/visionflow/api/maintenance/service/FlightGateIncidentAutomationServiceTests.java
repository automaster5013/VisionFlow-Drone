package com.visionflow.api.maintenance.service;

import com.visionflow.api.audit.domain.AuditAction;
import com.visionflow.api.audit.domain.AuditEntityType;
import com.visionflow.api.audit.dto.AuditLogResponse;
import com.visionflow.api.audit.repository.AuditLogRepository;
import com.visionflow.api.audit.service.AuditLogService;
import com.visionflow.api.drone.domain.Drone;
import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.incident.domain.Incident;
import com.visionflow.api.incident.domain.IncidentActionHistory;
import com.visionflow.api.incident.domain.IncidentPriority;
import com.visionflow.api.incident.domain.IncidentSourceType;
import com.visionflow.api.incident.domain.IncidentStatus;
import com.visionflow.api.incident.realtime.IncidentRealtimePublisher;
import com.visionflow.api.incident.repository.IncidentActionHistoryRepository;
import com.visionflow.api.incident.repository.IncidentRepository;
import com.visionflow.api.maintenance.config.MaintenanceFlightGateProperties;
import com.visionflow.api.maintenance.domain.FlightClearanceStatus;
import com.visionflow.api.maintenance.domain.MaintenanceFlightGateMode;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrderStatus;
import com.visionflow.api.maintenance.dto.MaintenanceFlightClearanceResponse;
import org.junit.jupiter.api.Test;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;

import java.time.Instant;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class FlightGateIncidentAutomationServiceTests {

    private final MaintenanceFlightGateProperties properties =
            new MaintenanceFlightGateProperties();
    private final AuditLogRepository auditLogRepository =
            mock(AuditLogRepository.class);
    private final DroneRepository droneRepository =
            mock(DroneRepository.class);
    private final IncidentRepository incidentRepository =
            mock(IncidentRepository.class);
    private final IncidentActionHistoryRepository historyRepository =
            mock(IncidentActionHistoryRepository.class);
    private final IncidentRealtimePublisher realtimePublisher =
            mock(IncidentRealtimePublisher.class);
    private final AuditLogService auditLogService =
            mock(AuditLogService.class);
    private final FlightGateIncidentAutomationService service =
            new FlightGateIncidentAutomationService(
                    properties,
                    auditLogRepository,
                    droneRepository,
                    incidentRepository,
                    historyRepository,
                    realtimePublisher,
                    auditLogService
            );

    @Test
    void createsIncidentWhenRecentBlocksReachThreshold() {
        stubRecentBlockCount(3);
        when(incidentRepository.findBySourceTypeAndSourceIdForUpdate(
                IncidentSourceType.FLIGHT_GATE,
                3L
        )).thenReturn(Optional.empty());
        when(incidentRepository.saveAndFlush(any(Incident.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));

        var result = service.handleBlocked(clearance(), decisionLog());

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().sourceType())
                .isEqualTo(IncidentSourceType.FLIGHT_GATE);
        assertThat(result.orElseThrow().sourceId()).isEqualTo(3L);
        assertThat(result.orElseThrow().droneId()).isEqualTo(3L);
        assertThat(result.orElseThrow().status())
                .isEqualTo(IncidentStatus.OPEN);
        assertThat(result.orElseThrow().priority())
                .isEqualTo(IncidentPriority.HIGH);
        verify(historyRepository)
                .saveAndFlush(any(IncidentActionHistory.class));
    }

    @Test
    void doesNotCreateIncidentBelowThreshold() {
        stubRecentBlockCount(2);

        var result = service.handleBlocked(clearance(), decisionLog());

        assertThat(result).isEmpty();
        verify(incidentRepository, never())
                .findBySourceTypeAndSourceIdForUpdate(
                        any(IncidentSourceType.class),
                        any(Long.class)
                );
        verify(incidentRepository, never())
                .saveAndFlush(any(Incident.class));
    }

    @Test
    void reusesActiveIncidentInsteadOfCreatingDuplicate() {
        stubRecentBlockCount(5);
        Incident existing = activeIncident();
        when(incidentRepository.findBySourceTypeAndSourceIdForUpdate(
                IncidentSourceType.FLIGHT_GATE,
                3L
        )).thenReturn(Optional.of(existing));

        var result = service.handleBlocked(clearance(), decisionLog());

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().status())
                .isEqualTo(IncidentStatus.OPEN);
        verify(incidentRepository, never())
                .saveAndFlush(any(Incident.class));
    }

    @Test
    void returnToServiceResolvesActiveIncident() {
        Incident existing = activeIncident();
        when(incidentRepository.findBySourceTypeAndSourceIdForUpdate(
                IncidentSourceType.FLIGHT_GATE,
                3L
        )).thenReturn(Optional.of(existing));
        when(incidentRepository.saveAndFlush(existing))
                .thenReturn(existing);

        var result = service.resolveForDrone(
                3L,
                "demo-operator",
                "점검 완료 및 재운항 승인"
        );

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().status())
                .isEqualTo(IncidentStatus.RESOLVED);
        verify(historyRepository)
                .saveAndFlush(any(IncidentActionHistory.class));
    }

    private void stubRecentBlockCount(long total) {
        when(auditLogRepository.search(
                eq(AuditAction.MAINTENANCE_FLIGHT_START_BLOCKED),
                eq(AuditEntityType.MAINTENANCE_FLIGHT_GATE),
                eq("3"),
                eq(null),
                eq(LocalDateTime.of(2026, 7, 26, 4, 50)),
                eq(LocalDateTime.of(2026, 7, 26, 5, 0)),
                eq(PageRequest.of(0, 1))
        )).thenReturn(new PageImpl<>(
                List.of(),
                PageRequest.of(0, 1),
                total
        ));
        if (total >= properties.getIncident().getThreshold()) {
            when(droneRepository.findByIdForUpdate(3L))
                    .thenReturn(Optional.of(mock(Drone.class)));
        }
    }

    private MaintenanceFlightClearanceResponse clearance() {
        return new MaintenanceFlightClearanceResponse(
                3L,
                MaintenanceFlightGateMode.ENFORCED,
                true,
                false,
                true,
                31L,
                MaintenanceWorkOrderStatus.OPEN,
                FlightClearanceStatus.PENDING_INSPECTION,
                "점검 또는 승인 대기 상태이므로 새 비행 세션을 시작할 수 없습니다."
        );
    }

    private AuditLogResponse decisionLog() {
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

    private Incident activeIncident() {
        return Incident.create(
                IncidentSourceType.FLIGHT_GATE,
                3L,
                3L,
                null,
                IncidentPriority.HIGH,
                IncidentStatus.OPEN,
                "반복 비행 시작 차단: Drone #3",
                "10분 내 3회 차단",
                LocalDateTime.of(2026, 7, 26, 5, 0),
                null
        );
    }
}
