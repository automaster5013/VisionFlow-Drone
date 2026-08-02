package com.visionflow.api.incident.service;

import com.visionflow.api.incident.domain.Incident;
import com.visionflow.api.incident.domain.IncidentPriority;
import com.visionflow.api.incident.domain.IncidentStatus;
import com.visionflow.api.incident.realtime.IncidentRealtimePublisher;
import com.visionflow.api.incident.repository.IncidentActionHistoryRepository;
import com.visionflow.api.incident.repository.IncidentRepository;
import org.junit.jupiter.api.Test;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class IncidentSlaEscalationServiceConcurrencyTests {

    private final IncidentRepository incidentRepository =
            mock(IncidentRepository.class);
    private final IncidentActionHistoryRepository historyRepository =
            mock(IncidentActionHistoryRepository.class);
    private final IncidentRealtimePublisher realtimePublisher =
            mock(IncidentRealtimePublisher.class);
    private final IncidentSlaEscalationService service =
            new IncidentSlaEscalationService(
                    incidentRepository,
                    historyRepository,
                    realtimePublisher
            );

    @Test
    void targetedEscalationLocksIncidentRow() {
        Incident incident = mock(Incident.class);
        when(incident.getSlaDueAt())
                .thenReturn(LocalDateTime.of(2020, 1, 1, 0, 0));
        when(incident.getStatus()).thenReturn(IncidentStatus.OPEN);
        when(incident.getPriority()).thenReturn(IncidentPriority.HIGH);
        when(incident.markSlaBreached(any())).thenReturn(true);
        when(incidentRepository.findByIdForUpdate(71L))
                .thenReturn(Optional.of(incident));

        service.escalateIncidentIfOverdue(71L);

        verify(incidentRepository).findByIdForUpdate(71L);
        verify(incidentRepository).flush();
    }

    @Test
    void scheduledScanUsesLockedOverdueQuery() {
        when(incidentRepository.findOverdueForEscalationForUpdate(
                any(),
                any(),
                any()
        )).thenReturn(List.of());

        int escalated = service.escalateOverdueIncidents();

        assertThat(escalated).isZero();
        verify(incidentRepository).findOverdueForEscalationForUpdate(
                any(),
                any(),
                any()
        );
    }
}
