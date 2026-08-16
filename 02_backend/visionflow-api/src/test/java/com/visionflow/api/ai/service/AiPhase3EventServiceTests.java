package com.visionflow.api.ai.service;

import com.visionflow.api.ai.domain.AiPhase3Event;
import com.visionflow.api.ai.domain.VideoSourceType;
import com.visionflow.api.ai.dto.AiPhase3DepthUpdateRequest;
import com.visionflow.api.ai.dto.AiPhase3EventCreateRequest;
import com.visionflow.api.ai.dto.AiPhase3EventResponse;
import com.visionflow.api.ai.repository.AiPhase3EventRepository;
import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.flight.service.FlightSessionCorrelationGuard;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AiPhase3EventServiceTests {

    private final AiPhase3EventRepository eventRepository =
            mock(AiPhase3EventRepository.class);

    private final DroneRepository droneRepository =
            mock(DroneRepository.class);

    private final FlightSessionCorrelationGuard sessionCorrelationGuard =
            mock(FlightSessionCorrelationGuard.class);

    private final AiPhase3EventService service =
            new AiPhase3EventService(
                    eventRepository,
                    droneRepository,
                    sessionCorrelationGuard
            );

    @Test
    void createPersistsPhase3PpeEvent() {
        AiPhase3EventCreateRequest request =
                new AiPhase3EventCreateRequest(
                        "source-1:session-1:NO_HELMET:7",
                        "source-1",
                        "session-1",
                        VideoSourceType.DUMMY_VIDEO,
                        1L,
                        7L,
                        28L,
                        Instant.parse("2026-08-16T09:00:00Z"),
                        "CONFIRMED_NO_HELMET",
                        new BigDecimal("1.000000"),
                        new BigDecimal("0.000000"),
                        new BigDecimal("0.000000"),
                        new BigDecimal("0.900")
                );

        when(sessionCorrelationGuard.requireOwnedSessionForUpdate(
                "session-1",
                1L
        )).thenReturn("session-1");

        when(eventRepository.findByEventKey(
                "source-1:session-1:NO_HELMET:7"
        )).thenReturn(Optional.empty());

        when(droneRepository.existsById(1L)).thenReturn(true);

        when(eventRepository.saveAndFlush(any(AiPhase3Event.class)))
                .thenAnswer(invocation -> {
                    AiPhase3Event event = invocation.getArgument(0);
                    ReflectionTestUtils.setField(event, "id", 101L);
                    return event;
                });

        AiPhase3EventResponse response = service.create(request);

        assertThat(response.id()).isEqualTo(101L);
        assertThat(response.eventKey())
                .isEqualTo("source-1:session-1:NO_HELMET:7");
        assertThat(response.trackId()).isEqualTo(7L);
        assertThat(response.frameIndex()).isEqualTo(28L);
        assertThat(response.ppeState())
                .isEqualTo("CONFIRMED_NO_HELMET");
        assertThat(response.estimatedDepthM()).isNull();

        verify(eventRepository).saveAndFlush(any(AiPhase3Event.class));
    }

    @Test
    void enrichDepthUpdatesExistingPhase3Event() {
        AiPhase3Event event = AiPhase3Event.create(
                "source-1:session-1:NO_HELMET:7",
                "source-1",
                "session-1",
                VideoSourceType.DUMMY_VIDEO,
                1L,
                7L,
                28L,
                Instant.parse("2026-08-16T09:00:00Z"),
                "CONFIRMED_NO_HELMET",
                new BigDecimal("1.000000"),
                new BigDecimal("0.000000"),
                new BigDecimal("0.000000"),
                new BigDecimal("0.900")
        );

        ReflectionTestUtils.setField(event, "id", 101L);

        when(eventRepository.findByEventKeyForUpdate(
                "source-1:session-1:NO_HELMET:7"
        )).thenReturn(Optional.of(event));

        when(eventRepository.saveAndFlush(event)).thenReturn(event);

        AiPhase3DepthUpdateRequest request =
                new AiPhase3DepthUpdateRequest(
                        new BigDecimal("1.844"),
                        new BigDecimal("1.648"),
                        new BigDecimal("2.170"),
                        "MID",
                        new BigDecimal("66.44")
                );

        AiPhase3EventResponse response = service.enrichDepth(
                "source-1:session-1:NO_HELMET:7",
                request
        );

        assertThat(response.estimatedDepthM())
                .isEqualByComparingTo("1.844");
        assertThat(response.sceneQ33M())
                .isEqualByComparingTo("1.648");
        assertThat(response.sceneQ66M())
                .isEqualByComparingTo("2.170");
        assertThat(response.depthBucket()).isEqualTo("MID");
        assertThat(response.enrichmentLatencyMs())
                .isEqualByComparingTo("66.44");

        verify(eventRepository).findByEventKeyForUpdate(
                "source-1:session-1:NO_HELMET:7"
        );
        verify(eventRepository).saveAndFlush(event);
    }
}