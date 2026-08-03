package com.visionflow.api.ai.service;

import com.visionflow.api.ai.domain.VideoSourceType;
import com.visionflow.api.ai.dto.AiInferenceEventCreateRequest;
import com.visionflow.api.ai.realtime.AiRealtimePublisher;
import com.visionflow.api.ai.repository.AiDetectionRepository;
import com.visionflow.api.ai.repository.AiInferenceEventRepository;
import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.flight.exception.FlightSessionDroneMismatchException;
import com.visionflow.api.flight.service.FlightSessionCorrelationGuard;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AiInferenceEventServiceCorrelationTests {

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
    void rejectsMismatchedSessionBeforeIdempotencyLookupOrPersistence() {
        AiInferenceEventCreateRequest request = request();
        when(correlationGuard.requireOwnedSessionForUpdate(
                "session-1",
                7L
        ))
                .thenThrow(new FlightSessionDroneMismatchException(
                        "mismatch"
                ));

        assertThatThrownBy(() -> service.create(request))
                .isInstanceOf(FlightSessionDroneMismatchException.class);

        verify(eventRepository, never())
                .findBySourceIdAndSessionIdAndFrameIndex(
                        "source-1",
                        "session-1",
                        1L
                );
        verify(droneRepository, never()).existsById(7L);
    }

    private AiInferenceEventCreateRequest request() {
        return new AiInferenceEventCreateRequest(
                "source-1",
                "session-1",
                VideoSourceType.SMARTPHONE_LIVE,
                7L,
                1L,
                Instant.parse("2026-08-02T12:00:00Z"),
                BigDecimal.ONE,
                0,
                List.of()
        );
    }
}
