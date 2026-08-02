package com.visionflow.api.flight.quality.service;

import com.visionflow.api.audit.service.AuditLogService;
import com.visionflow.api.drone.domain.Drone;
import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.flight.domain.FlightSessionStatus;
import com.visionflow.api.flight.quality.domain.FleetReliabilityStatus;
import com.visionflow.api.flight.quality.domain.FlightQualityGrade;
import com.visionflow.api.flight.quality.domain.FlightQualityIncidentSyncAction;
import com.visionflow.api.flight.quality.domain.FlightQualitySeverity;
import com.visionflow.api.flight.quality.dto.DroneReliabilityResponse;
import com.visionflow.api.flight.quality.dto.FlightQualityAssessmentResponse;
import com.visionflow.api.flight.quality.dto.FlightQualityMetricsResponse;
import com.visionflow.api.flight.quality.dto.FlightQualityRiskResponse;
import com.visionflow.api.incident.domain.Incident;
import com.visionflow.api.incident.domain.IncidentActionHistory;
import com.visionflow.api.incident.domain.IncidentPriority;
import com.visionflow.api.incident.domain.IncidentSourceType;
import com.visionflow.api.incident.domain.IncidentStatus;
import com.visionflow.api.incident.realtime.IncidentRealtimePublisher;
import com.visionflow.api.incident.repository.IncidentActionHistoryRepository;
import com.visionflow.api.incident.repository.IncidentRepository;
import com.visionflow.api.maintenance.service.MaintenanceWorkOrderService;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class FlightQualityIncidentAutomationServiceTests {

    private final FleetReliabilityService reliabilityService =
            mock(FleetReliabilityService.class);
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
    private final MaintenanceWorkOrderService maintenanceWorkOrderService =
            mock(MaintenanceWorkOrderService.class);
    private final FlightQualityIncidentAutomationService service =
            new FlightQualityIncidentAutomationService(
                    reliabilityService,
                    droneRepository,
                    incidentRepository,
                    historyRepository,
                    realtimePublisher,
                    auditLogService,
                    maintenanceWorkOrderService
            );

    @Test
    void createsOneIncidentWithDroneIdAsStableDeduplicationKey() {
        DroneReliabilityResponse reliability =
                reliability(FleetReliabilityStatus.CHECK, 52, 1);
        when(reliabilityService.summarizeDrone(1L, 20))
                .thenReturn(Optional.of(reliability));
        when(droneRepository.findByIdForUpdate(1L))
                .thenReturn(Optional.of(mock(Drone.class)));
        when(incidentRepository.findBySourceTypeAndSourceIdForUpdate(
                IncidentSourceType.FLIGHT_QUALITY,
                1L
        )).thenReturn(Optional.empty());
        when(incidentRepository.saveAndFlush(any(Incident.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));

        var result = service.synchronizeDrone(1L, 20);

        assertThat(result.action())
                .isEqualTo(FlightQualityIncidentSyncAction.CREATED);
        assertThat(result.incident().sourceType())
                .isEqualTo(IncidentSourceType.FLIGHT_QUALITY);
        assertThat(result.incident().sourceId()).isEqualTo(1L);
        assertThat(result.incident().priority())
                .isEqualTo(IncidentPriority.CRITICAL);
        verify(incidentRepository).saveAndFlush(any(Incident.class));
        verify(maintenanceWorkOrderService)
                .synchronizeRequired(any(Incident.class), any(Long.class));
    }

    @Test
    void updatesExistingActiveIncidentInsteadOfCreatingDuplicate() {
        DroneReliabilityResponse reliability =
                reliability(FleetReliabilityStatus.CHECK, 58, 0);
        Incident existing = incident(
                IncidentPriority.MEDIUM,
                IncidentStatus.OPEN
        );
        when(reliabilityService.summarizeDrone(1L, 20))
                .thenReturn(Optional.of(reliability));
        when(droneRepository.findByIdForUpdate(1L))
                .thenReturn(Optional.of(mock(Drone.class)));
        when(incidentRepository.findBySourceTypeAndSourceIdForUpdate(
                IncidentSourceType.FLIGHT_QUALITY,
                1L
        )).thenReturn(Optional.of(existing));
        when(incidentRepository.saveAndFlush(existing))
                .thenReturn(existing);

        var result = service.synchronizeDrone(1L, 20);

        assertThat(result.action())
                .isEqualTo(FlightQualityIncidentSyncAction.UPDATED);
        assertThat(result.incident().priority())
                .isEqualTo(IncidentPriority.HIGH);
        verify(incidentRepository).saveAndFlush(existing);
        verify(maintenanceWorkOrderService)
                .synchronizeRequired(existing, 100L);
    }

    @Test
    void stableReliabilityResolvesOpenIncident() {
        DroneReliabilityResponse reliability =
                reliability(FleetReliabilityStatus.STABLE, 92, 0);
        Incident existing = incident(
                IncidentPriority.HIGH,
                IncidentStatus.OPEN
        );
        when(reliabilityService.summarizeDrone(1L, 20))
                .thenReturn(Optional.of(reliability));
        when(droneRepository.findByIdForUpdate(1L))
                .thenReturn(Optional.of(mock(Drone.class)));
        when(incidentRepository.findBySourceTypeAndSourceIdForUpdate(
                IncidentSourceType.FLIGHT_QUALITY,
                1L
        )).thenReturn(Optional.of(existing));
        when(incidentRepository.saveAndFlush(existing))
                .thenReturn(existing);

        var result = service.synchronizeDrone(1L, 20);

        assertThat(result.action())
                .isEqualTo(FlightQualityIncidentSyncAction.RESOLVED);
        assertThat(result.incident().status())
                .isEqualTo(IncidentStatus.RESOLVED);
        verify(maintenanceWorkOrderService, never())
                .synchronizeRequired(any(Incident.class), any(Long.class));
    }

    @Test
    void stableReliabilityWithoutIncidentDoesNotWrite() {
        DroneReliabilityResponse reliability =
                reliability(FleetReliabilityStatus.STABLE, 95, 0);
        when(reliabilityService.summarizeDrone(1L, 20))
                .thenReturn(Optional.of(reliability));
        when(droneRepository.findByIdForUpdate(1L))
                .thenReturn(Optional.of(mock(Drone.class)));
        when(incidentRepository.findBySourceTypeAndSourceIdForUpdate(
                IncidentSourceType.FLIGHT_QUALITY,
                1L
        )).thenReturn(Optional.empty());

        var result = service.synchronizeDrone(1L, 20);

        assertThat(result.action())
                .isEqualTo(FlightQualityIncidentSyncAction.SKIPPED_STABLE);
        verify(incidentRepository, never())
                .saveAndFlush(any(Incident.class));
        verify(historyRepository, never())
                .saveAndFlush(any(IncidentActionHistory.class));
    }

    private Incident incident(
            IncidentPriority priority,
            IncidentStatus status
    ) {
        return Incident.create(
                IncidentSourceType.FLIGHT_QUALITY,
                1L,
                1L,
                "session-old",
                priority,
                status,
                "기체 신뢰도 점검",
                "기존 품질 상태",
                LocalDateTime.of(2026, 7, 25, 1, 0),
                status == IncidentStatus.RESOLVED
                        ? LocalDateTime.of(2026, 7, 25, 1, 5)
                        : null
        );
    }

    private DroneReliabilityResponse reliability(
            FleetReliabilityStatus status,
            int score,
            int criticalCount
    ) {
        FlightQualityRiskResponse risk = criticalCount > 0
                ? new FlightQualityRiskResponse(
                        FlightQualitySeverity.CRITICAL,
                        "비행 품질 위험",
                        "즉시 기체 점검이 필요합니다."
                )
                : status == FleetReliabilityStatus.WATCH
                ? new FlightQualityRiskResponse(
                        FlightQualitySeverity.WARNING,
                        "비행 품질 주의",
                        "추세 관찰이 필요합니다."
                )
                : null;
        FlightQualityAssessmentResponse assessment =
                new FlightQualityAssessmentResponse(
                        100L,
                        1L,
                        "session-new",
                        FlightSessionStatus.COMPLETED,
                        FlightQualityAssessmentService
                                .CURRENT_RULE_VERSION,
                        score,
                        score >= 90
                                ? FlightQualityGrade.EXCELLENT
                                : score >= 75
                                ? FlightQualityGrade.GOOD
                                : score >= 60
                                ? FlightQualityGrade.CAUTION
                                : FlightQualityGrade.RISK,
                        30,
                        20,
                        20,
                        status == FleetReliabilityStatus.WATCH ? 1 : 0,
                        criticalCount,
                        risk,
                        new FlightQualityMetricsResponse(
                                10,
                                10,
                                new BigDecimal("100.00"),
                                new BigDecimal("100.00"),
                                new BigDecimal("1.00"),
                                0,
                                0,
                                0,
                                70,
                                1,
                                1,
                                new BigDecimal("100.00"),
                                new BigDecimal("100.00")
                        ),
                        Instant.parse("2026-07-25T05:00:00Z")
                );
        return new DroneReliabilityResponse(
                1L,
                "DRONE-001",
                "Vision Eagle 1",
                "Custom Vision Drone",
                status,
                3,
                BigDecimal.valueOf(score),
                score,
                score,
                score + 1,
                3,
                0,
                300,
                criticalCount,
                status == FleetReliabilityStatus.WATCH ? 1 : 0,
                assessment,
                List.of()
        );
    }
}
