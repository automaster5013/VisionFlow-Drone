package com.visionflow.api.maintenance.service;

import com.visionflow.api.incident.domain.Incident;
import com.visionflow.api.incident.domain.IncidentActionHistory;
import com.visionflow.api.incident.domain.IncidentActionType;
import com.visionflow.api.incident.domain.IncidentPriority;
import com.visionflow.api.incident.domain.IncidentSourceType;
import com.visionflow.api.incident.domain.IncidentStatus;
import com.visionflow.api.incident.repository.IncidentActionHistoryRepository;
import com.visionflow.api.incident.repository.IncidentRepository;
import com.visionflow.api.maintenance.domain.FlightClearanceStatus;
import com.visionflow.api.maintenance.domain.MaintenanceCompletionDecision;
import com.visionflow.api.maintenance.domain.MaintenanceSlaClosureStatus;
import com.visionflow.api.maintenance.domain.MaintenanceSlaStatus;
import com.visionflow.api.maintenance.domain.MaintenanceSlaResponseStatus;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrder;
import com.visionflow.api.maintenance.dto.MaintenanceSlaIncidentTrackingResponse;
import com.visionflow.api.maintenance.repository.MaintenanceWorkOrderRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.util.ReflectionTestUtils;

import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class MaintenanceSlaIncidentTrackingServiceTests {

    @Mock
    private MaintenanceWorkOrderRepository workOrderRepository;

    @Mock
    private IncidentRepository incidentRepository;

    @Mock
    private IncidentActionHistoryRepository historyRepository;

    private MaintenanceSlaIncidentTrackingService service;

    @BeforeEach
    void setUp() {
        service = new MaintenanceSlaIncidentTrackingService(
                workOrderRepository,
                incidentRepository,
                historyRepository
        );
    }

    @Test
    void returnsLinkedEscalationEvidenceForOverdueWorkOrder() {
        LocalDateTime openedAt = LocalDateTime.now(ZoneOffset.UTC)
                .minusHours(3);
        MaintenanceWorkOrder workOrder = MaintenanceWorkOrder.open(
                201L,
                1L,
                "session-001",
                301L,
                openedAt
        );
        ReflectionTestUtils.setField(workOrder, "id", 101L);

        Incident incident = Incident.create(
                IncidentSourceType.FLIGHT_QUALITY,
                301L,
                1L,
                "session-001",
                IncidentPriority.CRITICAL,
                IncidentStatus.OPEN,
                "기체 품질 위험",
                "정비 점검 필요",
                openedAt,
                null
        );
        ReflectionTestUtils.setField(incident, "id", 201L);

        IncidentActionHistory escalation =
                IncidentActionHistory.create(
                        201L,
                        IncidentActionType.SLA_ESCALATED,
                        IncidentStatus.OPEN,
                        IncidentStatus.OPEN,
                        MaintenanceSlaIncidentEscalationService
                                .SYSTEM_ACTOR,
                        "정비 작업 SLA 초과"
                );
        ReflectionTestUtils.setField(
                escalation,
                "createdAt",
                openedAt.plusHours(2)
        );

        List<MaintenanceWorkOrder> workOrders = List.of(workOrder);
        List<Incident> incidents = List.of(incident);
        List<IncidentActionHistory> histories = List.of(escalation);
        when(
                workOrderRepository
                        .findAllByOpenedAtGreaterThanEqualOrderByOpenedAtDescIdDesc(
                                any(LocalDateTime.class)
                        )
        ).thenReturn(workOrders);
        when(incidentRepository.findAllById(any())).thenReturn(incidents);
        when(
                historyRepository
                        .findAllByIncidentIdOrderByCreatedAtAscIdAsc(201L)
        ).thenReturn(histories);

        MaintenanceSlaIncidentTrackingResponse response =
                service.getTracking(30);

        assertThat(response.totalWorkOrders()).isEqualTo(1);
        assertThat(response.connectedIncidents()).isEqualTo(1);
        assertThat(response.overdueWorkOrders()).isEqualTo(1);
        assertThat(response.escalatedIncidents()).isEqualTo(1);
        assertThat(response.assignmentRequiredIncidents()).isEqualTo(1);
        assertThat(response.inResponseIncidents()).isZero();
        assertThat(response.pendingWorkOrderClosures()).isZero();
        assertThat(response.returnToServiceConfirmed()).isZero();
        assertThat(response.groundedClosures()).isZero();
        assertThat(response.closureConsistencyAlerts()).isZero();
        assertThat(response.items()).singleElement().satisfies(item -> {
            assertThat(item.workOrderId()).isEqualTo(101L);
            assertThat(item.incidentId()).isEqualTo(201L);
            assertThat(item.slaStatus())
                    .isEqualTo(MaintenanceSlaStatus.OVERDUE);
            assertThat(item.incidentPriority())
                    .isEqualTo(IncidentPriority.CRITICAL);
            assertThat(item.escalated()).isTrue();
            assertThat(item.escalatedAt()).isNotNull();
            assertThat(item.responseStatus())
                    .isEqualTo(
                            MaintenanceSlaResponseStatus
                                    .ASSIGNMENT_REQUIRED
                    );
            assertThat(item.recommendedAction())
                    .contains("담당자를 지정");
            assertThat(item.flightClearanceStatus())
                    .isEqualTo(FlightClearanceStatus.PENDING_INSPECTION);
            assertThat(item.closureStatus())
                    .isEqualTo(
                            MaintenanceSlaClosureStatus.RESPONSE_ACTIVE
                    );
        });
    }

    @Test
    void resolvedIncidentRequiresPendingWorkOrderClosure() {
        LocalDateTime openedAt = LocalDateTime.now(ZoneOffset.UTC)
                .minusHours(2);
        MaintenanceWorkOrder workOrder = MaintenanceWorkOrder.open(
                202L,
                2L,
                "session-002",
                302L,
                openedAt
        );
        workOrder.startInspection(
                "demo-operator",
                openedAt.plusMinutes(10)
        );
        ReflectionTestUtils.setField(workOrder, "id", 102L);

        Incident incident = Incident.create(
                IncidentSourceType.FLIGHT_QUALITY,
                302L,
                2L,
                "session-002",
                IncidentPriority.HIGH,
                IncidentStatus.RESOLVED,
                "정비 조치 완료",
                "Incident 해결 후 작업 마감 대기",
                openedAt,
                null
        );
        ReflectionTestUtils.setField(incident, "id", 202L);

        when(
                workOrderRepository
                        .findAllByOpenedAtGreaterThanEqualOrderByOpenedAtDescIdDesc(
                                any(LocalDateTime.class)
                        )
        ).thenReturn(List.of(workOrder));
        when(incidentRepository.findAllById(any()))
                .thenReturn(List.of(incident));
        when(
                historyRepository
                        .findAllByIncidentIdOrderByCreatedAtAscIdAsc(202L)
        ).thenReturn(List.of());

        MaintenanceSlaIncidentTrackingResponse response =
                service.getTracking(30);

        assertThat(response.pendingWorkOrderClosures()).isEqualTo(1);
        assertThat(response.returnToServiceConfirmed()).isZero();
        assertThat(response.closureConsistencyAlerts()).isZero();
        assertThat(response.items()).singleElement().satisfies(item -> {
            assertThat(item.closureStatus())
                    .isEqualTo(
                            MaintenanceSlaClosureStatus
                                    .WORK_ORDER_PENDING
                    );
            assertThat(item.closureRecommendedAction())
                    .contains("정비 작업을 마감");
        });
    }

    @Test
    void resolvedIncidentAndClearedWorkOrderAreConfirmed() {
        LocalDateTime openedAt = LocalDateTime.now(ZoneOffset.UTC)
                .minusHours(2);
        MaintenanceWorkOrder workOrder = MaintenanceWorkOrder.open(
                203L,
                3L,
                "session-003",
                303L,
                openedAt
        );
        workOrder.startInspection(
                "demo-operator",
                openedAt.plusMinutes(10)
        );
        workOrder.complete(
                MaintenanceCompletionDecision.RETURN_TO_SERVICE,
                "기체 점검 정상",
                "재시험 통과",
                openedAt.plusHours(1)
        );
        ReflectionTestUtils.setField(workOrder, "id", 103L);

        Incident incident = Incident.create(
                IncidentSourceType.FLIGHT_QUALITY,
                303L,
                3L,
                "session-003",
                IncidentPriority.MEDIUM,
                IncidentStatus.RESOLVED,
                "정비 및 재운항 승인",
                "정상 마감",
                openedAt,
                null
        );
        ReflectionTestUtils.setField(incident, "id", 203L);

        when(
                workOrderRepository
                        .findAllByOpenedAtGreaterThanEqualOrderByOpenedAtDescIdDesc(
                                any(LocalDateTime.class)
                        )
        ).thenReturn(List.of(workOrder));
        when(incidentRepository.findAllById(any()))
                .thenReturn(List.of(incident));
        when(
                historyRepository
                        .findAllByIncidentIdOrderByCreatedAtAscIdAsc(203L)
        ).thenReturn(List.of());

        MaintenanceSlaIncidentTrackingResponse response =
                service.getTracking(30);

        assertThat(response.returnToServiceConfirmed()).isEqualTo(1);
        assertThat(response.pendingWorkOrderClosures()).isZero();
        assertThat(response.closureConsistencyAlerts()).isZero();
        assertThat(response.items()).singleElement().satisfies(item -> {
            assertThat(item.flightClearanceStatus())
                    .isEqualTo(FlightClearanceStatus.CLEARED);
            assertThat(item.closureStatus())
                    .isEqualTo(
                            MaintenanceSlaClosureStatus
                                    .RETURN_TO_SERVICE_CONFIRMED
                    );
        });
    }

    @Test
    void activeIncidentWithClearedWorkOrderRequiresReview() {
        LocalDateTime openedAt = LocalDateTime.now(ZoneOffset.UTC)
                .minusHours(2);
        MaintenanceWorkOrder workOrder = MaintenanceWorkOrder.open(
                204L,
                4L,
                "session-004",
                304L,
                openedAt
        );
        workOrder.startInspection(
                "demo-operator",
                openedAt.plusMinutes(10)
        );
        workOrder.complete(
                MaintenanceCompletionDecision.RETURN_TO_SERVICE,
                "기체 점검 정상",
                "재시험 통과",
                openedAt.plusHours(1)
        );
        ReflectionTestUtils.setField(workOrder, "id", 104L);

        Incident incident = Incident.create(
                IncidentSourceType.FLIGHT_QUALITY,
                304L,
                4L,
                "session-004",
                IncidentPriority.HIGH,
                IncidentStatus.IN_PROGRESS,
                "Incident 상태 불일치",
                "작업은 완료됐지만 Incident가 활성 상태",
                openedAt,
                null
        );
        ReflectionTestUtils.setField(incident, "id", 204L);

        when(
                workOrderRepository
                        .findAllByOpenedAtGreaterThanEqualOrderByOpenedAtDescIdDesc(
                                any(LocalDateTime.class)
                        )
        ).thenReturn(List.of(workOrder));
        when(incidentRepository.findAllById(any()))
                .thenReturn(List.of(incident));
        when(
                historyRepository
                        .findAllByIncidentIdOrderByCreatedAtAscIdAsc(204L)
        ).thenReturn(List.of());

        MaintenanceSlaIncidentTrackingResponse response =
                service.getTracking(30);

        assertThat(response.closureConsistencyAlerts()).isEqualTo(1);
        assertThat(response.items()).singleElement().satisfies(item -> {
            assertThat(item.closureStatus())
                    .isEqualTo(
                            MaintenanceSlaClosureStatus.REVIEW_REQUIRED
                    );
            assertThat(item.closureRecommendedAction())
                    .contains("수동 점검");
        });
    }

    @Test
    void rejectsWindowOutsideSupportedRange() {
        assertThatThrownBy(() -> service.getTracking(0))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("1~90일");

        verifyNoInteractions(
                workOrderRepository,
                incidentRepository,
                historyRepository
        );
    }
}
