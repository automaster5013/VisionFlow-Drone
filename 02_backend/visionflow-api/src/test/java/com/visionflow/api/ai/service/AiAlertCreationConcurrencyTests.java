package com.visionflow.api.ai.service;

import com.visionflow.api.ai.domain.AiAlert;
import com.visionflow.api.ai.domain.AiAlertSeverity;
import com.visionflow.api.ai.domain.AiDetection;
import com.visionflow.api.ai.domain.AiInferenceEvent;
import com.visionflow.api.ai.domain.VideoSourceType;
import com.visionflow.api.ai.realtime.AiAlertRealtimeAction;
import com.visionflow.api.ai.realtime.AiAlertRealtimePublisher;
import com.visionflow.api.ai.repository.AiAlertRepository;
import com.visionflow.api.ai.repository.AiDetectionRepository;
import com.visionflow.api.ai.repository.AiInferenceEventRepository;
import com.visionflow.api.incident.service.IncidentService;
import jakarta.persistence.LockModeType;
import org.junit.jupiter.api.Test;
import org.mockito.InOrder;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.test.util.ReflectionTestUtils;

import java.lang.reflect.Method;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AiAlertCreationConcurrencyTests {

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
    void eventMutationLookupUsesPessimisticWriteLock()
            throws NoSuchMethodException {
        Method method = AiInferenceEventRepository.class.getMethod(
                "findByIdForUpdate",
                Long.class
        );

        Lock lock = method.getAnnotation(Lock.class);

        assertThat(lock).isNotNull();
        assertThat(lock.value()).isEqualTo(
                LockModeType.PESSIMISTIC_WRITE
        );
    }

    @Test
    void createLocksEventBeforeIdempotencyLookupAndSideEffects() {
        AiInferenceEvent event = event(201L);
        List<AiDetection> detections = List.of(detection(201L));
        AiAlertRiskEvaluator.RiskAssessment assessment =
                new AiAlertRiskEvaluator.RiskAssessment(
                        AiAlertSeverity.CRITICAL,
                        "긴급 탐지: fire",
                        "1개 객체 탐지 · 최고 신뢰도 94.0%",
                        "fire",
                        new BigDecimal("0.94")
                );
        when(eventRepository.findByIdForUpdate(201L))
                .thenReturn(Optional.of(event));
        when(alertRepository.findByEventId(201L))
                .thenReturn(Optional.empty());
        when(riskEvaluator.evaluate(detections)).thenReturn(assessment);
        when(alertRepository.saveAndFlush(any(AiAlert.class)))
                .thenAnswer(invocation -> {
                    AiAlert alert = invocation.getArgument(0);
                    ReflectionTestUtils.setField(alert, "id", 301L);
                    return alert;
                });

        service.createForEvent(event, detections);

        InOrder order = inOrder(
                eventRepository,
                alertRepository,
                riskEvaluator,
                incidentService,
                realtimePublisher
        );
        order.verify(eventRepository).findByIdForUpdate(201L);
        order.verify(alertRepository).findByEventId(201L);
        order.verify(riskEvaluator).evaluate(detections);
        order.verify(alertRepository).saveAndFlush(any(AiAlert.class));
        order.verify(incidentService).createFromAiAlert(
                any(AiAlert.class)
        );
        order.verify(realtimePublisher).publishAfterCommit(
                org.mockito.ArgumentMatchers.eq(
                        AiAlertRealtimeAction.CREATED
                ),
                any()
        );
        verify(eventRepository, never()).findById(201L);
    }

    @Test
    void duplicateEventReturnsAfterLockWithoutSecondSideEffects() {
        AiInferenceEvent event = event(202L);
        List<AiDetection> detections = List.of(detection(202L));
        AiAlert existing = alert(event, 302L);
        when(eventRepository.findByIdForUpdate(202L))
                .thenReturn(Optional.of(event));
        when(alertRepository.findByEventId(202L))
                .thenReturn(Optional.of(existing));

        service.createForEvent(event, detections);

        verify(eventRepository).findByIdForUpdate(202L);
        verify(alertRepository).findByEventId(202L);
        verify(riskEvaluator, never()).evaluate(any());
        verify(alertRepository, never()).saveAndFlush(any(AiAlert.class));
        verify(incidentService, never()).createFromAiAlert(any());
        verify(realtimePublisher, never()).publishAfterCommit(any(), any());
    }

    private AiInferenceEvent event(Long id) {
        AiInferenceEvent event = AiInferenceEvent.create(
                "source-1",
                "session-1",
                VideoSourceType.SMARTPHONE_LIVE,
                7L,
                1L,
                Instant.parse("2026-08-04T04:30:00Z"),
                BigDecimal.ONE,
                1
        );
        ReflectionTestUtils.setField(event, "id", id);
        return event;
    }

    private AiDetection detection(Long eventId) {
        return AiDetection.create(
                eventId,
                0,
                "fire",
                new BigDecimal("0.94"),
                BigDecimal.ZERO,
                BigDecimal.ZERO,
                BigDecimal.TEN,
                BigDecimal.TEN
        );
    }

    private AiAlert alert(AiInferenceEvent event, Long id) {
        AiAlert alert = AiAlert.create(
                event,
                AiAlertSeverity.CRITICAL,
                "긴급 탐지: fire",
                "동시성 검증 경보",
                "fire",
                new BigDecimal("0.94")
        );
        ReflectionTestUtils.setField(alert, "id", id);
        return alert;
    }
}
