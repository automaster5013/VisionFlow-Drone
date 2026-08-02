package com.visionflow.api.incident.service;

import com.visionflow.api.common.exception.ResourceNotFoundException;
import com.visionflow.api.incident.domain.Incident;
import com.visionflow.api.incident.domain.IncidentActionHistory;
import com.visionflow.api.incident.domain.IncidentActionType;
import com.visionflow.api.incident.domain.IncidentPriority;
import com.visionflow.api.incident.domain.IncidentStatus;
import com.visionflow.api.incident.dto.IncidentResponse;
import com.visionflow.api.incident.realtime.IncidentRealtimeAction;
import com.visionflow.api.incident.realtime.IncidentRealtimePublisher;
import com.visionflow.api.incident.repository.IncidentActionHistoryRepository;
import com.visionflow.api.incident.repository.IncidentRepository;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;

@Service
public class IncidentSlaEscalationService {

    private static final int SCAN_BATCH_SIZE = 100;
    private static final String SYSTEM_ACTOR = "SYSTEM_SLA";

    private final IncidentRepository incidentRepository;
    private final IncidentActionHistoryRepository historyRepository;
    private final IncidentRealtimePublisher realtimePublisher;

    public IncidentSlaEscalationService(
            IncidentRepository incidentRepository,
            IncidentActionHistoryRepository historyRepository,
            IncidentRealtimePublisher realtimePublisher
    ) {
        this.incidentRepository = incidentRepository;
        this.historyRepository = historyRepository;
        this.realtimePublisher = realtimePublisher;
    }

    @Transactional
    public int escalateOverdueIncidents() {
        LocalDateTime now = LocalDateTime.now(ZoneOffset.UTC);
        List<Incident> overdue = incidentRepository
                .findOverdueForEscalationForUpdate(
                        now,
                        List.of(
                                IncidentStatus.OPEN,
                                IncidentStatus.IN_PROGRESS
                        ),
                        PageRequest.of(0, SCAN_BATCH_SIZE)
                );
        int escalatedCount = 0;

        for (Incident incident : overdue) {
            if (escalate(incident, now)) {
                escalatedCount += 1;
            }
        }

        incidentRepository.flush();
        historyRepository.flush();
        return escalatedCount;
    }

    @Transactional
    public IncidentResponse escalateIncidentIfOverdue(Long incidentId) {
        Incident incident = incidentRepository.findByIdForUpdate(incidentId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Incident를 찾을 수 없습니다: " + incidentId
                ));
        LocalDateTime now = LocalDateTime.now(ZoneOffset.UTC);

        if (incident.getSlaDueAt() == null
                || incident.getSlaDueAt().isAfter(now)) {
            throw new IllegalArgumentException(
                    "아직 SLA 대응 기한을 초과하지 않았습니다: "
                            + incidentId
            );
        }
        if (incident.getStatus() != IncidentStatus.OPEN
                && incident.getStatus() != IncidentStatus.IN_PROGRESS) {
            throw new IllegalArgumentException(
                    "종료된 Incident는 SLA 상향할 수 없습니다: "
                            + incidentId
            );
        }

        escalate(incident, now);
        incidentRepository.flush();
        historyRepository.flush();
        return IncidentResponse.from(incident);
    }

    private boolean escalate(Incident incident, LocalDateTime now) {
        IncidentPriority previousPriority = incident.getPriority();

        if (!incident.markSlaBreached(now)) {
            return false;
        }

        IncidentPriority escalatedPriority = incident.getPriority();
        historyRepository.save(IncidentActionHistory.create(
                incident.getId(),
                IncidentActionType.SLA_ESCALATED,
                null,
                null,
                SYSTEM_ACTOR,
                buildEscalationNote(
                        previousPriority,
                        escalatedPriority
                )
        ));
        realtimePublisher.publishAfterCommit(
                IncidentRealtimeAction.SLA_ESCALATED,
                IncidentResponse.from(incident)
        );
        return true;
    }

    private String buildEscalationNote(
            IncidentPriority previousPriority,
            IncidentPriority escalatedPriority
    ) {
        if (previousPriority == escalatedPriority) {
            return "SLA 대응 기한 초과: 이미 최고 우선순위입니다.";
        }

        return "SLA 대응 기한 초과로 우선순위 자동 상향: "
                + previousPriority
                + " -> "
                + escalatedPriority;
    }
}
