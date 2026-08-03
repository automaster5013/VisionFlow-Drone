package com.visionflow.api.ai.service;

import com.visionflow.api.ai.domain.AiInferenceEvent;
import com.visionflow.api.ai.domain.VideoSourceType;
import com.visionflow.api.ai.dto.AiInferenceEventResponse;
import com.visionflow.api.ai.realtime.AiRealtimePublisher;
import com.visionflow.api.ai.repository.AiDetectionRepository;
import com.visionflow.api.ai.repository.AiInferenceEventRepository;
import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.flight.service.FlightSessionCorrelationGuard;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.Resource;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.multipart.MultipartFile;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AiInferenceEventServiceConcurrencyTests {

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
    void snapshotAttachmentUsesWriteLockBeforeStorageAndPersistence() {
        AiInferenceEvent event = event(101L);
        MultipartFile file = mock(MultipartFile.class);
        AiSnapshotStorageService.StoredSnapshot stored =
                new AiSnapshotStorageService.StoredSnapshot(
                        "event-101.jpg",
                        "image/jpeg",
                        4L
                );
        when(eventRepository.findByIdForUpdate(101L))
                .thenReturn(Optional.of(event));
        when(snapshotStorageService.store(101L, file))
                .thenReturn(stored);
        when(eventRepository.saveAndFlush(event)).thenReturn(event);
        when(detectionRepository.findAllByEventIdOrderByIdAsc(101L))
                .thenReturn(List.of());

        AiInferenceEventResponse response = service.attachSnapshot(
                101L,
                file
        );

        var ordered = inOrder(
                eventRepository,
                snapshotStorageService
        );
        ordered.verify(eventRepository).findByIdForUpdate(101L);
        ordered.verify(snapshotStorageService).store(101L, file);
        ordered.verify(eventRepository).saveAndFlush(event);
        verify(eventRepository, never()).findById(101L);
        assertThat(response.snapshotAvailable()).isTrue();
        assertThat(response.snapshotSizeBytes()).isEqualTo(4L);
    }

    @Test
    void snapshotReadKeepsNonLockingLookup() {
        AiInferenceEvent event = event(102L);
        event.attachSnapshot("event-102.jpg", "image/jpeg", 8L);
        Resource resource = mock(Resource.class);
        when(eventRepository.findById(102L))
                .thenReturn(Optional.of(event));
        when(snapshotStorageService.load("event-102.jpg"))
                .thenReturn(resource);

        AiInferenceEventService.AiSnapshotDownload result =
                service.findSnapshot(102L);

        assertThat(result.resource()).isSameAs(resource);
        verify(eventRepository).findById(102L);
        verify(eventRepository, never()).findByIdForUpdate(102L);
    }

    private AiInferenceEvent event(Long id) {
        AiInferenceEvent event = AiInferenceEvent.create(
                "source-1",
                "session-1",
                VideoSourceType.SMARTPHONE_LIVE,
                7L,
                1L,
                Instant.parse("2026-08-03T12:00:00Z"),
                BigDecimal.ONE,
                0
        );
        ReflectionTestUtils.setField(event, "id", id);
        return event;
    }
}
