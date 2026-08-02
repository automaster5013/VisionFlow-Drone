package com.visionflow.api.ai.service;

import com.visionflow.api.ai.domain.AiAlert;
import com.visionflow.api.ai.domain.AiAlertSeverity;
import com.visionflow.api.ai.domain.AiInferenceEvent;
import com.visionflow.api.ai.domain.VideoSourceType;
import com.visionflow.api.ai.realtime.AiAlertRealtimePublisher;
import com.visionflow.api.ai.repository.AiAlertRepository;
import com.visionflow.api.ai.repository.AiDetectionRepository;
import com.visionflow.api.ai.repository.AiInferenceEventRepository;
import com.visionflow.api.incident.service.IncidentService;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AiAlertServiceConcurrencyTests {

    private final AiAlertRepository alertRepository =
            mock(AiAlertRepository.class);
    private final AiInferenceEventRepository eventRepository =
            mock(AiInferenceEventRepository.class);
    private final AiDetectionRepository detectionRepository =
            mock(AiDetectionRepository.class);
    private final AiAlertRiskEvaluator riskEvaluator =
            mock(AiAlertRiskEvaluator.class);
    private final AiAlertRealtimePublisher realtimePublisher =
            mock(AiAlertRealtimePublisher.class);
    private final IncidentService incidentService =
            mock(IncidentService.class);
    private final AiAlertService service = new AiAlertService(
            alertRepository,
            eventRepository,
            detectionRepository,
            riskEvaluator,
            realtimePublisher,
            incidentService
    );

    @Test
    void acknowledgeLocksAlertBeforeMutation() {
        AiInferenceEvent event = event();
        AiAlert alert = alert(event);
        when(alertRepository.findByIdForUpdate(51L))
                .thenReturn(Optional.of(alert));
        when(alertRepository.saveAndFlush(alert)).thenReturn(alert);
        when(eventRepository.findById(201L))
                .thenReturn(Optional.of(event));

        service.acknowledge(51L, "demo-operator");

        verify(alertRepository).findByIdForUpdate(51L);
        verify(alertRepository, never()).findById(51L);
        verify(incidentService).synchronizeAiAlert(
                alert,
                "demo-operator",
                "AI 경보 확인 처리와 동기화"
        );
    }

    @Test
    void resolveLocksAlertBeforeMutation() {
        AiInferenceEvent event = event();
        AiAlert alert = alert(event);
        when(alertRepository.findByIdForUpdate(52L))
                .thenReturn(Optional.of(alert));
        when(alertRepository.saveAndFlush(alert)).thenReturn(alert);
        when(eventRepository.findById(201L))
                .thenReturn(Optional.of(event));

        service.resolve(52L, "demo-admin", "안전 확인 완료");

        verify(alertRepository).findByIdForUpdate(52L);
        verify(alertRepository, never()).findById(52L);
        verify(incidentService).synchronizeAiAlert(
                alert,
                "demo-admin",
                "안전 확인 완료"
        );
    }

    @Test
    void readOnlyDetailKeepsNonLockingLookup() {
        AiInferenceEvent event = event();
        AiAlert alert = alert(event);
        when(alertRepository.findById(53L))
                .thenReturn(Optional.of(alert));
        when(eventRepository.findById(201L))
                .thenReturn(Optional.of(event));
        when(detectionRepository.findAllByEventIdOrderByIdAsc(201L))
                .thenReturn(List.of());

        service.findDetail(53L);

        verify(alertRepository).findById(53L);
        verify(alertRepository, never()).findByIdForUpdate(53L);
    }

    private AiInferenceEvent event() {
        AiInferenceEvent event = AiInferenceEvent.create(
                "camera-1",
                "session-1",
                VideoSourceType.DJI_LIVE,
                3L,
                10L,
                Instant.parse("2026-08-02T12:00:00Z"),
                BigDecimal.valueOf(12.5),
                1
        );
        ReflectionTestUtils.setField(event, "id", 201L);
        return event;
    }

    private AiAlert alert(AiInferenceEvent event) {
        AiAlert alert = AiAlert.create(
                event,
                AiAlertSeverity.WARNING,
                "안전 경보",
                "동시성 검증용 AI 경보",
                "without_helmet",
                BigDecimal.valueOf(0.91)
        );
        ReflectionTestUtils.setField(alert, "id", 51L);
        ReflectionTestUtils.setField(
                alert,
                "createdAt",
                LocalDateTime.of(2026, 8, 2, 12, 0)
        );
        ReflectionTestUtils.setField(
                alert,
                "updatedAt",
                LocalDateTime.of(2026, 8, 2, 12, 0)
        );
        return alert;
    }
}
