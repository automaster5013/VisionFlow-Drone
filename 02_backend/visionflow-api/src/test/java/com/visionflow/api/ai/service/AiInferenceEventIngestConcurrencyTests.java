package com.visionflow.api.ai.service;

import com.visionflow.api.ai.domain.AiInferenceEvent;
import com.visionflow.api.ai.domain.VideoSourceType;
import com.visionflow.api.ai.dto.AiInferenceEventCreateRequest;
import com.visionflow.api.ai.dto.AiInferenceEventResponse;
import com.visionflow.api.ai.realtime.AiRealtimePublisher;
import com.visionflow.api.ai.repository.AiDetectionRepository;
import com.visionflow.api.ai.repository.AiInferenceEventRepository;
import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.flight.domain.FlightSession;
import com.visionflow.api.flight.repository.FlightSessionRepository;
import com.visionflow.api.flight.service.FlightSessionCorrelationGuard;
import jakarta.persistence.LockModeType;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.InOrder;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.test.util.ReflectionTestUtils;

import java.lang.reflect.Method;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AiInferenceEventIngestConcurrencyTests {

    private final AiInferenceEventRepository eventRepository =
            mock(AiInferenceEventRepository.class);
    private final AiDetectionRepository detectionRepository =
            mock(AiDetectionRepository.class);
    private final DroneRepository droneRepository =
            mock(DroneRepository.class);
    private final FlightSessionCorrelationGuard correlationGuard =
            mock(FlightSessionCorrelationGuard.class);
    private final AiRealtimePublisher realtimePublisher =
            mock(AiRealtimePublisher.class);
    private final AiSnapshotStorageService snapshotStorageService =
            mock(AiSnapshotStorageService.class);
    private final AiAlertService alertService =
            mock(AiAlertService.class);

    private AiInferenceEventService service;

    @BeforeEach
    void setUp() {
        service = new AiInferenceEventService(
                eventRepository,
                detectionRepository,
                droneRepository,
                correlationGuard,
                realtimePublisher,
                snapshotStorageService,
                alertService
        );
    }

    @Test
    void sessionMutationLookupUsesPessimisticWriteLock()
            throws NoSuchMethodException {
        Method method = FlightSessionRepository.class.getMethod(
                "findBySessionIdAndDroneIdForUpdate",
                String.class,
                Long.class
        );

        Lock lock = method.getAnnotation(Lock.class);

        assertThat(lock).isNotNull();
        assertThat(lock.value()).isEqualTo(
                LockModeType.PESSIMISTIC_WRITE
        );
    }

    @Test
    void correlationGuardLocksOwnedSessionForEventCreation() {
        FlightSessionRepository sessionRepository =
                mock(FlightSessionRepository.class);
        FlightSessionCorrelationGuard guard =
                new FlightSessionCorrelationGuard(sessionRepository);
        FlightSession session = FlightSession.start(
                "session-1",
                7L,
                "test session",
                null,
                "test-device",
                LocalDateTime.of(2026, 8, 4, 3, 0)
        );
        when(sessionRepository.findBySessionIdAndDroneIdForUpdate(
                "session-1",
                7L
        )).thenReturn(Optional.of(session));

        String result = guard.requireOwnedSessionForUpdate(
                "  session-1  ",
                7L
        );

        assertThat(result).isEqualTo("session-1");
        verify(sessionRepository)
                .findBySessionIdAndDroneIdForUpdate(
                        "session-1",
                        7L
                );
        verify(sessionRepository, never()).findById("session-1");
    }

    @Test
    void createLocksSessionBeforeIdempotencyLookupAndInsert() {
        AiInferenceEventCreateRequest request = request();
        when(correlationGuard.requireOwnedSessionForUpdate(
                "session-1",
                7L
        )).thenReturn("session-1");
        when(eventRepository.findBySourceIdAndSessionIdAndFrameIndex(
                "source-1",
                "session-1",
                1L
        )).thenReturn(Optional.empty());
        when(droneRepository.existsById(7L)).thenReturn(true);
        when(eventRepository.saveAndFlush(
                any(AiInferenceEvent.class)
        )).thenAnswer(invocation -> {
            AiInferenceEvent event = invocation.getArgument(0);
            ReflectionTestUtils.setField(event, "id", 201L);
            return event;
        });

        AiInferenceEventResponse response = service.create(request);

        InOrder order = inOrder(
                correlationGuard,
                eventRepository,
                droneRepository
        );
        order.verify(correlationGuard)
                .requireOwnedSessionForUpdate("session-1", 7L);
        order.verify(eventRepository)
                .findBySourceIdAndSessionIdAndFrameIndex(
                        "source-1",
                        "session-1",
                        1L
                );
        order.verify(droneRepository).existsById(7L);
        order.verify(eventRepository)
                .saveAndFlush(any(AiInferenceEvent.class));
        verify(correlationGuard, never())
                .requireOwnedSession("session-1", 7L);
        assertThat(response.id()).isEqualTo(201L);
    }

    @Test
    void duplicateFrameReturnsExistingEventWithoutSecondInsert() {
        AiInferenceEvent existing = event(202L);
        when(correlationGuard.requireOwnedSessionForUpdate(
                "session-1",
                7L
        )).thenReturn("session-1");
        when(eventRepository.findBySourceIdAndSessionIdAndFrameIndex(
                "source-1",
                "session-1",
                1L
        )).thenReturn(Optional.of(existing));
        when(detectionRepository.findAllByEventIdOrderByIdAsc(202L))
                .thenReturn(List.of());

        AiInferenceEventResponse response = service.create(request());

        assertThat(response.id()).isEqualTo(202L);
        verify(droneRepository, never()).existsById(7L);
        verify(eventRepository, never()).saveAndFlush(
                any(AiInferenceEvent.class)
        );
    }

    private AiInferenceEventCreateRequest request() {
        return new AiInferenceEventCreateRequest(
                "source-1",
                "session-1",
                VideoSourceType.SMARTPHONE_LIVE,
                7L,
                1L,
                Instant.parse("2026-08-04T03:00:00Z"),
                BigDecimal.ONE,
                0,
                List.of()
        );
    }

    private AiInferenceEvent event(Long id) {
        AiInferenceEvent event = AiInferenceEvent.create(
                "source-1",
                "session-1",
                VideoSourceType.SMARTPHONE_LIVE,
                7L,
                1L,
                Instant.parse("2026-08-04T03:00:00Z"),
                BigDecimal.ONE,
                0
        );
        ReflectionTestUtils.setField(event, "id", id);
        return event;
    }
}
