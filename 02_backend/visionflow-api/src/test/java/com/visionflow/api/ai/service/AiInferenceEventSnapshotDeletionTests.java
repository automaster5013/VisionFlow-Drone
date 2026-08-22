package com.visionflow.api.ai.service;

import com.visionflow.api.ai.domain.AiInferenceEvent;
import com.visionflow.api.ai.domain.VideoSourceType;
import com.visionflow.api.ai.realtime.AiRealtimePublisher;
import com.visionflow.api.ai.repository.AiDetectionRepository;
import com.visionflow.api.ai.repository.AiInferenceEventRepository;
import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.flight.service.FlightSessionCorrelationGuard;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AiInferenceEventSnapshotDeletionTests {
    private final AiInferenceEventRepository eventRepository = mock(AiInferenceEventRepository.class);
    private final AiDetectionRepository detectionRepository = mock(AiDetectionRepository.class);
    private final DroneRepository droneRepository = mock(DroneRepository.class);
    private final FlightSessionCorrelationGuard correlationGuard = mock(FlightSessionCorrelationGuard.class);
    private final AiRealtimePublisher realtimePublisher = mock(AiRealtimePublisher.class);
    private final AiSnapshotStorageService snapshotStorageService = mock(AiSnapshotStorageService.class);
    private final AiAlertService alertService = mock(AiAlertService.class);
    private AiInferenceEventService service;

    @BeforeEach
    void setUp() {
        service = new AiInferenceEventService(
                eventRepository, detectionRepository, droneRepository,
                correlationGuard, realtimePublisher, snapshotStorageService, alertService
        );
    }

    @Test
    void deletesPhysicalSnapshotAndClearsMetadataWithoutDeletingEvent() {
        AiInferenceEvent event = event(42L);
        event.attachSnapshot("event-42.jpg", "image/jpeg", 1234L);
        when(eventRepository.findByIdForUpdate(42L)).thenReturn(Optional.of(event));
        when(snapshotStorageService.delete("event-42.jpg")).thenReturn(true);
        when(eventRepository.saveAndFlush(event)).thenReturn(event);
        when(detectionRepository.findAllByEventIdOrderByIdAsc(42L)).thenReturn(List.of());

        var result = service.deleteSnapshot(42L);

        assertThat(result.snapshotExisted()).isTrue();
        assertThat(result.physicalFileDeleted()).isTrue();
        assertThat(result.snapshotSizeBytes()).isEqualTo(1234L);
        assertThat(event.getSnapshotFileName()).isNull();
        assertThat(event.getSnapshotContentType()).isNull();
        assertThat(event.getSnapshotSizeBytes()).isNull();
        assertThat(event.getSnapshotCreatedAt()).isNull();
        verify(snapshotStorageService).delete("event-42.jpg");
        verify(eventRepository).saveAndFlush(event);
    }

    @Test
    void repeatedDeleteIsIdempotentWhenSnapshotMetadataIsAlreadyAbsent() {
        AiInferenceEvent event = event(43L);
        when(eventRepository.findByIdForUpdate(43L)).thenReturn(Optional.of(event));

        var result = service.deleteSnapshot(43L);

        assertThat(result.snapshotExisted()).isFalse();
        assertThat(result.physicalFileDeleted()).isFalse();
        assertThat(result.snapshotSizeBytes()).isZero();
        verify(snapshotStorageService, never()).delete(org.mockito.ArgumentMatchers.anyString());
        verify(eventRepository, never()).saveAndFlush(event);
    }

    private AiInferenceEvent event(Long id) {
        AiInferenceEvent event = AiInferenceEvent.create(
                "privacy-test-source", "privacy-test-session",
                VideoSourceType.SMARTPHONE_LIVE, 1L, id,
                Instant.parse("2026-08-22T00:00:00Z"), BigDecimal.ONE, 0
        );
        ReflectionTestUtils.setField(event, "id", id);
        return event;
    }
}
