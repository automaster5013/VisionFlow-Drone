package com.visionflow.api.demo.service;

import com.visionflow.api.ai.domain.AiAlert;
import com.visionflow.api.ai.domain.VideoSourceType;
import com.visionflow.api.ai.dto.AiInferenceEventResponse;
import com.visionflow.api.ai.repository.AiAlertRepository;
import com.visionflow.api.ai.service.AiAlertService;
import com.visionflow.api.ai.service.AiInferenceEventService;
import com.visionflow.api.demo.domain.DemoScenario;
import com.visionflow.api.demo.domain.DemoScenarioStage;
import com.visionflow.api.demo.repository.DemoScenarioRepository;
import com.visionflow.api.drone.service.DroneService;
import com.visionflow.api.flight.service.FlightSessionManagementService;
import com.visionflow.api.incident.domain.Incident;
import com.visionflow.api.incident.repository.IncidentRepository;
import com.visionflow.api.incident.service.IncidentContextService;
import com.visionflow.api.incident.service.IncidentSlaEscalationService;
import org.junit.jupiter.api.Test;
import org.mockito.InOrder;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.List;
import java.util.Optional;

import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class DemoScenarioServiceConcurrencyTests {

    private final DemoScenarioRepository scenarioRepository =
            mock(DemoScenarioRepository.class);
    private final FlightSessionManagementService flightSessionService =
            mock(FlightSessionManagementService.class);
    private final DroneService droneService = mock(DroneService.class);
    private final AiInferenceEventService inferenceEventService =
            mock(AiInferenceEventService.class);
    private final AiAlertService alertService =
            mock(AiAlertService.class);
    private final AiAlertRepository alertRepository =
            mock(AiAlertRepository.class);
    private final IncidentRepository incidentRepository =
            mock(IncidentRepository.class);
    private final IncidentContextService incidentContextService =
            mock(IncidentContextService.class);
    private final IncidentSlaEscalationService escalationService =
            mock(IncidentSlaEscalationService.class);
    private final JdbcTemplate jdbcTemplate = mock(JdbcTemplate.class);
    private final DemoScenarioService service = new DemoScenarioService(
            scenarioRepository,
            flightSessionService,
            droneService,
            inferenceEventService,
            alertService,
            alertRepository,
            incidentRepository,
            incidentContextService,
            escalationService,
            jdbcTemplate
    );

    @Test
    void detectLocksScenarioBeforeCreatingAiChain() {
        DemoScenario scenario = scenario("demo-detect");
        AiAlert alert = mock(AiAlert.class);
        Incident incident = mock(Incident.class);
        when(scenarioRepository.findByIdForUpdate("demo-detect"))
                .thenReturn(Optional.of(scenario));
        when(inferenceEventService.create(org.mockito.ArgumentMatchers.any()))
                .thenReturn(eventResponse(201L));
        when(alertRepository.findByEventId(201L))
                .thenReturn(Optional.of(alert));
        when(alert.getId()).thenReturn(301L);
        when(incidentRepository.findBySourceTypeAndSourceId(
                org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.eq(301L)
        )).thenReturn(Optional.of(incident));
        when(incident.getId()).thenReturn(401L);
        when(incidentRepository.findById(401L))
                .thenReturn(Optional.of(incident));
        when(scenarioRepository.saveAndFlush(scenario))
                .thenReturn(scenario);

        service.detect(" demo-detect ");

        InOrder order = inOrder(
                scenarioRepository,
                inferenceEventService
        );
        order.verify(scenarioRepository)
                .findByIdForUpdate("demo-detect");
        order.verify(inferenceEventService)
                .create(org.mockito.ArgumentMatchers.any());
        verify(scenarioRepository, never()).findById("demo-detect");
    }

    @Test
    void resolveLocksScenarioBeforeAlertMutation() {
        DemoScenario scenario = scenario("demo-resolve");
        ReflectionTestUtils.setField(
                scenario,
                "stage",
                DemoScenarioStage.ESCALATED
        );
        ReflectionTestUtils.setField(scenario, "aiAlertId", 302L);
        when(scenarioRepository.findByIdForUpdate("demo-resolve"))
                .thenReturn(Optional.of(scenario));
        when(scenarioRepository.saveAndFlush(scenario))
                .thenReturn(scenario);

        service.resolve("demo-resolve");

        InOrder order = inOrder(scenarioRepository, alertService);
        order.verify(scenarioRepository)
                .findByIdForUpdate("demo-resolve");
        order.verify(alertService).resolve(
                302L,
                "visionflow-demo-operator",
                "발표 시연 대응 완료"
        );
        verify(scenarioRepository, never()).findById("demo-resolve");
    }

    @Test
    void completeLocksScenarioBeforeFlightSessionMutation() {
        DemoScenario scenario = scenario("demo-complete");
        ReflectionTestUtils.setField(
                scenario,
                "stage",
                DemoScenarioStage.RESOLVED
        );
        when(scenarioRepository.findByIdForUpdate("demo-complete"))
                .thenReturn(Optional.of(scenario));
        when(scenarioRepository.saveAndFlush(scenario))
                .thenReturn(scenario);

        service.complete("demo-complete");

        InOrder order = inOrder(
                scenarioRepository,
                flightSessionService
        );
        order.verify(scenarioRepository)
                .findByIdForUpdate("demo-complete");
        order.verify(flightSessionService).complete(
                7L,
                "session-demo"
        );
        verify(scenarioRepository, never()).findById("demo-complete");
    }

    @Test
    void readOnlyFindKeepsNonLockingLookup() {
        DemoScenario scenario = scenario("demo-read");
        when(scenarioRepository.findById("demo-read"))
                .thenReturn(Optional.of(scenario));

        service.find(" demo-read ");

        verify(scenarioRepository).findById("demo-read");
        verify(scenarioRepository, never())
                .findByIdForUpdate("demo-read");
    }

    private DemoScenario scenario(String scenarioId) {
        return DemoScenario.start(
                scenarioId,
                7L,
                "session-demo"
        );
    }

    private AiInferenceEventResponse eventResponse(Long id) {
        return new AiInferenceEventResponse(
                id,
                "demo-source",
                "session-demo",
                VideoSourceType.DUMMY_VIDEO,
                7L,
                0L,
                null,
                null,
                null,
                1,
                false,
                null,
                null,
                null,
                List.of()
        );
    }
}
