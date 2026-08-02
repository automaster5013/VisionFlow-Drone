package com.visionflow.api.incident.service;

import com.visionflow.api.incident.domain.Incident;
import com.visionflow.api.incident.domain.IncidentActionHistory;
import com.visionflow.api.incident.domain.IncidentPriority;
import com.visionflow.api.incident.domain.IncidentSourceType;
import com.visionflow.api.incident.domain.IncidentStatus;
import com.visionflow.api.incident.realtime.IncidentRealtimePublisher;
import com.visionflow.api.incident.repository.IncidentActionHistoryRepository;
import com.visionflow.api.incident.repository.IncidentRepository;
import org.junit.jupiter.api.Test;

import java.time.LocalDateTime;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class IncidentServiceConcurrencyTests {

    private final IncidentRepository incidentRepository =
            mock(IncidentRepository.class);
    private final IncidentActionHistoryRepository historyRepository =
            mock(IncidentActionHistoryRepository.class);
    private final IncidentRealtimePublisher realtimePublisher =
            mock(IncidentRealtimePublisher.class);
    private final IncidentContextService contextService =
            mock(IncidentContextService.class);
    private final IncidentService service = new IncidentService(
            incidentRepository,
            historyRepository,
            realtimePublisher,
            contextService
    );

    @Test
    void operatorMutationLocksIncidentBeforeAssignment() {
        Incident incident = incident();
        when(incidentRepository.findByIdForUpdate(41L))
                .thenReturn(Optional.of(incident));
        when(incidentRepository.saveAndFlush(incident))
                .thenReturn(incident);

        var response = service.assign(
                41L,
                "demo-operator",
                "demo-admin"
        );

        assertThat(response.assignee()).isEqualTo("demo-operator");
        verify(incidentRepository).findByIdForUpdate(41L);
        verify(incidentRepository, never()).findById(41L);
        verify(historyRepository).saveAndFlush(
                any(IncidentActionHistory.class)
        );
    }

    @Test
    void readOnlyDetailKeepsNonLockingLookup() {
        Incident incident = incident();
        when(incidentRepository.findById(42L))
                .thenReturn(Optional.of(incident));
        when(historyRepository
                .findAllByIncidentIdOrderByCreatedAtAscIdAsc(42L))
                .thenReturn(java.util.List.of());

        service.findDetail(42L);

        verify(incidentRepository).findById(42L);
        verify(incidentRepository, never()).findByIdForUpdate(42L);
    }

    private Incident incident() {
        return Incident.create(
                IncidentSourceType.AI_ALERT,
                100L,
                3L,
                "session-1",
                IncidentPriority.HIGH,
                IncidentStatus.OPEN,
                "AI 경보",
                "동시성 검증용 Incident",
                LocalDateTime.of(2026, 8, 2, 12, 0),
                null
        );
    }
}
