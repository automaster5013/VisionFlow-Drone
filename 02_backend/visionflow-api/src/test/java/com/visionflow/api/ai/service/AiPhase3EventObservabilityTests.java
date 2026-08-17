package com.visionflow.api.ai.service;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import com.visionflow.api.ai.domain.AiPhase3Event;
import com.visionflow.api.ai.domain.VideoSourceType;
import com.visionflow.api.ai.dto.AiPhase3DepthUpdateRequest;
import com.visionflow.api.ai.dto.AiPhase3EventCreateRequest;
import com.visionflow.api.ai.repository.AiPhase3EventRepository;
import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.flight.service.FlightSessionCorrelationGuard;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.springframework.test.util.ReflectionTestUtils;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class AiPhase3EventObservabilityTests {

    private static final String EVENT_KEY =
            "source-1:session-1:NO_HELMET:7";

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

    private final Logger serviceLogger =
            (Logger) LoggerFactory.getLogger(
                    AiPhase3EventService.class
            );

    private final ListAppender<ILoggingEvent> logAppender =
            new ListAppender<>();

    @BeforeEach
    void attachLogAppender() {
        logAppender.start();
        serviceLogger.addAppender(logAppender);
    }

    @AfterEach
    void detachLogAppender() {
        serviceLogger.detachAppender(logAppender);
        logAppender.stop();
    }

    @Test
    void createEmitsStructuredIngestLog() {
        AiPhase3EventCreateRequest request =
                new AiPhase3EventCreateRequest(
                        EVENT_KEY,
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
        when(eventRepository.findByEventKey(EVENT_KEY))
                .thenReturn(Optional.empty());
        when(droneRepository.existsById(1L)).thenReturn(true);
        when(eventRepository.saveAndFlush(any(AiPhase3Event.class)))
                .thenAnswer(invocation -> {
                    AiPhase3Event event = invocation.getArgument(0);
                    ReflectionTestUtils.setField(event, "id", 101L);
                    return event;
                });

        service.create(request);

        assertThat(logAppender.list)
                .extracting(ILoggingEvent::getFormattedMessage)
                .anySatisfy(message -> assertThat(message)
                        .contains("VISIONFLOW_PHASE3_EVENT_INGEST")
                        .contains("outcome=created")
                        .contains("eventKey=\"" + EVENT_KEY + "\"")
                        .contains("eventId=101")
                        .contains("droneId=1")
                        .contains("ppeState=\"CONFIRMED_NO_HELMET\"")
                );
    }

    @Test
    void enrichDepthEmitsStructuredEnrichmentLog() {
        AiPhase3Event event = AiPhase3Event.create(
                EVENT_KEY,
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

        when(eventRepository.findByEventKeyForUpdate(EVENT_KEY))
                .thenReturn(Optional.of(event));
        when(eventRepository.saveAndFlush(event)).thenReturn(event);

        service.enrichDepth(
                EVENT_KEY,
                new AiPhase3DepthUpdateRequest(
                        new BigDecimal("1.844"),
                        new BigDecimal("1.648"),
                        new BigDecimal("2.170"),
                        "MID",
                        new BigDecimal("66.44")
                )
        );

        assertThat(logAppender.list)
                .extracting(ILoggingEvent::getFormattedMessage)
                .anySatisfy(message -> assertThat(message)
                        .contains("VISIONFLOW_PHASE3_DEPTH_ENRICH")
                        .contains("outcome=updated")
                        .contains("eventKey=\"" + EVENT_KEY + "\"")
                        .contains("depthBucket=\"MID\"")
                        .contains("estimatedDepthM=1.844")
                        .contains("enrichmentLatencyMs=66.44")
                );
    }
}
