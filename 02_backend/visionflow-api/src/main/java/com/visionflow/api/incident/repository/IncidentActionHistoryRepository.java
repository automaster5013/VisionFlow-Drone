package com.visionflow.api.incident.repository;

import com.visionflow.api.incident.domain.IncidentActionHistory;
import com.visionflow.api.incident.domain.IncidentActionType;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface IncidentActionHistoryRepository
        extends JpaRepository<IncidentActionHistory, Long> {

    List<IncidentActionHistory>
    findAllByIncidentIdOrderByCreatedAtAscIdAsc(Long incidentId);

    boolean existsByIncidentIdAndActionTypeAndActor(
            Long incidentId,
            IncidentActionType actionType,
            String actor
    );
}
